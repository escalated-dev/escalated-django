import os
import pytest
from django.utils import translation


LOCALES = ["en", "de", "es", "fr"]
LOCALE_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "escalated", "locale"
)


class TestTranslations:
    def test_locale_directories_exist(self):
        for locale in LOCALES:
            po_path = os.path.join(LOCALE_DIR, locale, "LC_MESSAGES", "django.po")
            assert os.path.isfile(po_path), f"Missing {po_path}"

    @pytest.mark.parametrize("locale", LOCALES)
    def test_enum_labels_resolve(self, locale):
        with translation.override(locale):
            from escalated.models import Ticket

            for value, label in Ticket.Status.choices:
                assert len(str(label)) > 0

    @pytest.mark.parametrize("locale", LOCALES)
    def test_no_empty_translations(self, locale):
        """Non-English locales should have msgstr filled in for all msgid entries."""
        if locale == "en":
            return
        po_path = os.path.join(LOCALE_DIR, locale, "LC_MESSAGES", "django.po")
        with open(po_path, "r", encoding="utf-8") as f:
            content = f.read()
        lines = content.split("\n")
        in_header = True
        for i, line in enumerate(lines):
            if line.startswith("msgid ") and line != 'msgid ""':
                in_header = False
            if not in_header and line == 'msgstr ""':
                if i + 1 < len(lines) and lines[i + 1].startswith('"'):
                    continue
                for j in range(i - 1, -1, -1):
                    if lines[j].startswith("msgid"):
                        pytest.fail(f"Empty translation in {locale}: {lines[j]}")
                        break
