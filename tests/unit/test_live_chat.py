import json
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from escalated.models import (
    AgentProfile,
    ChatRoutingRule,
    ChatSession,
    Ticket,
)
from escalated.services.chat_availability_service import ChatAvailabilityService
from escalated.services.chat_routing_service import ChatRoutingService
from escalated.services.chat_session_service import ChatSessionService
from tests.factories import DepartmentFactory, UserFactory

# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestChatSessionModel:
    def test_create_chat_session(self):
        ticket = Ticket.objects.create(
            subject="Test chat",
            description="Chat ticket",
            channel="chat",
            guest_name="Alice",
            guest_email="alice@example.com",
        )
        session = ChatSession.objects.create(
            ticket=ticket,
            customer_session_id="abc123",
            status=ChatSession.Status.WAITING,
        )
        assert session.is_waiting is True
        assert session.is_active is False
        assert str(session) == f"ChatSession {session.pk} (waiting)"

    def test_queryset_filters(self):
        ticket = Ticket.objects.create(
            subject="Test",
            description="desc",
            channel="chat",
            guest_name="Bob",
            guest_email="bob@example.com",
        )
        ChatSession.objects.create(
            ticket=ticket,
            customer_session_id="s1",
            status=ChatSession.Status.WAITING,
        )
        ChatSession.objects.create(
            ticket=ticket,
            customer_session_id="s2",
            status=ChatSession.Status.ACTIVE,
        )
        ChatSession.objects.create(
            ticket=ticket,
            customer_session_id="s3",
            status=ChatSession.Status.ENDED,
        )

        assert ChatSession.objects.waiting().count() == 1
        assert ChatSession.objects.active().count() == 1
        assert ChatSession.objects.ended().count() == 1


@pytest.mark.django_db
class TestChatRoutingRuleModel:
    def test_create_routing_rule(self):
        rule = ChatRoutingRule.objects.create(
            routing_strategy=ChatRoutingRule.RoutingStrategy.ROUND_ROBIN,
            offline_behavior=ChatRoutingRule.OfflineBehavior.TICKET,
            max_concurrent_chats=3,
            welcome_message="Hello!",
            is_active=True,
        )
        assert "Global" in str(rule)
        assert rule.is_active is True

    def test_queryset_active(self):
        ChatRoutingRule.objects.create(is_active=True)
        ChatRoutingRule.objects.create(is_active=False)
        assert ChatRoutingRule.objects.active().count() == 1


@pytest.mark.django_db
class TestTicketChatFields:
    def test_ticket_live_chat_fields(self):
        ticket = Ticket.objects.create(
            subject="Chat ticket",
            description="desc",
            channel="chat",
            guest_name="Carol",
            guest_email="carol@example.com",
            chat_metadata={"source": "widget"},
        )
        assert ticket.is_live_chat is True
        assert ticket.chat_ended_at is None
        assert ticket.chat_metadata == {"source": "widget"}

    def test_live_chats_queryset(self):
        Ticket.objects.create(
            subject="Chat",
            description="d",
            channel="chat",
            guest_name="A",
            guest_email="a@e.com",
        )
        Ticket.objects.create(
            subject="Email",
            description="d",
            channel="email",
            guest_name="B",
            guest_email="b@e.com",
        )
        assert Ticket.objects.live_chats().count() == 1


@pytest.mark.django_db
class TestAgentProfileChatStatus:
    def test_chat_status_default(self):
        user = UserFactory()
        profile = AgentProfile.objects.create(user=user)
        assert profile.chat_status == AgentProfile.ChatStatus.OFFLINE
        assert profile.is_chat_online() is False

    def test_set_online(self):
        user = UserFactory()
        profile = AgentProfile.objects.create(user=user, chat_status=AgentProfile.ChatStatus.ONLINE)
        assert profile.is_chat_online() is True


