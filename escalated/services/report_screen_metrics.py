"""The figures the report screens read, in the shape they read them.

``AdvancedReportingService`` answers the API, where a report is a nested object
-- a distribution with its buckets, stats and percentiles inside it. The screens
read something flatter and differently named: a list of ``{label, value}`` per
chart, four headline numbers per screen.

Keeping that here rather than in the views means the mapping is tested where the
data is, and keeps the service itself to one job.
"""

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone


class ReportScreenMetrics:
    """Wraps an ``AdvancedReportingService`` and answers in the screens' terms."""

    # What the two time screens measure "on target" against. They show the share
    # met inside it, so it has to be stated somewhere.
    FIRST_RESPONSE_TARGET_HOURS = 4
    RESOLUTION_TARGET_HOURS = 24

    def __init__(self, service):
        self.service = service
        self.tickets = service.tickets
        self.start = service.start
        self.end = service.end

    # -- headline figures ------------------------------------------------

    def frt_summary(self):
        """Average, median, P90 and the share answered inside target.

        The distribution and the trend are the body of the first-response
        screen; these are the four tiles above them, and without them it renders
        zeroes over a chart that is plainly not describing zero.
        """
        return self._summarise(self._hours("first_response_at"), self.FIRST_RESPONSE_TARGET_HOURS)

    def resolution_summary(self):
        return self._summarise(self._hours("resolved_at"), self.RESOLUTION_TARGET_HOURS)

    def sla_breach_counts(self):
        """Counts for the SLA screen, over the same window as its trends."""
        total = self.tickets.count()
        breached = self.tickets.filter(Q(sla_first_response_breached=True) | Q(sla_resolution_breached=True)).count()

        return {
            "total": breached,
            "rate": round(breached / total * 100, 1) if total else 0.0,
            "first_response": self.tickets.filter(sla_first_response_breached=True).count(),
            "resolution": self.tickets.filter(sla_resolution_breached=True).count(),
        }

    # -- charts ----------------------------------------------------------

    def frt_by_department(self):
        return self._average_hours_by("department__name", "first_response_at")

    def frt_by_priority(self):
        return self._average_hours_by("priority", "first_response_at")

    def resolution_by_department(self):
        return self._average_hours_by("department__name", "resolved_at")

    def resolution_by_channel(self):
        return self._average_hours_by("channel", "resolved_at")

    def sla_breach_by_department(self):
        return self._counts_by("department__name", self._breached())

    def sla_breach_by_priority(self):
        return self._counts_by("priority", self._breached())

    def volume_by_date(self, start, end):
        """Tickets raised per day over an arbitrary window.

        The comparison screen charts both of its periods, and only one of them
        is the window this service was built around.
        """
        from escalated.models import Ticket

        days = min((end.date() - start.date()).days + 1, 90)

        series = []
        for offset in range(max(days, 1)):
            day = start.date() + timedelta(days=offset)
            series.append(
                {
                    "label": day.isoformat(),
                    "value": Ticket.objects.filter(created_at__date=day).count(),
                }
            )

        return series

    # -- lists -----------------------------------------------------------

    def at_risk_tickets(self, within_hours=8, limit=50):
        """Open tickets whose SLA is close but not yet missed, soonest first.

        The screen sorts them into bands by ``hours_remaining``.
        """
        now = timezone.now()
        deadline = now + timedelta(hours=within_hours)

        tickets = (
            self.tickets.model.objects.filter(
                resolved_at__isnull=True,
                resolution_due_at__gte=now,
                resolution_due_at__lte=deadline,
            )
            .exclude(sla_resolution_breached=True)
            .order_by("resolution_due_at")[:limit]
        )

        return [
            {
                "id": ticket.id,
                "reference": ticket.reference,
                "subject": ticket.subject,
                "priority": ticket.priority,
                "hours_remaining": round((ticket.resolution_due_at - now).total_seconds() / 3600, 1),
            }
            for ticket in tickets
        ]

    def resolution_by_agent(self):
        """Resolution time per agent, the same shape as the service's FRT one."""
        rows = {}

        for ticket in self.tickets.exclude(resolved_at__isnull=True).exclude(assigned_to__isnull=True):
            hours = (ticket.resolved_at - ticket.created_at).total_seconds() / 3600
            rows.setdefault(ticket.assigned_to_id, {"agent": ticket.assigned_to, "hours": []})["hours"].append(hours)

        out = []
        for agent_id, row in rows.items():
            hours = sorted(row["hours"])
            out.append(
                {
                    "agent_id": agent_id,
                    "agent_name": getattr(row["agent"], "name", None) or str(row["agent"]),
                    "avg_hours": round(sum(hours) / len(hours), 2),
                    "count": len(hours),
                    "percentiles": self.service._percentiles(hours),
                }
            )

        return sorted(out, key=lambda row: row["avg_hours"])

    # -- reshaping what the service already returns ------------------------

    @staticmethod
    def chart_series(rows, label_key, value_key):
        """Every chart on these screens reads ``{label, value}``."""
        return [{"label": row[label_key], "value": row.get(value_key) or 0} for row in rows]

    @staticmethod
    def distribution_series(distribution):
        return [{"label": b["range"], "value": b["count"]} for b in distribution.get("buckets", [])]

    @staticmethod
    def agent_time_rows(rows):
        """The agent table on the time screens sorts on these four keys."""
        return [
            {
                "agent_id": row["agent_id"],
                "agent_name": row["agent_name"],
                "count": row["count"],
                "avg": row["avg_hours"],
                "median": (row.get("percentiles") or {}).get("p50", 0),
                "p90": (row.get("percentiles") or {}).get("p90", 0),
            }
            for row in rows
        ]

    @staticmethod
    def cohort_rows(rows):
        if not isinstance(rows, list):
            return []

        return [
            {
                "name": row["name"],
                "volume": row["total"],
                "avg_resolution": row.get("avg_resolution_hours") or 0,
                "breach_rate": row.get("breach_rate") or 0,
                "csat": row.get("csat") or 0,
            }
            for row in rows
        ]

    @staticmethod
    def comparison_side(stats, volume_trend):
        return {
            "total_tickets": stats["total_created"],
            "resolved_tickets": stats["total_resolved"],
            "avg_frt": stats.get("avg_frt_hours") or 0,
            "avg_resolution": stats.get("avg_resolution_hours") or 0,
            "sla_compliance": stats["resolution_rate"],
            "csat": stats.get("csat") or 0,
            "breach_count": stats["sla_breaches"],
            "volume_trend": volume_trend,
        }

    @staticmethod
    def agent_ranking_rows(rows):
        return [
            {
                "agent_id": row["agent_id"],
                "agent_name": row["agent_name"],
                "volume": row["total_tickets"],
                "resolution_rate": row["resolution_rate"],
                "avg_frt": row["avg_frt_hours"],
                "avg_resolution": row["avg_resolution_hours"],
                "csat": row["avg_csat"],
                "composite_score": row["composite_score"],
            }
            for row in rows
        ]

    # -- internals -------------------------------------------------------

    def _breached(self):
        return self.tickets.filter(Q(sla_first_response_breached=True) | Q(sla_resolution_breached=True))

    def _hours(self, stamp):
        return [
            (getattr(t, stamp) - t.created_at).total_seconds() / 3600
            for t in self.tickets.exclude(**{f"{stamp}__isnull": True})
        ]

    def _summarise(self, values, target_hours):
        if not values:
            return {"avg": 0, "median": 0, "p90": 0, "pct_under_target": 0}

        ordered = sorted(values)
        within = sum(1 for value in ordered if value <= target_hours)

        return {
            "avg": round(sum(ordered) / len(ordered), 2),
            "median": self.service._pct(ordered, 50),
            "p90": self.service._pct(ordered, 90),
            "pct_under_target": round(within / len(ordered) * 100, 1),
        }

    def _average_hours_by(self, field, stamp):
        grouped = {}

        for ticket in self.tickets.exclude(**{f"{stamp}__isnull": True}):
            key = self._label_for(ticket, field)
            hours = (getattr(ticket, stamp) - ticket.created_at).total_seconds() / 3600
            grouped.setdefault(key, []).append(hours)

        rows = [{"label": label, "value": round(sum(hours) / len(hours), 2)} for label, hours in grouped.items()]

        return sorted(rows, key=lambda row: -row["value"])

    def _counts_by(self, field, scope):
        grouped = {}

        for ticket in scope:
            key = self._label_for(ticket, field)
            grouped[key] = grouped.get(key, 0) + 1

        rows = [{"label": label, "value": count} for label, count in grouped.items()]

        return sorted(rows, key=lambda row: -row["value"])

    @staticmethod
    def _label_for(ticket, field):
        if field == "department__name":
            return ticket.department.name if ticket.department_id else "Unassigned"

        return str(getattr(ticket, field, None) or "unknown")
