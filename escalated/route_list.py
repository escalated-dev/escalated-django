"""
The named routes the shared frontend calls through ``route(name, params)``.

The shared pages (``@escalated-dev/escalated``) were written against Laravel's
Ziggy: every link and form action is ``route('escalated.agent.tickets.show',
ticket.reference)``. A name the page cannot resolve renders as ``#`` -- a
button that does nothing. This module maps each of those names to the URL this
package serves it at, and shares the table as the ``ziggy`` Inertia prop in the
shape ziggy-js reads (``{url, port, defaults, routes: {name: {uri, methods}},
location}``).

The uris are not written out by hand: each is ``reverse()``d from the package's
own URL names, so they follow wherever the host ``include()``s
``escalated.urls`` (and ``SCRIPT_NAME``). Parameters carry escalated-laravel's
names (``{ticket}``, ``{id}``, ``{jobId}``...), as some pages pass them by name.

Hosts keep the last word, name by name:

* ``ESCALATED["ROUTES"] = {"login": "/accounts/login/", "<name>": None}`` --
  a path (or ``{"uri", "methods"}``) replaces one name, ``None`` removes it;
* a ``ziggy`` prop the host shares itself (e.g. from django-ziggy) is merged
  over this table;
* a ``window.route`` or ``window.Ziggy`` the host installs wins over the
  helper (``{% escalated_route_helper %}``).
"""

import uuid
from collections import namedtuple

from django.conf import settings
from django.core.signals import setting_changed
from django.shortcuts import resolve_url
from django.urls import NoReverseMatch, get_script_prefix, get_urlconf, reverse

from escalated.conf import get_setting

GET = ("GET", "HEAD")
POST = ("POST",)
PUT = ("PUT",)
PATCH = ("PATCH",)
DELETE = ("DELETE",)

Route = namedtuple("Route", ["url_name", "methods", "params"])


def r(url_name, methods=GET, **params):
    """A route: the package URL name, its verbs, and {view kwarg: Ziggy param name}."""
    return Route(url_name, methods, params)


def _resource(prefix, singular, kwarg, *, index, create, edit, delete):
    """Laravel's resource names over this package's create/edit/delete views."""
    return {
        f"escalated.admin.{prefix}.index": r(index),
        f"escalated.admin.{prefix}.create": r(create),
        f"escalated.admin.{prefix}.store": r(create, POST),
        f"escalated.admin.{prefix}.edit": r(edit, **{kwarg: singular}),
        f"escalated.admin.{prefix}.update": r(edit, PUT, **{kwarg: singular}),
        f"escalated.admin.{prefix}.destroy": r(delete, DELETE, **{kwarg: singular}),
    }


def _ticket_actions(scope, name, *, actions, pin, **extra):
    routes = {
        f"escalated.{scope}.tickets.{action}": r(f"{name}_{action}", POST, ticket_id="ticket") for action in actions
    }
    routes[f"escalated.{scope}.tickets.pin"] = r(pin, POST, ticket_id="ticket", reply_id="reply")
    routes.update(extra)
    return routes


T = {"ticket_id": "ticket"}