# ---------------------------------------------------------------------------
# Service tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestChatSessionService:
    def test_start_chat(self):
        service = ChatSessionService()
        ticket, session = service.start_chat(name="Alice", email="alice@test.com")

        assert ticket.channel == "chat"
        assert ticket.guest_name == "Alice"
        assert ticket.guest_email == "alice@test.com"
        assert session.status == ChatSession.Status.WAITING
        assert session.customer_session_id

    def test_assign_agent(self):
        service = ChatSessionService()
        ticket, session = service.start_chat(name="Alice", email="alice@test.com")

        agent = UserFactory(username="agent1")
        session = service.assign_agent(session, agent)

        assert session.status == ChatSession.Status.ACTIVE
        assert session.agent == agent
        ticket.refresh_from_db()
        assert ticket.assigned_to == agent
        assert ticket.status == Ticket.Status.IN_PROGRESS

    def test_end_chat(self):
        service = ChatSessionService()
        ticket, session = service.start_chat(name="Alice", email="alice@test.com")
        agent = UserFactory(username="agent2")
        session = service.assign_agent(session, agent)
        session = service.end_chat(session, ended_by=agent)

        assert session.status == ChatSession.Status.ENDED
        assert session.ended_at is not None
        ticket.refresh_from_db()
        assert ticket.chat_ended_at is not None
        assert ticket.status == Ticket.Status.RESOLVED

    def test_transfer_chat(self):
        service = ChatSessionService()
        ticket, session = service.start_chat(name="Alice", email="alice@test.com")
        agent1 = UserFactory(username="agent_a")
        agent2 = UserFactory(username="agent_b")
        session = service.assign_agent(session, agent1)
        session = service.transfer_chat(session, from_agent=agent1, to_agent=agent2)

        assert session.agent == agent2
        ticket.refresh_from_db()
        assert ticket.assigned_to == agent2

    def test_send_message(self):
        service = ChatSessionService()
        ticket, session = service.start_chat(name="Alice", email="alice@test.com")
        agent = UserFactory(username="agent3")
        session = service.assign_agent(session, agent)

        reply = service.send_message(session, body="Hello!", sender=agent, sender_type="agent")
        assert reply.body == "Hello!"
        assert reply.author == agent
        assert reply.metadata["chat_sender_type"] == "agent"

        reply2 = service.send_message(session, body="Hi!", sender=None, sender_type="customer")
        assert reply2.author is None
        assert reply2.metadata["chat_sender_type"] == "customer"

    def test_update_typing(self):
        service = ChatSessionService()
        ticket, session = service.start_chat(name="Alice", email="alice@test.com")

        session = service.update_typing(session, is_typing=True, sender_type="customer")
        assert session.customer_typing_at is not None

        session = service.update_typing(session, is_typing=False, sender_type="customer")
        assert session.customer_typing_at is None

    def test_rate_chat(self):
        service = ChatSessionService()
        ticket, session = service.start_chat(name="Alice", email="alice@test.com")
        agent = UserFactory(username="agent4")
        session = service.assign_agent(session, agent)
        session = service.end_chat(session, ended_by=agent)

        session = service.rate_chat(session, rating=5, comment="Great!")
        assert session.rating == 5
        assert session.rating_comment == "Great!"


@pytest.mark.django_db
class TestChatRoutingService:
    def _make_online_agent(self, username, department=None):
        user = UserFactory(username=username)
        AgentProfile.objects.create(user=user, chat_status=AgentProfile.ChatStatus.ONLINE)
        if department:
            department.agents.add(user)
        return user

    def test_find_available_agent_no_agents(self):
        service = ChatRoutingService()
        assert service.find_available_agent() is None

    def test_find_available_agent_with_online(self):
        agent = self._make_online_agent("routing_agent")
        service = ChatRoutingService()
        found = service.find_available_agent()
        assert found == agent

    def test_find_available_agent_at_capacity(self):
        agent = self._make_online_agent("cap_agent")
        ChatRoutingRule.objects.create(
            routing_strategy=ChatRoutingRule.RoutingStrategy.ROUND_ROBIN,
            max_concurrent_chats=1,
            is_active=True,
        )
        # Create an active session to fill capacity
        ticket = Ticket.objects.create(
            subject="t",
            description="d",
            channel="chat",
            guest_name="x",
            guest_email="x@e.com",
        )
        ChatSession.objects.create(
            ticket=ticket,
            customer_session_id="cap1",
            status=ChatSession.Status.ACTIVE,
            agent=agent,
        )

        service = ChatRoutingService()
        assert service.find_available_agent() is None

    def test_evaluate_routing(self):
        self._make_online_agent("eval_agent")
        service = ChatRoutingService()
        result = service.evaluate_routing()
        assert result["is_available"] is True
        assert result["total_online_agents"] == 1
        assert result["available_agents"] == 1


