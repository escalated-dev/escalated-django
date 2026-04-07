from django.contrib.contenttypes.models import ContentType


class AuditableMixin:
    """Mixin that auto-logs create/update/delete to AuditLog."""

    audit_exclude = ["updated_at", "created_at"]

    def save(self, *args, **kwargs):
        from escalated.models import AuditLog

        is_new = self._state.adding
        old_values = {}
        new_values = {}

        if not is_new:
            try:
                old_instance = type(self).objects.get(pk=self.pk)
                for field in self._meta.fields:
                    name = field.name
                    if name in self.audit_exclude:
                        continue
                    old_val = getattr(old_instance, name)
                    new_val = getattr(self, name)
                    if old_val != new_val:
                        old_values[name] = str(old_val) if old_val is not None else None
                        new_values[name] = str(new_val) if new_val is not None else None
            except type(self).DoesNotExist:
                pass

        super().save(*args, **kwargs)

        request = self._get_current_request()
        ct = ContentType.objects.get_for_model(self)

        if is_new:
            attrs = {}
            for field in self._meta.fields:
                name = field.name
                if name in self.audit_exclude:
                    continue
                val = getattr(self, name)
                if val is not None:
                    attrs[name] = str(val)
            AuditLog.objects.create(
                user=request.user if request and request.user.is_authenticated else None,
                action="created",
                auditable_content_type=ct,
                auditable_object_id=self.pk,
                new_values=attrs or None,
                ip_address=request.META.get("REMOTE_ADDR") if request else None,
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:500] if request else None,
            )
        elif new_values:
            AuditLog.objects.create(
                user=request.user if request and request.user.is_authenticated else None,
                action="updated",
                auditable_content_type=ct,
                auditable_object_id=self.pk,
                old_values=old_values or None,
                new_values=new_values or None,
                ip_address=request.META.get("REMOTE_ADDR") if request else None,
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:500] if request else None,
            )

    def delete(self, *args, **kwargs):
        from escalated.models import AuditLog

        request = self._get_current_request()
        ct = ContentType.objects.get_for_model(self)
        attrs = {}
        for field in self._meta.fields:
            name = field.name
            if name in self.audit_exclude:
                continue
            val = getattr(self, name)
            if val is not None:
                attrs[name] = str(val)

        result = super().delete(*args, **kwargs)

        AuditLog.objects.create(
            user=request.user if request and request.user.is_authenticated else None,
            action="deleted",
            auditable_content_type=ct,
            auditable_object_id=self.pk,
            old_values=attrs or None,
            ip_address=request.META.get("REMOTE_ADDR") if request else None,
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:500] if request else None,
        )
        return result

    @staticmethod
    def _get_current_request():
        try:
            import threading

            from django.middleware.common import CommonMiddleware  # noqa: F401

            # Fall back to None if no request middleware is available
            return getattr(threading.current_thread(), "_escalated_request", None)
        except Exception:
            return None
