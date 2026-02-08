import django.dispatch

# Ticket lifecycle signals
ticket_created = django.dispatch.Signal()          # sender=Ticket, ticket, user
ticket_updated = django.dispatch.Signal()          # sender=Ticket, ticket, user, changes
ticket_status_changed = django.dispatch.Signal()   # sender=Ticket, ticket, user, old_status, new_status
ticket_assigned = django.dispatch.Signal()          # sender=Ticket, ticket, user, agent
ticket_unassigned = django.dispatch.Signal()        # sender=Ticket, ticket, user, previous_agent
ticket_priority_changed = django.dispatch.Signal()  # sender=Ticket, ticket, user, old_priority, new_priority
ticket_escalated = django.dispatch.Signal()         # sender=Ticket, ticket, user, reason
ticket_resolved = django.dispatch.Signal()          # sender=Ticket, ticket, user
ticket_closed = django.dispatch.Signal()            # sender=Ticket, ticket, user
ticket_reopened = django.dispatch.Signal()          # sender=Ticket, ticket, user

# Reply signals
reply_created = django.dispatch.Signal()            # sender=Reply, reply, ticket, user
internal_note_added = django.dispatch.Signal()      # sender=Reply, reply, ticket, user

# SLA signals
sla_breached = django.dispatch.Signal()             # sender=Ticket, ticket, breach_type
sla_warning = django.dispatch.Signal()              # sender=Ticket, ticket, warning_type, remaining

# Tag signals
tag_added = django.dispatch.Signal()                # sender=Tag, tag, ticket, user
tag_removed = django.dispatch.Signal()              # sender=Tag, tag, ticket, user

# Department signals
department_changed = django.dispatch.Signal()       # sender=Ticket, ticket, user, old_department, new_department
