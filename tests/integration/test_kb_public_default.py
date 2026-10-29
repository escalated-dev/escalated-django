"""
``knowledge_base_public`` defaults on, as in escalated-laravel.

New installs get a public knowledge base. Installs that already existed when
the default changed keep it private unless an admin had chosen otherwise:
migration 0036 stores the old default explicitly for them.
"""

import json
from datetime import timedelta
from importlib import import_module

import pytest
from django.apps import apps as django_apps
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from escalated.kb_guards import kb_public
from escalated.models import EscalatedSetting
from tests.factories import ArticleFactory, TicketFactory


def _run_migration():
    module = import_module("escalated.migrations.0036_knowledge_base_public_default_on")

    class Editor:
        pass

    editor = Editor()
    editor.connection = connection
    module.keep_knowledge_base_private_for_existing_installs(django_apps, editor)


@pytest.mark.django_db
class TestFreshInstall:
    def test_knowledge_base_is_public_by_default(self, client):
        assert EscalatedSetting.get("knowledge_base_public") is None
        assert kb_public() is True
        # A guest can read the customer knowledge base without signing in.
        response = client.get(reverse("escalated:customer_kb_index"), HTTP_X_INERTIA="true")
        assert response.status_code == 200

    def test_widget_serves_articles_to_guests_by_default(self, client):
        EscalatedSetting.set("widget_enabled", "1")
        ArticleFactory(title="Reset password", status="published")

        assert client.get("/support/widget/articles", {"q": "Reset"}).status_code == 200
        assert json.loads(client.get("/support/widget/config").content)["kb_enabled"] is True

    def test_settings_page_shows_the_switch_on(self, admin_user):
        client = Client()
        client.force_login(admin_user)
        response = client.get(reverse("escalated:admin_settings"), HTTP_X_INERTIA="true")
        assert json.loads(response.content)["props"]["settings"]["knowledge_base_public"] is True

    def test_migration_writes_nothing_on_a_fresh_install(self):
        _run_migration()
        assert EscalatedSetting.get("knowledge_base_public") is None
        assert kb_public() is True


@pytest.mark.django_db
class TestExistingInstall:
    def test_install_with_tickets_stays_private(self, client):
        TicketFactory()
        _run_migration()

        assert EscalatedSetting.get("knowledge_base_public") == "0"
        assert kb_public() is False
        assert client.get(reverse("escalated:customer_kb_index"), HTTP_X_INERTIA="true").status_code == 403

    def test_install_with_articles_stays_private(self):
        ArticleFactory(status="published")
        _run_migration()
        assert EscalatedSetting.get("knowledge_base_public") == "0"

    def test_install_migrated_long_ago_stays_private(self):
        MigrationRecorder(connection).migration_qs.filter(app="escalated", name="0001_initial").update(
            applied=timezone.now() - timedelta(days=30)
        )
        _run_migration()
        assert EscalatedSetting.get("knowledge_base_public") == "0"

    @pytest.mark.parametrize("stored", ["1", "0", "true"])
    def test_explicit_admin_choice_is_kept(self, stored):
        TicketFactory()
        EscalatedSetting.set("knowledge_base_public", stored)
        _run_migration()
        assert EscalatedSetting.get("knowledge_base_public") == stored
