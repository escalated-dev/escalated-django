"""
Admin views for plugin management.

Provides CRUD operations for plugins: list, upload, activate, deactivate,
and delete. Follows the same patterns as the existing admin views in
``escalated.views.admin``.
"""

import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from inertia import render

from escalated.conf import get_setting
from escalated.permissions import is_admin
from escalated.plugin_service import PluginService

logger = logging.getLogger("escalated.plugins")


def _require_admin(request):
    """Return an error response if user is not admin, else None."""
    if not request.user.is_authenticated:
        return redirect("login")
    if not is_admin(request.user):
        return HttpResponseForbidden("Admin access required.")
    return None


def _require_plugins_enabled():
    """Return an error response if plugins are disabled, else None."""
    if not get_setting("PLUGINS_ENABLED"):
        return HttpResponseForbidden("Plugin system is disabled.")
    return None


# ---------------------------------------------------------------------------
# Plugin List
# ---------------------------------------------------------------------------


@login_required
def plugin_list(request):
    """Display a listing of all installed plugins with their status."""
    check = _require_admin(request)
    if check:
        return check

    check = _require_plugins_enabled()
    if check:
        return check

    service = PluginService()
    plugins = service.get_all_plugins()

    return render(request, "Escalated/Admin/Plugins/Index", props={
        "plugins": plugins,
    })


# ---------------------------------------------------------------------------
# Upload Plugin
# ---------------------------------------------------------------------------


@login_required
def plugin_upload(request):
    """Upload a new plugin from a ZIP file."""
    check = _require_admin(request)
    if check:
        return check

    check = _require_plugins_enabled()
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden("Method not allowed.")

    uploaded_file = request.FILES.get("plugin")
    if not uploaded_file:
        return redirect("escalated:admin_plugins_index")

    service = PluginService()

    try:
        result = service.upload_plugin(uploaded_file)
        logger.info(
            "Plugin uploaded successfully: %s",
            result.get("slug", "unknown"),
        )
        # Redirect back to plugin list on success
        return redirect("escalated:admin_plugins_index")

    except Exception as exc:
        logger.error(
            "Plugin upload failed: %s (file: %s)",
            exc,
            uploaded_file.name,
        )
        return redirect("escalated:admin_plugins_index")


# ---------------------------------------------------------------------------
# Activate Plugin
# ---------------------------------------------------------------------------


@login_required
def plugin_activate(request, slug):
    """Activate an installed plugin."""
    check = _require_admin(request)
    if check:
        return check

    check = _require_plugins_enabled()
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden("Method not allowed.")

    service = PluginService()

    try:
        service.activate_plugin(slug)
        logger.info("Plugin activated: %s", slug)
    except Exception as exc:
        logger.error("Plugin activation failed for '%s': %s", slug, exc)

    return redirect("escalated:admin_plugins_index")


# ---------------------------------------------------------------------------
# Deactivate Plugin
# ---------------------------------------------------------------------------


@login_required
def plugin_deactivate(request, slug):
    """Deactivate an active plugin."""
    check = _require_admin(request)
    if check:
        return check

    check = _require_plugins_enabled()
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden("Method not allowed.")

    service = PluginService()

    try:
        service.deactivate_plugin(slug)
        logger.info("Plugin deactivated: %s", slug)
    except Exception as exc:
        logger.error("Plugin deactivation failed for '%s': %s", slug, exc)

    return redirect("escalated:admin_plugins_index")


# ---------------------------------------------------------------------------
# Delete Plugin
# ---------------------------------------------------------------------------


@login_required
def plugin_delete(request, slug):
    """Permanently delete a plugin (files + DB record)."""
    check = _require_admin(request)
    if check:
        return check

    check = _require_plugins_enabled()
    if check:
        return check

    if request.method != "POST":
        return HttpResponseForbidden("Method not allowed.")

    service = PluginService()

    # Check if plugin is package-sourced before attempting delete
    all_plugins = service.get_all_plugins()
    plugin_data = next((p for p in all_plugins if p["slug"] == slug), None)
    if plugin_data and plugin_data.get("source") == "composer":
        return redirect("escalated:admin_plugins_index")

    try:
        service.delete_plugin(slug)
        logger.info("Plugin deleted: %s", slug)
    except Exception as exc:
        logger.error("Plugin deletion failed for '%s': %s", slug, exc)

    return redirect("escalated:admin_plugins_index")
