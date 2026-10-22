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

from escalated.models import Reply, SatisfactionRating, SlaPolicy, Ticket

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


def _hours(start, end):
    return (end - start).total_seconds() / 3600


def _day(value):
    return timezone.localtime(value).date().isoformat()


def _tally(values):
    counts = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def _label_rows(counts):
    return [{"label": label, "value": count} for label, count in sorted(counts.items())]


def _rating_average(ratings):
    return round(sum(ratings) / len(ratings), 1) if ratings else 0.0


def overview(days):
    """``Admin/Reports``, the classic overview, as Laravel's ``ReportController::__invoke``.

    Everything reads the tickets created (ratings given, tickets resolved) in
    the last ``days`` days. ``by_status``/``by_priority`` and the CSAT
    ``breakdown`` are maps keyed by value, which is what the screen iterates.
    """
    since = _since(days)
    period = Ticket.objects.filter(created_at__gte=since)

    responded = [
        _hours(created, first)
        for created, first in period.filter(first_response_at__isnull=False).values_list(
            "created_at", "first_response_at"
        )
    ]
    ratings = sorted(SatisfactionRating.objects.filter(created_at__gte=since).values_list("rating", flat=True))

    return {
        "period_days": days,
        "total_tickets": period.count(),
        "resolved_tickets": Ticket.objects.filter(resolved_at__isnull=False, resolved_at__gte=since).count(),
        "avg_first_response_hours": round(sum(responded) / len(responded), 1) if responded else 0.0,
        "sla_breach_count": period.filter(BREACHED).count(),
        "by_status": _tally(period.values_list("status", flat=True)),
        "by_priority": _tally(period.values_list("priority", flat=True)),
        "csat": {
            "average": _rating_average(ratings),
            "total": len(ratings),
            "breakdown": {str(rating): count for rating, count in _tally(ratings).items()},
        },
    }


def dashboard(days):
    """``Reports/Dashboard``, as Laravel's ``ReportController::dashboard``.

    Volume, response and resolution read the tickets created in the period;
    the status and priority breakdowns cover every ticket, as Laravel's
    ``getTicketsByStatus`` and ``getTicketsByPriority`` do. Charts are
    ``{label, value}`` rows.
    """
    since = _since(days)
    period = list(Ticket.objects.filter(created_at__gte=since).order_by("created_at", "pk"))

    covered = [t for t in period if t.sla_policy_id is not None]
    breached = [t for t in covered if t.sla_first_response_breached or t.sla_resolution_breached]
    ratings = list(SatisfactionRating.objects.filter(created_at__gte=since).values_list("rating", flat=True))

    return {
        "period_days": days,
        "volume": _label_rows(_tally(_day(t.created_at) for t in period)),
        "by_status": _label_rows(_tally(Ticket.objects.values_list("status", flat=True))),
        "by_priority": _label_rows(_tally(Ticket.objects.values_list("priority", flat=True))),
        "avg_response_hours": _average_hours(period, "first_response_at") or 0.0,
        "avg_resolution_hours": _average_hours(period, "resolved_at") or 0.0,
        "sla_compliance": 100.0 if not covered else round((len(covered) - len(breached)) / len(covered) * 100, 1),
        "csat_average": _rating_average(ratings),
        "agent_performance": agent_performance(days),
    }


def _percentile(ordered, p):
    """Linear interpolation between closest ranks, as Laravel's ``percentile``."""
    if not ordered:
        return 0.0
    index = p / 100 * (len(ordered) - 1)
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (index - lower) * (ordered[upper] - ordered[lower])


def _agent_window(agent_id, start, end):
    """One agent's figures between ``start`` and ``end``, under the names
    ``Reports/AgentDetail`` reads. ``csat_score`` is None without ratings,
    rather than a zero that reads like a rating."""
    tickets = list(
        Ticket.objects.filter(assigned_to_id=agent_id, created_at__gte=start, created_at__lte=end).order_by(
            "created_at", "pk"
        )
    )
    response = sorted(_hours(t.created_at, t.first_response_at) for t in tickets if t.first_response_at)
    resolution = [_hours(t.created_at, t.resolved_at) for t in tickets if t.resolved_at]
    ratings = list(
        SatisfactionRating.objects.filter(ticket_id__in=[t.pk for t in tickets]).values_list("rating", flat=True)
    )

    # Public replies the agent wrote, and the agent's tickets resolved, per day.
    productivity = {}
    replies = Reply.objects.filter(
        author_id=agent_id,
        is_internal_note=False,
        is_deleted=False,
        created_at__gte=start,
        created_at__lte=end,
    ).values_list("created_at", flat=True)
    for at in replies:
        productivity.setdefault(_day(at), [0, 0])[0] += 1
    resolved = Ticket.objects.filter(assigned_to_id=agent_id, resolved_at__gte=start, resolved_at__lte=end).values_list(
        "resolved_at", flat=True
    )
    for at in resolved:
        productivity.setdefault(_day(at), [0, 0])[1] += 1

    return {
        "total_tickets": len(tickets),
        "resolved_tickets": sum(1 for t in tickets if t.resolved_at is not None),
        "avg_frt": round(sum(response) / len(response), 1) if response else 0.0,
        "avg_resolution": round(sum(resolution) / len(resolution), 1) if resolution else 0.0,
        "csat_score": round(sum(ratings) / len(ratings), 1) if ratings else None,
        "response_percentiles": {f"p{p}": round(_percentile(response, p), 1) for p in (50, 75, 90, 95, 99)},
        "productivity": [
            {"label": day, "value": written + closed, "values": [written, closed]}
            for day, (written, closed) in sorted(productivity.items())
        ],
        "workload": _label_rows(_tally(_day(t.created_at) for t in tickets)),
        "csat_breakdown": [
            {"label": f"{rating} stars", "value": count} for rating, count in sorted(_tally(ratings).items())
        ],
    }


def agent_detail(agent_id, days):
    """``Reports/AgentDetail``: the period against the period of the same length before it.

    These are the props the shared page declares, as escalated-rails, -go,
    -spring, -nestjs and -dotnet send them (escalated-laravel #260 brings
    Laravel to the same shape; its old ``agent_id``/``metrics``/``percentiles``
    are not read by the page).
    """
    from django.contrib.auth import get_user_model

    end = timezone.now()
    start = end - timedelta(days=days)
    current = _agent_window(agent_id, start, end)
    previous = _agent_window(agent_id, start - timedelta(days=days), start)
    user = get_user_model().objects.filter(pk=agent_id).first()

    return {
        "period_days": days,
        "agent": {
            "id": agent_id,
            "name": _name(user),
            "email": getattr(user, "email", None) if user is not None else None,
        },
        **current,
        "prev_total_tickets": previous["total_tickets"],
        "prev_resolved_tickets": previous["resolved_tickets"],
        "prev_avg_frt": previous["avg_frt"],
        "prev_avg_resolution": previous["avg_resolution"],
        "prev_csat_score": previous["csat_score"],
    }
