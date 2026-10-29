"""The plugin contract (escalated-developer-context domain-model/plugin-contract.md).

- Plugin menus, slots and widgets are shared as ``escalated.plugins``
  (``menuItems``, ``pageComponents``, ``dashboardWidgets``), the shape the
  shared frontend reads. They were never shared, and the share middleware
  called inertia-django's ``share()`` with positional arguments it refuses.
- The canonical events reach plugins' actions under their canonical names,
  with the ticket flat and under ``ticket``. Python plugins got only the
  legacy hook names and the bridge got ids without the ticket.
- ``ctx.tickets.query`` / ``ctx.replies.query`` filter only on the contract's
  keys. They passed the filter straight to ``objects.filter(**filter)``, so a
  plugin could filter on any field or follow any relation.
"""

from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings
from django.test import Client, override_settings

from escalated.bridge.context_handler import ContextHandler
from escalated.hooks import add_action, remove_action
from escalated.models import Reply, Ticket
from escalated.plugin_ui_service import plugin_ui
from tests.factories import ReplyFactory, TicketFactory, UserFactory

INERTIA = {"HTTP_X_INERTIA": "true"}
SHARE_MIDDLEWARE = [*settings.MIDDLEWARE, "escalated.middleware.EscalatedInertiaShareMiddleware"]


@pytest.fixture(autouse=True)
def clean_ui():
    plugin_ui.clear()
    yield
    plugin_ui.clear()


@pytest.fixture
def listen():
    registered = []

    def _listen(*names):
        seen = []
        for name in names:

            def callback(payload, _name=name):
                seen.append((_name, payload))

            add_action(name, callback)
            registered.append((name, callback))
        return seen

    yield _listen
    for name, callback in registered:
        remove_action(name, callback)


def client_for(user):
    client = Client()
    client.force_login(user)
    return client


def shared_plugins(user):
    with override_settings(ESCALATED={"UI_ENABLED": True}, MIDDLEWARE=SHARE_MIDDLEWARE):
        response = client_for(user).get("/support/agent/", **INERTIA)
    assert response.status_code == 200, response.content[:500]
    return response.json()["props"]["escalated"]["plugins"]


# ---------------------------------------------------------------------------
# escalated.plugins
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_python_plugin_menus_widgets_and_slots_are_shared_as_escalated_plugins():
    plugin_ui.add_menu_item(
        {"label": "Billing", "url": "/support/admin/billing", "icon": "cash", "position": 5, "target": "admin"}
    )
    plugin_ui.add_menu_item({"label": "Secret", "url": "/x", "permission": "nobody-has-this"})
    plugin_ui.add_dashboard_widget(
        {"id": "acme.stats", "title": "Stats", "component": "StatsWidget", "plugin": "acme", "width": "half"}
    )
    plugin_ui.add_page_component(
        "ticket.show", "sidebar", {"component": "Panel", "plugin": "acme", "data": {"a": 1}, "position": 3}
    )

    plugins = shared_plugins(UserFactory(username="plugins_admin", is_staff=True, is_superuser=True))

    assert [item["label"] for item in plugins["menuItems"]] == ["Billing", "Secret"]
    assert {k: plugins["menuItems"][0][k] for k in ("route", "icon", "position", "section")} == {
        "route": "/support/admin/billing",
        "icon": "cash",
        "position": 5,
        "section": "admin",
    }
    widget = plugins["dashboardWidgets"][0]
    assert (widget["id"], widget["title"], widget["component"], widget["plugin"]) == (
        "acme.stats",
        "Stats",
        "StatsWidget",
        "acme",
    )
    assert plugins["pageComponents"]["ticket.show.sidebar"] == [
        {"plugin": "acme", "component": "Panel", "data": {"a": 1}, "position": 3}
    ]


