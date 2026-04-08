import pytest

from escalated.models import SavedView
from tests.factories import UserFactory


@pytest.mark.django_db
class TestSavedViewModel:
    def test_create_saved_view(self):
        user = UserFactory()
        view = SavedView.objects.create(
            name="My Open Tickets",
            filters={"status": "open", "assigned": "me"},
            user=user,
        )
        assert view.pk is not None
        assert view.name == "My Open Tickets"
        assert view.filters == {"status": "open", "assigned": "me"}
        assert view.user == user

    def test_shared_view(self):
        view = SavedView.objects.create(
            name="All Urgent",
            filters={"priority": "urgent"},
            is_shared=True,
        )
        assert view.is_shared is True
        assert view.user is None

    def test_default_values(self):
        view = SavedView.objects.create(name="Test View")
        assert view.filters == {}
        assert view.is_shared is False
        assert view.is_default is False
        assert view.position == 0
        assert view.icon == ""
        assert view.color == "#6b7280"

    def test_ordering_by_position_and_name(self):
        v3 = SavedView.objects.create(name="C View", position=2)
        v1 = SavedView.objects.create(name="A View", position=0)
        v2 = SavedView.objects.create(name="B View", position=1)

        views = list(SavedView.objects.all())
        assert views == [v1, v2, v3]

    def test_str_representation(self):
        view = SavedView.objects.create(name="My Queue")
        assert str(view) == "My Queue"

    def test_user_can_have_multiple_views(self):
        user = UserFactory()
        SavedView.objects.create(name="View 1", user=user, position=0)
        SavedView.objects.create(name="View 2", user=user, position=1)
        assert SavedView.objects.filter(user=user).count() == 2

    def test_is_default_flag(self):
        user = UserFactory()
        view = SavedView.objects.create(
            name="Default View",
            user=user,
            is_default=True,
        )
        assert view.is_default is True

    def test_icon_and_color(self):
        view = SavedView.objects.create(
            name="Styled",
            icon="inbox",
            color="#ff5722",
        )
        assert view.icon == "inbox"
        assert view.color == "#ff5722"

    def test_filters_jsonfield(self):
        filters = {
            "status": ["open", "in_progress"],
            "priority": "high",
            "department_id": 5,
            "tags": ["bug", "feature"],
        }
        view = SavedView.objects.create(name="Complex", filters=filters)
        view.refresh_from_db()
        assert view.filters == filters

    def test_delete_user_cascades(self):
        user = UserFactory()
        SavedView.objects.create(name="Personal", user=user)
        assert SavedView.objects.filter(user=user).count() == 1

        user.delete()
        assert SavedView.objects.filter(name="Personal").count() == 0

    def test_reorder(self):
        v1 = SavedView.objects.create(name="V1", position=0)
        v2 = SavedView.objects.create(name="V2", position=1)
        v3 = SavedView.objects.create(name="V3", position=2)

        # Reorder: V3, V1, V2
        for pos, pk in enumerate([v3.pk, v1.pk, v2.pk]):
            SavedView.objects.filter(pk=pk).update(position=pos)

        v1.refresh_from_db()
        v2.refresh_from_db()
        v3.refresh_from_db()

        assert v3.position == 0
        assert v1.position == 1
        assert v2.position == 2
