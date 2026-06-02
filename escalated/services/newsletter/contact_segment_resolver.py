"""Resolves a NewsletterList to its set of contact IDs."""

from __future__ import annotations

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

    # op -> ORM lookup suffix. "!=" is handled via .exclude() (Django has no
    # __ne lookup — the previous mapping raised FieldError).
    OP_SUFFIX = {
        "=": "",
        ">": "__gt",
        ">=": "__gte",
        "<": "__lt",
        "<=": "__lte",
        "contains": "__icontains",
    }

    def _apply_filter(self, filter_dict: dict, qs=None):
        qs = qs if qs is not None else Contact.objects.all()
        allowed_fields = {f.name for f in Contact._meta.get_fields()}
        for rule in (filter_dict or {}).get("rules", []):
            field = rule.get("field")
            op = rule.get("op") or "="
            value = rule.get("value")
            if not field:
                continue
            if field.startswith("metadata."):
                key = field.split(".", 1)[1]
                # JSON key lookup — metadata__contains is NOT supported on SQLite
                # and raised NotSupportedError. The key transform works on both.
                qs = qs.filter(**{f"metadata__{key}": value})
                continue
            # Allowlist the field (avoid FieldError on arbitrary input) and op.
            if field not in allowed_fields or (op != "=" and op not in self.OP_SUFFIX and op != "!="):
                continue
            if op == "!=":
                qs = qs.exclude(**{field: value})
                continue
            qs = qs.filter(**{f"{field}{self.OP_SUFFIX.get(op, '')}": value})
        return qs
