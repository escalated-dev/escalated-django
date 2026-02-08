import logging

from django.db.models import Count, Q

from escalated.models import Ticket, Department

logger = logging.getLogger("escalated")


class AssignmentService:
    """
    Handles automatic and manual ticket assignment to agents.
    """

    @staticmethod
    def auto_assign(ticket):
        """
        Automatically assign a ticket to the least-busy agent in the
        ticket's department. Returns the assigned agent or None.
        """
        department = ticket.department
        if not department:
            return None

        agents = department.agents.all()
        if not agents.exists():
            logger.info(
                f"No agents in department '{department.name}' for auto-assign "
                f"on ticket {ticket.reference}"
            )
            return None

        # Find agent with fewest open tickets
        agent = (
            agents.annotate(
                open_ticket_count=Count(
                    "escalated_assigned_tickets",
                    filter=Q(
                        escalated_assigned_tickets__status__in=[
                            Ticket.Status.OPEN,
                            Ticket.Status.IN_PROGRESS,
                            Ticket.Status.WAITING_ON_CUSTOMER,
                            Ticket.Status.WAITING_ON_AGENT,
                            Ticket.Status.ESCALATED,
                            Ticket.Status.REOPENED,
                        ]
                    ),
                )
            )
            .order_by("open_ticket_count")
            .first()
        )

        if agent:
            ticket.assigned_to = agent
            if ticket.status == Ticket.Status.OPEN:
                ticket.status = Ticket.Status.IN_PROGRESS
            ticket.save(update_fields=["assigned_to", "status", "updated_at"])
            logger.info(
                f"Auto-assigned ticket {ticket.reference} to {agent} "
                f"in department '{department.name}'"
            )

        return agent

    @staticmethod
    def reassign(ticket, new_agent, user):
        """
        Reassign a ticket from one agent to another.
        """
        from escalated.drivers import get_driver

        driver = get_driver()
        return driver.assign_ticket(ticket, user, new_agent)

    @staticmethod
    def get_available_agents(department=None):
        """
        Get agents available for assignment, optionally filtered by department.
        """
        if department:
            agents = department.agents.filter(is_active=True)
        else:
            agents = Department.objects.filter(is_active=True).values_list(
                "agents", flat=True
            )
            from django.contrib.auth import get_user_model
            User = get_user_model()
            agents = User.objects.filter(pk__in=agents, is_active=True)

        return agents.annotate(
            open_ticket_count=Count(
                "escalated_assigned_tickets",
                filter=Q(
                    escalated_assigned_tickets__status__in=[
                        Ticket.Status.OPEN,
                        Ticket.Status.IN_PROGRESS,
                        Ticket.Status.WAITING_ON_CUSTOMER,
                        Ticket.Status.WAITING_ON_AGENT,
                    ]
                ),
            )
        ).order_by("open_ticket_count")
