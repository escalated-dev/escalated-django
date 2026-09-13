"""HTTP-level checks of the Workflows admin screen against the shared contract.

The contract lives in escalated-developer-context,
domain-model/workflow-admin-contract.md. Every request here uses the body the
shared builder sends -- top-level ``name``/``trigger_event``/``conditions``/
``actions`` with ``{all}``/``{any}`` conditions and ``{type, value}`` actions --
not whatever this backend happens to store. Posting the backend's own field
names is how every earlier test passed while the UI could not save a workflow
that ever ran.
"""

import json

import pytest
from django.test import Client, override_settings

from escalated import signals as esc_signals
from escalated.models import Reply, Ticket
from escalated.workflow_models import Workflow
from tests.factories import DepartmentFactory, TicketFactory, UserFactory

INDEX = "/support/admin/workflows/"
CREATE = "/support/admin/workflows/create/"
REORDER = "/support/admin/workflows/reorder/"

INERTIA = {"HTTP_X_INERTIA": "true"}


def detail(workflow_id):
    return f"/support/admin/workflows/{workflow_id}/"


def example_body(department_id=4):
    """The request body from the contract, verbatim apart from the department id."""
    return {
        "name": "Route refunds to billing",
        "description": None,
        "trigger_event": "ticket.created",
        "conditions": {"all": [{"field": "subject", "operator": "contains", "value": "refund"}]},
        "actions": [
            {"type": "change_priority", "value": "high"},
            {"type": "set_department", "value": str(department_id)},
        ],
        "is_active": True,
    }


@pytest.fixture
def ui_enabled():
    with override_settings(ESCALATED={"UI_ENABLED": True}):
        yield


@pytest.fixture
def admin_client(db, ui_enabled):
    client = Client()
    client.force_login(UserFactory(username="wf_admin", is_staff=True, is_superuser=True))
    return client


def option_values(options):
    """The values of an option list in any of the three shapes the contract allows."""
    if isinstance(options, dict):
        return set(options)
    return {option["value"] if isinstance(option, dict) else option for option in options}


def inertia_props(response):
    assert response.status_code == 200, response.content[:500]
    page = json.loads(response.content)
    return page["props"]


def make_workflow(**kwargs):
    defaults = {
        "name": "Existing",
        "trigger_event": "ticket.created",
        "conditions": {"all": []},
        "actions": [{"type": "change_priority", "value": "high"}],
        "is_active": True,
        "position": 0,
    }
    defaults.update(kwargs)
    return Workflow.objects.create(**defaults)


@pytest.mark.django_db
class TestCreate:
    def test_create_stores_the_contract_body(self, admin_client):
        department = DepartmentFactory()
        body = example_body(department.pk)

        response = admin_client.post(INDEX, data=json.dumps(body), content_type="application/json", **INERTIA)

        assert response.status_code == 302
        assert response["Location"] == INDEX
        workflow = Workflow.objects.get()
        assert workflow.name == body["name"]
        assert workflow.trigger_event == body["trigger_event"]
        assert workflow.conditions == body["conditions"]
        assert workflow.actions == body["actions"]
        assert workflow.is_active is True

    def test_create_flashes_success_on_the_index(self, admin_client):
        admin_client.post(INDEX, data=json.dumps(example_body()), content_type="application/json", **INERTIA)

        props = inertia_props(admin_client.get(INDEX, **INERTIA))

        assert props["flash"]["success"]

    def test_legacy_create_url_also_accepts_the_contract_body(self, admin_client):
        response = admin_client.post(
            CREATE, data=json.dumps(example_body()), content_type="application/json", **INERTIA
        )

        assert response.status_code == 302
        assert response["Location"] == INDEX
        assert Workflow.objects.get().trigger_event == "ticket.created"

    def test_omitted_conditions_are_stored_as_an_empty_all(self, admin_client):
        body = example_body()
        del body["conditions"]

        admin_client.post(INDEX, data=json.dumps(body), content_type="application/json", **INERTIA)

        assert Workflow.objects.get().conditions == {"all": []}

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("name", ""),
            ("trigger_event", ""),
            ("actions", []),
        ],
    )
    def test_create_rejects_a_missing_required_field(self, admin_client, field, value):
        body = example_body()
        body[field] = value

        response = admin_client.post(
            INDEX,
            data=json.dumps(body),
            content_type="application/json",
            HTTP_REFERER="http://testserver" + CREATE,
            **INERTIA,
        )

        assert response.status_code == 302
        assert response["Location"] == "http://testserver" + CREATE
        assert not Workflow.objects.exists()
        props = inertia_props(admin_client.get(CREATE, **INERTIA))
        assert field in props["errors"]

    def test_errors_are_shown_once(self, admin_client):
        body = example_body()
        body["name"] = ""
        admin_client.post(INDEX, data=json.dumps(body), content_type="application/json", **INERTIA)

        assert "name" in inertia_props(admin_client.get(CREATE, **INERTIA))["errors"]
        assert inertia_props(admin_client.get(CREATE, **INERTIA))["errors"] == {}

    def test_create_rejects_an_unknown_trigger_event(self, admin_client):
        body = example_body()
        body["trigger_event"] = "ticket_created"

        admin_client.post(INDEX, data=json.dumps(body), content_type="application/json", **INERTIA)

        assert not Workflow.objects.exists()