ROUTES = {
    # Agent
    "escalated.agent.dashboard": r("agent_dashboard"),
    "escalated.agent.tickets.index": r("agent_ticket_list"),
    "escalated.agent.tickets.bulk": r("agent_ticket_bulk", POST),
    "escalated.agent.tickets.show": r("agent_ticket_show", **T),
    "escalated.agent.tickets.update": r("agent_ticket_update", PUT, **T),
    **_ticket_actions(
        "agent",
        "agent_ticket",
        actions=["reply", "note", "assign", "status", "priority", "tags", "department", "macro", "follow", "presence"],
        pin="agent_ticket_pin",
    ),
    "escalated.agent.tickets.custom-action": r("agent_ticket_custom_action", POST, ticket_id="ticket", action="action"),
    # Admin -- tickets
    "escalated.admin.tickets.index": r("admin_tickets_index"),
    "escalated.admin.tickets.bulk": r("admin_tickets_bulk", POST),
    "escalated.admin.tickets.merge-search": r("admin_ticket_merge_search"),
    "escalated.admin.tickets.show": r("admin_tickets_show", **T),
    **_ticket_actions(
        "admin",
        "admin_tickets",
        actions=["reply", "note", "assign", "status", "priority", "tags", "department", "macro", "follow", "presence"],
        pin="admin_tickets_pin",
    ),
    "escalated.admin.tickets.merge": r("admin_ticket_merge", POST, **T),
    "escalated.admin.tickets.snooze": r("admin_ticket_snooze", POST, **T),
    "escalated.admin.tickets.unsnooze": r("admin_ticket_unsnooze", POST, **T),
    "escalated.admin.tickets.split": r("admin_ticket_split", POST, **T),
    "escalated.admin.tickets.links.index": r("admin_ticket_links_index", **T),
    "escalated.admin.tickets.links.store": r("admin_ticket_links_store", POST, **T),
    "escalated.admin.tickets.links.destroy": r(
        "admin_ticket_links_destroy", DELETE, ticket_id="ticket", link_id="link"
    ),
    "escalated.admin.tickets.side-conversations.index": r("admin_side_conversations_index", **T),
    "escalated.admin.tickets.side-conversations.store": r("admin_side_conversations_store", POST, **T),
    "escalated.admin.tickets.side-conversations.reply": r(
        "admin_side_conversations_reply", POST, ticket_id="ticket", conversation_id="sideConversation"
    ),
    "escalated.admin.tickets.side-conversations.close": r(
        "admin_side_conversations_close", POST, ticket_id="ticket", conversation_id="sideConversation"
    ),
    # Admin -- resources
    **_resource(
        "departments",
        "department",
        "department_id",
        index="admin_departments_index",
        create="admin_departments_create",
        edit="admin_departments_edit",
        delete="admin_departments_delete",
    ),
    **_resource(
        "sla-policies",
        "sla_policy",
        "policy_id",
        index="admin_sla_policies_index",
        create="admin_sla_policies_create",
        edit="admin_sla_policies_edit",
        delete="admin_sla_policies_delete",
    ),
    **_resource(
        "escalation-rules",
        "escalation_rule",
        "rule_id",
        index="admin_escalation_rules_index",
        create="admin_escalation_rules_create",
        edit="admin_escalation_rules_edit",
        delete="admin_escalation_rules_delete",
    ),
    **_resource(
        "custom-fields",
        "custom_field",
        "field_id",
        index="admin_custom_fields_index",
        create="admin_custom_fields_create",
        edit="admin_custom_fields_edit",
        delete="admin_custom_fields_delete",
    ),
    "escalated.admin.custom-fields.reorder": r("admin_custom_fields_reorder", POST),
    **_resource(
        "statuses",
        "status",
        "status_id",
        index="admin_statuses_index",
        create="admin_statuses_create",
        edit="admin_statuses_edit",
        delete="admin_statuses_delete",
    ),
    **_resource(
        "business-hours",
        "business_hour",
        "schedule_id",
        index="admin_business_hours_index",
        create="admin_business_hours_create",
        edit="admin_business_hours_edit",
        delete="admin_business_hours_delete",
    ),
    **_resource(
        "roles",
        "role",
        "role_id",
        index="admin_roles_index",
        create="admin_roles_create",
        edit="admin_roles_edit",
        delete="admin_roles_delete",
    ),
    **_resource(
        "automations",
        "automation",
        "automation_id",
        index="admin_automations_index",
        create="admin_automations_create",
        edit="admin_automations_edit",
        delete="admin_automations_delete",
    ),
    **_resource(
        "webhooks",
        "webhook",
        "webhook_id",
        index="admin_webhooks_index",
        create="admin_webhooks_create",
        edit="admin_webhooks_edit",
        delete="admin_webhooks_delete",
    ),
    "escalated.admin.webhooks.deliveries": r("admin_webhooks_deliveries", webhook_id="webhook"),
    "escalated.admin.webhooks.retry": r("admin_webhooks_retry", POST, delivery_id="delivery"),
    **_resource(
        "kb-articles",
        "kb_article",
        "article_id",
        index="admin_articles_index",
        create="admin_articles_create",
        edit="admin_articles_edit",
        delete="admin_articles_delete",
    ),
    **_resource(
        "custom-objects",
        "custom_object",
        "object_id",
        index="admin_custom_objects_index",
        create="admin_custom_objects_create",
        edit="admin_custom_objects_edit",
        delete="admin_custom_objects_delete",
    ),
    "escalated.admin.custom-objects.records": r("admin_custom_object_records", object_id="custom_object"),
    "escalated.admin.custom-objects.records.store": r(
        "admin_custom_object_records_store", POST, object_id="custom_object"
    ),
    "escalated.admin.custom-objects.records.update": r(
        "admin_custom_object_records_update", PUT, object_id="custom_object", record_id="record"
    ),
    "escalated.admin.custom-objects.records.destroy": r(
        "admin_custom_object_records_delete", DELETE, object_id="custom_object", record_id="record"
    ),
    "escalated.admin.skills.index": r("admin_skills_index"),
    "escalated.admin.skills.create": r("admin_skills_create"),
    "escalated.admin.skills.store": r("admin_skills_store", POST),
    "escalated.admin.skills.edit": r("admin_skills_edit", skill_id="skill"),
    "escalated.admin.skills.update": r("admin_skills_update", PUT, skill_id="skill"),
    "escalated.admin.skills.destroy": r("admin_skills_destroy", DELETE, skill_id="skill"),
    "escalated.admin.tags.index": r("admin_tags_index"),
    "escalated.admin.tags.store": r("admin_tags_create", POST),
    "escalated.admin.tags.update": r("admin_tags_edit", PUT, tag_id="tag"),
    "escalated.admin.tags.destroy": r("admin_tags_delete", DELETE, tag_id="tag"),
    "escalated.admin.canned-responses.index": r("admin_canned_responses_index"),
    "escalated.admin.canned-responses.store": r("admin_canned_responses_create", POST),
    "escalated.admin.canned-responses.update": r("admin_canned_responses_edit", PUT, response_id="cannedResponse"),
    "escalated.admin.canned-responses.destroy": r(
        "admin_canned_responses_delete", DELETE, response_id="cannedResponse"
    ),
    "escalated.admin.macros.index": r("admin_macros_index"),
    "escalated.admin.macros.store": r("admin_macros_create", POST),
    "escalated.admin.macros.update": r("admin_macros_edit", PUT, macro_id="macro"),
    "escalated.admin.macros.destroy": r("admin_macros_delete", DELETE, macro_id="macro"),
    "escalated.admin.kb-categories.index": r("admin_kb_categories_index"),
    "escalated.admin.kb-categories.store": r("admin_kb_categories_store", POST),
    "escalated.admin.kb-categories.update": r("admin_kb_categories_update", PUT, category_id="kb_category"),
    "escalated.admin.kb-categories.destroy": r("admin_kb_categories_delete", DELETE, category_id="kb_category"),
    "escalated.admin.saved-views.index": r("admin_saved_views_index"),
    "escalated.admin.saved-views.store": r("admin_saved_views_store", POST),
    "escalated.admin.saved-views.update": r("admin_saved_views_update", PUT, view_id="savedView"),
    "escalated.admin.saved-views.destroy": r("admin_saved_views_delete", DELETE, view_id="savedView"),
    "escalated.admin.saved-views.reorder": r("admin_saved_views_reorder", POST),
    "escalated.admin.capacity.index": r("admin_capacity_index"),
    "escalated.admin.capacity.update": r("admin_capacity_update", PUT, capacity_id="capacity"),
    "escalated.admin.plugins.index": r("admin_plugins_index"),
    "escalated.admin.plugins.upload": r("admin_plugins_upload", POST),
    "escalated.admin.plugins.activate": r("admin_plugins_activate", POST, slug="slug"),
    "escalated.admin.plugins.deactivate": r("admin_plugins_deactivate", POST, slug="slug"),
    "escalated.admin.plugins.destroy": r("admin_plugins_delete", DELETE, slug="slug"),
    "escalated.admin.users.index": r("admin_users_index"),
    "escalated.admin.users.role": r("admin_users_role", PATCH, user_id="user"),
    "escalated.admin.users.roles": r("admin_users_roles", PUT, user_id="user"),
    "escalated.admin.audit-log": r("admin_audit_logs_index"),
    # Admin -- live chat (the agent chat endpoints; admins pass the agent gate)
    "escalated.admin.chat.end": r("agent_chat_end", POST, session_id="session"),
    "escalated.admin.chat.transfer": r("agent_chat_transfer", POST, session_id="session"),
    # Admin -- settings
    "escalated.admin.settings": r("admin_settings"),
    "escalated.admin.settings.update": r("admin_settings_update", POST),
    "escalated.admin.settings.csat": r("admin_settings_csat"),
    "escalated.admin.settings.csat.update": r("admin_settings_csat_update", POST),
    "escalated.admin.settings.public-tickets": r("admin_settings_public_tickets"),
    "escalated.admin.settings.public-tickets.update": r("admin_settings_public_tickets_update", POST),
    "escalated.admin.settings.data-retention": r("admin_settings_data_retention"),
    "escalated.admin.settings.data-retention.update": r("admin_settings_data_retention_update", POST),
    "escalated.admin.settings.database": r("admin_settings_database"),
    "escalated.admin.settings.database.update": r("admin_settings_database_update", POST),
    "escalated.admin.settings.database.test": r("admin_settings_database_test", POST),
    "escalated.admin.settings.email": r("admin_settings_email"),
    "escalated.admin.settings.email.update": r("admin_settings_email_update", POST),
    "escalated.admin.settings.sso": r("admin_settings_sso"),
    "escalated.admin.settings.sso.update": r("admin_settings_sso", POST),
    # Two-factor (ADR 2026-10-29); these answer 404 while two-factor is off.
    "escalated.admin.two-factor.index": r("admin_settings_two_factor"),
    "escalated.admin.two-factor.setup": r("admin_two_factor_setup", POST),
    "escalated.admin.two-factor.confirm": r("admin_two_factor_confirm", POST),
    "escalated.admin.two-factor.disable": r("admin_two_factor_disable", POST),
    "escalated.two-factor.challenge": r("two_factor_challenge"),
    "escalated.two-factor.verify": r("two_factor_challenge", POST),
    # Admin -- reports
    "escalated.admin.reports": r("admin_reports"),
    "escalated.admin.reports.dashboard": r("admin_reports_dashboard"),
    "escalated.admin.reports.agents": r("admin_reports_agents"),
    "escalated.admin.reports.sla": r("admin_reports_sla"),
    "escalated.admin.reports.csat": r("admin_reports_csat"),
    "escalated.admin.reports.agent-detail": r("admin_reports_agent_detail", agent_id="id"),
    "escalated.admin.reports.sla-trends": r("admin_reports_sla_trends"),
    "escalated.admin.reports.response-times": r("admin_reports_response_times"),
    "escalated.admin.reports.resolution-times": r("admin_reports_resolution_times"),
    "escalated.admin.reports.agent-ranking": r("admin_reports_agent_ranking"),
    "escalated.admin.reports.cohorts": r("admin_reports_cohorts"),
    "escalated.admin.reports.comparison": r("admin_reports_comparison"),
    # Admin -- workflows
    "escalated.admin.workflows.index": r("admin_workflows"),
    "escalated.admin.workflows.create": r("admin_workflow_create"),
    "escalated.admin.workflows.store": r("admin_workflow_create", POST),
    "escalated.admin.workflows.reorder": r("admin_workflow_reorder", POST),
    "escalated.admin.workflows.edit": r("admin_workflow_update", workflow_id="workflow"),
    "escalated.admin.workflows.update": r("admin_workflow_update", PUT, workflow_id="workflow"),
    "escalated.admin.workflows.destroy": r("admin_workflow_update", DELETE, workflow_id="workflow"),
    "escalated.admin.workflows.toggle": r("admin_workflow_toggle", POST, workflow_id="workflow"),
    # Admin -- import wizard
    "escalated.admin.import.index": r("admin_import_index"),
    "escalated.admin.import.connect": r("admin_import_connect", platform="platform"),
    "escalated.admin.import.test-connection": r("admin_import_test_connection", POST, platform="platform"),
    "escalated.admin.import.mapping": r("admin_import_platform_mapping", platform="platform"),
    "escalated.admin.import.review": r("admin_import_review", POST, platform="platform"),
    "escalated.admin.import.start": r("admin_import_start", POST, platform="platform"),
    "escalated.admin.import.progress": r("admin_import_progress_page", job_uuid="jobId"),
    "escalated.admin.import.status": r("admin_import_status", job_uuid="jobId"),
    "escalated.admin.import.pause": r("admin_import_pause_job", POST, job_uuid="jobId"),
    "escalated.admin.import.resume": r("admin_import_resume", POST, job_uuid="jobId"),
    "escalated.admin.import.cancel": r("admin_import_cancel", POST, job_uuid="jobId"),
    # Customer
    "escalated.customer.tickets.index": r("customer_ticket_list"),
    "escalated.customer.tickets.create": r("customer_ticket_create"),
    "escalated.customer.tickets.store": r("customer_ticket_store", POST),
    "escalated.customer.tickets.show": r("customer_ticket_show", **T),
    "escalated.customer.tickets.reply": r("customer_ticket_reply", POST, **T),
    "escalated.customer.tickets.close": r("customer_ticket_close", POST, **T),
    "escalated.customer.tickets.reopen": r("customer_ticket_reopen", POST, **T),
    "escalated.customer.tickets.rate": r("customer_ticket_rate", POST, **T),
    "escalated.customer.kb.index": r("customer_kb_index"),
    "escalated.customer.kb.show": r("customer_kb_show", slug="slug"),
    "escalated.customer.kb.feedback": r("customer_kb_feedback", POST, slug="slug"),
    # Guest
    "escalated.guest.tickets.create": r("guest_ticket_create"),
    "escalated.guest.tickets.store": r("guest_ticket_store", POST),
    "escalated.guest.tickets.show": r("guest_ticket_show", token="token"),
    "escalated.guest.tickets.reply": r("guest_ticket_reply", POST, token="token"),
    "escalated.guest.tickets.rate": r("guest_ticket_rate", POST, token="token"),
    "escalated.guest.verification": r("guest_verification", POST),
    "escalated.guest.lookup": r("guest_lookup", POST),
    # Shared
    "escalated.attachments.download": r("attachment_download", attachment_id="attachment"),
    "escalated.sso.login": r("sso_login"),
    "escalated.sso.saml.metadata": r("sso_saml_metadata"),
    "escalated.sso.saml.acs": r("sso_saml_acs", POST),
    "escalated.sso.oauth.callback": r("sso_oauth_callback"),
    "escalated.sso.jwt.callback": r("sso_jwt_callback", GET + POST),
}

