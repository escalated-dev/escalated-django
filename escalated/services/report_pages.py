"""The basic report sub-screens' props, as escalated-laravel builds them.

Laravel's ``Admin\\ReportController`` renders ``Reports/AgentMetrics``,
``Reports/SlaReport`` and ``Reports/CsatReport`` from ``ReportingService``'s
``getAgentPerformance``, ``getSlaComplianceRate``, ``getSlaComplianceByPolicy``,
``getSlaBreachDetails``, ``getCsatAverage``, ``getCsatByAgent`` and
``getCsatOverTime``. Each covers the tickets created (or the ratings given) in
the last ``days`` days. A ticket breached its SLA when either breach flag is set.
"""

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from escalated.models import SatisfactionRating, SlaPolicy, Ticket

BREACHED = Q(sla_first_response_breached=True) | Q(sla_resolution_breached=True)


def _since(days):
    return timezone.now() - timedelta(days=days)


def _name(user):
    if user is None:
        return None
    full = user.get_full_name() if hasattr(user, "get_full_name") else ""
    return full or getattr(user, "username", None) or str(user.pk)


def _iso(value):
    return value.isoformat() if value else None


def _average_hours(tickets, stamp):
    hours = [(getattr(t, stamp) - t.created_at).total_seconds() / 3600 for t in tickets if getattr(t, stamp)]
    return round(sum(hours) / len(hours), 1) if hours else None


def agent_performance(days):
    """Per assignee: tickets, resolved, average first response and resolution hours."""
    tickets = (
        Ticket.objects.filter(created_at__gte=_since(days), assigned_to__isnull=False)
        .select_related("assigned_to")
        .order_by("assigned_to_id", "pk")
    )
    by_agent = {}
    for ticket in tickets:
        by_agent.setdefault(ticket.assigned_to_id, []).append(ticket)

    return [
        {
            "agent_id": agent_id,
            "agent_name": _name(rows[0].assigned_to),
            "total_tickets": len(rows),
            "resolved_tickets": sum(1 for t in rows if t.resolved_at is not None),
            "avg_response_hours": _average_hours(rows, "first_response_at"),
            "avg_resolution_hours": _average_hours(rows, "resolved_at"),
        }
        for agent_id, rows in by_agent.items()
    ]


def agent_metrics(days):
    return {"period_days": days, "agents": agent_performance(days)}


def sla_report(days):
    since = _since(days)
    period = Ticket.objects.filter(created_at__gte=since)

    covered = period.filter(sla_policy__isnull=False)
    total = covered.count()
    compliance = 100.0 if total == 0 else round((total - covered.filter(BREACHED).count()) / total * 100, 1)

    by_policy = []
    for policy in SlaPolicy.objects.filter(is_active=True).order_by("pk"):
        under = period.filter(sla_policy=policy)
        count = under.count()
        breached = under.filter(BREACHED).count()
        by_policy.append({"policy_name": policy.name, "total": count, "met": count - breached, "breached": breached})

    breaches = []
    for ticket in (
        period.filter(BREACHED).select_related("assigned_to", "sla_policy").order_by("-created_at", "-pk")[:100]
    ):
        assignee = ticket.assigned_to
        policy = ticket.sla_policy
        breaches.append(
            {
                "id": ticket.pk,
                "reference": ticket.reference,
                "subject": ticket.subject,
                "assigned_to": ticket.assigned_to_id,
                "sla_policy_id": ticket.sla_policy_id,
                "sla_first_response_breached": ticket.sla_first_response_breached,
                "sla_resolution_breached": ticket.sla_resolution_breached,
                "first_response_at": _iso(ticket.first_response_at),
                "resolved_at": _iso(ticket.resolved_at),
                "created_at": _iso(ticket.created_at),
                "assignee": None
                if assignee is None
                else {"id": assignee.pk, "name": _name(assignee), "email": getattr(assignee, "email", "")},
                "sla_policy": None if policy is None else {"id": policy.pk, "name": policy.name},
            }
        )

    return {
        "period_days": days,
        "compliance_rate": compliance,
        "compliance_by_policy": by_policy,
        "breaches": breaches,
    }


def csat_report(days):
    since = _since(days)
    ratings = list(
        SatisfactionRating.objects.filter(created_at__gte=since)
        .select_related("ticket", "ticket__assigned_to")
        .order_by("created_at", "pk")
    )
    total_tickets = Ticket.objects.filter(created_at__gte=since).count()

    def average(rows):
        return round(sum(r.rating for r in rows) / len(rows), 1) if rows else 0.0

    by_agent = {}
    for rating in ratings:
        if rating.ticket.assigned_to_id is not None:
            by_agent.setdefault(rating.ticket.assigned_to_id, []).append(rating)

    by_date = {}
    for rating in ratings:
        by_date.setdefault(timezone.localtime(rating.created_at).date().isoformat(), []).append(rating)

    return {
        "period_days": days,
        "csat_average": average(ratings),
        "response_rate": round(len(ratings) / total_tickets * 100, 1) if total_tickets else 0,
        "total_ratings": len(ratings),
        "by_agent": [
            {
                "agent_id": agent_id,
                "agent_name": _name(rows[0].ticket.assigned_to),
                "avg_rating": average(rows),
                "total_ratings": len(rows),
            }
            for agent_id, rows in sorted(by_agent.items())
        ],
        "over_time": [{"label": date, "value": average(rows)} for date, rows in sorted(by_date.items())],
    }
