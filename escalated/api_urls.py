"""
URL configuration for the Escalated REST API.

All routes are mounted under the configured API_PREFIX (default: support/api/v1).
Authentication and rate limiting are handled by middleware.
"""

from django.urls import path

from escalated.views import api, admin_api_tokens

app_name = "escalated_api"

# API v1 routes (mounted under API_PREFIX by the consumer project)
api_patterns = [
    # Auth
    path("auth/validate/", api.auth_validate, name="auth_validate"),

    # Dashboard
    path("dashboard/", api.dashboard, name="dashboard"),

    # Tickets - list & create
    path("tickets/", api.ticket_list, name="ticket_list"),
    path("tickets/create/", api.ticket_create, name="ticket_create"),

    # Tickets - detail & actions (by reference or ID)
    path("tickets/<str:reference>/", api.ticket_show, name="ticket_show"),
    path("tickets/<str:reference>/reply/", api.ticket_reply, name="ticket_reply"),
    path("tickets/<str:reference>/status/", api.ticket_status, name="ticket_status"),
    path("tickets/<str:reference>/priority/", api.ticket_priority, name="ticket_priority"),
    path("tickets/<str:reference>/assign/", api.ticket_assign, name="ticket_assign"),
    path("tickets/<str:reference>/follow/", api.ticket_follow, name="ticket_follow"),
    path("tickets/<str:reference>/macro/", api.ticket_apply_macro, name="ticket_macro"),
    path("tickets/<str:reference>/tags/", api.ticket_tags, name="ticket_tags"),
    path("tickets/<str:reference>/delete/", api.ticket_destroy, name="ticket_destroy"),

    # Resources
    path("agents/", api.resource_agents, name="agents"),
    path("departments/", api.resource_departments, name="departments"),
    path("tags/", api.resource_tags, name="tags"),
    path("canned-responses/", api.resource_canned_responses, name="canned_responses"),
    path("macros/", api.resource_macros, name="macros"),
    path("realtime/config/", api.resource_realtime_config, name="realtime_config"),
]

# Admin token management routes
admin_api_token_patterns = [
    path(
        "admin/api-tokens/",
        admin_api_tokens.api_tokens_index,
        name="admin_api_tokens_index",
    ),
    path(
        "admin/api-tokens/create/",
        admin_api_tokens.api_tokens_create,
        name="admin_api_tokens_create",
    ),
    path(
        "admin/api-tokens/<int:token_id>/update/",
        admin_api_tokens.api_tokens_update,
        name="admin_api_tokens_update",
    ),
    path(
        "admin/api-tokens/<int:token_id>/delete/",
        admin_api_tokens.api_tokens_destroy,
        name="admin_api_tokens_destroy",
    ),
]

urlpatterns = api_patterns + admin_api_token_patterns
