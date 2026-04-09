from django.urls import include, path

from escalated.conf import get_setting
from escalated.views import (
    admin,
    admin_plugins,
    agent,
    chat,
    customer,
    guest,
    import_views,
    inbound,
    mentions,
    widget,
    widget_chat,
    workflows,
)

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
    # Mentions
    path("agent/mentions/", mentions.mention_list, name="agent_mentions"),
    path("agent/mentions/mark-read/", mentions.mention_mark_read, name="agent_mentions_mark_read"),
    path("agent/mentions/search-agents/", mentions.search_agents, name="agent_mentions_search_agents"),
]

# Admin-facing URLs
admin_patterns = [
    path("admin/reports/", admin.reports, name="admin_reports"),
    # Tickets
    path("admin/tickets/", admin.tickets_index, name="admin_tickets_index"),
    path("admin/tickets/bulk/", admin.tickets_bulk_action, name="admin_tickets_bulk"),
    path("admin/tickets/merge-search/", admin.ticket_merge_search, name="admin_ticket_merge_search"),
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
    # Ticket Links
    path("admin/tickets/<int:ticket_id>/links/", admin.ticket_links_index, name="admin_ticket_links_index"),
    path("admin/tickets/<int:ticket_id>/links/store/", admin.ticket_links_store, name="admin_ticket_links_store"),
    path(
        "admin/tickets/<int:ticket_id>/links/<int:link_id>/delete/",
        admin.ticket_links_destroy,
        name="admin_ticket_links_destroy",
    ),
    # Ticket Merging
    path("admin/tickets/<int:ticket_id>/merge/", admin.ticket_merge, name="admin_ticket_merge"),
    # Saved Views
    path("admin/saved-views/", admin.saved_views_index, name="admin_saved_views_index"),
    path("admin/saved-views/store/", admin.saved_views_store, name="admin_saved_views_store"),
    path("admin/saved-views/<int:view_id>/update/", admin.saved_views_update, name="admin_saved_views_update"),
    path("admin/saved-views/<int:view_id>/delete/", admin.saved_views_delete, name="admin_saved_views_delete"),
    path("admin/saved-views/reorder/", admin.saved_views_reorder, name="admin_saved_views_reorder"),
    # Ticket Snooze
    path("admin/tickets/<int:ticket_id>/snooze/", admin.ticket_snooze, name="admin_ticket_snooze"),
    path("admin/tickets/<int:ticket_id>/unsnooze/", admin.ticket_unsnooze, name="admin_ticket_unsnooze"),
    # Ticket Splitting
    path("admin/tickets/<int:ticket_id>/split/", admin.ticket_split, name="admin_ticket_split"),
    # Side Conversations
    path(
        "admin/tickets/<int:ticket_id>/side-conversations/",
        admin.side_conversations_index,
        name="admin_side_conversations_index",
    ),
    path(
        "admin/tickets/<int:ticket_id>/side-conversations/store/",
        admin.side_conversations_store,
        name="admin_side_conversations_store",
    ),
    path(
        "admin/tickets/<int:ticket_id>/side-conversations/<int:conversation_id>/reply/",
        admin.side_conversations_reply,
        name="admin_side_conversations_reply",
    ),
    path(
        "admin/tickets/<int:ticket_id>/side-conversations/<int:conversation_id>/close/",
        admin.side_conversations_close,
        name="admin_side_conversations_close",
    ),
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
    path(
        "admin/escalation-rules/<int:rule_id>/delete/",
        admin.escalation_rules_delete,
        name="admin_escalation_rules_delete",
    ),
    # Tags
    path("admin/tags/", admin.tags_index, name="admin_tags_index"),
    path("admin/tags/create/", admin.tags_create, name="admin_tags_create"),
    path("admin/tags/<int:tag_id>/edit/", admin.tags_edit, name="admin_tags_edit"),
    path("admin/tags/<int:tag_id>/delete/", admin.tags_delete, name="admin_tags_delete"),
    # Canned Responses
    path("admin/canned-responses/", admin.canned_responses_index, name="admin_canned_responses_index"),
    path("admin/canned-responses/create/", admin.canned_responses_create, name="admin_canned_responses_create"),
    path(
        "admin/canned-responses/<int:response_id>/edit/",
        admin.canned_responses_edit,
        name="admin_canned_responses_edit",
    ),
    path(
        "admin/canned-responses/<int:response_id>/delete/",
        admin.canned_responses_delete,
        name="admin_canned_responses_delete",
    ),
    # Macros
    path("admin/macros/", admin.macros_index, name="admin_macros_index"),
    path("admin/macros/create/", admin.macros_create, name="admin_macros_create"),
    path("admin/macros/<int:macro_id>/edit/", admin.macros_edit, name="admin_macros_edit"),
    path("admin/macros/<int:macro_id>/delete/", admin.macros_delete, name="admin_macros_delete"),
    # Settings
    path("admin/settings/", admin.settings_index, name="admin_settings"),
    path("admin/settings/update/", admin.settings_update, name="admin_settings_update"),
    # Audit Logs
    path("admin/audit-logs/", admin.audit_logs_index, name="admin_audit_logs_index"),
    # Statuses
    path("admin/statuses/", admin.statuses_index, name="admin_statuses_index"),
    path("admin/statuses/create/", admin.statuses_create, name="admin_statuses_create"),
    path("admin/statuses/<int:status_id>/edit/", admin.statuses_edit, name="admin_statuses_edit"),
    path("admin/statuses/<int:status_id>/delete/", admin.statuses_delete, name="admin_statuses_delete"),
    # Business Hours
    path("admin/business-hours/", admin.business_hours_index, name="admin_business_hours_index"),
    path("admin/business-hours/create/", admin.business_hours_create, name="admin_business_hours_create"),
    path("admin/business-hours/<int:schedule_id>/edit/", admin.business_hours_edit, name="admin_business_hours_edit"),
    path(
        "admin/business-hours/<int:schedule_id>/delete/",
        admin.business_hours_delete,
        name="admin_business_hours_delete",
    ),
    # Roles
    path("admin/roles/", admin.roles_index, name="admin_roles_index"),
    path("admin/roles/create/", admin.roles_create, name="admin_roles_create"),
    path("admin/roles/<int:role_id>/edit/", admin.roles_edit, name="admin_roles_edit"),
    path("admin/roles/<int:role_id>/delete/", admin.roles_delete, name="admin_roles_delete"),
    # Custom Fields
    path("admin/custom-fields/", admin.custom_fields_index, name="admin_custom_fields_index"),
    path("admin/custom-fields/create/", admin.custom_fields_create, name="admin_custom_fields_create"),
    path("admin/custom-fields/<int:field_id>/edit/", admin.custom_fields_edit, name="admin_custom_fields_edit"),
    path("admin/custom-fields/<int:field_id>/delete/", admin.custom_fields_delete, name="admin_custom_fields_delete"),
    path("admin/custom-fields/reorder/", admin.custom_fields_reorder, name="admin_custom_fields_reorder"),
    # Knowledge Base - Articles
    path("admin/kb/articles/", admin.articles_index, name="admin_articles_index"),
    path("admin/kb/articles/create/", admin.articles_create, name="admin_articles_create"),
    path("admin/kb/articles/<int:article_id>/edit/", admin.articles_edit, name="admin_articles_edit"),
    path("admin/kb/articles/<int:article_id>/delete/", admin.articles_delete, name="admin_articles_delete"),
    # Knowledge Base - Categories
    path("admin/kb/categories/", admin.kb_categories_index, name="admin_kb_categories_index"),
    path("admin/kb/categories/store/", admin.kb_categories_store, name="admin_kb_categories_store"),
    path(
        "admin/kb/categories/<int:category_id>/update/", admin.kb_categories_update, name="admin_kb_categories_update"
    ),
    path(
        "admin/kb/categories/<int:category_id>/delete/", admin.kb_categories_delete, name="admin_kb_categories_delete"
    ),
    # Plugins
    path("admin/plugins/", admin_plugins.plugin_list, name="admin_plugins_index"),
    path("admin/plugins/upload/", admin_plugins.plugin_upload, name="admin_plugins_upload"),
    path("admin/plugins/<slug:slug>/activate/", admin_plugins.plugin_activate, name="admin_plugins_activate"),
    path("admin/plugins/<slug:slug>/deactivate/", admin_plugins.plugin_deactivate, name="admin_plugins_deactivate"),
    path("admin/plugins/<slug:slug>/delete/", admin_plugins.plugin_delete, name="admin_plugins_delete"),
    # Skills
    path("admin/skills/", admin.skills_index, name="admin_skills_index"),
    path("admin/skills/create/", admin.skills_create, name="admin_skills_create"),
    path("admin/skills/<int:skill_id>/edit/", admin.skills_edit, name="admin_skills_edit"),
    path("admin/skills/<int:skill_id>/delete/", admin.skills_delete, name="admin_skills_delete"),
    # Capacity
    path("admin/capacity/", admin.capacity_index, name="admin_capacity_index"),
    path("admin/capacity/<int:capacity_id>/update/", admin.capacity_update, name="admin_capacity_update"),
    # Webhooks
    path("admin/webhooks/", admin.webhooks_index, name="admin_webhooks_index"),
    path("admin/webhooks/create/", admin.webhooks_create, name="admin_webhooks_create"),
    path("admin/webhooks/<int:webhook_id>/edit/", admin.webhooks_edit, name="admin_webhooks_edit"),
    path("admin/webhooks/<int:webhook_id>/delete/", admin.webhooks_delete, name="admin_webhooks_delete"),
    path("admin/webhooks/<int:webhook_id>/deliveries/", admin.webhooks_deliveries, name="admin_webhooks_deliveries"),
    path("admin/webhooks/deliveries/<int:delivery_id>/retry/", admin.webhooks_retry, name="admin_webhooks_retry"),
    # Automations
    path("admin/automations/", admin.automations_index, name="admin_automations_index"),
    path("admin/automations/create/", admin.automations_create, name="admin_automations_create"),
    path("admin/automations/<int:automation_id>/edit/", admin.automations_edit, name="admin_automations_edit"),
    path("admin/automations/<int:automation_id>/delete/", admin.automations_delete, name="admin_automations_delete"),
    # Settings - CSAT, SSO, 2FA
    path("admin/settings/csat/", admin.settings_csat, name="admin_settings_csat"),
    path("admin/settings/sso/", admin.settings_sso, name="admin_settings_sso"),
    path("admin/settings/two-factor/", admin.settings_two_factor, name="admin_settings_two_factor"),
    path("admin/settings/two-factor/setup/", admin.two_factor_setup, name="admin_two_factor_setup"),
    path("admin/settings/two-factor/confirm/", admin.two_factor_confirm, name="admin_two_factor_confirm"),
    path("admin/settings/two-factor/disable/", admin.two_factor_disable, name="admin_two_factor_disable"),
    # Custom Objects
    path("admin/custom-objects/", admin.custom_objects_index, name="admin_custom_objects_index"),
    path("admin/custom-objects/create/", admin.custom_objects_create, name="admin_custom_objects_create"),
    path("admin/custom-objects/<int:object_id>/edit/", admin.custom_objects_edit, name="admin_custom_objects_edit"),
    path(
        "admin/custom-objects/<int:object_id>/delete/", admin.custom_objects_delete, name="admin_custom_objects_delete"
    ),
    path(
        "admin/custom-objects/<int:object_id>/records/", admin.custom_object_records, name="admin_custom_object_records"
    ),
    path(
        "admin/custom-objects/<int:object_id>/records/store/",
        admin.custom_object_records_store,
        name="admin_custom_object_records_store",
    ),
    path(
        "admin/custom-objects/<int:object_id>/records/<int:record_id>/update/",
        admin.custom_object_records_update,
        name="admin_custom_object_records_update",
    ),
    path(
        "admin/custom-objects/<int:object_id>/records/<int:record_id>/delete/",
        admin.custom_object_records_delete,
        name="admin_custom_object_records_delete",
    ),
    # Reports
    path("admin/reports/dashboard/", admin.reports_dashboard, name="admin_reports_dashboard"),
    # Workflows
    path("admin/workflows/", workflows.workflow_list, name="admin_workflows"),
    path("admin/workflows/create/", workflows.workflow_create, name="admin_workflow_create"),
    path("admin/workflows/reorder/", workflows.workflow_reorder, name="admin_workflow_reorder"),
    path("admin/workflows/<int:workflow_id>/", workflows.workflow_update, name="admin_workflow_update"),
    path("admin/workflows/<int:workflow_id>/delete/", workflows.workflow_delete, name="admin_workflow_delete"),
    path("admin/workflows/<int:workflow_id>/toggle/", workflows.workflow_toggle, name="admin_workflow_toggle"),
    path("admin/workflows/<int:workflow_id>/logs/", workflows.workflow_logs, name="admin_workflow_logs"),
    path("admin/workflows/<int:workflow_id>/dry-run/", workflows.workflow_dry_run, name="admin_workflow_dry_run"),
    # Import
    path("admin/import/", import_views.import_index, name="admin_import_index"),
    path("admin/import/create/", import_views.import_create, name="admin_import_create"),
    path("admin/import/store/", import_views.import_store, name="admin_import_store"),
    path("admin/import/<uuid:job_uuid>/", import_views.import_show, name="admin_import_show"),
    path(
        "admin/import/<uuid:job_uuid>/authenticate/", import_views.import_authenticate, name="admin_import_authenticate"
    ),
    path("admin/import/<uuid:job_uuid>/mapping/", import_views.import_mapping, name="admin_import_mapping"),
    path(
        "admin/import/<uuid:job_uuid>/mapping/save/", import_views.import_mapping_save, name="admin_import_mapping_save"
    ),
    path("admin/import/<uuid:job_uuid>/run/", import_views.import_run, name="admin_import_run"),
    path("admin/import/<uuid:job_uuid>/pause/", import_views.import_pause, name="admin_import_pause"),
    path("admin/import/<uuid:job_uuid>/progress/", import_views.import_progress, name="admin_import_progress"),
    path("admin/import/<uuid:job_uuid>/delete/", import_views.import_delete, name="admin_import_delete"),
]

