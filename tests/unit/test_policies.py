import pytest
from django.contrib.auth.models import AnonymousUser

from escalated.policies.article_policy import ArticlePolicy
from escalated.policies.canned_response_policy import CannedResponsePolicy
from escalated.policies.department_policy import DepartmentPolicy
from escalated.policies.escalation_rule_policy import EscalationRulePolicy
from escalated.policies.macro_policy import MacroPolicy
from escalated.policies.sla_policy_policy import SlaPolicyPolicy
from escalated.policies.tag_policy import TagPolicy
from escalated.policies.ticket_policy import TicketPolicy
from tests.factories import CannedResponseFactory, DepartmentFactory, MacroFactory, UserFactory


@pytest.mark.django_db
class TestTicketPolicy:
    def test_admin_can_view(self, admin_user, ticket):
        assert TicketPolicy.view(admin_user, ticket) is True

    def test_agent_can_view(self, agent_user, ticket):
        assert TicketPolicy.view(agent_user, ticket) is True

    def test_requester_can_view(self, user, ticket):
        assert TicketPolicy.view(user, ticket) is True

    def test_random_user_cannot_view(self, db, ticket):
        stranger = UserFactory(username="stranger")
        assert TicketPolicy.view(stranger, ticket) is False

    def test_admin_can_delete(self, admin_user, ticket):
        assert TicketPolicy.delete(admin_user, ticket) is True

    def test_agent_cannot_delete(self, agent_user, ticket):
        assert TicketPolicy.delete(agent_user, ticket) is False

    def test_requester_cannot_delete(self, user, ticket):
        assert TicketPolicy.delete(user, ticket) is False

    def test_admin_can_create(self, admin_user):
        assert TicketPolicy.create(admin_user) is True

    def test_agent_can_create(self, agent_user):
        assert TicketPolicy.create(agent_user) is True

    def test_regular_user_can_create(self, user):
        assert TicketPolicy.create(user) is True

    def test_agent_can_add_note(self, agent_user, ticket):
        assert TicketPolicy.add_note(agent_user, ticket) is True

    def test_requester_cannot_add_note(self, user, ticket):
        assert TicketPolicy.add_note(user, ticket) is False

    def test_assigned_agent_can_update(self, db, ticket):
        agent = UserFactory(username="assigned_agent")
        dept = DepartmentFactory()
        dept.agents.add(agent)
        ticket.assigned_to = agent
        ticket.save()
        assert TicketPolicy.update(agent, ticket) is True

    def test_unauthenticated_user_cannot_view(self, ticket):
        assert TicketPolicy.view(AnonymousUser(), ticket) is False


@pytest.mark.django_db
class TestDepartmentPolicy:
    def test_admin_can_create(self, admin_user):
        assert DepartmentPolicy.create(admin_user) is True

    def test_agent_cannot_create(self, agent_user):
        assert DepartmentPolicy.create(agent_user) is False

    def test_agent_can_view(self, agent_user, department):
        assert DepartmentPolicy.view(agent_user, department) is True

    def test_admin_can_delete(self, admin_user, department):
        assert DepartmentPolicy.delete(admin_user, department) is True


@pytest.mark.django_db
class TestTagPolicy:
    def test_admin_can_create(self, admin_user):
        assert TagPolicy.create(admin_user) is True

    def test_agent_cannot_create(self, agent_user):
        assert TagPolicy.create(agent_user) is False

    def test_agent_can_view(self, agent_user, tag):
        assert TagPolicy.view(agent_user, tag) is True


@pytest.mark.django_db
class TestCannedResponsePolicy:
    def test_admin_can_manage_any(self, admin_user, canned_response):
        assert CannedResponsePolicy.update(admin_user, canned_response) is True

    def test_creator_can_update_own_private(self, agent_user):
        cr = CannedResponseFactory(created_by=agent_user, is_shared=False)
        assert CannedResponsePolicy.update(agent_user, cr) is True

    def test_creator_cannot_update_shared(self, agent_user, canned_response):
        # Factory defaults is_shared=True, so creator needs admin to edit
        assert CannedResponsePolicy.update(agent_user, canned_response) is False

    def test_other_agent_cannot_update_private(self, db, canned_response):
        other = UserFactory(username="other_agent")
        dept = DepartmentFactory(slug="other-dept")
        dept.agents.add(other)
        assert CannedResponsePolicy.update(other, canned_response) is False


@pytest.mark.django_db
class TestSlaPolicyPolicy:
    def test_admin_can_manage(self, admin_user):
        assert SlaPolicyPolicy.create(admin_user) is True

    def test_agent_cannot_manage(self, agent_user):
        assert SlaPolicyPolicy.create(agent_user) is False


@pytest.mark.django_db
class TestEscalationRulePolicy:
    def test_admin_can_manage(self, admin_user):
        assert EscalationRulePolicy.create(admin_user) is True

    def test_agent_cannot_manage(self, agent_user):
        assert EscalationRulePolicy.create(agent_user) is False


@pytest.mark.django_db
class TestMacroPolicy:
    def test_admin_can_manage_any(self, admin_user, macro):
        assert MacroPolicy.update(admin_user, macro) is True

    def test_creator_can_update_own_private(self, agent_user):
        m = MacroFactory(created_by=agent_user, is_shared=False)
        assert MacroPolicy.update(agent_user, m) is True

    def test_creator_cannot_update_shared(self, agent_user, macro):
        assert MacroPolicy.update(agent_user, macro) is False


@pytest.mark.django_db
class TestArticlePolicy:
    def test_admin_can_create(self, admin_user):
        assert ArticlePolicy.create(admin_user) is True

    def test_agent_cannot_create(self, agent_user):
        assert ArticlePolicy.create(agent_user) is False

    def test_anyone_can_view(self, user, article):
        assert ArticlePolicy.view(user, article) is True