@pytest.mark.django_db
class TestChatAvailabilityService:
    def test_not_available_without_agents(self):
        service = ChatAvailabilityService()
        assert service.is_available() is False

    def test_available_with_online_agent(self):
        user = UserFactory(username="avail_agent")
        AgentProfile.objects.create(user=user, chat_status=AgentProfile.ChatStatus.ONLINE)

        service = ChatAvailabilityService()
        assert service.is_available() is True

    def test_get_queue_position(self):
        service = ChatAvailabilityService()
        session_service = ChatSessionService()

        _, s1 = session_service.start_chat(name="A", email="a@e.com")
        _, s2 = session_service.start_chat(name="B", email="b@e.com")

        pos1 = service.get_queue_position(s1)
        pos2 = service.get_queue_position(s2)
        assert pos1 == 1
        assert pos2 == 2

    def test_get_agent_chat_count(self):
        user = UserFactory(username="count_agent")
        AgentProfile.objects.create(user=user, chat_status=AgentProfile.ChatStatus.ONLINE)

        service = ChatAvailabilityService()
        assert service.get_agent_chat_count(user) == 0

        ticket = Ticket.objects.create(
            subject="t",
            description="d",
            channel="chat",
            guest_name="x",
            guest_email="x@e.com",
        )
        ChatSession.objects.create(
            ticket=ticket,
            customer_session_id="cnt1",
            status=ChatSession.Status.ACTIVE,
            agent=user,
        )
        assert service.get_agent_chat_count(user) == 1


