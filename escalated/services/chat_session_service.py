import uuid

from django.utils import timezone

from escalated.models import ChatSession, Reply, Ticket
from escalated.signals import chat_ended, chat_message_sent, chat_rated, chat_started, chat_transferred


class ChatSessionService:
    """Service for managing live chat sessions."""

    def start_chat(self, *, name, email, department=None, metadata=None):
        """
        Start a new chat session. Creates a ticket with channel='chat' and
        a ChatSession in 'waiting' status.

        Returns:
            tuple: (ticket, session)
        """
        customer_session_id = uuid.uuid4().hex

        ticket = Ticket.objects.create(
            subject=f"Chat from {name}",
            description="Live chat conversation",
            status=Ticket.Status.OPEN,
            priority=Ticket.Priority.MEDIUM,
            channel="chat",
            department=department,
            guest_name=name,
            guest_email=email,
            chat_metadata=metadata or {},
        )

        session = ChatSession.objects.create(
            ticket=ticket,
            customer_session_id=customer_session_id,
            status=ChatSession.Status.WAITING,
            metadata=metadata or {},
        )

        chat_started.send(sender=ChatSession, session=session, ticket=ticket)

        return ticket, session

    def assign_agent(self, session, agent):
        """
        Assign an agent to a waiting chat session.

        Returns:
            ChatSession: The updated session.
        """
        session.agent = agent
        session.status = ChatSession.Status.ACTIVE
        session.save(update_fields=["agent", "status", "updated_at"])

        ticket = session.ticket
        ticket.assigned_to = agent
        ticket.status = Ticket.Status.IN_PROGRESS
        ticket.save(update_fields=["assigned_to", "status", "updated_at"])

        return session

    def end_chat(self, session, ended_by=None):
        """
        End a chat session.

        Args:
            session: The ChatSession to end.
            ended_by: The user who ended the chat (agent or None for customer).

        Returns:
            ChatSession: The updated session.
        """
        now = timezone.now()
        session.status = ChatSession.Status.ENDED
        session.ended_at = now
        session.save(update_fields=["status", "ended_at", "updated_at"])

        ticket = session.ticket
        ticket.chat_ended_at = now
        ticket.status = Ticket.Status.RESOLVED
        ticket.resolved_at = now
        ticket.save(update_fields=["chat_ended_at", "status", "resolved_at", "updated_at"])

        chat_ended.send(sender=ChatSession, session=session, ticket=ticket, ended_by=ended_by)

        return session

    def transfer_chat(self, session, from_agent, to_agent):
        """
        Transfer a chat session from one agent to another.

        Returns:
            ChatSession: The updated session.
        """
        session.agent = to_agent
        session.save(update_fields=["agent", "updated_at"])

        ticket = session.ticket
        ticket.assigned_to = to_agent
        ticket.save(update_fields=["assigned_to", "updated_at"])

        chat_transferred.send(
            sender=ChatSession,
            session=session,
            ticket=ticket,
            from_agent=from_agent,
            to_agent=to_agent,
        )

        return session

    def send_message(self, session, *, body, sender=None, sender_type="customer"):
        """
        Send a message in a chat session. Creates a Reply on the ticket.

        Args:
            session: The ChatSession.
            body: The message text.
            sender: The user sending (agent) or None (customer).
            sender_type: 'customer' or 'agent'.

        Returns:
            Reply: The created reply.
        """
        reply = Reply.objects.create(
            ticket=session.ticket,
            author=sender,
            body=body,
            type=Reply.Type.REPLY,
            metadata={"chat_sender_type": sender_type, "chat_session_id": session.pk},
        )

        chat_message_sent.send(
            sender=ChatSession,
            session=session,
            ticket=session.ticket,
            message=reply,
            sender_type=sender_type,
        )

        return reply

    def update_typing(self, session, *, is_typing, sender_type="customer"):
        """
        Update the typing indicator for a chat session.
        """
        now = timezone.now() if is_typing else None
        if sender_type == "customer":
            session.customer_typing_at = now
            session.save(update_fields=["customer_typing_at", "updated_at"])
        else:
            session.agent_typing_at = now
            session.save(update_fields=["agent_typing_at", "updated_at"])

        return session

    def rate_chat(self, session, *, rating, comment=""):
        """
        Rate a completed chat session.

        Returns:
            ChatSession: The updated session.
        """
        session.rating = rating
        session.rating_comment = comment
        session.save(update_fields=["rating", "rating_comment", "updated_at"])

        chat_rated.send(sender=ChatSession, session=session, rating=rating, comment=comment)

        return session
