from datetime import date

import pytest

from escalated.models import (
    AuditLog,
    Holiday,
    Permission,
    TicketStatus,
)
from tests.factories import (
    AuditLogFactory,
    BusinessScheduleFactory,
    HolidayFactory,
    PermissionFactory,
    RoleFactory,
    TicketStatusFactory,
    UserFactory,
)


@pytest.mark.django_db
class TestTicketStatusModel:
    def test_auto_generates_slug(self):
        status = TicketStatusFactory(label="Waiting on Customer", slug="")
        assert status.slug == "waiting_on_customer"

    def test_default_ordering_by_category_and_position(self):
        s1 = TicketStatusFactory(category="open", position=1, slug="s1")
        s2 = TicketStatusFactory(category="new", position=0, slug="s2")
        s3 = TicketStatusFactory(category="open", position=0, slug="s3")

        statuses = list(TicketStatus.objects.all())
        assert statuses[0] == s2  # new comes before open
        assert statuses[1] == s3  # open, position 0
        assert statuses[2] == s1  # open, position 1

    def test_str_returns_label(self):
        status = TicketStatusFactory(label="In Progress")
        assert str(status) == "In Progress"

    def test_category_choices(self):
        for cat in ["new", "open", "pending", "on_hold", "solved"]:
            s = TicketStatusFactory(category=cat, slug=f"test-{cat}")
            assert s.category == cat

    def test_is_default_field(self):
        s = TicketStatusFactory(is_default=True)
        assert s.is_default is True


@pytest.mark.django_db
class TestBusinessScheduleModel:
    def test_str_returns_name(self):
        schedule = BusinessScheduleFactory(name="Default Hours")
        assert str(schedule) == "Default Hours"

    def test_holidays_relationship(self):
        schedule = BusinessScheduleFactory()
        h1 = HolidayFactory(schedule=schedule, name="Christmas", date=date(2026, 12, 25))
        h2 = HolidayFactory(schedule=schedule, name="New Year", date=date(2027, 1, 1))

        assert schedule.holidays.count() == 2
        assert h1 in schedule.holidays.all()
        assert h2 in schedule.holidays.all()

    def test_holiday_str(self):
        h = HolidayFactory(name="Christmas", date=date(2026, 12, 25))
        assert "Christmas" in str(h)
        assert "2026-12-25" in str(h)

    def test_default_schedule_json(self):
        schedule = BusinessScheduleFactory()
        assert "monday" in schedule.schedule
        assert schedule.schedule["monday"]["start"] == "09:00"

    def test_cascade_delete(self):
        schedule = BusinessScheduleFactory()
        HolidayFactory(schedule=schedule)
        schedule_pk = schedule.pk

        schedule.delete()
        assert not Holiday.objects.filter(schedule_id=schedule_pk).exists()


@pytest.mark.django_db
class TestRolePermissionModels:
    def test_role_auto_generates_slug(self):
        role = RoleFactory(name="Support Agent", slug="")
        assert role.slug == "support_agent"

    def test_role_str_returns_name(self):
        role = RoleFactory(name="Admin")
        assert str(role) == "Admin"

    def test_permission_str_returns_name(self):
        perm = PermissionFactory(name="Create Tickets")
        assert str(perm) == "Create Tickets"

    def test_role_has_permission(self):
        perm = PermissionFactory(slug="tickets-create")
        role = RoleFactory()
        role.permissions.add(perm)

        assert role.has_permission("tickets-create") is True
        assert role.has_permission("nonexistent") is False

    def test_role_users_m2m(self):
        role = RoleFactory()
        user = UserFactory()
        role.users.add(user)

        assert user in role.users.all()
        assert role in user.escalated_roles.all()

    def test_permission_ordering(self):
        p1 = PermissionFactory(group="tickets", name="View", slug="t-view")
        p2 = PermissionFactory(group="admin", name="Manage", slug="a-manage")
        p3 = PermissionFactory(group="tickets", name="Create", slug="t-create")

        perms = list(Permission.objects.all())
        assert perms[0] == p2  # admin group first
        assert perms[1] == p3  # tickets, Create
        assert perms[2] == p1  # tickets, View

    def test_system_role_flag(self):
        role = RoleFactory(is_system=True)
        assert role.is_system is True


@pytest.mark.django_db
class TestAuditLogModel:
    def test_str_representation(self):
        log = AuditLogFactory(action="created")
        assert "created" in str(log)

    def test_ordering_by_created_at_desc(self):
        log1 = AuditLogFactory()
        log2 = AuditLogFactory()

        logs = list(AuditLog.objects.all())
        assert logs[0] == log2
        assert logs[1] == log1

    def test_stores_json_values(self):
        log = AuditLogFactory(
            old_values={"status": "open"},
            new_values={"status": "closed"},
        )
        log.refresh_from_db()
        assert log.old_values == {"status": "open"}
        assert log.new_values == {"status": "closed"}

    def test_user_nullable(self):
        log = AuditLogFactory(user=None)
        assert log.user is None

    def test_ip_address_stored(self):
        log = AuditLogFactory(ip_address="192.168.1.1")
        log.refresh_from_db()
        assert log.ip_address == "192.168.1.1"