# ---------------------------------------------------------------------------
# View tests - Agent chat
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAgentChatViews:
    def _login_agent(self, client):
        department = DepartmentFactory()
        agent = UserFactory(username="view_agent")
        department.agents.add(agent)
        client.force_login(agent)
        return agent

    def test_active_chats_requires_auth(self, client):
        response = client.get("/support/agent/chat/active/")
        assert response.status_code == 302  # redirect to login

    def test_active_chats_empty(self, client):
        self._login_agent(client)
        response = client.get("/support/agent/chat/active/")
        assert response.status_code == 200
        assert response.json()["chats"] == []

    def test_chat_queue(self, client):
        self._login_agent(client)
        session_service = ChatSessionService()
        session_service.start_chat(name="Q", email="q@e.com")

        response = client.get("/support/agent/chat/queue/")
        assert response.status_code == 200
        assert len(response.json()["queue"]) == 1

    def test_accept_chat(self, client):
        self._login_agent(client)
        session_service = ChatSessionService()
        _, session = session_service.start_chat(name="Accept", email="a@e.com")

        response = client.post(f"/support/agent/chat/{session.pk}/accept/")
        assert response.status_code == 200
        data = response.json()
        assert data["chat"]["status"] == "active"

    def test_end_chat(self, client):
        agent = self._login_agent(client)
        session_service = ChatSessionService()
        _, session = session_service.start_chat(name="End", email="e@e.com")
        session_service.assign_agent(session, agent)

        response = client.post(f"/support/agent/chat/{session.pk}/end/")
        assert response.status_code == 200
        assert response.json()["chat"]["status"] == "ended"

    def test_send_message(self, client):
        agent = self._login_agent(client)
        session_service = ChatSessionService()
        _, session = session_service.start_chat(name="Msg", email="m@e.com")
        session_service.assign_agent(session, agent)

        response = client.post(
            f"/support/agent/chat/{session.pk}/message/",
            data=json.dumps({"body": "Hello from agent"}),
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json()["message"]["sender_type"] == "agent"

    def test_update_status(self, client):
        self._login_agent(client)
        response = client.post(
            "/support/agent/chat/status/",
            data=json.dumps({"status": "online"}),
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json()["status"] == "online"

    def test_transfer_chat(self, client):
        agent = self._login_agent(client)
        agent2 = UserFactory(username="transfer_target")

        session_service = ChatSessionService()
        _, session = session_service.start_chat(name="Transfer", email="t@e.com")
        session_service.assign_agent(session, agent)

        response = client.post(
            f"/support/agent/chat/{session.pk}/transfer/",
            data=json.dumps({"agent_id": agent2.pk}),
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json()["chat"]["agent_id"] == agent2.pk

    def test_update_typing(self, client):
        self._login_agent(client)
        session_service = ChatSessionService()
        _, session = session_service.start_chat(name="Typing", email="ty@e.com")

        response = client.post(
            f"/support/agent/chat/{session.pk}/typing/",
            data=json.dumps({"is_typing": True}),
            content_type="application/json",
        )
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# View tests - Widget chat
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestWidgetChatViews:
    def setup_method(self):
        cache.clear()

    def test_availability_no_agents(self, client):
        response = client.get("/support/widget/chat/availability/")
        assert response.status_code == 200
        data = response.json()
        assert data["available"] is False

    def test_availability_with_agent(self, client):
        user = UserFactory(username="widget_agent")
        AgentProfile.objects.create(user=user, chat_status=AgentProfile.ChatStatus.ONLINE)

        response = client.get("/support/widget/chat/availability/")
        assert response.status_code == 200
        assert response.json()["available"] is True

    def test_start_chat(self, client):
        response = client.post(
            "/support/widget/chat/start/",
            data=json.dumps({"name": "Visitor", "email": "visitor@example.com"}),
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"]
        assert data["ticket_reference"]

    def test_start_chat_validation(self, client):
        response = client.post(
            "/support/widget/chat/start/",
            data=json.dumps({"name": "", "email": ""}),
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_send_message(self, client):
        # Start a chat first
        session_service = ChatSessionService()
        _, session = session_service.start_chat(name="Msg", email="msg@e.com")

        response = client.post(
            "/support/widget/chat/message/",
            data=json.dumps({"session_id": session.customer_session_id, "body": "Hello"}),
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json()["message"]["body"] == "Hello"

    def test_end_chat(self, client):
        session_service = ChatSessionService()
        _, session = session_service.start_chat(name="End", email="end@e.com")

        response = client.post(
            "/support/widget/chat/end/",
            data=json.dumps({"session_id": session.customer_session_id}),
            content_type="application/json",
        )
        assert response.status_code == 200

    def test_rate_chat(self, client):
        session_service = ChatSessionService()
        _, session = session_service.start_chat(name="Rate", email="rate@e.com")
        agent = UserFactory(username="rate_agent")
        session_service.assign_agent(session, agent)
        session_service.end_chat(session)

        response = client.post(
            "/support/widget/chat/rate/",
            data=json.dumps(
                {
                    "session_id": session.customer_session_id,
                    "rating": 4,
                    "comment": "Good",
                }
            ),
            content_type="application/json",
        )
        assert response.status_code == 200

    def test_rate_chat_invalid_rating(self, client):
        session_service = ChatSessionService()
        _, session = session_service.start_chat(name="Rate2", email="rate2@e.com")
        agent = UserFactory(username="rate_agent2")
        session_service.assign_agent(session, agent)
        session_service.end_chat(session)

        response = client.post(
            "/support/widget/chat/rate/",
            data=json.dumps(
                {
                    "session_id": session.customer_session_id,
                    "rating": 10,
                }
            ),
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_typing(self, client):
        session_service = ChatSessionService()
        _, session = session_service.start_chat(name="Typ", email="typ@e.com")

        response = client.post(
            "/support/widget/chat/typing/",
            data=json.dumps({"session_id": session.customer_session_id, "is_typing": True}),
            content_type="application/json",
        )
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Management command tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCloseIdleChatsCommand:
    def test_closes_idle_sessions(self):
        from io import StringIO

        from django.core.management import call_command

        service = ChatSessionService()
        _, session = service.start_chat(name="Idle", email="idle@e.com")
        agent = UserFactory(username="idle_agent")
        service.assign_agent(session, agent)

        # Make the session appear idle by backdating updated_at
        ChatSession.objects.filter(pk=session.pk).update(
            updated_at=timezone.now() - timedelta(minutes=60),
        )

        out = StringIO()
        call_command("close_idle_chats", "--minutes=30", stdout=out)
        output = out.getvalue()
        assert "1" in output

        session.refresh_from_db()
        assert session.status == ChatSession.Status.ENDED

    def test_dry_run(self):
        from io import StringIO

        from django.core.management import call_command

        service = ChatSessionService()
        _, session = service.start_chat(name="Dry", email="dry@e.com")
        agent = UserFactory(username="dry_agent")
        service.assign_agent(session, agent)

        ChatSession.objects.filter(pk=session.pk).update(
            updated_at=timezone.now() - timedelta(minutes=60),
        )

        out = StringIO()
        call_command("close_idle_chats", "--minutes=30", "--dry-run", stdout=out)
        output = out.getvalue()
        assert "DRY RUN" in output

        session.refresh_from_db()
        assert session.status == ChatSession.Status.ACTIVE


@pytest.mark.django_db
class TestCleanupAbandonedChatsCommand:
    def test_marks_abandoned(self):
        from io import StringIO

        from django.core.management import call_command

        service = ChatSessionService()
        _, session = service.start_chat(name="Abandon", email="abandon@e.com")

        # Backdate created_at
        ChatSession.objects.filter(pk=session.pk).update(
            created_at=timezone.now() - timedelta(minutes=20),
        )

        out = StringIO()
        call_command("cleanup_abandoned_chats", "--minutes=10", stdout=out)
        output = out.getvalue()
        assert "1" in output

        session.refresh_from_db()
        assert session.status == ChatSession.Status.ABANDONED

    def test_no_abandoned(self):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("cleanup_abandoned_chats", "--minutes=10", stdout=out)
        assert "No abandoned" in out.getvalue()
