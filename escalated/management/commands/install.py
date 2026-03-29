from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils.translation import gettext as _


class Command(BaseCommand):
    help = "Set up Escalated: run migrations, seed data, and configure defaults."

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-input",
            action="store_true",
            help="Run non-interactively with defaults (for CI).",
        )

    def handle(self, *args, **options):
        no_input = options["no_input"]

        # Step 1: Run migrations
        self.stdout.write(_("Running migrations..."))
        call_command("migrate", verbosity=0)
        self.stdout.write(self.style.SUCCESS(_("Migrations complete.")))

        # Step 2: Seed permissions
        self.stdout.write(_("Seeding permissions..."))
        call_command("seed_permissions", verbosity=0)
        self.stdout.write(self.style.SUCCESS(_("Permissions seeded.")))

        # Step 3: Create default department
        from escalated.models import Department

        dept, created = Department.objects.get_or_create(
            slug="general",
            defaults={"name": "General", "description": "Default support department"},
        )
        if created:
            self.stdout.write(self.style.SUCCESS(_("Created default 'General' department.")))
        else:
            self.stdout.write(_("Default department already exists."))

        # Step 4: Create default SLA policy
        from escalated.models import SlaPolicy

        if not SlaPolicy.objects.filter(is_default=True).exists():
            SlaPolicy.objects.create(
                name="Default",
                description="Default SLA policy",
                is_default=True,
                first_response_hours={
                    "low": 24, "medium": 8, "high": 4, "urgent": 1, "critical": 0.5,
                },
                resolution_hours={
                    "low": 72, "medium": 24, "high": 8, "urgent": 4, "critical": 2,
                },
            )
            self.stdout.write(self.style.SUCCESS(_("Created default SLA policy.")))
        else:
            self.stdout.write(_("Default SLA policy already exists."))

        # Step 5: Create superuser (interactive only)
        if not no_input:
            from django.contrib.auth import get_user_model

            User = get_user_model()
            if not User.objects.filter(is_superuser=True).exists():
                self.stdout.write(_("\nNo superuser found. Creating one now:"))
                call_command("createsuperuser")
            else:
                self.stdout.write(_("Superuser already exists."))

        # Summary
        from escalated.conf import get_setting

        prefix = get_setting("ROUTE_PREFIX")
        api_prefix = get_setting("API_PREFIX")
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(_("Installation complete!")))
        self.stdout.write(_(f"  Admin panel:     /{prefix}/admin/"))
        self.stdout.write(_(f"  Agent dashboard: /{prefix}/agent/"))
        self.stdout.write(_(f"  Customer portal: /{prefix}/customer/"))
        self.stdout.write(_(f"  REST API:        /{api_prefix}/"))