_cache = {}


def _uri(route):
    """reverse() with stand-ins for the parameters, then the stand-ins as {placeholders}."""
    stand_ins = {}
    for index, kwarg in enumerate(route.params):
        stand_ins[kwarg] = uuid.UUID(int=index + 1) if kwarg.endswith("uuid") else str(918273640 + index)
    path = reverse(f"escalated:{route.url_name}", kwargs=stand_ins or None)
    for kwarg, value in stand_ins.items():
        path = path.replace(str(value), "{" + route.params[kwarg] + "}", 1)
    return path.lstrip("/")


def _built_in():
    key = (get_script_prefix(), get_urlconf() or settings.ROOT_URLCONF)
    if key not in _cache:
        routes = {}
        for name, route in ROUTES.items():
            try:
                routes[name] = {"uri": _uri(route), "methods": list(route.methods)}
            except NoReverseMatch:
                # Not mounted on this host (UI or a feature's URLs switched off).
                continue
        _cache[key] = routes
    return _cache[key]


def _login():
    url = resolve_url(settings.LOGIN_URL)
    if "://" in url:
        # Ziggy uris are paths on the host's own origin.
        return None
    return {"uri": url.lstrip("/"), "methods": list(GET)}


def _override(value):
    if value is None or isinstance(value, dict):
        return value
    return {"uri": str(value).lstrip("/"), "methods": list(GET)}


