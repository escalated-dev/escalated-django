from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.utils import timezone

from escalated.permissions import is_admin
from escalated.rendering import render_page
from escalated.services.advanced_reporting_service import AdvancedReportingService
from escalated.services.export_service import ExportService
from escalated.services.report_screen_metrics import ReportScreenMetrics


def _parse_period(request):
    from_str = request.GET.get("from")
    to_str = request.GET.get("to")
    try:
        start = timezone.datetime.fromisoformat(from_str) if from_str else None
    except (ValueError, TypeError):
        start = None
    try:
        end = timezone.datetime.fromisoformat(to_str) if to_str else None
    except (ValueError, TypeError):
        end = None
    if start is None:
        start = timezone.now() - timedelta(days=30)
    if end is None:
        end = timezone.now()
    if timezone.is_naive(start):
        start = timezone.make_aware(start)
    if timezone.is_naive(end):
        end = timezone.make_aware(end)
    return start, end


def _get_service(request):
    start, end = _parse_period(request)
    return AdvancedReportingService(start, end), start, end


def _screen(request):
    """The service, the screen-shaped view of it, the period, and its length.

    Inertia passes props by name, and a name the component does not declare is
    not passed at all -- it lands on the root element as an attribute. Every
    view here used to send ``{"data": ..., "filters": ...}``, which no report
    component reads, so all nine screens rendered their defaults: zeroes and
    empty charts, on a 200, which is indistinguishable from a quiet period.
    """
    svc, start, end = _get_service(request)

    return svc, ReportScreenMetrics(svc), start, end, max((end.date() - start.date()).days, 1)


def _forbidden():
    return JsonResponse({"error": "Forbidden"}, status=403)


@login_required
def sla_trends(request):
    if not is_admin(request.user):
        return _forbidden()

    svc, screen, _start, _end, days = _screen(request)
    counts = screen.sla_breach_counts()
    trend = svc.sla_breach_trends()

    return render_page(
        request,
        "Escalated/Admin/Reports/SlaTrends",
        {
            "period_days": days,
            "breach_trend": screen.chart_series(trend, "date", "total_breaches"),
            "breach_by_type_trend": [
                {"label": row["date"], "values": [row["frt_breaches"], row["resolution_breaches"]]} for row in trend
            ],
            "breach_by_department": screen.sla_breach_by_department(),
            "breach_by_priority": screen.sla_breach_by_priority(),
            "at_risk_tickets": screen.at_risk_tickets(),
            "total_breaches": counts["total"],
            "breach_rate": counts["rate"],
            "first_response_breaches": counts["first_response"],
            "resolution_breaches": counts["resolution"],
        },
    )


@login_required
def response_times(request):
    if not is_admin(request.user):
        return _forbidden()

    svc, screen, _start, _end, days = _screen(request)
    summary = screen.frt_summary()

    return render_page(
        request,
        "Escalated/Admin/Reports/ResponseTimes",
        {
            "period_days": days,
            "avg_frt": summary["avg"],
            "median_frt": summary["median"],
            "p90_frt": summary["p90"],
            "pct_under_target": summary["pct_under_target"],
            "target_hours": ReportScreenMetrics.FIRST_RESPONSE_TARGET_HOURS,
            "distribution": screen.distribution_series(svc.frt_distribution()),
            "trend": screen.chart_series(svc.frt_trends(), "date", "avg_hours"),
            "by_agent": screen.agent_time_rows(svc.frt_by_agent()),
            "by_department": screen.frt_by_department(),
            "by_priority": screen.frt_by_priority(),
        },
    )


@login_required
def resolution_times(request):
    if not is_admin(request.user):
        return _forbidden()

    svc, screen, _start, _end, days = _screen(request)
    summary = screen.resolution_summary()

    return render_page(
        request,
        "Escalated/Admin/Reports/ResolutionTimes",
        {
            "period_days": days,
            "avg_resolution": summary["avg"],
            "median_resolution": summary["median"],
            "p90_resolution": summary["p90"],
            "pct_under_target": summary["pct_under_target"],
            "target_hours": ReportScreenMetrics.RESOLUTION_TARGET_HOURS,
            "distribution": screen.distribution_series(svc.resolution_time_distribution()),
            "trend": screen.chart_series(svc.resolution_time_trends(), "date", "avg_hours"),
            "by_agent": screen.agent_time_rows(screen.resolution_by_agent()),
            "by_department": screen.resolution_by_department(),
            "by_channel": screen.resolution_by_channel(),
        },
    )


@login_required
def agent_ranking(request):
    if not is_admin(request.user):
        return _forbidden()

    svc, screen, _start, _end, days = _screen(request)

    return render_page(
        request,
        "Escalated/Admin/Reports/AgentRanking",
        {
            "period_days": days,
            "agents": screen.agent_ranking_rows(svc.agent_performance_ranking()),
        },
    )


@login_required
def cohorts(request):
    if not is_admin(request.user):
        return _forbidden()

    svc, screen, _start, _end, days = _screen(request)

    # The screen shows every dimension at once, in tabs. This served one at a
    # time, chosen by a query parameter the screen does not send.
    return render_page(
        request,
        "Escalated/Admin/Reports/Cohorts",
        {
            "period_days": days,
            "by_tag": screen.cohort_rows(svc.cohort_analysis("tag")),
            "by_department": screen.cohort_rows(svc.cohort_analysis("department")),
            "by_channel": screen.cohort_rows(svc.cohort_analysis("channel")),
            "by_type": screen.cohort_rows(svc.cohort_analysis("type")),
            "by_priority": screen.cohort_rows(svc.cohort_analysis("priority")),
        },
    )


@login_required
def comparison(request):
    if not is_admin(request.user):
        return _forbidden()

    svc, screen, start, end, days = _screen(request)
    data = svc.period_comparison()
    duration = end - start

    return render_page(
        request,
        "Escalated/Admin/Reports/Comparison",
        {
            "period_days": days,
            "current": screen.comparison_side(data["current"], screen.volume_by_date(start, end)),
            "previous": screen.comparison_side(data["previous"], screen.volume_by_date(start - duration, start)),
        },
    )


# The first-response screen was three paths and the resolution screen two. Both
# are one screen in the frontend; these keep the old links working rather than
# 404 on them.
@login_required
def frt_distribution(request):
    return redirect("escalated:admin_reports_response_times")


@login_required
def frt_trends(request):
    return redirect("escalated:admin_reports_response_times")


@login_required
def frt_by_agent(request):
    return redirect("escalated:admin_reports_response_times")


@login_required
def resolution_distribution(request):
    return redirect("escalated:admin_reports_resolution_times")


@login_required
def resolution_trends(request):
    return redirect("escalated:admin_reports_resolution_times")


@login_required
def cohort(request):
    return redirect("escalated:admin_reports_cohorts")


@login_required
def export(request):
    if not is_admin(request.user):
        return JsonResponse({"error": "Forbidden"}, status=403)
    start, end = _parse_period(request)
    report_type = request.GET.get("report_type")
    fmt = request.GET.get("export_format", "csv")
    dimension = request.GET.get("dimension")
    svc = ExportService(start, end)

    try:
        if dimension:
            content = svc.export_cohort_json(dimension) if fmt == "json" else svc.export_cohort_csv(dimension)
        else:
            content = svc.export_json(report_type) if fmt == "json" else svc.export_csv(report_type)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)

    content_type = "application/json" if fmt == "json" else "text/csv"
    filename = f"{report_type or 'cohort'}_{timezone.now().strftime('%Y%m%d')}.{fmt}"
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