# Guest-facing URLs (no authentication required)
guest_patterns = [
    path("guest/create/", guest.ticket_create, name="guest_ticket_create"),
    path("guest/store/", guest.ticket_store, name="guest_ticket_store"),
    path("guest/<str:token>/", guest.ticket_show, name="guest_ticket_show"),
    path("guest/<str:token>/reply/", guest.ticket_reply, name="guest_ticket_reply"),
    path("guest/<str:token>/rate/", guest.ticket_rate, name="guest_ticket_rate"),
]

# Agent chat URLs
chat_patterns = [
    path("agent/chat/active/", chat.active_chats, name="agent_chat_active"),
    path("agent/chat/queue/", chat.chat_queue, name="agent_chat_queue"),
    path("agent/chat/<int:session_id>/accept/", chat.accept_chat, name="agent_chat_accept"),
    path("agent/chat/<int:session_id>/end/", chat.end_chat, name="agent_chat_end"),
    path("agent/chat/<int:session_id>/transfer/", chat.transfer_chat, name="agent_chat_transfer"),
    path("agent/chat/status/", chat.update_status, name="agent_chat_status"),
    path("agent/chat/<int:session_id>/message/", chat.send_message, name="agent_chat_message"),
    path("agent/chat/<int:session_id>/typing/", chat.update_typing, name="agent_chat_typing"),
]

