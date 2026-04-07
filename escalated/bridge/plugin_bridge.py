"""
Core bridge between Django and the Node.js plugin runtime.

Architecture
────────────
The bridge spawns ``node @escalated-dev/plugin-runtime`` as a long-lived
child process.  Communication is bidirectional JSON-RPC 2.0 over stdio
(newline-delimited JSON).  The plugin runtime loads all installed SDK
plugins, handles their lifecycle, and routes hook dispatches from the host.

The process is spawned LAZILY on the first hook dispatch, not at boot time.
This avoids slowing down requests that never touch plugins (health checks,
etc.).

Heartbeat & restart
───────────────────
The process is monitored via poll().  On crash or timeout the process is
killed and restarted with exponential backoff (up to 5 minutes).

Queue depth
───────────
Action hook messages are queued internally up to 1 000 entries.  Beyond
that new action hooks are dropped with a warning.  Filter hooks return the
unmodified value instead of being dropped.
"""

import logging
import os
import shutil
import subprocess
import time

logger = logging.getLogger("escalated.bridge")

PROTOCOL_VERSION = "1.0"
HOST_NAME = "django"

TIMEOUT_ACTION = 30
TIMEOUT_FILTER = 5
TIMEOUT_ENDPOINT = 30
TIMEOUT_WEBHOOK = 60
TIMEOUT_HANDSHAKE = 15
TIMEOUT_MANIFEST = 15

MAX_BACKOFF_SECS = 300  # 5 minutes
MAX_QUEUE_DEPTH = 1000