@pytest.mark.django_db
class TestUpdate:
    def test_put_updates_with_the_contract_body(self, admin_client):
        workflow = make_workflow()
        body = example_body()
        body["trigger_event"] = "ticket.updated"
        body["is_active"] = False

        response = admin_client.put(
            detail(workflow.pk), data=json.dumps(body), content_type="application/json", **INERTIA
        )

        assert response.status_code == 303
        assert response["Location"] == INDEX
        workflow.refresh_from_db()
        assert workflow.name == body["name"]
        assert workflow.trigger_event == "ticket.updated"
        assert workflow.conditions == body["conditions"]
        assert workflow.actions == body["actions"]
        assert workflow.is_active is False

    def test_update_flashes_success(self, admin_client):
        workflow = make_workflow()
        admin_client.put(
            detail(workflow.pk), data=json.dumps(example_body()), content_type="application/json", **INERTIA
        )

        assert inertia_props(admin_client.get(INDEX, **INERTIA))["flash"]["success"]

    def test_legacy_post_update_still_works(self, admin_client):
        workflow = make_workflow()

        response = admin_client.post(
            detail(workflow.pk), data=json.dumps(example_body()), content_type="application/json", **INERTIA
        )

        assert response.status_code == 302
        workflow.refresh_from_db()
        assert workflow.name == "Route refunds to billing"

    def test_put_rejects_empty_actions(self, admin_client):
        workflow = make_workflow()
        body = example_body()
        body["actions"] = []

        response = admin_client.put(
            detail(workflow.pk), data=json.dumps(body), content_type="application/json", **INERTIA
        )

        assert response.status_code == 303
        workflow.refresh_from_db()
        assert workflow.actions == [{"type": "change_priority", "value": "high"}]
        props = inertia_props(admin_client.get(detail(workflow.pk), **INERTIA))
        assert "actions" in props["errors"]

    def test_update_of_a_missing_workflow_is_404(self, admin_client):
        response = admin_client.put(detail(999999), data=json.dumps(example_body()), content_type="application/json")

        assert response.status_code == 404


@pytest.mark.django_db
class TestIndexActions:
    def test_toggle_flips_is_active_and_redirects_to_the_index(self, admin_client):
        workflow = make_workflow(is_active=True)

        response = admin_client.post(f"{detail(workflow.pk)}toggle/", **INERTIA)

        assert response.status_code == 302
        assert response["Location"] == INDEX
        workflow.refresh_from_db()
        assert workflow.is_active is False

    def test_reorder_sets_positions_in_the_given_order(self, admin_client):
        a = make_workflow(name="a", position=0)
        b = make_workflow(name="b", position=1)
        c = make_workflow(name="c", position=2)

        response = admin_client.post(
            REORDER,
            data=json.dumps({"workflow_ids": [c.pk, a.pk, b.pk]}),
            content_type="application/json",
            **INERTIA,
        )

        assert response.status_code == 302
        assert response["Location"] == INDEX
        ordered = list(Workflow.objects.order_by("position").values_list("pk", flat=True))
        assert ordered == [c.pk, a.pk, b.pk]

    def test_delete_method_removes_the_workflow(self, admin_client):
        workflow = make_workflow()

        response = admin_client.delete(detail(workflow.pk), **INERTIA)

        assert response.status_code == 303
        assert response["Location"] == INDEX
        assert not Workflow.objects.filter(pk=workflow.pk).exists()

    def test_legacy_delete_url_still_works(self, admin_client):
        workflow = make_workflow()

        response = admin_client.post(f"{detail(workflow.pk)}delete/", **INERTIA)

        assert response.status_code == 302
        assert not Workflow.objects.filter(pk=workflow.pk).exists()

    def test_non_admin_cannot_create(self, db, ui_enabled):
        client = Client()
        client.force_login(UserFactory(username="wf_agent", is_staff=False))

        response = client.post(INDEX, data=json.dumps(example_body()), content_type="application/json", **INERTIA)

        assert response.status_code == 403
        assert not Workflow.objects.exists()


