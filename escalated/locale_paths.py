"""Helpers for wiring the central `escalated-locale` package into Django.

The canonical translation source for the entire Escalated portfolio is
the `escalated-locale` PyPI package. It is expected to ship both the
canonical JSON catalogues and pre-compiled gettext artifacts at::

    escalated_locale/locale/<lang>/LC_MESSAGES/django.po
    escalated_locale/locale/<lang>/LC_MESSAGES/django.mo

This module exposes those paths so host projects can compose Django's
`LOCALE_PATHS` with the plugin-local override winning over the central
package, e.g.::

    # settings.py
    from escalated.locale_paths import get_locale_paths

    LOCALE_PATHS = get_locale_paths()

`LOCALE_PATHS` is searched in order, so the plugin-local override comes
first and the central package provides the baseline.
"""

from __future__ import annotations

import os
from importlib import import_module
from typing import List, Optional

# Plugin-local override directory shipped with this package. Translators
# can drop overrides in here to win over the central catalogues.
PLUGIN_LOCALE_DIR: str = os.path.join(os.path.dirname(__file__), "locale")


def get_central_locale_path() -> Optional[str]:
    """Return the absolute path to `escalated_locale/locale`, or None.

    Resolves the path lazily so a missing/unpublished `escalated-locale`
    package does not break import-time settings loading. Host projects
    that need translations should ensure the package is installed.
    """
    try:
        pkg = import_module("escalated_locale")
    except ImportError:
        return None

    pkg_dir = os.path.dirname(getattr(pkg, "__file__", "") or "")
    if not pkg_dir:
        return None

    candidate = os.path.join(pkg_dir, "locale")
    return candidate if os.path.isdir(candidate) else None


def get_locale_paths(*extra: str) -> List[str]:
    """Compose a Django-compatible `LOCALE_PATHS` tuple.

    Order (highest priority first):
        1. Any caller-supplied `extra` paths
        2. The plugin-local override at `escalated/locale/`
        3. The central `escalated_locale/locale/` directory (if installed)

    The plugin-local directory is always included so existing overrides
    keep working even if the central package is not yet installed.
    """
    paths: List[str] = [p for p in extra if p]
    paths.append(PLUGIN_LOCALE_DIR)

    central = get_central_locale_path()
    if central:
        paths.append(central)

    return paths
