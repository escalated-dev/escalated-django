from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from escalated.models import Department, Reply, SlaPolicy, Tag, Ticket


class Command(BaseCommand):
    help = "Seed demo users + escalated fixtures."

    def handle(self, *args, **options):
        User = get_user_model()
        password = "password"

        users = [
            ("alice", "Alice", "Admin", "alice@demo.test", True, True),
            ("bob", "Bob", "Agent", "bob@demo.test", False, True),
            ("carol", "Carol", "Agent", "carol@demo.test", False, True),
            ("frank", "Frank", "Customer", "frank@acme.example", False, False),
            ("grace", "Grace", "Customer", "grace@acme.example", False, False),
            ("henry", "Henry", "Customer", "henry@globex.example", False, False),
        ]
        created = []
        for username, first, last, email, is_super, is_staff in users:
            u, _ = User.objects.update_or_create(
                username=username,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "email": email,
                    "is_superuser": is_super,
                    "is_staff": is_staff or is_super,
                },
            )
            u.set_password(password)
            u.save()
            created.append(u)
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(created)} users."))

        support, _ = Department.objects.get_or_create(
            slug="support",
            defaults={"name": "Support", "description": "General support."},
        )
        billing, _ = Department.objects.get_or_create(
            slug="billing",
            defaults={"name": "Billing", "description": "Invoices."},
        )
        for tag_slug, color in [("bug", "#ef4444"), ("refund", "#10b981"), ("billing", "#f59e0b")]:
            Tag.objects.get_or_create(slug=tag_slug, defaults={"name": tag_slug.title(), "color": color})

        sla, _ = SlaPolicy.objects.get_or_create(
            name="Standard",
            defaults={
                "description": "Default SLA",
                "is_default": True,
                "first_response_hours": {"low": 24, "medium": 8, "high": 4, "urgent": 2},
                "resolution_hours": {"low": 72, "medium": 48, "high": 24, "urgent": 8},
            },
        )

        subjects = [
            "Unable to log in",
            "Feature request: bulk-export",
            "Refund for duplicate charge",
            "Slack integration broken",
            "API returning 502",
            "SSO config questions",
            "Cannot upload large files",
            "Switch to annual billing",
        ]
        statuses = ["open", "in_progress", "resolved", "closed"]
        priorities = ["low", "medium", "high", "urgent"]
        agents = [u for u in created if u.is_staff]
        customers = [u for u in created if not u.is_staff]

        for i, subject in enumerate(subjects):
            customer = customers[i % len(customers)]
            agent = agents[i % len(agents)] if agents else None
            try:
                t = Ticket.objects.create(
                    reference=f"ESC-{i + 1:05d}",
                    subject=subject,
                    description=f"Demo ticket #{i + 1}",
                    status=statuses[i % len(statuses)],
                    priority=priorities[i % len(priorities)],
                    channel="web",
                    requester=customer,
                    assigned_to=agent,
                    department=support if i % 2 == 0 else billing,
                    sla_policy=sla,
                )
                Reply.objects.create(
                    ticket=t,
                    author=customer,
                    body=f"Initial demo reply on {subject}",
                    type="reply",
                    is_internal_note=False,
                )
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  ticket {i + 1} skipped: {e}"))

        self.stdout.write(self.style.SUCCESS("Demo seed complete."))