@pytest.mark.django_db
class TestFormProps:
    def test_create_page_carries_trigger_events_and_action_types(self, admin_client):
        props = inertia_props(admin_client.get(CREATE, **INERTIA))

        assert props["workflow"] is None
        assert props["trigger_events"]
        assert props["action_types"]
        assert props["operators"]

    def test_edit_page_serializes_the_workflow(self, admin_client):
        workflow = make_workflow(conditions={"any": [{"field": "status", "operator": "equals", "value": "open"}]})

        props = inertia_props(admin_client.get(detail(workflow.pk), **INERTIA))

        assert props["workflow"]["id"] == workflow.pk
        assert props["workflow"]["trigger_event"] == "ticket.created"
        assert props["workflow"]["conditions"] == workflow.conditions
        assert props["workflow"]["actions"] == workflow.actions
        assert props["workflow"]["is_active"] is True
        assert props["workflow"]["position"] == 0

    def test_trigger_events_are_exactly_the_events_this_backend_fires(self, admin_client):
        offered = option_values(inertia_props(admin_client.get(CREATE, **INERTIA))["trigger_events"])

        assert offered == fired_trigger_events()

    def test_trigger_events_include_the_canonical_five(self, admin_client):
        offered = option_values(inertia_props(admin_client.get(CREATE, **INERTIA))["trigger_events"])

        assert {
            "ticket.created",
            "ticket.updated",
            "ticket.assigned",
            "ticket.status_changed",
            "reply.created",
        } <= offered

    def test_action_types_include_the_core_catalog(self, admin_client):
        offered = option_values(inertia_props(admin_client.get(CREATE, **INERTIA))["action_types"])

        assert {
            "change_status",
            "change_priority",
            "add_tag",
            "remove_tag",
            "set_department",
            "assign_agent",
            "add_note",
            "insert_canned_reply",
        } <= offered


def fired_trigger_events():
    """Every trigger name the workflow signal handlers pass to the engine.

    Sends each signal the handlers subscribe to and records the name the engine
    was asked to run, so the assertion follows the handlers rather than a list
    copied into the test.
    """
    from unittest.mock import MagicMock, patch

    ticket = TicketFactory()
    engine = MagicMock()
    with patch("escalated.services.workflow_engine.WorkflowEngine", return_value=engine):
        from escalated import workflow_handlers

        for handler, kwargs in [
            (workflow_handlers._workflow_ticket_created, {}),
            (workflow_handlers._workflow_ticket_updated, {}),
            (workflow_handlers._workflow_status_changed, {}),
            (workflow_handlers._workflow_ticket_assigned, {}),
            (workflow_handlers._workflow_priority_changed, {}),
            (workflow_handlers._workflow_ticket_escalated, {}),
            (workflow_handlers._workflow_reply_created, {"reply": None}),
            (workflow_handlers._workflow_sla_breached, {}),
            (workflow_handlers._workflow_sla_warning, {}),
        ]:
            handler(sender=Ticket, ticket=ticket, **kwargs)
    return {c.args[0] for c in engine.process_event.call_args_list}


@pytest.mark.django_db
class TestSavedWorkflowRuns:
    """Contract test 2: a workflow saved through the endpoint runs when its event fires."""

    def test_saved_workflow_runs_on_ticket_created(self, admin_client):
        department = DepartmentFactory()
        admin_client.post(
            INDEX, data=json.dumps(example_body(department.pk)), content_type="application/json", **INERTIA
        )

        ticket = TicketFactory(subject="Please refund my order", priority="low", department=None)
        esc_signals.ticket_created.send(sender=Ticket, ticket=ticket, user=None)

        ticket.refresh_from_db()
        assert ticket.priority == "high"
        assert ticket.department_id == department.pk

    def test_saved_workflow_does_not_run_on_a_non_matching_ticket(self, admin_client):
        department = DepartmentFactory()
        admin_client.post(
            INDEX, data=json.dumps(example_body(department.pk)), content_type="application/json", **INERTIA
        )

        ticket = TicketFactory(subject="Password reset", priority="low", department=None)
        esc_signals.ticket_created.send(sender=Ticket, ticket=ticket, user=None)

        ticket.refresh_from_db()
        assert ticket.priority == "low"

    def test_saved_reply_created_workflow_runs_when_a_reply_is_created(self, admin_client):
        body = example_body()
        body["trigger_event"] = "reply.created"
        body["conditions"] = {"all": []}
        body["actions"] = [{"type": "change_priority", "value": "urgent"}]
        admin_client.post(INDEX, data=json.dumps(body), content_type="application/json", **INERTIA)

        ticket = TicketFactory(priority="low")
        reply = Reply.objects.create(ticket=ticket, body="thanks")
        esc_signals.reply_created.send(sender=Reply, reply=reply, ticket=ticket, user=None)

        ticket.refresh_from_db()
        assert ticket.priority == "urgent"