@pytest.mark.django_db
def test_agents_do_not_get_admin_items_or_items_they_lack_permission_for():
    plugin_ui.add_menu_item({"label": "Billing", "url": "/support/admin/billing", "target": "admin"})
    plugin_ui.add_menu_item({"label": "Secret", "url": "/x", "permission": "nobody-has-this"})

    agent = UserFactory(username="plugins_agent", is_staff=True)
    with patch("escalated.middleware.is_admin", return_value=False):
        assert shared_plugins(agent) == {}


@pytest.mark.django_db
def test_sdk_plugin_widgets_and_slots_are_keyed_by_slug():
    bridge = MagicMock()
    bridge.is_booted.return_value = True
    bridge.get_manifests.return_value = {
        "@acme/plugin-crm": {
            "widgets": [{"component": "CrmWidget", "label": "CRM deals", "order": 2, "size": "full"}],
            "components": [
                {"page": "ticket.show", "slot": "sidebar", "component": "CrmPanel", "props": {"x": 1}, "order": 4}
            ],
        }
    }

    with patch("escalated.bridge.plugin_bridge.get_bridge", return_value=bridge):
        plugins = shared_plugins(UserFactory(username="plugins_sdk", is_staff=True, is_superuser=True))

    assert plugins["dashboardWidgets"] == [
        {
            "id": "acme--plugin-crm.CrmWidget",
            "title": "CRM deals",
            "component": "CrmWidget",
            "plugin": "acme--plugin-crm",
            "position": 2,
            "width": "full",
        }
    ]
    assert plugins["pageComponents"] == {
        "ticket.show.sidebar": [
            {"plugin": "acme--plugin-crm", "component": "CrmPanel", "data": {"x": 1}, "position": 4}
        ]
    }


# ---------------------------------------------------------------------------
# Canonical events
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_creating_a_ticket_over_http_delivers_ticket_created(listen, django_capture_on_commit_callbacks):
    seen = listen("ticket.created")
    bridge = MagicMock()
    bridge.is_booted.return_value = True
    customer = UserFactory(username="plugins_customer")

    with (
        patch("escalated.bridge.plugin_bridge.get_bridge", return_value=bridge),
        override_settings(ESCALATED={"UI_ENABLED": True}),
        django_capture_on_commit_callbacks(execute=True),
    ):
        response = client_for(customer).post(
            "/support/tickets/store/", {"subject": "Plugin ticket", "description": "Body", "priority": "medium"}
        )

    assert response.status_code in (302, 303), response.content[:500]
    ticket = Ticket.objects.get(subject="Plugin ticket")
    assert [name for name, _ in seen] == ["ticket.created"]
    payload = seen[0][1]
    assert {k: payload[k] for k in ("id", "reference", "subject", "title", "status")} == {
        "id": ticket.pk,
        "reference": ticket.reference,
        "subject": "Plugin ticket",
        "title": "Plugin ticket",
        "status": ticket.status,
    }
    for key in ("department_id", "assigned_to", "requester_id", "metadata", "created_at"):
        assert key in payload
    flat = {k: v for k, v in payload.items() if k != "ticket"}
    assert payload["ticket"] == flat

    hooks = [call.args[0] for call in bridge.dispatch_action.call_args_list]
    assert hooks.count("ticket.created") == 1
    sent = next(call.args[1] for call in bridge.dispatch_action.call_args_list if call.args[0] == "ticket.created")
    assert sent["id"] == ticket.pk


@pytest.mark.django_db
def test_a_reply_delivers_reply_created_and_never_a_legacy_name(listen, django_capture_on_commit_callbacks):
    seen = listen("reply.created", "ticket.replied", "note.created")
    customer = UserFactory(username="plugins_replier")
    ticket = TicketFactory(requester=customer)

    with override_settings(ESCALATED={"UI_ENABLED": True}), django_capture_on_commit_callbacks(execute=True):
        response = client_for(customer).post(f"/support/tickets/{ticket.pk}/reply/", {"body": "Hello plugin"})

    assert response.status_code in (302, 303), response.content[:500]
    reply = Reply.objects.get(body="Hello plugin")
    assert [name for name, _ in seen] == ["reply.created"]
    payload = seen[0][1]
    assert (payload["id"], payload["ticket_id"], payload["is_internal"]) == (reply.pk, ticket.pk, False)
    assert payload["reply"]["id"] == reply.pk
    assert payload["ticket"]["id"] == ticket.pk


