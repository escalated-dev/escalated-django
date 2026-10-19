"""Helpers for wiring the central Escalated translations into Django.

The canonical translation source for the entire Escalated portfolio is
the `escalated-locale` package. It ships pre-compiled gettext artifacts
at::

    escalated_locale/locale/<lang>/LC_MESSAGES/django.po
    escalated_locale/locale/<lang>/LC_MESSAGES/django.mo

`escalated-locale` is not published on PyPI, and PyPI refuses packages
that depend on a git URL, so escalated-django also bundles a copy of
those catalogues at `escalated/_central_locale/locale/` (vendored from a
tagged escalated-locale release by `scripts/sync_central_locale.py`).
When the `escalated_locale` package is installed
(`pip install escalated-django[locale]`) it wins; otherwise the bundled
copy is used.

Host projects compose Django's `LOCALE_PATHS` with the plugin-local
override winning over the central catalogues, e.g.::

    # settings.py
    from escalated.locale_paths import get_locale_paths

    LOCALE_PATHS = get_locale_paths()

`LOCALE_PATHS` is searched in order, so the plugin-local override comes
first and the central catalogues provide the baseline.
"""

from __future__ import annotations

import os
from importlib import import_module

_PACKAGE_DIR = os.path.dirname(__file__)

# Plugin-local override directory shipped with this package. Translators
# can drop overrides in here to win over the central catalogues.
PLUGIN_LOCALE_DIR: str = os.path.join(_PACKAGE_DIR, "locale")

# Copy of escalated-locale's gettext catalogues bundled with this package.
VENDORED_CENTRAL_LOCALE_DIR: str = os.path.join(_PACKAGE_DIR, "_central_locale", "locale")


def _installed_central_locale_path() -> str | None:
    try:
        pkg = import_module("escalated_locale")
    except ImportError:
        return None

    pkg_dir = os.path.dirname(getattr(pkg, "__file__", "") or "")
    if not pkg_dir:
        return None

    candidate = os.path.join(pkg_dir, "locale")
    return candidate if os.path.isdir(candidate) else None


def get_central_locale_path() -> str | None:
    """Return the directory holding the central gettext catalogues.

    The installed `escalated_locale` package's `locale/` directory wins
    when it is importable. Otherwise the copy bundled with this package
    is returned. Returns None only if neither exists on disk.

    Resolved lazily so import-time settings loading never fails.
    """
    installed = _installed_central_locale_path()
    if installed:
        return installed

    if os.path.isdir(VENDORED_CENTRAL_LOCALE_DIR):
        return VENDORED_CENTRAL_LOCALE_DIR
    return None


def get_locale_paths(*extra: str) -> list[str]:
    """Compose a Django-compatible `LOCALE_PATHS` list.

    Order (highest priority first):
        1. Any caller-supplied `extra` paths
        2. The plugin-local override at `escalated/locale/`
        3. The central catalogues: the installed `escalated_locale`
           package if present, else the copy bundled with this package

    The plugin-local directory is always included so existing overrides
    keep working.
    """
    paths: list[str] = [p for p in extra if p]
    paths.append(PLUGIN_LOCALE_DIR)

    central = get_central_locale_path()
    if central:
        paths.append(central)

    return paths
