"""Resolves a NewsletterList to its set of contact IDs."""

from __future__ import annotations

from django.db.models import Q

from escalated.models import Contact, NewsletterList, NewsletterListMember


class ContactSegmentResolver:
    def resolve(self, lst: NewsletterList) -> list[int]:
        if lst.kind == "static":
            return list(NewsletterListMember.objects.filter(list_id=lst.id).values_list("contact_id", flat=True))
        return list(self._apply_filter(lst.filter_json or {"rules": []}).values_list("id", flat=True))

    def resolve_sendable(self, lst: NewsletterList) -> list[int]:
        qs = Contact.objects.filter(marketing_opt_out_at__isnull=True)
        if lst.kind == "static":
            qs = qs.filter(
                id__in=NewsletterListMember.objects.filter(list_id=lst.id).values_list("contact_id", flat=True),
            )
        else:
            qs = self._apply_filter(lst.filter_json or {"rules": []}, qs)
        return list(qs.values_list("id", flat=True))

    def count_matches(self, filter_dict: dict) -> int:
        return self._apply_filter(filter_dict).count()

    def _apply_filter(self, filter_dict: dict, qs=None):
        qs = qs if qs is not None else Contact.objects.all()
        for rule in (filter_dict or {}).get("rules", []):
            field = rule.get("field")
            op = rule.get("op") or "="
            value = rule.get("value")
            if not field:
                continue
            if field.startswith("metadata."):
                key = field.split(".", 1)[1]
                qs = qs.filter(metadata__contains={key: value})
                continue
            lookup = self._django_lookup(field, op)
            qs = qs.filter(Q(**{lookup: value}))
        return qs

    def _django_lookup(self, field: str, op: str) -> str:
        ops = {
            "=": "",
            "!=": "__ne",  # Django uses .exclude — simplified for v1
            ">": "__gt",
            ">=": "__gte",
            "<": "__lt",
            "<=": "__lte",
            "contains": "__icontains",
        }
        suffix = ops.get(op, "")
        return f"{field}{suffix}"
