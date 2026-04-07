"""
Form-based request validators for Escalated API views.

Each validator parses a JSON request body and returns either
(cleaned_data, None) on success or (None, JsonResponse) on failure,
matching the existing error format.
"""

import json
import re

from django import forms
from django.http import JsonResponse

from escalated.models import Ticket


class BaseValidator(forms.Form):
    """Base class for JSON request validators."""

    @classmethod
    def validate_request(cls, request):
        """
        Parse JSON body, validate, return (cleaned_data, None) or (None, JsonResponse).
        """
        try:
            raw = json.loads(request.body) if request.body else {}
        except (json.JSONDecodeError, ValueError, TypeError):
            return None, JsonResponse({"message": "Invalid JSON."}, status=400)

        if not isinstance(raw, dict):
            return None, JsonResponse({"message": "Invalid JSON."}, status=400)

        form = cls(raw)
        if not form.is_valid():
            errors = {field: msgs[0] if isinstance(msgs, list) else msgs for field, msgs in form.errors.items()}
            return None, JsonResponse(
                {"message": "Validation failed.", "errors": errors},
                status=422,
            )
        return form.cleaned_data, None


class CreateTicketValidator(BaseValidator):
    subject = forms.CharField(max_length=255, required=True)
    description = forms.CharField(required=True)
    priority = forms.ChoiceField(
        choices=Ticket.Priority.choices,
        required=False,
        initial="medium",
    )
    department_id = forms.IntegerField(required=False)
    tags = forms.JSONField(required=False)

    def clean_priority(self):
        return self.cleaned_data.get("priority") or "medium"

    def clean_tags(self):
        tags = self.cleaned_data.get("tags")
        if tags is not None and not isinstance(tags, list):
            raise forms.ValidationError("Must be a list of tag IDs.")
        return tags or []


class UpdateTicketValidator(BaseValidator):
    subject = forms.CharField(max_length=255, required=False)
    description = forms.CharField(required=False)
    priority = forms.ChoiceField(choices=Ticket.Priority.choices, required=False)
    department_id = forms.IntegerField(required=False)


class ReplyToTicketValidator(BaseValidator):
    body = forms.CharField(required=True)
    is_internal_note = forms.BooleanField(required=False, initial=False)

    def clean_is_internal_note(self):
        return self.cleaned_data.get("is_internal_note") or False


class AssignTicketValidator(BaseValidator):
    agent_id = forms.IntegerField(required=True)


class ChangeStatusValidator(BaseValidator):
    status = forms.ChoiceField(choices=Ticket.Status.choices, required=True)


class ChangePriorityValidator(BaseValidator):
    priority = forms.ChoiceField(choices=Ticket.Priority.choices, required=True)


class UpdateTagsValidator(BaseValidator):
    tag_ids = forms.JSONField(required=True)

    def clean_tag_ids(self):
        value = self.cleaned_data.get("tag_ids")
        if not isinstance(value, list):
            raise forms.ValidationError("Must be a list of tag IDs.")
        return value


class BulkActionValidator(BaseValidator):
    ALLOWED_ACTIONS = [
        "change_status",
        "change_priority",
        "assign",
        "add_tags",
        "remove_tags",
        "delete",
    ]

    ticket_ids = forms.JSONField(required=True)
    action = forms.ChoiceField(
        choices=[(a, a) for a in ALLOWED_ACTIONS],
        required=True,
    )
    value = forms.CharField(required=False)

    def clean_ticket_ids(self):
        value = self.cleaned_data.get("ticket_ids")
        if not isinstance(value, list) or len(value) == 0:
            raise forms.ValidationError("Must be a non-empty list of ticket IDs.")
        return value


class StoreDepartmentValidator(BaseValidator):
    name = forms.CharField(max_length=255, required=True)
    description = forms.CharField(required=False)
    is_active = forms.BooleanField(required=False, initial=True)

    def clean_is_active(self):
        return self.cleaned_data.get("is_active", True)


class StoreTagValidator(BaseValidator):
    name = forms.CharField(max_length=100, required=True)
    color = forms.CharField(max_length=7, required=True)

    def clean_color(self):
        color = self.cleaned_data.get("color", "")
        if not re.match(r"^#[0-9a-fA-F]{6}$", color):
            raise forms.ValidationError("Must be a valid hex color (e.g. #ef4444).")
        return color


class StoreCannedResponseValidator(BaseValidator):
    title = forms.CharField(max_length=255, required=True)
    body = forms.CharField(required=True)
    category = forms.CharField(max_length=100, required=False)
    is_shared = forms.BooleanField(required=False, initial=False)

    def clean_is_shared(self):
        return self.cleaned_data.get("is_shared") or False


class StoreMacroValidator(BaseValidator):
    name = forms.CharField(max_length=255, required=True)
    description = forms.CharField(required=False)
    actions = forms.JSONField(required=True)
    is_shared = forms.BooleanField(required=False, initial=False)

    def clean_actions(self):
        value = self.cleaned_data.get("actions")
        if not isinstance(value, list) or len(value) == 0:
            raise forms.ValidationError("Must be a non-empty list of actions.")
        return value

    def clean_is_shared(self):
        return self.cleaned_data.get("is_shared") or False


class StoreSlaPolicyValidator(BaseValidator):
    name = forms.CharField(max_length=255, required=True)
    description = forms.CharField(required=False)
    first_response_hours = forms.JSONField(required=False)
    resolution_hours = forms.JSONField(required=False)
    business_hours_only = forms.BooleanField(required=False, initial=False)
    is_default = forms.BooleanField(required=False, initial=False)

    def clean_first_response_hours(self):
        value = self.cleaned_data.get("first_response_hours")
        if value is not None and not isinstance(value, dict):
            raise forms.ValidationError("Must be a dict of priority to hours.")
        return value or {}

    def clean_resolution_hours(self):
        value = self.cleaned_data.get("resolution_hours")
        if value is not None and not isinstance(value, dict):
            raise forms.ValidationError("Must be a dict of priority to hours.")
        return value or {}

    def clean_business_hours_only(self):
        return self.cleaned_data.get("business_hours_only") or False

    def clean_is_default(self):
        return self.cleaned_data.get("is_default") or False


class StoreEscalationRuleValidator(BaseValidator):
    TRIGGER_TYPES = ["time_based", "condition_based", "sla_breach"]

    trigger_type = forms.ChoiceField(
        choices=[(t, t) for t in TRIGGER_TYPES],
        required=True,
    )
    conditions = forms.JSONField(required=True)
    actions = forms.JSONField(required=True)
    is_active = forms.BooleanField(required=False, initial=True)
    order = forms.IntegerField(required=False, initial=0)

    def clean_conditions(self):
        value = self.cleaned_data.get("conditions")
        if not isinstance(value, list):
            raise forms.ValidationError("Must be a list of conditions.")
        return value

    def clean_actions(self):
        value = self.cleaned_data.get("actions")
        if not isinstance(value, list):
            raise forms.ValidationError("Must be a list of actions.")
        return value

    def clean_is_active(self):
        return self.cleaned_data.get("is_active", True)

    def clean_order(self):
        return self.cleaned_data.get("order") or 0
