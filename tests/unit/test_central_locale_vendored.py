"""The central catalogues must work whether or not `escalated-locale` is installed.

`escalated-locale` is not on PyPI, so escalated-django cannot depend on it
there. A copy of its gettext catalogues is vendored at
`escalated/_central_locale/locale/`; the installed package still wins when
it is importable.
"""

import os
import types

import pytest
from django.test import override_settings
from django.utils import translation

import escalated
from escalated import locale_paths

VENDORED_DIR = os.path.join(os.path.dirname(escalated.__file__), "_central_locale", "locale")

LANGUAGES = ["ar", "de", "en", "es", "fr", "it", "ja", "ko", "nl", "pl", "pt_BR", "ru", "tr", "zh_CN"]


def _hide_escalated_locale(monkeypatch):
    real_import_module = locale_paths.import_module

    def fake_import_module(name, *args, **kwargs):
        if name == "escalated_locale":
            raise ImportError("simulated missing package")
        return real_import_module(name, *args, **kwargs)

    monkeypatch.setattr(locale_paths, "import_module", fake_import_module)


def test_vendored_path_used_when_package_not_importable(monkeypatch):
    _hide_escalated_locale(monkeypatch)
    assert locale_paths.get_central_locale_path() == VENDORED_DIR


def test_get_locale_paths_order_with_vendored_fallback(monkeypatch):
    _hide_escalated_locale(monkeypatch)
    paths = locale_paths.get_locale_paths("/host/locale")
    assert paths == ["/host/locale", locale_paths.PLUGIN_LOCALE_DIR, VENDORED_DIR]


def test_installed_package_wins_over_vendored_copy(monkeypatch, tmp_path):
    pkg_dir = tmp_path / "escalated_locale"
    (pkg_dir / "locale").mkdir(parents=True)
    fake_pkg = types.ModuleType("escalated_locale")
    fake_pkg.__file__ = str(pkg_dir / "__init__.py")

    real_import_module = locale_paths.import_module

    def fake_import_module(name, *args, **kwargs):
        if name == "escalated_locale":
            return fake_pkg
        return real_import_module(name, *args, **kwargs)

    monkeypatch.setattr(locale_paths, "import_module", fake_import_module)
    assert locale_paths.get_central_locale_path() == str(pkg_dir / "locale")


@pytest.mark.parametrize("lang", LANGUAGES)
def test_vendored_catalogue_present_for_every_language(lang):
    messages = os.path.join(VENDORED_DIR, lang, "LC_MESSAGES")
    assert os.path.isfile(os.path.join(messages, "django.po"))
    assert os.path.isfile(os.path.join(messages, "django.mo"))


def test_vendored_catalogue_translates_through_django_gettext(monkeypatch):
    _hide_escalated_locale(monkeypatch)
    with override_settings(LOCALE_PATHS=locale_paths.get_locale_paths()):
        with translation.override("de"):
            assert translation.gettext("nav.admin") == "Verwaltung"