class PluginBridge:
    """
    Manages the lifecycle of the Node.js plugin runtime subprocess and
    provides high-level methods for dispatching hooks and calling plugin
    endpoints.
    """

    def __init__(self):
        from escalated.bridge.context_handler import ContextHandler
        from escalated.bridge.route_registrar import RouteRegistrar

        self._process: subprocess.Popen | None = None
        self._rpc = None  # JsonRpcClient, set after spawn

        self._context_handler = ContextHandler()
        self._context_handler.set_bridge(self)

        self._route_registrar = RouteRegistrar(self)

        self._manifests: dict[str, dict] = {}
        self._booted: bool = False
        self._routes_registered: bool = False

        # Crash-restart state
        self._restart_attempts: int = 0
        self._last_restart_at: float = 0.0

        # Pending action count (enforces queue depth limit)
        self._pending_action_count: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def boot(self) -> None:
        """
        Boot the bridge: spawn the runtime, perform the handshake, retrieve
        plugin manifests, and register URL patterns.

        Called from EscalatedConfig.ready().  Safe to call when Node.js is
        not installed — any exception is caught and logged (SDK plugins will
        simply be unavailable).
        """
        if self._booted:
            return

        if not self._is_runtime_available():
            logger.info("Escalated PluginBridge: Node.js runtime not available — SDK plugins disabled")
            return

        try:
            self._ensure_running()
            self._fetch_manifests()
            self._register_routes()
            self._booted = True
        except Exception as exc:
            logger.warning("Escalated PluginBridge: boot failed — SDK plugins disabled: %s", exc)
            self._teardown()

    def dispatch_action(self, hook: str, event: dict) -> None:
        """
        Dispatch a fire-and-forget action hook to SDK plugins.

        Blocks until the runtime acknowledges the action (or until the 30 s
        timeout).  Errors are caught and logged — action hooks are
        best-effort.
        """
        if not self._ensure_alive():
            return

        if self._pending_action_count >= MAX_QUEUE_DEPTH:
            logger.warning("Escalated PluginBridge: action queue full — dropping action '%s'", hook)
            return

        self._pending_action_count += 1
        try:
            self._context_handler.set_current_plugin("__host__")
            self._rpc.call(
                "action",
                {"hook": hook, "event": event},
                TIMEOUT_ACTION,
                self._context_handler.handle,
            )
        except Exception as exc:
            logger.warning("Escalated PluginBridge: action '%s' failed: %s", hook, exc)
            self._handle_crash()
        finally:
            self._pending_action_count -= 1

    def apply_filter(self, hook: str, value: object) -> object:
        """
        Apply a filter hook through SDK plugins.

        Returns the filtered value, or the original value on timeout/error.
        """
        if not self._ensure_alive():
            return value

        try:
            self._context_handler.set_current_plugin("__host__")
            result = self._rpc.call(
                "filter",
                {"hook": hook, "value": value},
                TIMEOUT_FILTER,
                self._context_handler.handle,
            )
            return result if result is not None else value
        except Exception as exc:
            logger.warning(
                "Escalated PluginBridge: filter '%s' failed — returning unmodified value: %s",
                hook,
                exc,
            )
            self._handle_crash()
            return value

    def call_endpoint(
        self,
        plugin: str,
        method: str,
        path: str,
        request: dict | None = None,
    ) -> object:
        """
        Call a plugin's data endpoint (used by API route handlers and page
        props).

        Raises RuntimeError if the runtime is not available.
        """
        if not self._ensure_alive():
            raise RuntimeError("Plugin runtime is not available")

        request = request or {}
        self._context_handler.set_current_plugin(plugin)
        return self._rpc.call(
            "endpoint",
            {
                "plugin": plugin,
                "method": method,
                "path": path,
                "body": request.get("body"),
                "params": request.get("params") or {},
            },
            TIMEOUT_ENDPOINT,
            self._context_handler.handle,
        )

    def call_webhook(
        self,
        plugin: str,
        method: str,
        path: str,
        body: dict,
        headers: dict,
    ) -> object:
        """
        Call a plugin's webhook handler (used by webhook route handlers).

        Raises RuntimeError if the runtime is not available.
        """
        if not self._ensure_alive():
            raise RuntimeError("Plugin runtime is not available")

        self._context_handler.set_current_plugin(plugin)
        return self._rpc.call(
            "webhook",
            {
                "plugin": plugin,
                "method": method,
                "path": path,
                "body": body,
                "headers": headers,
            },
            TIMEOUT_WEBHOOK,
            self._context_handler.handle,
        )

    def get_manifests(self) -> dict[str, dict]:
        """Return plugin manifests keyed by plugin name (empty if not booted)."""
        return dict(self._manifests)

    def is_booted(self) -> bool:
        """Return whether the bridge has successfully booted."""
        return self._booted

    def get_plugin_urls(self) -> list:
        """
        Return a list of Django URL patterns registered from plugin manifests.

        Returns an empty list if the bridge has not booted or no manifests
        were received.
        """
        return self._route_registrar.get_url_patterns()

    # ------------------------------------------------------------------
    # Process lifecycle
    # ------------------------------------------------------------------

    def _is_runtime_available(self) -> bool:
        """Check that Node.js is available and SDK plugins are enabled."""

        # Honour the SDK_ENABLED config key if present
        escalated_settings = {}
        try:
            from django.conf import settings

            escalated_settings = getattr(settings, "ESCALATED", {})
        except Exception:
            pass

        if not escalated_settings.get("SDK_ENABLED", True):
            return False

        node_path = shutil.which("node")
        if node_path is None:
            return False

        try:
            result = subprocess.run(
                ["node", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0 and result.stdout.strip().startswith("v")
        except Exception:
            return False

    def _spawn(self) -> None:
        """Spawn the Node.js plugin runtime subprocess."""
        from django.conf import settings

        escalated_settings = getattr(settings, "ESCALATED", {})

        command = escalated_settings.get(
            "RUNTIME_COMMAND",
            "node node_modules/@escalated-dev/plugin-runtime/dist/index.js",
        )

        cwd = escalated_settings.get(
            "RUNTIME_CWD",
            getattr(settings, "BASE_DIR", os.getcwd()),
        )

        try:
            self._process = subprocess.Popen(
                command,
                shell=True,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(cwd),
                text=True,  # text mode — we exchange UTF-8 JSON lines
                bufsize=1,  # line-buffered
            )
        except OSError as exc:
            raise RuntimeError(f"Failed to spawn plugin runtime '{command}': {exc}") from exc

        from escalated.bridge.json_rpc_client import JsonRpcClient

        self._rpc = JsonRpcClient(
            self._process.stdin,
            self._process.stdout,
        )

        logger.info("Escalated PluginBridge: plugin runtime spawned (pid %d)", self._process.pid)

    def _handshake(self) -> None:
        """Perform the protocol handshake with the runtime."""
        result = self._rpc.call(
            "handshake",
            {
                "protocol_version": PROTOCOL_VERSION,
                "host": HOST_NAME,
                "host_version": self._host_version(),
            },
            TIMEOUT_HANDSHAKE,
            self._context_handler.handle,
        )

        if not (result or {}).get("compatible", False):
            runtime_ver = (result or {}).get("runtime_version", "unknown")
            protocol_ver = (result or {}).get("protocol_version", "unknown")
            raise RuntimeError(
                f"Plugin runtime protocol mismatch: runtime speaks v{protocol_ver} "
                f"(runtime v{runtime_ver}), host speaks v{PROTOCOL_VERSION}"
            )

        logger.info(
            "Escalated PluginBridge: handshake OK (runtime v%s, protocol v%s)",
            (result or {}).get("runtime_version", "unknown"),
            (result or {}).get("protocol_version", "unknown"),
        )

    def _fetch_manifests(self) -> None:
        """Fetch plugin manifests from the runtime and store them locally."""
        result = self._rpc.call(
            "manifest",
            {},
            TIMEOUT_MANIFEST,
            self._context_handler.handle,
        )

        if isinstance(result, list):
            for manifest in result:
                name = manifest.get("name") if isinstance(manifest, dict) else None
                if name:
                    self._manifests[name] = manifest

        logger.info(
            "Escalated PluginBridge: received manifests for plugins: %s",
            list(self._manifests.keys()),
        )

    def _register_routes(self) -> None:
        """Register Django URL patterns from the loaded manifests."""
        if self._routes_registered or not self._manifests:
            return
        self._route_registrar.register_all(self._manifests)
        self._routes_registered = True

    def _ensure_running(self) -> bool:
        """
        Ensure the runtime is running, spawning it lazily if needed.

        Returns False if the runtime could not be started.
        """
        if self._is_process_alive():
            return True

        # Exponential backoff on repeated restarts
        if self._restart_attempts > 0:
            backoff = min(
                int(2 ** (self._restart_attempts - 1)) * 5,
                MAX_BACKOFF_SECS,
            )
            elapsed = time.monotonic() - self._last_restart_at
            if elapsed < backoff:
                logger.debug(
                    "Escalated PluginBridge: waiting for backoff before restart (%.0f s remaining)",
                    backoff - elapsed,
                )
                return False

        try:
            self._teardown()
            self._spawn()
            self._handshake()
            self._fetch_manifests()
            self._register_routes()
            self._restart_attempts = 0
            self._booted = True
            return True
        except Exception as exc:
            self._restart_attempts += 1
            self._last_restart_at = time.monotonic()
            logger.error(
                "Escalated PluginBridge: failed to start plugin runtime (attempt %d): %s",
                self._restart_attempts,
                exc,
            )
            self._teardown()
            return False

    def _ensure_alive(self) -> bool:
        """Check process liveness, restarting if necessary."""
        if not self._is_runtime_available():
            return False
        if self._is_process_alive():
            return True
        return self._ensure_running()

    def _is_process_alive(self) -> bool:
        """Return True if the subprocess is still running."""
        if self._process is None:
            return False
        return self._process.poll() is None

    def _handle_crash(self) -> None:
        """Clean up after a crash so the next call triggers a restart."""
        if not self._is_process_alive():
            logger.warning("Escalated PluginBridge: plugin runtime process has crashed — will restart on next dispatch")
            self._teardown()

    def _teardown(self) -> None:
        """Terminate the subprocess and release all handles."""
        if self._process is not None:
            try:
                self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait()
            except Exception:
                pass

        self._process = None
        self._rpc = None

    def _host_version(self) -> str:
        """Return the escalated-django package version."""
        try:
            from importlib.metadata import version

            return version("escalated-django")
        except Exception:
            pass
        # Fallback: read pyproject.toml from the package root
        try:
            pkg_root = os.path.join(os.path.dirname(__file__), "..", "..")
            pyproject = os.path.join(pkg_root, "pyproject.toml")
            if os.path.isfile(pyproject):
                import re

                with open(pyproject, encoding="utf-8") as fh:
                    content = fh.read()
                match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
                if match:
                    return match.group(1)
        except Exception:
            pass
        return "0.0.0"

    # ------------------------------------------------------------------
    # Destructor
    # ------------------------------------------------------------------

    def __del__(self):
        self._teardown()


# ---------------------------------------------------------------------------
# Module-level singleton — created lazily so it does not execute at import
# time (avoids issues during Django setup / migration).
# ---------------------------------------------------------------------------

_bridge_instance: PluginBridge | None = None


def get_bridge() -> PluginBridge:
    """Return the module-level singleton PluginBridge instance."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = PluginBridge()
    return _bridge_instance