@pytest.mark.django_db
def test_a_failing_plugin_does_not_fail_the_request(django_capture_on_commit_callbacks):
    def broken(payload):
        raise RuntimeError("plugin broke")

    add_action("ticket.created", broken)
    bridge = MagicMock()
    bridge.is_booted.return_value = True
    bridge.dispatch_action.side_effect = RuntimeError("runtime broke")
    try:
        with (
            patch("escalated.bridge.plugin_bridge.get_bridge", return_value=bridge),
            override_settings(ESCALATED={"UI_ENABLED": True}),
            django_capture_on_commit_callbacks(execute=True),
        ):
            response = client_for(UserFactory(username="plugins_broken")).post(
                "/support/tickets/store/", {"subject": "Still created", "description": "Body"}
            )
    finally:
        remove_action("ticket.created", broken)

    assert response.status_code in (302, 303)
    assert Ticket.objects.filter(subject="Still created").exists()


# ---------------------------------------------------------------------------
# ctx
# ---------------------------------------------------------------------------


def handler():
    h = ContextHandler()
    h.set_current_plugin("acme")
    return h


@pytest.mark.django_db
def test_ticket_query_maps_contract_keys():
    agent = UserFactory(username="plugins_query_agent")
    mine = TicketFactory(priority=Ticket.Priority.HIGH, assigned_to=agent)
    TicketFactory(priority=Ticket.Priority.LOW)

    rows = handler().handle("ctx.tickets.query", {"filter": {"assigned_to": agent.pk, "priority": "high"}})
    assert [row["id"] for row in rows] == [mine.pk]
    rows = handler().handle("ctx.tickets.query", {"filter": {"reference": mine.reference}})
    assert [row["id"] for row in rows] == [mine.pk]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "key", ["guest_token", "subject", "requester_content_type", "assigned_to__password__startswith", "pk__gt"]
)
def test_ticket_query_rejects_keys_outside_the_contract(key):
    TicketFactory()
    with pytest.raises(ValueError, match="cannot filter"):
        handler().handle("ctx.tickets.query", {"filter": {key: "x"}})


@pytest.mark.django_db
def test_ticket_query_rejects_non_scalar_values():
    with pytest.raises(ValueError, match="single value"):
        handler().handle("ctx.tickets.query", {"filter": {"id": [1, 2]}})


@pytest.mark.django_db
def test_reply_query_maps_is_internal_and_rejects_other_keys():
    ticket = TicketFactory()
    note = ReplyFactory(ticket=ticket, is_internal_note=True, type=Reply.Type.NOTE)
    ReplyFactory(ticket=ticket, is_internal_note=False)

    rows = handler().handle("ctx.replies.query", {"filter": {"ticket_id": ticket.pk, "is_internal": True}})
    assert [row["id"] for row in rows] == [note.pk]
    for key in ("is_internal_note", "body", "author__password"):
        with pytest.raises(ValueError, match="cannot filter"):
            handler().handle("ctx.replies.query", {"filter": {key: True}})


def test_ctx_emit_drops_names_that_impersonate_host_events():
    h = handler()
    bridge = MagicMock()
    h.set_bridge(bridge)

    for hook in ("ticket.created", "plugin.activated", "ticket.replied", "acme.synced"):
        h.handle("ctx.emit", {"hook": hook, "data": {"n": 1}})

    assert [call.args for call in bridge.dispatch_action.call_args_list] == [("acme.synced", {"n": 1})]
