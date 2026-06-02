"""Merge the parallel newsletter and ticket-subjects migration branches.

`0023_newsletter_system` (newsletter) and `0024_ticket_subjects` both branched
from the skills/host-user-key line, leaving two leaf nodes in the migration
graph. They touch disjoint tables, so an empty merge migration is sufficient
to linearise the graph.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("escalated", "0023_newsletter_system"),
        ("escalated", "0024_ticket_subjects"),
    ]

    operations = []
