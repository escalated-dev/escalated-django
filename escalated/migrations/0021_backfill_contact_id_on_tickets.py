"""Backfills ticket.contact_id from inline guest_email.

Safe to re-run: skips tickets already carrying a contact_id, and the
unique email index on escalated_contacts prevents duplicate rows.
"""

from django.db import migrations


def backfill(apps, schema_editor):
    Ticket = apps.get_model("escalated", "Ticket")
    Contact = apps.get_model("escalated", "Contact")

    seen: dict[str, int] = {}
    qs = Ticket.objects.filter(guest_email__isnull=False, contact_id__isnull=True)
    for ticket in qs.iterator():
        email = (ticket.guest_email or "").strip().lower()
        if not email:
            continue
        if email not in seen:
            contact, _ = Contact.objects.get_or_create(
                email=email,
                defaults={"name": ticket.guest_name or None, "metadata": {}},
            )
            seen[email] = contact.id
        Ticket.objects.filter(pk=ticket.pk).update(contact_id=seen[email])


def reverse(apps, schema_editor):
    Ticket = apps.get_model("escalated", "Ticket")
    Ticket.objects.update(contact_id=None)


class Migration(migrations.Migration):
    dependencies = [
        ("escalated", "0020_contact_and_ticket_contact_fk"),
    ]

    operations = [
        migrations.RunPython(backfill, reverse),
    ]
