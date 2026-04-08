import pytest
from django.http import HttpResponseNotFound
from django.test import RequestFactory

from escalated.kb_guards import (
    kb_enabled,
    kb_feedback_enabled,
    kb_public,
    require_kb_enabled,
)
from escalated.models import EscalatedSetting


@pytest.mark.django_db
class TestKbSettings:
    def test_kb_enabled_default_true(self):
        assert kb_enabled() is True

    def test_kb_enabled_set_false(self):
        EscalatedSetting.set("knowledge_base_enabled", "false")
        assert kb_enabled() is False

    def test_kb_enabled_set_true(self):
        EscalatedSetting.set("knowledge_base_enabled", "true")
        assert kb_enabled() is True

    def test_kb_public_default_false(self):
        assert kb_public() is False

    def test_kb_public_set_true(self):
        EscalatedSetting.set("knowledge_base_public", "true")
        assert kb_public() is True

    def test_kb_feedback_enabled_default_true(self):
        assert kb_feedback_enabled() is True

    def test_kb_feedback_enabled_set_false(self):
        EscalatedSetting.set("knowledge_base_feedback_enabled", "false")
        assert kb_feedback_enabled() is False


@pytest.mark.django_db
class TestRequireKbEnabledDecorator:
    def setup_method(self):
        self.factory = RequestFactory()

    def _make_view(self):
        @require_kb_enabled
        def my_view(request):
            from django.http import JsonResponse

            return JsonResponse({"ok": True})

        return my_view

    def test_allows_when_enabled(self):
        EscalatedSetting.set("knowledge_base_enabled", "true")
        view = self._make_view()
        request = self.factory.get("/test/")
        response = view(request)
        assert response.status_code == 200

    def test_blocks_when_disabled(self):
        EscalatedSetting.set("knowledge_base_enabled", "false")
        view = self._make_view()
        request = self.factory.get("/test/")
        response = view(request)
        assert response.status_code == 404
        assert isinstance(response, HttpResponseNotFound)

    def test_allows_by_default(self):
        # No setting set, should default to enabled
        view = self._make_view()
        request = self.factory.get("/test/")
        response = view(request)
        assert response.status_code == 200

    def test_preserves_function_name(self):
        view = self._make_view()
        assert view.__name__ == "my_view"
