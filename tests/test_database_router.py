"""Escalated on a database of its own.

Django has no per-model connection setting -- routing is the mechanism -- so
``ESCALATED["DATABASE"]`` is wired through ``EscalatedRouter``.

These tests use two separate SQLite databases that share no schema, so a query
resolving the wrong one fails with "no such table" rather than quietly reading
the right rows from the wrong database.
"""

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from escalated.models import Department, Ticket
from escalated.routers import EscalatedRouter


class EscalatedRouterUnconfiguredTests(TestCase):
    """With no database configured the router must have no opinion at all.

    Returning anything other than None here would hijack a project that added
    the router but never set the option.
    """

    def setUp(self):
        self.router = EscalatedRouter()

    def test_has_no_opinion_on_reads(self):
        self.assertIsNone(self.router.db_for_read(Ticket))

    def test_has_no_opinion_on_writes(self):
        self.assertIsNone(self.router.db_for_write(Ticket))

    def test_has_no_opinion_on_migrations(self):
        self.assertIsNone(self.router.allow_migrate("default", "escalated"))
        self.assertIsNone(self.router.allow_migrate("default", "auth"))

    def test_has_no_opinion_on_relations(self):
        self.assertIsNone(self.router.allow_relation(Ticket(), User()))


@override_settings(ESCALATED={"DATABASE": "support"})
class EscalatedRouterConfiguredTests(TestCase):
    def setUp(self):
        self.router = EscalatedRouter()

    def test_routes_escalated_reads_and_writes_to_the_named_database(self):
        self.assertEqual(self.router.db_for_read(Ticket), "support")
        self.assertEqual(self.router.db_for_write(Ticket), "support")
        self.assertEqual(self.router.db_for_read(Department), "support")

    def test_leaves_the_host_user_model_alone(self):
        # The users table belongs to the project. Routing it would send Django
        # looking for auth_user in a database it was never migrated into.
        self.assertIsNone(self.router.db_for_read(User))
        self.assertIsNone(self.router.db_for_write(User))

    def test_keeps_escalated_tables_on_their_own_database(self):
        self.assertTrue(self.router.allow_migrate("support", "escalated"))
        self.assertFalse(self.router.allow_migrate("default", "escalated"))

    def test_keeps_everything_else_off_that_database(self):
        # Without this, the project's own tables would be created on Escalated's
        # database as well -- migrated twice, diverging silently.
        self.assertFalse(self.router.allow_migrate("support", "auth"))
        self.assertIsNone(self.router.allow_migrate("default", "auth"))

    def test_permits_relations_that_cross_the_boundary(self):
        # A ticket's assignee is a host user. Django refuses cross-database
        # relations unless a router says otherwise, and single-object traversal
        # is resolved with a second query, so it works.
        self.assertTrue(self.router.allow_relation(Ticket(), User()))
        self.assertTrue(self.router.allow_relation(User(), Ticket()))

    def test_has_no_opinion_on_two_host_models(self):
        self.assertIsNone(self.router.allow_relation(User(), User()))

    def test_treats_an_empty_database_name_as_unset(self):
        with override_settings(ESCALATED={"DATABASE": ""}):
            self.assertIsNone(self.router.db_for_read(Ticket))
            self.assertIsNone(self.router.allow_migrate("default", "escalated"))


class HostUserForeignKeysTests(TestCase):
    """The constraint that had to go for any of this to be possible.

    Django cannot create a foreign key across databases, so while Escalated's
    keys to the host user table carried database constraints, the setting could
    not work at all -- migrate failed on the first user-referencing table.
    """

    def test_no_escalated_field_constrains_the_host_user_table(self):
        """Sweeps every model in the app, not a hand-picked few.

        A relation added later that constrains the user table would break the
        setting again, and the failure appears at migrate time in someone
        else's project rather than here.
        """
        from django.apps import apps

        offenders = []

        for model in apps.get_app_config("escalated").get_models():
            for field in model._meta.get_fields():
                remote = getattr(field, "remote_field", None)
                if remote is None or getattr(remote, "model", None) is not User:
                    continue

                # A ManyToManyField with an explicit `through` cannot carry
                # db_constraint at all -- Django refuses the combination. The
                # through model is one of ours, and its own foreign key to the
                # user is what crosses the boundary, so it is checked on its own
                # pass through this loop.
                through = getattr(remote, "through", None)
                if through is not None and not through._meta.auto_created:
                    continue

                # ForeignKey/OneToOneField keep db_constraint on the field;
                # ManyToManyField keeps it on remote_field. Checking only the
                # field silently passed every M2M.
                constrained = getattr(remote, "db_constraint", getattr(field, "db_constraint", True))

                if constrained:
                    offenders.append(f"{model.__name__}.{field.name}")

        self.assertEqual(
            sorted(offenders),
            [],
            "these fields constrain the host user table and cannot span databases: " + ", ".join(sorted(offenders)),
        )

    def test_the_through_models_carry_it_instead(self):
        """The two relations the check above skips, verified explicitly."""
        from escalated.models import AgentSkill, TicketFollower

        for model in (TicketFollower, AgentSkill):
            field = model._meta.get_field("user")
            self.assertFalse(
                field.db_constraint,
                f"{model.__name__}.user must not constrain the host user table",
            )

    def test_on_delete_still_cascades_in_python(self):
        # Dropping the database constraint does not change deletion behaviour:
        # Django's collector implements on_delete, not the database.
        user = User.objects.create_user("cascade@example.com", password="x")
        department = Department.objects.create(name="Support", slug="support")
        department.agents.add(user)

        self.assertEqual(department.agents.count(), 1)

        user.delete()

        self.assertEqual(department.agents.count(), 0)