# Widget public API (no authentication)
widget_patterns = [
    path("widget/config/", widget.widget_config, name="widget_config"),
    path("widget/articles/search/", widget.widget_article_search, name="widget_article_search"),
    path("widget/articles/<int:article_id>/", widget.widget_article_detail, name="widget_article_detail"),
    path("widget/tickets/create/", widget.widget_create_ticket, name="widget_create_ticket"),
    path("widget/tickets/lookup/", widget.widget_lookup_ticket, name="widget_lookup_ticket"),
]

# Widget chat API (no authentication)
widget_chat_patterns = [
    path("widget/chat/availability/", widget_chat.chat_availability, name="widget_chat_availability"),
    path("widget/chat/start/", widget_chat.start_chat, name="widget_chat_start"),
    path("widget/chat/message/", widget_chat.send_message, name="widget_chat_message"),
    path("widget/chat/typing/", widget_chat.update_typing, name="widget_chat_typing"),
    path("widget/chat/end/", widget_chat.end_chat, name="widget_chat_end"),
    path("widget/chat/rate/", widget_chat.rate_chat, name="widget_chat_rate"),
]

# Inbound email webhook (no authentication — external services POST here)
inbound_patterns = [
    path("inbound/<str:adapter_name>/", inbound.inbound_webhook, name="inbound_webhook"),
]

# Core routes (always registered)
urlpatterns = list(inbound_patterns) + list(widget_patterns) + list(widget_chat_patterns)

# UI routes (only when UI is enabled)
if get_setting("UI_ENABLED"):
    urlpatterns = customer_patterns + agent_patterns + chat_patterns + admin_patterns + guest_patterns + urlpatterns

# Inject plugin bridge routes (pages, API endpoints, webhooks) if the SDK
# bridge has booted and registered patterns from plugin manifests.
try:
    from escalated.bridge.plugin_bridge import get_bridge as _get_bridge

    _bridge = _get_bridge()
    _plugin_urls = _bridge.get_plugin_urls()
    if _plugin_urls:
        urlpatterns = list(urlpatterns) + _plugin_urls
except Exception:
    pass

# Conditionally include API URLs when API is enabled
if get_setting("API_ENABLED"):
    from escalated.api_urls import admin_api_token_patterns, api_patterns

    api_prefix = get_setting("API_PREFIX").strip("/")

    urlpatterns += [
        path(f"{api_prefix}/", include((api_patterns, "escalated_api"))),
    ]

    # Admin API token management (under the main admin prefix)
    urlpatterns += admin_api_token_patterns
