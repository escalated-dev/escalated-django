from datetime import timedelta

import pytest
from django.utils import timezone

from escalated.services.advanced_reporting_service import AdvancedReportingService
from escalated.services.export_service import ExportService


@pytest.mark.django_db
class TestAdvancedReportingService:
    def _create_ticket(self, **kwargs):
        from escalated.models import Ticket

        defaults = {
            "subject": "Test ticket",
            "description": "Test description",
            "status": "open",
            "priority": "medium",
        }
        defaults.update(kwargs)
        return Ticket.objects.create(**defaults)

    def setup_method(self):
        self.start = timezone.now() - timedelta(days=30)
        self.end = timezone.now()
        self.service = AdvancedReportingService(self.start, self.end)

    def test_sla_breach_trends_returns_list(self):
        result = self.service.sla_breach_trends()
        assert isinstance(result, list)
        if result:
            assert "date" in result[0]
            assert "total_breaches" in result[0]

    def test_frt_distribution_empty(self):
        result = self.service.frt_distribution()
        assert "buckets" in result
        assert "stats" in result

    def test_frt_trends_returns_list(self):
        result = self.service.frt_trends()
        assert isinstance(result, list)

    def test_frt_by_agent_returns_list(self):
        result = self.service.frt_by_agent()
        assert isinstance(result, list)

    def test_resolution_time_distribution(self):
        result = self.service.resolution_time_distribution()
        assert "buckets" in result

    def test_resolution_time_trends(self):
        result = self.service.resolution_time_trends()
        assert isinstance(result, list)

    def test_agent_performance_ranking(self):
        result = self.service.agent_performance_ranking()
        assert isinstance(result, list)

    def test_cohort_analysis_department(self):
        result = self.service.cohort_analysis("department")
        assert isinstance(result, list)

    def test_cohort_analysis_channel(self):
        result = self.service.cohort_analysis("channel")
        assert isinstance(result, list)

    def test_cohort_analysis_type(self):
        result = self.service.cohort_analysis("type")
        assert isinstance(result, list)

    def test_cohort_analysis_unknown(self):
        result = self.service.cohort_analysis("unknown")
        assert isinstance(result, dict)
        assert "error" in result

    def test_period_comparison(self):
        result = self.service.period_comparison()
        assert "current" in result
        assert "previous" in result
        assert "changes" in result

    def test_percentiles_calculation(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        pcts = self.service._percentiles(values)
        assert "p50" in pcts
        assert "p75" in pcts
        assert "p90" in pcts
        assert "p95" in pcts
        assert "p99" in pcts


@pytest.mark.django_db
class TestExportService:
    def setup_method(self):
        self.start = timezone.now() - timedelta(days=30)
        self.end = timezone.now()
        self.service = ExportService(self.start, self.end)

    def test_export_csv_valid_types(self):
        for report_type in ExportService.EXPORTABLE_REPORTS:
            result = self.service.export_csv(report_type)
            assert isinstance(result, str)

    def test_export_json_valid_types(self):
        for report_type in ExportService.EXPORTABLE_REPORTS:
            result = self.service.export_json(report_type)
            assert isinstance(result, str)

    def test_export_csv_invalid_type(self):
        with pytest.raises(ValueError):
            self.service.export_csv("nonexistent")

    def test_export_json_invalid_type(self):
        with pytest.raises(ValueError):
            self.service.export_json("nonexistent")

    def test_export_cohort_csv(self):
        for dim in ["department", "channel", "type"]:
            result = self.service.export_cohort_csv(dim)
            assert isinstance(result, str)

    def test_export_cohort_json(self):
        for dim in ["department", "channel", "type"]:
            result = self.service.export_cohort_json(dim)
            assert isinstance(result, str)