def escalated_routes():
    """``{name: {"uri", "methods"}}``: the built-in table with the host's ROUTES applied."""
    routes = dict(_built_in())
    login = _login()
    if login is not None:
        routes["login"] = login
    for name, value in (get_setting("ROUTES") or {}).items():
        value = _override(value)
        if value is None:
            routes.pop(name, None)
        else:
            routes[name] = value
    return routes


def ziggy_props(request, shared=None):
    """
    The ``ziggy`` prop: this package's routes, with a host-shared ``ziggy``
    (``shared``) merged over it name by name, and its other keys kept.
    """
    origin = f"{request.scheme}://{request.get_host()}"
    ziggy = {
        "url": origin,
        "port": None,
        "defaults": {},
        "routes": escalated_routes(),
        "location": request.build_absolute_uri(),
    }
    if callable(shared):
        shared = shared()
    if isinstance(shared, dict):
        routes = {**ziggy["routes"], **(shared.get("routes") or {})}
        ziggy = {**ziggy, **shared, "routes": routes}
    return ziggy


def share_ziggy(request):
    """Share the ``ziggy`` prop on this request, keeping what the host shared."""
    from inertia import share

    shared = request.inertia.all().get("ziggy") if hasattr(request, "inertia") else None
    share(request, ziggy=ziggy_props(request, shared))


