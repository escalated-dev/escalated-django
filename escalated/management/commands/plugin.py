from django.core.management.base import BaseCommand, CommandError

from escalated.plugin_models import EscalatedPlugin


class Command(BaseCommand):
    help = "Manage Escalated plugins: list, activate, deactivate."

    def add_arguments(self, parser):
        subparsers = parser.add_subparsers(dest="subcommand", help="Plugin subcommand")

        subparsers.add_parser("list", help="List all plugins")

        activate_parser = subparsers.add_parser("activate", help="Activate a plugin")
        activate_parser.add_argument("slug", type=str)

        deactivate_parser = subparsers.add_parser("deactivate", help="Deactivate a plugin")
        deactivate_parser.add_argument("slug", type=str)

    def handle(self, *args, **options):
        subcommand = options.get("subcommand")

        if subcommand == "list":
            return self._list()
        elif subcommand == "activate":
            return self._activate(options["slug"])
        elif subcommand == "deactivate":
            return self._deactivate(options["slug"])
        else:
            self.stdout.write(self.style.ERROR("Usage: plugin <list|activate|deactivate>"))

    def _list(self):
        plugins = EscalatedPlugin.objects.all().order_by("slug")
        if not plugins.exists():
            self.stdout.write("No plugins installed. 0 plugins found.")
            return

        self.stdout.write(f"\n{'Slug':<40} {'Status':<10}")
        self.stdout.write("-" * 55)
        for p in plugins:
            status = self.style.SUCCESS("active") if p.is_active else self.style.WARNING("inactive")
            self.stdout.write(f"{p.slug:<40} {status}")
        self.stdout.write(f"\n{plugins.count()} plugins found.")

    def _activate(self, slug):
        try:
            plugin = EscalatedPlugin.objects.get(slug=slug)
        except EscalatedPlugin.DoesNotExist:
            raise CommandError(f"Plugin '{slug}' not found.")

        if plugin.is_active:
            self.stdout.write(f"Plugin '{slug}' is already active.")
            return

        plugin.is_active = True
        plugin.save(update_fields=["is_active"])
        self.stdout.write(self.style.SUCCESS(f"Plugin '{slug}' activated."))

    def _deactivate(self, slug):
        try:
            plugin = EscalatedPlugin.objects.get(slug=slug)
        except EscalatedPlugin.DoesNotExist:
            raise CommandError(f"Plugin '{slug}' not found.")

        if not plugin.is_active:
            self.stdout.write(f"Plugin '{slug}' is already inactive.")
            return

        plugin.is_active = False
        plugin.save(update_fields=["is_active"])
        self.stdout.write(self.style.SUCCESS(f"Plugin '{slug}' deactivated."))
