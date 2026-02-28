import pytest

from escalated.mixins import AuditableMixin


class TestAuditableMixin:
    def test_mixin_has_expected_methods(self):
        assert hasattr(AuditableMixin, 'save')
        assert hasattr(AuditableMixin, 'delete')

    def test_mixin_audit_exclude_attribute(self):
        assert hasattr(AuditableMixin, 'audit_exclude')
        assert 'created_at' in AuditableMixin.audit_exclude
        assert 'updated_at' in AuditableMixin.audit_exclude

    def test_mixin_has_request_getter(self):
        assert hasattr(AuditableMixin, '_get_current_request')
        # Should return None when no request thread-local is set
        assert AuditableMixin._get_current_request() is None