def _clear_cache(**kwargs):
    if kwargs.get("setting") in ("ROOT_URLCONF", "FORCE_SCRIPT_NAME"):
        _cache.clear()


setting_changed.connect(_clear_cache)


# Installs window.route() unless the host already has one. Reads the table from
# window.Ziggy first, then the page's ziggy prop. An unknown name warns and
# returns '#'. Same semantics as escalated-nestjs's built-in helper.
ROUTE_HELPER = r"""(function () {
  if (typeof window.route === 'function') return;
  function table() {
    try {
      var el = document.querySelector('script[data-page]');
      var page = el ? JSON.parse(el.textContent) : JSON.parse(document.getElementById('app').dataset.page);
      return (page.props && page.props.ziggy) || {};
    } catch (e) { return {}; }
  }
  var ziggy = table();
  window.route = function (name, params) {
    var routes = (window.Ziggy && window.Ziggy.routes) || ziggy.routes || {};
    var route = routes[name];
    if (!route) {
      if (window.console) console.warn('[escalated] no route named ' + name);
      return '#';
    }
    var list = params == null ? []
      : (Array.isArray(params) ? params.slice() : (typeof params === 'object' ? null : [params]));
    var query = {};
    if (list === null) { for (var k in params) query[k] = params[k]; }
    var uri = route.uri.replace(/\{(\w+)\??\}/g, function (_, key) {
      var value;
      if (list !== null) { value = list.shift(); }
      else { value = query[key]; delete query[key]; }
      if (value != null && typeof value === 'object') value = value.reference != null ? value.reference : value.id;
      return value == null ? '' : encodeURIComponent(value);
    });
    var search = Object.keys(query).filter(function (key) { return query[key] != null; })
      .map(function (key) { return encodeURIComponent(key) + '=' + encodeURIComponent(query[key]); }).join('&');
    return '/' + uri + (search ? '?' + search : '');
  };
})();"""
