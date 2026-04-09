import math
from datetime import timedelta

from django.db.models import Avg, Q
from django.utils import timezone


class AdvancedReportingService:
    def __init__(self, start, end):
        from escalated.models import Ticket

        self.start = start
        self.end = end
        self.tickets = Ticket.objects.filter(created_at__gte=start, created_at__lte=end)

    # ── SLA breach trends ──────────────────────────────────────────────

    def sla_breach_trends(self):
        from escalated.models import Ticket

        result = []
        for date in self._date_series():
            day_start = timezone.make_aware(timezone.datetime.combine(date, timezone.datetime.min.time()))
            day_end = day_start + timedelta(days=1)
            day_tickets = Ticket.objects.filter(created_at__lte=day_end)
            result.append(
                {
                    "date": date.isoformat(),
                    "frt_breaches": day_tickets.filter(
                        sla_first_response_breached=True,
                        first_response_at__isnull=True,
                        first_response_due_at__gte=day_start,
                        first_response_due_at__lt=day_end,
                    ).count(),
                    "resolution_breaches": day_tickets.filter(
                        sla_resolution_breached=True,
                        resolved_at__isnull=True,
                        resolution_due_at__gte=day_start,
                        resolution_due_at__lt=day_end,
                    ).count(),
                    "total_breaches": day_tickets.filter(
                        Q(sla_first_response_breached=True) | Q(sla_resolution_breached=True),
                        updated_at__gte=day_start,
                        updated_at__lt=day_end,
                    ).count(),
                }
            )
        return result

    # ── FRT distribution ───────────────────────────────────────────────

    def frt_distribution(self):
        values = self._frt_values()
        return self._build_distribution(values, "hours")

    # ── FRT trends ─────────────────────────────────────────────────────

    def frt_trends(self):
        from escalated.models import Ticket

        result = []
        for date in self._date_series():
            day_start = timezone.make_aware(timezone.datetime.combine(date, timezone.datetime.min.time()))
            day_end = day_start + timedelta(days=1)
            day_tickets = Ticket.objects.filter(
                first_response_at__gte=day_start,
                first_response_at__lt=day_end,
            ).exclude(first_response_at__isnull=True)
            frts = [(t.first_response_at - t.created_at).total_seconds() / 3600 for t in day_tickets]
            result.append(
                {
                    "date": date.isoformat(),
                    "avg_hours": round(sum(frts) / len(frts), 2) if frts else None,
                    "count": len(frts),
                    "percentiles": self._percentiles(frts) if frts else {},
                }
            )
        return result

    # ── FRT by agent ───────────────────────────────────────────────────

    def frt_by_agent(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        tickets = self.tickets.exclude(first_response_at__isnull=True).exclude(assigned_to__isnull=True)
        grouped = {}
        for t in tickets:
            frt = (t.first_response_at - t.created_at).total_seconds() / 3600
            grouped.setdefault(t.assigned_to_id, []).append(frt)

        result = []
        for agent_id, frts in grouped.items():
            try:
                agent = User.objects.get(pk=agent_id)
            except User.DoesNotExist:
                continue
            result.append(
                {
                    "agent_id": agent_id,
                    "agent_name": getattr(agent, "name", agent.email if hasattr(agent, "email") else str(agent)),
                    "avg_hours": round(sum(frts) / len(frts), 2),
                    "count": len(frts),
                    "percentiles": self._percentiles(frts),
                }
            )
        return sorted(result, key=lambda x: x["avg_hours"])

    # ── Resolution time distribution ───────────────────────────────────

    def resolution_time_distribution(self):
        tickets = self.tickets.exclude(resolved_at__isnull=True)
        values = [(t.resolved_at - t.created_at).total_seconds() / 3600 for t in tickets]
        return self._build_distribution(values, "hours")

    # ── Resolution time trends ─────────────────────────────────────────

    def resolution_time_trends(self):
        from escalated.models import Ticket

        result = []
        for date in self._date_series():
            day_start = timezone.make_aware(timezone.datetime.combine(date, timezone.datetime.min.time()))
            day_end = day_start + timedelta(days=1)
            day_tickets = Ticket.objects.filter(resolved_at__gte=day_start, resolved_at__lt=day_end).exclude(
                resolved_at__isnull=True
            )
            times = [(t.resolved_at - t.created_at).total_seconds() / 3600 for t in day_tickets]
            result.append(
                {
                    "date": date.isoformat(),
                    "avg_hours": round(sum(times) / len(times), 2) if times else None,
                    "count": len(times),
                    "percentiles": self._percentiles(times) if times else {},
                }
            )
        return result

    # ── Agent performance ranking ──────────────────────────────────────

    def agent_performance_ranking(self):
        from django.contrib.auth import get_user_model

        from escalated.models import SatisfactionRating

        User = get_user_model()
        agent_ids = self.tickets.exclude(assigned_to__isnull=True).values_list("assigned_to_id", flat=True).distinct()
        rankings = []
        for agent_id in agent_ids:
            try:
                agent = User.objects.get(pk=agent_id)
            except User.DoesNotExist:
                continue
            agent_tickets = self.tickets.filter(assigned_to_id=agent_id)
            resolved = agent_tickets.exclude(resolved_at__isnull=True)
            total = agent_tickets.count()
            res_count = resolved.count()
            resolution_rate = round(res_count / total * 100, 1) if total > 0 else 0

            frts = [
                (t.first_response_at - t.created_at).total_seconds() / 3600
                for t in agent_tickets.exclude(first_response_at__isnull=True)
            ]
            res_times = [(t.resolved_at - t.created_at).total_seconds() / 3600 for t in resolved]
            avg_frt = round(sum(frts) / len(frts), 2) if frts else None
            avg_res = round(sum(res_times) / len(res_times), 2) if res_times else None

            csat_qs = SatisfactionRating.objects.filter(
                ticket__assigned_to_id=agent_id,
                created_at__gte=self.start,
                created_at__lte=self.end,
            )
            avg_csat = None
            if csat_qs.exists():
                avg_csat = round(csat_qs.aggregate(avg=Avg("rating"))["avg"], 2)

            composite = self._composite_score(resolution_rate, avg_frt, avg_res, avg_csat)
            rankings.append(
                {
                    "agent_id": agent_id,
                    "agent_name": getattr(agent, "name", str(agent)),
                    "total_tickets": total,
                    "resolved_count": res_count,
                    "resolution_rate": resolution_rate,
                    "avg_frt_hours": avg_frt,
                    "avg_resolution_hours": avg_res,
                    "avg_csat": avg_csat,
                    "composite_score": composite,
                }
            )
        return sorted(rankings, key=lambda x: -(x["composite_score"] or 0))

    # ── Cohort analysis ────────────────────────────────────────────────

    def cohort_analysis(self, dimension):
        if dimension == "tag":
            return self._cohort_by_tag()
        elif dimension == "department":
            return self._cohort_by_department()
        elif dimension == "channel":
            return self._cohort_by_channel()
        elif dimension == "type":
            return self._cohort_by_type()
        return {"error": f"Unknown dimension: {dimension}"}

    # ── Period comparison ──────────────────────────────────────────────

    def period_comparison(self):
        duration = self.end - self.start
        prev_start = self.start - duration
        prev_end = self.start
        current = self._period_stats(self.start, self.end)
        previous = self._period_stats(prev_start, prev_end)
        return {
            "current": current,
            "previous": previous,
            "changes": self._calculate_changes(current, previous),
        }

    # ── Private helpers ────────────────────────────────────────────────

    def _date_series(self):
        days = min((self.end.date() - self.start.date()).days + 1, 90)
        return [self.start.date() + timedelta(days=i) for i in range(max(days, 1))]

    def _frt_values(self):
        tickets = self.tickets.exclude(first_response_at__isnull=True)
        return [round((t.first_response_at - t.created_at).total_seconds() / 3600, 2) for t in tickets]

    def _percentiles(self, values):
        if not values:
            return {}
        sorted_vals = sorted(values)
        return {
            "p50": self._pct(sorted_vals, 50),
            "p75": self._pct(sorted_vals, 75),
            "p90": self._pct(sorted_vals, 90),
            "p95": self._pct(sorted_vals, 95),
            "p99": self._pct(sorted_vals, 99),
        }

    def _pct(self, sorted_vals, p):
        if len(sorted_vals) == 1:
            return round(sorted_vals[0], 2)
        k = p / 100 * (len(sorted_vals) - 1)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return round(sorted_vals[f], 2)
        return round(sorted_vals[f] + (k - f) * (sorted_vals[c] - sorted_vals[f]), 2)

    def _build_distribution(self, values, unit):
        if not values:
            return {"buckets": [], "stats": {}}
        sorted_vals = sorted(values)
        max_val = sorted_vals[-1]
        bucket_size = max(math.ceil(max_val / 10), 1)
        buckets = []
        for start in range(0, math.ceil(max_val) + 1, bucket_size):
            end = start + bucket_size
            count = sum(1 for v in sorted_vals if start <= v < end)
            if count > 0:
                buckets.append({"range": f"{start}-{end}", "count": count})
        return {
            "buckets": buckets,
            "stats": {
                "min": sorted_vals[0],
                "max": sorted_vals[-1],
                "avg": round(sum(sorted_vals) / len(sorted_vals), 2),
                "median": self._pct(sorted_vals, 50),
                "count": len(sorted_vals),
                "unit": unit,
            },
            "percentiles": self._percentiles(sorted_vals),
        }

    def _composite_score(self, resolution_rate, avg_frt, avg_resolution, avg_csat):
        score = 0.0
        weights = 0.0
        if resolution_rate is not None:
            score += (resolution_rate / 100) * 30
            weights += 30
        if avg_frt and avg_frt > 0:
            score += max(1.0 - avg_frt / 24.0, 0) * 25
            weights += 25
        if avg_resolution and avg_resolution > 0:
            score += max(1.0 - avg_resolution / 72.0, 0) * 25
            weights += 25
        if avg_csat is not None:
            score += (avg_csat / 5.0) * 20
            weights += 20
        if weights == 0:
            return 0
        return round((score / weights) * 100, 1)

    def _cohort_by_tag(self):
        from escalated.models import Tag

        return [self._build_cohort(tag.name, self.tickets.filter(tags=tag)) for tag in Tag.objects.all()]

    def _cohort_by_department(self):
        from escalated.models import Department

        return [
            self._build_cohort(dept.name, self.tickets.filter(department=dept)) for dept in Department.objects.all()
        ]

    def _cohort_by_channel(self):
        channels = self.tickets.values_list("channel", flat=True).distinct()
        return [self._build_cohort(ch, self.tickets.filter(channel=ch)) for ch in channels if ch]

    def _cohort_by_type(self):
        types = self.tickets.values_list("ticket_type", flat=True).distinct()
        return [self._build_cohort(t, self.tickets.filter(ticket_type=t)) for t in types if t]

    def _build_cohort(self, name, scope):
        resolved = scope.exclude(resolved_at__isnull=True)
        total = scope.count()
        res_count = resolved.count()
        res_times = [(t.resolved_at - t.created_at).total_seconds() / 3600 for t in resolved]
        frts = [
            (t.first_response_at - t.created_at).total_seconds() / 3600
            for t in scope.exclude(first_response_at__isnull=True)
        ]
        return {
            "name": name,
            "total": total,
            "resolved": res_count,
            "resolution_rate": round(res_count / total * 100, 1) if total > 0 else 0,
            "avg_resolution_hours": round(sum(res_times) / len(res_times), 2) if res_times else None,
            "avg_frt_hours": round(sum(frts) / len(frts), 2) if frts else None,
            "percentiles": {
                "resolution": self._percentiles(res_times) if res_times else {},
                "frt": self._percentiles(frts) if frts else {},
            },
        }

    def _period_stats(self, start, end):
        from escalated.models import Ticket

        tickets = Ticket.objects.filter(created_at__gte=start, created_at__lte=end)
        resolved = tickets.exclude(resolved_at__isnull=True)
        total = tickets.count()
        res_count = resolved.count()
        res_times = [(t.resolved_at - t.created_at).total_seconds() / 3600 for t in resolved]
        frts = [
            (t.first_response_at - t.created_at).total_seconds() / 3600
            for t in tickets.exclude(first_response_at__isnull=True)
        ]
        return {
            "total_created": total,
            "total_resolved": res_count,
            "resolution_rate": round(res_count / total * 100, 1) if total > 0 else 0,
            "avg_frt_hours": round(sum(frts) / len(frts), 2) if frts else None,
            "avg_resolution_hours": round(sum(res_times) / len(res_times), 2) if res_times else None,
            "sla_breaches": tickets.filter(
                Q(sla_first_response_breached=True) | Q(sla_resolution_breached=True)
            ).count(),
            "percentiles": {
                "resolution": self._percentiles(res_times) if res_times else {},
                "frt": self._percentiles(frts) if frts else {},
            },
        }

    def _calculate_changes(self, current, previous):
        changes = {}
        for key in [
            "total_created",
            "total_resolved",
            "resolution_rate",
            "avg_frt_hours",
            "avg_resolution_hours",
            "sla_breaches",
        ]:
            cur = float(current.get(key) or 0)
            prev = float(previous.get(key) or 0)
            if prev == 0:
                changes[key] = 100.0 if cur > 0 else 0.0
            else:
                changes[key] = round((cur - prev) / prev * 100, 1)
        return changes
