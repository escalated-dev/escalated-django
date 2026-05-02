"""Unit tests for `escalated.locale_paths`.

These tests intentionally do not require the `escalated-locale` package
to be installed — `get_central_locale_path()` returns None when it is
absent, and `get_locale_paths()` should still surface the plugin-local
override directory.
"""

import os

from escalated import locale_paths


def test_plugin_locale_dir_exists():
    """The plugin-local override directory must always exist on disk."""
    assert os.path.isdir(locale_paths.PLUGIN_LOCALE_DIR)


def test_get_locale_paths_includes_plugin_local_dir():
    paths = locale_paths.get_locale_paths()
    assert locale_paths.PLUGIN_LOCALE_DIR in paths


def test_get_locale_paths_extras_take_priority():
    """Caller-supplied paths must come before the plugin-local override."""
    extra = "/tmp/example-host-locale"
    paths = locale_paths.get_locale_paths(extra)
    assert paths[0] == extra
    assert paths.index(extra) < paths.index(locale_paths.PLUGIN_LOCALE_DIR)


def test_get_central_locale_path_handles_missing_package(monkeypatch):
    """If `escalated_locale` cannot be imported, return None gracefully."""
    import importlib

    real_import_module = importlib.import_module

    def fake_import_module(name, *args, **kwargs):
        if name == "escalated_locale":
            raise ImportError("simulated missing package")
        return real_import_module(name, *args, **kwargs)

    monkeypatch.setattr(locale_paths, "import_module", fake_import_module)
    assert locale_paths.get_central_locale_path() is None
