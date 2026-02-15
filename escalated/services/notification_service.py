import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.translation import gettext as _

from escalated.conf import get_setting

logger = logging.getLogger("escalated")


class NotificationService:
    """
    Sends notifications through configured channels (email, webhook).
    """

    @staticmethod
    def notify_ticket_created(ticket):
        """Send notification when a new ticket is created."""
        channels = get_setting("NOTIFICATION_CHANNELS")

        if "email" in channels:
            NotificationService._send_email(
                subject="[%s] %s" % (
                    ticket.reference,
                    _("New ticket: %(subject)s") % {"subject": ticket.subject},
                ),
                template="escalated/emails/new_ticket.html",
                context={"ticket": ticket},
                recipient=NotificationService._get_requester_email(ticket),
            )

        NotificationService._fire_webhook("ticket.created", {
            "ticket_id": ticket.pk,
            "reference": ticket.reference,
            "subject": ticket.subject,
            "priority": ticket.priority,
        })

    @staticmethod
    def notify_reply_added(ticket, reply):
        """Send notification when a reply is added."""
        channels = get_setting("NOTIFICATION_CHANNELS")

        if "email" in channels:
            # Notify the requester if an agent replied
            requester_email = NotificationService._get_requester_email(ticket)
            if requester_email and reply.author != ticket.requester:
                NotificationService._send_email(
                    subject="[%s] %s" % (
                        ticket.reference,
                        _("New reply on: %(subject)s") % {"subject": ticket.subject},
                    ),
                    template="escalated/emails/reply.html",
                    context={"ticket": ticket, "reply": reply},
                    recipient=requester_email,
                )

            # Notify assigned agent if customer replied
            if ticket.assigned_to and reply.author != ticket.assigned_to:
                agent_email = getattr(ticket.assigned_to, "email", None)
                if agent_email:
                    NotificationService._send_email(
                        subject="[%s] %s" % (
                            ticket.reference,
                            _("Customer reply on: %(subject)s") % {"subject": ticket.subject},
                        ),
                        template="escalated/emails/reply.html",
                        context={"ticket": ticket, "reply": reply},
                        recipient=agent_email,
                    )

            # Notify followers (except the author and assignee, already notified)
            NotificationService._notify_followers(
                ticket,
                reply.author,
                subject="[%s] %s" % (
                    ticket.reference,
                    _("New reply on: %(subject)s") % {"subject": ticket.subject},
                ),
                template="escalated/emails/reply.html",
                context={"ticket": ticket, "reply": reply},
                exclude_user_ids=[
                    ticket.assigned_to_id,
                ] if ticket.assigned_to_id else [],
            )

        NotificationService._fire_webhook("reply.created", {
            "ticket_id": ticket.pk,
            "reference": ticket.reference,
            "reply_id": reply.pk,
            "is_internal": reply.is_internal_note,
        })

    @staticmethod
    def notify_ticket_assigned(ticket, agent):
        """Send notification to an agent when they are assigned a ticket."""
        channels = get_setting("NOTIFICATION_CHANNELS")

        if "email" in channels:
            agent_email = getattr(agent, "email", None)
            if agent_email:
                NotificationService._send_email(
                    subject="[%s] %s" % (
                        ticket.reference,
                        _("Ticket assigned to you: %(subject)s") % {"subject": ticket.subject},
                    ),
                    template="escalated/emails/assigned.html",
                    context={"ticket": ticket, "agent": agent},
                    recipient=agent_email,
                )

        NotificationService._fire_webhook("ticket.assigned", {
            "ticket_id": ticket.pk,
            "reference": ticket.reference,
            "agent_id": agent.pk,
        })

    @staticmethod
    def notify_status_changed(ticket, old_status, new_status):
        """Send notification when ticket status changes."""
        channels = get_setting("NOTIFICATION_CHANNELS")

        if "email" in channels:
            requester_email = NotificationService._get_requester_email(ticket)
            if requester_email:
                NotificationService._send_email(
                    subject="[%s] %s" % (
                        ticket.reference,
                        _("Status updated: %(subject)s") % {"subject": ticket.subject},
                    ),
                    template="escalated/emails/status_changed.html",
                    context={
                        "ticket": ticket,
                        "old_status": old_status,
                        "new_status": new_status,
                    },
                    recipient=requester_email,
                )

            # Notify followers of status changes
            NotificationService._notify_followers(
                ticket,
                causer=None,
                subject="[%s] %s" % (
                    ticket.reference,
                    _("Status updated: %(subject)s") % {"subject": ticket.subject},
                ),
                template="escalated/emails/status_changed.html",
                context={
                    "ticket": ticket,
                    "old_status": old_status,
                    "new_status": new_status,
                },
            )

        NotificationService._fire_webhook("ticket.status_changed", {
            "ticket_id": ticket.pk,
            "reference": ticket.reference,
            "old_status": old_status,
            "new_status": new_status,
        })

    @staticmethod
    def notify_sla_breach(ticket, breach_type):
        """Send notification when an SLA is breached."""
        channels = get_setting("NOTIFICATION_CHANNELS")

        if "email" in channels and ticket.assigned_to:
            agent_email = getattr(ticket.assigned_to, "email", None)
            if agent_email:
                NotificationService._send_email(
                    subject="[SLA BREACH] [%s] %s" % (
                        ticket.reference,
                        _("%(breach_type)s: %(subject)s") % {
                            "breach_type": breach_type,
                            "subject": ticket.subject,
                        },
                    ),
                    template="escalated/emails/sla_breach.html",
                    context={"ticket": ticket, "breach_type": breach_type},
                    recipient=agent_email,
                )

        NotificationService._fire_webhook("sla.breached", {
            "ticket_id": ticket.pk,
            "reference": ticket.reference,
            "breach_type": breach_type,
        })

    @staticmethod
    def notify_ticket_escalated(ticket, reason):
        """Send notification when a ticket is escalated."""
        channels = get_setting("NOTIFICATION_CHANNELS")

        if "email" in channels and ticket.assigned_to:
            agent_email = getattr(ticket.assigned_to, "email", None)
            if agent_email:
                NotificationService._send_email(
                    subject="[ESCALATED] [%s] %s" % (ticket.reference, ticket.subject),
                    template="escalated/emails/escalated.html",
                    context={"ticket": ticket, "reason": reason},
                    recipient=agent_email,
                )

        NotificationService._fire_webhook("ticket.escalated", {
            "ticket_id": ticket.pk,
            "reference": ticket.reference,
            "reason": reason,
        })

    @staticmethod
    def notify_ticket_resolved(ticket):
        """Send notification when a ticket is resolved."""
        channels = get_setting("NOTIFICATION_CHANNELS")

        if "email" in channels:
            requester_email = NotificationService._get_requester_email(ticket)
            if requester_email:
                NotificationService._send_email(
                    subject="[%s] %s" % (
                        ticket.reference,
                        _("Status updated: %(subject)s") % {"subject": ticket.subject},
                    ),
                    template="escalated/emails/resolved.html",
                    context={"ticket": ticket},
                    recipient=requester_email,
                )

        NotificationService._fire_webhook("ticket.resolved", {
            "ticket_id": ticket.pk,
            "reference": ticket.reference,
        })

    # ----- Internal helpers -----

    @staticmethod
    def _notify_followers(ticket, causer, subject, template, context, exclude_user_ids=None):
        """
        Send email notifications to all followers of a ticket.

        Args:
            ticket: The ticket whose followers to notify.
            causer: The user who caused the event (excluded from notifications).
            subject: Email subject line.
            template: Email template name.
            context: Template context dict.
            exclude_user_ids: Additional user IDs to exclude (e.g. assignee).
        """
        exclude_ids = set(exclude_user_ids or [])
        if causer is not None:
            exclude_ids.add(causer.pk)

        try:
            followers = ticket.followers.all()
            for follower in followers:
                if follower.pk in exclude_ids:
                    continue
                follower_email = getattr(follower, "email", None)
                if follower_email:
                    NotificationService._send_email(
                        subject=subject,
                        template=template,
                        context=context,
                        recipient=follower_email,
                    )
        except Exception as e:
            logger.error(f"Failed to notify followers for ticket {ticket.reference}: {e}")

    @staticmethod
    def _get_requester_email(ticket):
        """Extract the email from the ticket's requester (GenericForeignKey)."""
        try:
            requester = ticket.requester
            if requester:
                return getattr(requester, "email", None)
        except Exception:
            pass
        return None

    @staticmethod
    def _send_email(subject, template, context, recipient):
        """Send an HTML email using Django's mail system."""
        if not recipient:
            return

        try:
            html_body = render_to_string(template, context)
            send_mail(
                subject=subject,
                message="",  # Plain text fallback
                from_email=getattr(
                    settings, "DEFAULT_FROM_EMAIL", "support@escalated.dev"
                ),
                recipient_list=[recipient],
                html_message=html_body,
                fail_silently=True,
            )
        except Exception as e:
            logger.error(f"Failed to send email to {recipient}: {e}")

    @staticmethod
    def _fire_webhook(event, payload):
        """POST event data to the configured webhook URL with optional HMAC-SHA256 signing."""
        webhook_url = get_setting("WEBHOOK_URL")
        if not webhook_url:
            return

        try:
            import requests

            body = {"event": event, "data": payload}
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "escalated-django/0.1.0",
            }

            # Add HMAC-SHA256 signature if a webhook secret is configured
            secret = get_setting("WEBHOOK_SECRET") or getattr(
                settings, "ESCALATED_WEBHOOK_SECRET", None
            )
            if secret:
                body_bytes = json.dumps(body, default=str).encode("utf-8")
                signature = hmac.new(
                    secret.encode("utf-8"),
                    body_bytes,
                    hashlib.sha256,
                ).hexdigest()
                headers["X-Escalated-Signature"] = signature

            requests.post(
                webhook_url,
                json=body,
                timeout=10,
                headers=headers,
            )
        except Exception as e:
            logger.error(f"Failed to fire webhook for {event}: {e}")
