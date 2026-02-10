"""
Plugin discovery, activation, lifecycle management.

Mirrors the Inventoros PluginService but adapted for Django/Python idioms.

The plugin directory lives in the **host application** (not inside the
escalated package) and is configurable via ``ESCALATED['PLUGINS_PATH']``.
"""

import importlib
import json
import logging
import os
import shutil
import sys
import zipfile

from django.utils import timezone

from escalated.conf import get_setting
from escalated.hooks import do_action

logger = logging.getLogger("escalated.plugins")


class PluginService:
    """
    Manages plugin discovery, activation, deactivation, upload, and loading.
    """

    def __init__(self):
        self._plugins_path = get_setting("PLUGINS_PATH")
        self._ensure_plugins_directory()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_plugins_directory(self):
        """Create the plugins directory if it does not exist."""
        if self._plugins_path and not os.path.isdir(self._plugins_path):
            try:
                os.makedirs(self._plugins_path, exist_ok=True)
            except OSError:
                logger.warning(
                    "Could not create plugins directory: %s", self._plugins_path
                )

    def _get_manifest(self, slug):
        """
        Read and return the plugin.json manifest for *slug*, or None.
        """
        manifest_path = os.path.join(self._plugins_path, slug, "plugin.json")
        if not os.path.isfile(manifest_path):
            return None
        try:
            with open(manifest_path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read manifest for plugin '%s': %s", slug, exc)
            return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_all_plugins(self):
        """
        Scan the plugins directory and merge each plugin's manifest with
        its database activation state.

        Returns a list of dicts suitable for passing to an Inertia page.
        """
        from escalated.plugin_models import EscalatedPlugin

        if not self._plugins_path or not os.path.isdir(self._plugins_path):
            return []

        plugins = []

        for entry in sorted(os.listdir(self._plugins_path)):
            plugin_dir = os.path.join(self._plugins_path, entry)
            if not os.path.isdir(plugin_dir):
                continue

            manifest = self._get_manifest(entry)
            if manifest is None:
                continue

            # Merge DB state
            try:
                db_plugin = EscalatedPlugin.objects.filter(slug=entry).first()
            except Exception:
                db_plugin = None

            plugins.append({
                "slug": entry,
                "name": manifest.get("name", entry),
                "description": manifest.get("description", ""),
                "version": manifest.get("version", "1.0.0"),
                "author": manifest.get("author", "Unknown"),
                "author_url": manifest.get("author_url", ""),
                "requires": manifest.get("requires", "1.0.0"),
                "main_file": manifest.get("main_file", "plugin.py"),
                "is_active": db_plugin.is_active if db_plugin else False,
                "activated_at": (
                    db_plugin.activated_at.isoformat()
                    if db_plugin and db_plugin.activated_at
                    else None
                ),
                "path": plugin_dir,
            })

        return plugins

    def get_activated_plugins(self):
        """Return a list of active plugin slugs from the database."""
        from escalated.plugin_models import EscalatedPlugin

        try:
            return list(EscalatedPlugin.objects.active().values_list("slug", flat=True))
        except Exception as exc:
            logger.debug(
                "Could not retrieve activated plugins (table may not exist yet): %s",
                exc,
            )
            return []

    def activate_plugin(self, slug):
        """
        Activate a plugin: create/update its DB record, load it, and
        fire lifecycle hooks.
        """
        from escalated.plugin_models import EscalatedPlugin

        plugin, _created = EscalatedPlugin.objects.get_or_create(
            slug=slug,
            defaults={"is_active": False},
        )

        if not plugin.is_active:
            plugin.is_active = True
            plugin.activated_at = timezone.now()
            plugin.deactivated_at = None
            plugin.save(update_fields=[
                "is_active", "activated_at", "deactivated_at", "updated_at",
            ])

            # Load the plugin so its hooks get registered
            self.load_plugin(slug)

            # Fire activation hooks
            do_action("plugin_activated", slug)
            do_action(f"plugin_activated_{slug}")

        return True

    def deactivate_plugin(self, slug):
        """
        Deactivate a plugin: fire hooks *before* flipping the flag.
        """
        from escalated.plugin_models import EscalatedPlugin

        try:
            plugin = EscalatedPlugin.objects.get(slug=slug)
        except EscalatedPlugin.DoesNotExist:
            return False

        if plugin.is_active:
            # Fire deactivation hooks before deactivating
            do_action("plugin_deactivated", slug)
            do_action(f"plugin_deactivated_{slug}")

            plugin.is_active = False
            plugin.deactivated_at = timezone.now()
            plugin.save(update_fields=["is_active", "deactivated_at", "updated_at"])

        return True

    def delete_plugin(self, slug):
        """
        Fully remove a plugin: fire uninstall hooks, delete DB record,
        and remove the plugin directory from disk.
        """
        from escalated.plugin_models import EscalatedPlugin

        plugin_path = os.path.join(self._plugins_path, slug)

        if not os.path.isdir(plugin_path):
            return False

        try:
            plugin = EscalatedPlugin.objects.get(slug=slug)
        except EscalatedPlugin.DoesNotExist:
            plugin = None

        # Load plugin so its uninstall hooks can run (if active)
        if plugin and plugin.is_active:
            self.load_plugin(slug)

        # Fire uninstall hooks
        do_action("plugin_uninstalling", slug)
        do_action(f"plugin_uninstalling_{slug}")

        # Deactivate first if active
        if plugin and plugin.is_active:
            self.deactivate_plugin(slug)

        # Delete DB record
        if plugin:
            plugin.delete()

        # Remove plugin directory
        try:
            shutil.rmtree(plugin_path)
        except OSError as exc:
            logger.error("Failed to delete plugin directory '%s': %s", plugin_path, exc)
            return False

        return True

    def upload_plugin(self, uploaded_file):
        """
        Accept a ZIP file (Django ``UploadedFile``), validate it, and
        extract it into the plugins directory.

        Returns a dict ``{'slug': ..., 'path': ...}`` on success.
        Raises ``Exception`` on validation failure.
        """
        if not zipfile.is_zipfile(uploaded_file):
            raise Exception("Uploaded file is not a valid ZIP archive.")

        # Save to a temp path
        import tempfile
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        try:
            for chunk in uploaded_file.chunks():
                tmp.write(chunk)
            tmp.close()

            with zipfile.ZipFile(tmp.name, "r") as zf:
                # Determine root folder
                names = zf.namelist()
                root_folder = None
                for name in names:
                    if "/" in name:
                        root_folder = name.split("/")[0]
                        break

                if not root_folder:
                    raise Exception("Invalid plugin structure: no root folder found.")

                extract_path = os.path.join(self._plugins_path, root_folder)
                if os.path.exists(extract_path):
                    raise Exception(
                        f"Plugin '{root_folder}' already exists. "
                        "Delete it first before uploading again."
                    )

                zf.extractall(self._plugins_path)

            # Validate plugin.json exists
            manifest_path = os.path.join(extract_path, "plugin.json")
            if not os.path.isfile(manifest_path):
                shutil.rmtree(extract_path, ignore_errors=True)
                raise Exception(
                    "Invalid plugin: missing plugin.json in root directory."
                )

            return {"slug": root_folder, "path": extract_path}

        finally:
            os.unlink(tmp.name)

    def load_active_plugins(self):
        """
        Load all currently active plugins.  Called once during Django's
        ``AppConfig.ready()`` to bootstrap the plugin system on startup.
        """
        if not get_setting("PLUGINS_ENABLED"):
            return

        for slug in self.get_activated_plugins():
            self.load_plugin(slug)

    def load_plugin(self, slug):
        """
        Load a single plugin by its slug.

        Reads the manifest to determine the entry-point file, then uses
        ``importlib`` or ``exec`` to execute it.  Fires the
        ``plugin_loaded`` action once the file has been executed.
        """
        manifest = self._get_manifest(slug)
        if manifest is None:
            logger.warning("Cannot load plugin '%s': no manifest found.", slug)
            return

        main_file = manifest.get("main_file", "plugin.py")
        plugin_file = os.path.join(self._plugins_path, slug, main_file)

        if not os.path.isfile(plugin_file):
            logger.warning(
                "Cannot load plugin '%s': main file '%s' not found.",
                slug,
                plugin_file,
            )
            return

        # Attempt import as a Python module first; fall back to exec
        module_name = f"escalated_plugins.{slug.replace('-', '_')}"
        plugin_dir = os.path.join(self._plugins_path, slug)

        try:
            # Add plugin directory to sys.path temporarily if needed
            if plugin_dir not in sys.path:
                sys.path.insert(0, plugin_dir)

            spec = importlib.util.spec_from_file_location(module_name, plugin_file)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
                logger.info("Plugin '%s' loaded via importlib.", slug)
            else:
                # Fallback: exec the file directly
                with open(plugin_file, "r", encoding="utf-8") as fh:
                    code = fh.read()
                exec(compile(code, plugin_file, "exec"), {"__name__": module_name})
                logger.info("Plugin '%s' loaded via exec.", slug)

        except Exception:
            logger.exception("Failed to load plugin '%s'.", slug)
            return

        # Fire the plugin_loaded action
        do_action("plugin_loaded", slug, manifest)
