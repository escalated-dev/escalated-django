from django.db import connection
from django.db.models import Count, Q


class ReportingService:
    def get_ticket_volume_by_date(self, start, end):
        """Get daily ticket creation counts between start and end dates."""
        from escalated.models import Ticket

        # Use database-agnostic date truncation
        if connection.vendor == "sqlite":
            date_expr = "date(created_at)"
        else:
            date_expr = "DATE(created_at)"

        rows = (
            Ticket.objects.filter(created_at__gte=start, created_at__lte=end)
            .extra(select={"day": date_expr})
            .values("day")
            .annotate(count=Count("id"))
            .order_by("day")
        )
        return [{"date": r["day"], "count": r["count"]} for r in rows]

    def get_tickets_by_status(self):
        """Get ticket counts grouped by status."""
        from escalated.models import Ticket

        rows = Ticket.objects.values("status").annotate(count=Count("id")).order_by("status")
        return [{"status": r["status"], "count": r["count"]} for r in rows]

    def get_tickets_by_priority(self):
        """Get ticket counts grouped by priority."""
        from escalated.models import Ticket

        rows = Ticket.objects.values("priority").annotate(count=Count("id")).order_by("priority")
        return [{"priority": r["priority"], "count": r["count"]} for r in rows]

    def get_average_response_time(self, start, end):
        """Get average first response time in hours."""
        from escalated.models import Reply, Ticket

        tickets = Ticket.objects.filter(created_at__gte=start, created_at__lte=end).values_list("id", "created_at")

        total_hours = 0
        count = 0

        for ticket_id, created_at in tickets:
            first_reply = (
                Reply.objects.filter(ticket_id=ticket_id, is_internal_note=False)
                .order_by("created_at")
                .values_list("created_at", flat=True)
                .first()
            )
            if first_reply:
                diff = (first_reply - created_at).total_seconds() / 3600
                total_hours += diff
                count += 1

        return round(total_hours / count, 2) if count > 0 else 0.0

    def get_average_resolution_time(self, start, end):
        """Get average resolution time in hours."""
        from escalated.models import Ticket

        tickets = Ticket.objects.filter(
            created_at__gte=start,
            created_at__lte=end,
            status__in=["resolved", "closed"],
        ).values_list("created_at", "updated_at")

        total_hours = 0
        count = 0

        for created_at, updated_at in tickets:
            diff = (updated_at - created_at).total_seconds() / 3600
            total_hours += diff
            count += 1

        return round(total_hours / count, 2) if count > 0 else 0.0

    def get_agent_performance(self, start, end):
        """Get per-agent performance metrics."""
        from django.contrib.auth import get_user_model

        from escalated.models import Ticket

        User = get_user_model()
        agents = User.objects.filter(
            escalated_assigned_tickets__created_at__gte=start,
            escalated_assigned_tickets__created_at__lte=end,
        ).distinct()

        results = []
        for agent in agents:
            agent_tickets = Ticket.objects.filter(
                assigned_to=agent,
                created_at__gte=start,
                created_at__lte=end,
            )
            total = agent_tickets.count()
            resolved = agent_tickets.filter(status__in=["resolved", "closed"]).count()

            results.append(
                {
                    "agent_id": agent.pk,
                    "agent_name": agent.get_full_name() or agent.username,
                    "total_tickets": total,
                    "resolved_tickets": resolved,
                }
            )

        return results

    def get_sla_compliance_rate(self, start, end):
        """Get SLA compliance rate as a percentage."""
        from escalated.models import Ticket

        tickets = Ticket.objects.filter(
            created_at__gte=start,
            created_at__lte=end,
            sla_policy__isnull=False,
        )
        total = tickets.count()
        if total == 0:
            return 100.0

        breached = tickets.filter(Q(sla_first_response_at__isnull=False) | Q(sla_resolution_at__isnull=False)).count()

        return round(((total - breached) / total) * 100, 1)
