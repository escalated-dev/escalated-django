from django.urls import path

from escalated.views import customer, agent, admin, guest, inbound

app_name = "escalated"

# Customer-facing URLs
customer_patterns = [
    path("tickets/", customer.ticket_list, name="customer_ticket_list"),
    path("tickets/create/", customer.ticket_create, name="customer_ticket_create"),
    path("tickets/store/", customer.ticket_store, name="customer_ticket_store"),
    path("tickets/<int:ticket_id>/", customer.ticket_show, name="customer_ticket_show"),
    path("tickets/<int:ticket_id>/reply/", customer.ticket_reply, name="customer_ticket_reply"),
    path("tickets/<int:ticket_id>/close/", customer.ticket_close, name="customer_ticket_close"),
    path("tickets/<int:ticket_id>/reopen/", customer.ticket_reopen, name="customer_ticket_reopen"),
    path("tickets/<int:ticket_id>/rate/", customer.ticket_rate, name="customer_ticket_rate"),
]

# Agent-facing URLs
agent_patterns = [
    path("agent/", agent.dashboard, name="agent_dashboard"),
    path("agent/tickets/", agent.ticket_list, name="agent_ticket_list"),
    path("agent/tickets/bulk/", agent.ticket_bulk_action, name="agent_ticket_bulk"),
    path("agent/tickets/<int:ticket_id>/", agent.ticket_show, name="agent_ticket_show"),
    path("agent/tickets/<int:ticket_id>/update/", agent.ticket_update, name="agent_ticket_update"),
    path("agent/tickets/<int:ticket_id>/reply/", agent.ticket_reply, name="agent_ticket_reply"),
    path("agent/tickets/<int:ticket_id>/note/", agent.ticket_note, name="agent_ticket_note"),
    path("agent/tickets/<int:ticket_id>/assign/", agent.ticket_assign, name="agent_ticket_assign"),
    path("agent/tickets/<int:ticket_id>/status/", agent.ticket_status, name="agent_ticket_status"),
    path("agent/tickets/<int:ticket_id>/priority/", agent.ticket_priority, name="agent_ticket_priority"),
    path("agent/tickets/<int:ticket_id>/tags/", agent.ticket_tags, name="agent_ticket_tags"),
    path("agent/tickets/<int:ticket_id>/department/", agent.ticket_department, name="agent_ticket_department"),
    path("agent/tickets/<int:ticket_id>/macro/", agent.ticket_apply_macro, name="agent_ticket_macro"),
    path("agent/tickets/<int:ticket_id>/follow/", agent.ticket_follow, name="agent_ticket_follow"),
    path("agent/tickets/<int:ticket_id>/presence/", agent.ticket_presence, name="agent_ticket_presence"),
    path("agent/tickets/<int:ticket_id>/<int:reply_id>/pin/", agent.ticket_pin_reply, name="agent_ticket_pin"),
]

