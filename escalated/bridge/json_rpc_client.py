"""
Low-level JSON-RPC 2.0 client over stdio.

Writes newline-delimited JSON to the process stdin and reads responses
line-by-line from stdout.  Communication is bidirectional — the plugin
runtime can send ctx.* callback requests back to the host while we are
waiting for a response to our own request.
"""

import json
import logging
import select
import time

logger = logging.getLogger("escalated.bridge")

# Maximum message size: 10 MB
MAX_MESSAGE_SIZE = 10 * 1024 * 1024


class JsonRpcError(RuntimeError):
    """Raised when the runtime returns a JSON-RPC error object."""

    def __init__(self, message: str, code: int = 0):
        super().__init__(message)
        self.code = code


class JsonRpcClient:
    """
    Synchronous JSON-RPC 2.0 client that communicates with the Node.js
    plugin runtime via subprocess stdin/stdout.

    The call() method blocks until the matching response arrives.  While
    waiting, any interleaved ctx.* requests sent by the runtime are
    dispatched to the provided ctx_handler callable.
    """

    def __init__(self, proc_stdin, proc_stdout):
        """
        Parameters
        ----------
        proc_stdin:
            Writable file-like object connected to the subprocess stdin.
        proc_stdout:
            Readable file-like object connected to the subprocess stdout.
        """
        self._stdin = proc_stdin
        self._stdout = proc_stdout
        self._next_id = 1

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def call(self, method: str, params: dict, timeout_seconds: int, ctx_handler) -> object:
        """
        Send a JSON-RPC request and block until the matching response arrives.

        While waiting, any incoming ctx.* requests from the runtime are
        dispatched to ctx_handler.

        Parameters
        ----------
        method:
            JSON-RPC method name (e.g. "action", "filter", "handshake").
        params:
            Parameters dict to include in the request.
        timeout_seconds:
            How long to wait before raising RuntimeError.
        ctx_handler:
            Callable(method: str, params: dict) -> object.  Called for
            every incoming ctx.* request while we are waiting for our
            response.

        Returns
        -------
        The ``result`` field of the JSON-RPC response.

        Raises
        ------
        RuntimeError
            On timeout, connection loss, or protocol error.
        JsonRpcError
            When the runtime returns a JSON-RPC error object.
        """
        msg_id = self._next_id
        self._next_id += 1

        message = json.dumps(
            {
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
                "id": msg_id,
            },
            ensure_ascii=False,
        )
        self._write_line(message)
        return self._wait_for_response(msg_id, timeout_seconds, ctx_handler)

    def notify(self, method: str, params: dict) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        message = json.dumps(
            {"jsonrpc": "2.0", "method": method, "params": params},
            ensure_ascii=False,
        )
        self._write_line(message)

    def respond(self, msg_id: int, result: object) -> None:
        """Send a JSON-RPC success response back to the runtime."""
        message = json.dumps(
            {"jsonrpc": "2.0", "result": result, "id": msg_id},
            ensure_ascii=False,
        )
        self._write_line(message)

    def respond_error(self, msg_id: int, code: int, message: str) -> None:
        """Send a JSON-RPC error response back to the runtime."""
        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "error": {"code": code, "message": message},
                "id": msg_id,
            },
            ensure_ascii=False,
        )
        self._write_line(payload)

    def read_line(self, timeout_seconds: int) -> str | None:
        """
        Read one newline-terminated line from the subprocess stdout.

        Returns None on timeout or EOF.  Raises RuntimeError if the line
        exceeds MAX_MESSAGE_SIZE.
        """
        # Use select() on POSIX; fall back to a simple blocking read on
        # platforms where select() does not support file objects (Windows).
        try:
            ready, _, _ = select.select([self._stdout], [], [], timeout_seconds)
            if not ready:
                return None
        except (select.error, ValueError):
            # select() is not available for this file object (e.g. Windows pipes).
            # Fall through to the blocking read below.
            pass

        try:
            line = self._stdout.readline()
        except OSError:
            return None

        if not line:
            return None

        if len(line) > MAX_MESSAGE_SIZE:
            raise RuntimeError("JSON-RPC message exceeds maximum size of 10 MB")

        return line.rstrip("\n\r")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _wait_for_response(self, expected_id: int, timeout_seconds: int, ctx_handler) -> object:
        """Block until we receive the response for expected_id."""
        deadline = time.monotonic() + timeout_seconds

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(
                    f"JSON-RPC timeout waiting for response to request #{expected_id}"
                )

            line = self.read_line(int(remaining) + 1)

            if line is None:
                raise RuntimeError(
                    f"JSON-RPC connection lost waiting for response to request #{expected_id}"
                )

            if line == "":
                continue

            try:
                decoded = json.loads(line)
            except json.JSONDecodeError:
                logger.warning(
                    "Escalated PluginBridge: received non-JSON line: %s", line[:200]
                )
                continue

            if not isinstance(decoded, dict) or "jsonrpc" not in decoded:
                logger.warning(
                    "Escalated PluginBridge: received invalid JSON-RPC message: %s",
                    line[:200],
                )
                continue

            # Incoming request from the runtime (ctx.* callback)
            if "method" in decoded:
                self._handle_incoming_request(decoded, ctx_handler)
                continue

            # Response to one of our requests
            if "id" in decoded:
                msg_id = int(decoded["id"])

                if msg_id == expected_id:
                    if "error" in decoded:
                        err = decoded["error"]
                        raise JsonRpcError(
                            err.get("message", "unknown error"),
                            code=int(err.get("code", 0)),
                        )
                    return decoded.get("result")

                # Response to a different in-flight request — should not
                # happen in the synchronous single-threaded model.
                logger.warning(
                    "Escalated PluginBridge: unexpected response id (expected %s, got %s)",
                    expected_id,
                    msg_id,
                )

    def _handle_incoming_request(self, message: dict, ctx_handler) -> None:
        """Dispatch a ctx.* request from the runtime and send the response."""
        msg_id = message.get("id")
        method = message.get("method", "")
        params = message.get("params") or {}

        try:
            result = ctx_handler(method, params)
            if msg_id is not None:
                self.respond(int(msg_id), result)
        except Exception as exc:
            logger.warning(
                "Escalated PluginBridge: ctx handler raised for method '%s': %s",
                method,
                exc,
            )
            if msg_id is not None:
                self.respond_error(int(msg_id), -32000, str(exc))

    def _write_line(self, data: str) -> None:
        """Write a newline-terminated line to the subprocess stdin."""
        try:
            self._stdin.write(data + "\n")
            self._stdin.flush()
        except OSError as exc:
            raise RuntimeError(f"Failed to write to plugin runtime stdin: {exc}") from exc
