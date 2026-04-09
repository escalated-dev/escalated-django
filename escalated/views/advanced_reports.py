from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.utils import timezone

from escalated.permissions import is_admin
from escalated.rendering import render_page
from escalated.services.advanced_reporting_service import AdvancedReportingService
from escalated.services.export_service import ExportService


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


@login_required
def sla_trends(request):
    if not is_admin(request.user):
        return JsonResponse({"error": "Forbidden"}, status=403)
    svc, start, end = _get_service(request)
    return render_page(
        request,
        "Escalated/Admin/Reports/SlaTrends",
        {"data": svc.sla_breach_trends(), "filters": {"from": start.isoformat(), "to": end.isoformat()}},
    )


@login_required
def frt_distribution(request):
    if not is_admin(request.user):
        return JsonResponse({"error": "Forbidden"}, status=403)
    svc, start, end = _get_service(request)
    return render_page(
        request,
        "Escalated/Admin/Reports/FrtDistribution",
        {"data": svc.frt_distribution(), "filters": {"from": start.isoformat(), "to": end.isoformat()}},
    )


@login_required
def frt_trends(request):
    if not is_admin(request.user):
        return JsonResponse({"error": "Forbidden"}, status=403)
    svc, start, end = _get_service(request)
    return render_page(
        request,
        "Escalated/Admin/Reports/FrtTrends",
        {"data": svc.frt_trends(), "filters": {"from": start.isoformat(), "to": end.isoformat()}},
    )


@login_required
def frt_by_agent(request):
    if not is_admin(request.user):
        return JsonResponse({"error": "Forbidden"}, status=403)
    svc, start, end = _get_service(request)
    return render_page(
        request,
        "Escalated/Admin/Reports/FrtByAgent",
        {"data": svc.frt_by_agent(), "filters": {"from": start.isoformat(), "to": end.isoformat()}},
    )


@login_required
def resolution_distribution(request):
    if not is_admin(request.user):
        return JsonResponse({"error": "Forbidden"}, status=403)
    svc, start, end = _get_service(request)
    return render_page(
        request,
        "Escalated/Admin/Reports/ResolutionDistribution",
        {"data": svc.resolution_time_distribution(), "filters": {"from": start.isoformat(), "to": end.isoformat()}},
    )


@login_required
def resolution_trends(request):
    if not is_admin(request.user):
        return JsonResponse({"error": "Forbidden"}, status=403)
    svc, start, end = _get_service(request)
    return render_page(
        request,
        "Escalated/Admin/Reports/ResolutionTrends",
        {"data": svc.resolution_time_trends(), "filters": {"from": start.isoformat(), "to": end.isoformat()}},
    )


@login_required
def agent_ranking(request):
    if not is_admin(request.user):
        return JsonResponse({"error": "Forbidden"}, status=403)
    svc, start, end = _get_service(request)
    return render_page(
        request,
        "Escalated/Admin/Reports/AgentRanking",
        {"data": svc.agent_performance_ranking(), "filters": {"from": start.isoformat(), "to": end.isoformat()}},
    )


@login_required
def cohort(request):
    if not is_admin(request.user):
        return JsonResponse({"error": "Forbidden"}, status=403)
    dimension = request.GET.get("dimension", "department")
    svc, start, end = _get_service(request)
    return render_page(
        request,
        "Escalated/Admin/Reports/Cohort",
        {
            "data": svc.cohort_analysis(dimension),
            "dimension": dimension,
            "filters": {"from": start.isoformat(), "to": end.isoformat()},
        },
    )


@login_required
def comparison(request):
    if not is_admin(request.user):
        return JsonResponse({"error": "Forbidden"}, status=403)
    svc, start, end = _get_service(request)
    return render_page(
        request,
        "Escalated/Admin/Reports/Comparison",
        {"data": svc.period_comparison(), "filters": {"from": start.isoformat(), "to": end.isoformat()}},
    )


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