# Admin-facing URLs
admin_patterns = [
    path("admin/reports/", admin.reports, name="admin_reports"),
    # Tickets
    path("admin/tickets/", admin.tickets_index, name="admin_tickets_index"),
    path("admin/tickets/bulk/", admin.tickets_bulk_action, name="admin_tickets_bulk"),
    path("admin/tickets/<int:ticket_id>/", admin.tickets_show, name="admin_tickets_show"),
    path("admin/tickets/<int:ticket_id>/reply/", admin.tickets_reply, name="admin_tickets_reply"),
    path("admin/tickets/<int:ticket_id>/note/", admin.tickets_note, name="admin_tickets_note"),
    path("admin/tickets/<int:ticket_id>/assign/", admin.tickets_assign, name="admin_tickets_assign"),
    path("admin/tickets/<int:ticket_id>/status/", admin.tickets_status, name="admin_tickets_status"),
    path("admin/tickets/<int:ticket_id>/priority/", admin.tickets_priority, name="admin_tickets_priority"),
    path("admin/tickets/<int:ticket_id>/tags/", admin.tickets_tags, name="admin_tickets_tags"),
    path("admin/tickets/<int:ticket_id>/department/", admin.tickets_department, name="admin_tickets_department"),
    path("admin/tickets/<int:ticket_id>/macro/", admin.tickets_apply_macro, name="admin_tickets_macro"),
    path("admin/tickets/<int:ticket_id>/follow/", admin.tickets_follow, name="admin_tickets_follow"),
    path("admin/tickets/<int:ticket_id>/presence/", admin.tickets_presence, name="admin_tickets_presence"),
    path("admin/tickets/<int:ticket_id>/<int:reply_id>/pin/", admin.tickets_pin_reply, name="admin_tickets_pin"),
    # Departments
    path("admin/departments/", admin.departments_index, name="admin_departments_index"),
    path("admin/departments/create/", admin.departments_create, name="admin_departments_create"),
    path("admin/departments/<int:department_id>/edit/", admin.departments_edit, name="admin_departments_edit"),
    path("admin/departments/<int:department_id>/delete/", admin.departments_delete, name="admin_departments_delete"),
    # SLA Policies
    path("admin/sla-policies/", admin.sla_policies_index, name="admin_sla_policies_index"),
    path("admin/sla-policies/create/", admin.sla_policies_create, name="admin_sla_policies_create"),
    path("admin/sla-policies/<int:policy_id>/edit/", admin.sla_policies_edit, name="admin_sla_policies_edit"),
    path("admin/sla-policies/<int:policy_id>/delete/", admin.sla_policies_delete, name="admin_sla_policies_delete"),
    # Escalation Rules
    path("admin/escalation-rules/", admin.escalation_rules_index, name="admin_escalation_rules_index"),
    path("admin/escalation-rules/create/", admin.escalation_rules_create, name="admin_escalation_rules_create"),
    path("admin/escalation-rules/<int:rule_id>/edit/", admin.escalation_rules_edit, name="admin_escalation_rules_edit"),
    path("admin/escalation-rules/<int:rule_id>/delete/", admin.escalation_rules_delete, name="admin_escalation_rules_delete"),
    # Tags
    path("admin/tags/", admin.tags_index, name="admin_tags_index"),
    path("admin/tags/create/", admin.tags_create, name="admin_tags_create"),
    path("admin/tags/<int:tag_id>/edit/", admin.tags_edit, name="admin_tags_edit"),
    path("admin/tags/<int:tag_id>/delete/", admin.tags_delete, name="admin_tags_delete"),
    # Canned Responses
    path("admin/canned-responses/", admin.canned_responses_index, name="admin_canned_responses_index"),
    path("admin/canned-responses/create/", admin.canned_responses_create, name="admin_canned_responses_create"),
    path("admin/canned-responses/<int:response_id>/edit/", admin.canned_responses_edit, name="admin_canned_responses_edit"),
    path("admin/canned-responses/<int:response_id>/delete/", admin.canned_responses_delete, name="admin_canned_responses_delete"),
    # Macros
    path("admin/macros/", admin.macros_index, name="admin_macros_index"),
    path("admin/macros/create/", admin.macros_create, name="admin_macros_create"),
    path("admin/macros/<int:macro_id>/edit/", admin.macros_edit, name="admin_macros_edit"),
    path("admin/macros/<int:macro_id>/delete/", admin.macros_delete, name="admin_macros_delete"),
    # Settings
    path("admin/settings/", admin.settings_index, name="admin_settings"),
    path("admin/settings/update/", admin.settings_update, name="admin_settings_update"),
]

# Guest-facing URLs (no authentication required)
guest_patterns = [
    path("guest/create/", guest.ticket_create, name="guest_ticket_create"),
    path("guest/store/", guest.ticket_store, name="guest_ticket_store"),
    path("guest/<str:token>/", guest.ticket_show, name="guest_ticket_show"),
    path("guest/<str:token>/reply/", guest.ticket_reply, name="guest_ticket_reply"),
    path("guest/<str:token>/rate/", guest.ticket_rate, name="guest_ticket_rate"),
]

# Inbound email webhook (no authentication — external services POST here)
inbound_patterns = [
    path("inbound/<str:adapter_name>/", inbound.inbound_webhook, name="inbound_webhook"),
]

urlpatterns = (
    customer_patterns
    + agent_patterns
    + admin_patterns
    + guest_patterns
    + inbound_patterns
)
