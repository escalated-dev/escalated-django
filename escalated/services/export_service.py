import csv
import io
import json


class ExportService:
    EXPORTABLE_REPORTS = [
        "sla_breach_trends",
        "frt_distribution",
        "frt_trends",
        "frt_by_agent",
        "resolution_time_distribution",
        "resolution_time_trends",
        "agent_performance_ranking",
        "period_comparison",
    ]

    def __init__(self, start, end):
        from escalated.services.advanced_reporting_service import AdvancedReportingService

        self.reporting = AdvancedReportingService(start, end)

    def export_csv(self, report_type):
        self._validate_report_type(report_type)
        data = getattr(self.reporting, report_type)()
        rows = self._flatten_for_csv(data, report_type)
        return self._generate_csv(rows)

    def export_json(self, report_type):
        self._validate_report_type(report_type)
        data = getattr(self.reporting, report_type)()
        return json.dumps(data, indent=2, default=str)

    def export_cohort_csv(self, dimension):
        data = self.reporting.cohort_analysis(dimension)
        rows = self._flatten_for_csv(data, "cohort")
        return self._generate_csv(rows)

    def export_cohort_json(self, dimension):
        data = self.reporting.cohort_analysis(dimension)
        return json.dumps(data, indent=2, default=str)

    def _validate_report_type(self, report_type):
        if report_type not in self.EXPORTABLE_REPORTS:
            raise ValueError(f"Unknown report type: {report_type}")

    def _flatten_for_csv(self, data, report_type):
        if isinstance(data, list):
            return [self._flatten_dict(row) for row in data]
        if isinstance(data, dict):
            if report_type == "period_comparison":
                current = self._flatten_dict(data.get("current", {}), "current")
                previous = self._flatten_dict(data.get("previous", {}), "previous")
                changes = self._flatten_dict(data.get("changes", {}), "change")
                merged = {**current, **previous, **changes}
                return [merged]
            if "stats" in data:
                stats = self._flatten_dict(data.get("stats", {}))
                pcts = self._flatten_dict(data.get("percentiles", {}))
                return [{**stats, **pcts}]
            return [self._flatten_dict(data)]
        return []

    def _flatten_dict(self, d, prefix=None):
        result = {}
        if not isinstance(d, dict):
            return result
        for key, value in d.items():
            full_key = f"{prefix}_{key}" if prefix else str(key)
            if isinstance(value, dict):
                result.update(self._flatten_dict(value, full_key))
            else:
                result[full_key] = value
        return result

    def _generate_csv(self, rows):
        if not rows:
            return ""
        output = io.StringIO()
        headers = list(dict.fromkeys(k for row in rows for k in row.keys()))
        writer = csv.DictWriter(output, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        return output.getvalue()
