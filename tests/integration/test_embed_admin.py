"""
The admin embedded in the host's own admin panel (ADR
2026-11-05-embeddable-admin): the admin URLs move under the host's prefix and
view decorators with the same names, Escalated's admin gate stays unless the
host replaces it, embedded pages carry ``escalated.embed``, every page carries
the admin menu as ``escalated.navigation``, the root view switches on embedded
pages only, and iframe mode allows the listed origins to frame them.

Every test goes through Django's router and middleware with the test client.
"""

import json
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse

from escalated import embed
from escalated.access import mapped_permissions
from escalated.models import EscalatedSetting, Permission, Role
from escalated.plugin_ui_service import plugin_ui
from escalated.route_list import escalated_routes
from tests.embed_host import (
    EMBED_MIDDLEWARE,
    SHARE,
    TEMPLATES_DIR,
    embedded,
)
from tests.factories import DepartmentFactory, UserFactory
from tests.route_table import route_table

pytestmark = pytest.mark.django_db

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "embed" / "default-routes.json"
INERTIA = {"HTTP_X_INERTIA": "true"}
BASE_MIDDLEWARE = [
    "django.middleware.common.CommonMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    SHARE,
]
HOST = "tests.embed_host.host_admin"
LAYOUT = {
    "PREFIX": "backoffice/helpdesk",
    "MIDDLEWARE": [HOST],
    "LAYOUT": "Layouts/AdminLayout",
}

# The admin URLs that stay where they are (ADR "What does not move"): the
# newsletter admin and the personal two-factor enrolment screens.
STAYS = ("escalated:admin_newsletters_", "escalated:admin_settings_two_factor", "escalated:admin_two_factor_")

_seq = iter(range(100_000))


def admin(**extra):
    return UserFactory(username=f"emb-admin{next(_seq)}", is_staff=True, is_superuser=True, first_name="Ann", **extra)


def agent(**extra):
    user = UserFactory(username=f"emb-agent{next(_seq)}", first_name="Al", **extra)
    DepartmentFactory().agents.add(user)
    return user


def props(response):
    assert response.status_code == 200, response.content[:300]
    return json.loads(response.content)["props"]


@pytest.fixture
def layout_mode():
    with embedded(middleware=BASE_MIDDLEWARE, **LAYOUT):
        yield


@pytest.fixture(autouse=True)
def _no_plugin_items():
    plugin_ui.clear()
    yield
    plugin_ui.clear()


# --- Routes -------------------------------------------------------------------


def test_mounts_the_admin_under_the_host_prefix_with_the_host_decorators(client, layout_mode):
    client.force_login(admin())

    response = client.get("/backoffice/helpdesk/tags/", **INERTIA)

    assert response.status_code == 200
    assert response["X-Host-Admin"] == "1"
    assert json.loads(response.content)["component"] == "Escalated/Admin/Tags/Index"
    assert reverse("escalated:admin_tags_index") == "/backoffice/helpdesk/tags/"


def test_the_host_decorators_run_first_and_can_refuse(client, layout_mode):
    assert client.get("/backoffice/helpdesk/tags/", **INERTIA).status_code == 401

    client.force_login(admin())
    # A plain request: an Inertia visit gets the shared Escalated/Error page.
    refused = client.get("/backoffice/helpdesk/tags/", HTTP_X_HOST_DENY="1")

    assert refused.status_code == 403
    assert refused.content == b"Refused by the host."


def test_no_longer_serves_the_standalone_admin_urls(client, layout_mode):
    client.force_login(admin())

    assert client.get("/support/admin/tags/", **INERTIA).status_code == 404
    assert client.get("/support/admin/reports/", **INERTIA).status_code == 404
    assert client.get("/support/admin/api-tokens/", **INERTIA).status_code == 404


def test_moves_every_admin_url_keeping_its_name_view_and_guards(layout_mode):
    before = json.loads(FIXTURE.read_text(encoding="utf-8"))
    after = {row["name"]: row for row in json.loads(json.dumps(route_table()))}

    moved = 0
    for row in before:
        live = after.pop(row["name"])
        if row["path"].startswith("support/admin/") and not row["name"].startswith(STAYS):
            moved += 1
            assert live["path"] == "backoffice/helpdesk/" + row["path"][len("support/admin/") :], row["name"]
            # The embed layer outermost, then exactly the guards it had.
            assert live["layers"] == ["escalated/embed.py:embedded", *row["layers"]], row["name"]
            assert {**live, "path": row["path"], "layers": row["layers"]} == row
        else:
            assert live == row, row["name"]

    assert moved > 150
    assert after == {}, f"routes that did not exist before: {sorted(after)}"


def test_the_route_table_the_frontend_reads_follows_the_move(layout_mode):
    routes = escalated_routes()

    assert routes["escalated.admin.tags.index"]["uri"] == "backoffice/helpdesk/tags/"
    assert routes["escalated.admin.tickets.show"]["uri"] == "backoffice/helpdesk/tickets/{ticket}/"
    assert routes["escalated.admin.plugins.index"]["uri"] == "backoffice/helpdesk/plugins/"
    assert routes["escalated.agent.tickets.index"]["uri"] == "support/agent/tickets/"
    assert routes["escalated.admin.two-factor.index"]["uri"] == "support/admin/settings/two-factor/"


def test_leaves_the_agent_panel_customer_guest_widget_and_api_urls_alone(client, layout_mode):
    assert reverse("escalated:agent_dashboard") == "/support/agent/"
    assert reverse("escalated:customer_ticket_list") == "/support/tickets/"
    assert reverse("escalated:guest_ticket_create") == "/support/guest/create/"
    assert reverse("escalated:widget_config") == "/support/widget/config/"
    assert reverse("escalated:admin_newsletters_index") == "/support/admin/newsletters/"
    assert reverse("escalated:escalated_api:ticket_list").startswith("/support/support/api/v1/")

    staff = agent()
    client.force_login(staff)
    assert client.get("/support/agent/", **INERTIA).status_code == 200


def test_keeps_escalateds_admin_gate(client, layout_mode):
    client.force_login(agent())

    assert client.get("/backoffice/helpdesk/tags/", **INERTIA).status_code == 403


def test_keeps_route_permissions(client):
    call_command("seed_permissions", verbosity=0)
    with embedded(middleware=BASE_MIDDLEWARE, extra={"ACCESS": {"roles_permissions": True}}, **LAYOUT):
        user = admin()
        role = Role.objects.create(name="Tag keeper", slug="tag-keeper")
        role.permissions.set(Permission.objects.filter(slug__in=["tag.view", "ticket.view"]))
        role.users.add(user)
        client.force_login(user)

        assert client.get("/backoffice/helpdesk/tags/", **INERTIA).status_code == 200
        assert client.get("/backoffice/helpdesk/settings/", **INERTIA).status_code == 403


# --- Shared props -------------------------------------------------------------


def test_shares_the_embed_flag_on_embedded_pages(client, layout_mode):
    client.force_login(admin())

    shared = props(client.get("/backoffice/helpdesk/tags/", **INERTIA))["escalated"]

    assert shared["embed"] == {
        "enabled": True,
        "mode": "layout",
        "layout": "Layouts/AdminLayout",
        "route": "escalated.admin.tags.index",
        "base_url": "/backoffice/helpdesk",
        "allowed_origins": [],
    }


def test_the_embed_route_is_the_frontend_name_for_pages_with_parameters(client, layout_mode):
    from tests.factories import TicketFactory

    ticket = TicketFactory()
    client.force_login(admin())

    shared = props(client.get(f"/backoffice/helpdesk/tickets/{ticket.reference}/", **INERTIA))["escalated"]

    assert shared["embed"]["route"] == "escalated.admin.tickets.show"


def test_marks_other_pages_as_not_embedded_but_still_shares_the_menu(client, layout_mode):
    user = admin()
    DepartmentFactory().agents.add(user)
    client.force_login(user)

    shared = props(client.get("/support/agent/", **INERTIA))["escalated"]

    assert shared["embed"]["enabled"] is False
    assert shared["embed"]["route"] is None
    assert shared["embed"]["base_url"] == "/backoffice/helpdesk"
    assert shared["navigation"][0]["key"] == "reports"


def test_shares_the_admin_menu_in_the_documented_shape_and_order(client, layout_mode):
    client.force_login(admin())

    navigation = props(client.get("/backoffice/helpdesk/tags/", **INERTIA))["escalated"]["navigation"]

    assert navigation[0] == {
        "key": "reports",
        "label": "Reports",
        "route": "escalated.admin.reports",
        "url": "/backoffice/helpdesk/reports/",
        "icon": "reports",
        "position": 10,
        "active": False,
        "badge": None,
        "plugin": None,
        "children": [],
    }
    assert navigation[1]["key"] == "tickets"
    assert [item["key"] for item in navigation if item["active"]] == ["tags"]
    positions = [item["position"] for item in navigation]
    assert positions == sorted(positions)
    assert navigation[-1]["key"] == "settings"
    assert {item["key"]: item["route"] for item in navigation}["knowledge-base"] == "escalated.admin.kb-articles.index"


def test_marks_the_section_active_below_its_url(client, layout_mode):
    client.force_login(admin())

    navigation = props(client.get("/backoffice/helpdesk/tags/create/", **INERTIA, follow=False))
    active = [item["key"] for item in navigation["escalated"]["navigation"] if item["active"]]

    assert active == ["tags"]


def test_leaves_out_screens_whose_feature_is_off(layout_mode):
    keys = [item["key"] for item in embed.admin_navigation(admin())]

    # Roles & permissions and newsletters are off by default; the API is on in
    # the test settings, plugins are on by default.
    assert "roles" not in keys
    assert "newsletters" not in keys
    assert {"tags", "settings", "api-tokens", "plugins", "knowledge-base"} <= set(keys)

    EscalatedSetting.set("knowledge_base_enabled", "0")
    assert "knowledge-base" not in [item["key"] for item in embed.admin_navigation(admin())]


def test_lists_newsletters_and_roles_while_their_features_are_on():
    extra = {"enable_newsletters": True, "ACCESS": {"roles_permissions": True}}
    call_command("seed_permissions", verbosity=0)
    with embedded(middleware=BASE_MIDDLEWARE, extra=extra, **LAYOUT):
        user = admin()
        Role.objects.get(slug="admin").users.add(user)
        keys = [item["key"] for item in embed.admin_navigation(user)]

    assert "newsletters" in keys
    assert "roles" in keys


def test_filters_the_menu_by_route_permission_while_roles_and_permissions_is_on():
    call_command("seed_permissions", verbosity=0)
    with embedded(middleware=BASE_MIDDLEWARE, extra={"ACCESS": {"roles_permissions": True}}, **LAYOUT):
        user = admin()
        role = Role.objects.create(name="Tag keeper", slug="tag-keeper")
        role.permissions.set(Permission.objects.filter(slug__in=["tag.view", "ticket.view"]))
        role.users.add(user)

        keys = [item["key"] for item in embed.admin_navigation(user)]

    assert "settings" in [item[0] for item in embed.NAVIGATION]
    assert mapped_permissions("admin_settings") == ["settings.view"]
    assert {"tags", "tickets"} <= set(keys)
    assert "settings" not in keys
    assert "users" not in keys
    assert "roles" not in keys


def test_gives_no_menu_to_a_user_who_may_not_use_the_admin(client, layout_mode):
    staff = agent()

    assert embed.admin_navigation(staff) == []
    assert embed.admin_navigation(None) == []

    client.force_login(staff)
    assert props(client.get("/support/agent/", **INERTIA))["escalated"]["navigation"] == []


def test_includes_plugin_admin_menu_items_in_position_order(layout_mode):
    plugin_ui.add_menu_item(
        {
            "label": "CRM",
            "url": "/backoffice/helpdesk/crm/",
            "icon": "crm",
            "position": 61,
            "target": "admin",
            "plugin": "crm",
            "badge": 3,
            "submenu": [{"label": "Leads", "url": "/backoffice/helpdesk/crm/leads/"}],
        }
    )
    plugin_ui.add_menu_item({"label": "Agent only", "url": "/x/", "target": "agent", "position": 1})

    items = embed.admin_navigation(admin())
    keys = [item["key"] for item in items]
    crm = next(item for item in items if item["label"] == "CRM")

    assert crm == {
        "key": "plugin:crm:0",
        "label": "CRM",
        "route": None,
        "url": "/backoffice/helpdesk/crm/",
        "icon": "crm",
        "position": 61,
        "active": False,
        "badge": 3,
        "plugin": "crm",
        "children": [{"label": "Leads", "url": "/backoffice/helpdesk/crm/leads/", "icon": None}],
    }
    assert keys.index("plugin:crm:0") == keys.index("tags") + 1
    assert "Agent only" not in [item["label"] for item in items]


def test_admin_navigation_works_without_embedding_too():
    items = embed.admin_navigation(admin())

    assert items[0]["url"] == "/support/admin/reports/"
    assert {item["key"]: item["url"] for item in items}["tags"] == "/support/admin/tags/"


def test_the_template_tag_renders_the_menu_for_the_request_user(rf, layout_mode):
    from django.template import Context, Template

    request = rf.get("/backoffice/helpdesk/macros/")
    request.user = admin()

    html = Template(
        "{% load escalated_embed %}{% escalated_admin_navigation as menu %}"
        "{% for item in menu %}{% if item.active %}[{{ item.label }}]{% endif %}{{ item.url }};{% endfor %}"
    ).render(Context({"request": request}))

    assert "[Macros]/backoffice/helpdesk/macros/;" in html
    assert "/backoffice/helpdesk/reports/;" in html


# --- The host replaces the admin gate -------------------------------------------


@pytest.fixture
def host_gate():
    config = {**LAYOUT, "MIDDLEWARE": ["tests.embed_host.host_backoffice_only"], "REPLACE_ADMIN_GATE": True}
    with embedded(middleware=BASE_MIDDLEWARE, **config):
        yield


def test_the_host_gate_alone_decides_who_reaches_the_admin(client, host_gate):
    backoffice = UserFactory(username="host-staff", first_name="Host")
    client.force_login(backoffice)

    assert client.get("/backoffice/helpdesk/tags/", **INERTIA).status_code == 200
    assert client.get("/backoffice/helpdesk/reports/", **INERTIA).status_code == 200
    assert [item["key"] for item in embed.admin_navigation(backoffice)][:2] == ["reports", "tickets"]

    client.force_login(admin())
    refused = client.get("/backoffice/helpdesk/tags/")
    assert refused.status_code == 403
    assert refused.content == b"Back office staff only."


def test_a_replaced_gate_keeps_route_permissions_and_the_agent_panels_gates(client):
    call_command("seed_permissions", verbosity=0)
    config = {**LAYOUT, "MIDDLEWARE": ["tests.embed_host.host_backoffice_only"], "REPLACE_ADMIN_GATE": True}
    with embedded(middleware=BASE_MIDDLEWARE, extra={"ACCESS": {"roles_permissions": True}}, **config):
        backoffice = UserFactory(username="host-noroles", first_name="Host")
        client.force_login(backoffice)

        # No Escalated role: route permissions still refuse.
        assert client.get("/backoffice/helpdesk/tags/", **INERTIA).status_code == 403
        # The agent panel still asks Escalated's own gates.
        assert client.get("/support/agent/", **INERTIA).status_code == 403
        # ...and so does `is_admin` in the shared props (the customer portal here).
        assert props(client.get("/support/tickets/", **INERTIA))["escalated"]["is_admin"] is False


def test_replacing_the_gate_needs_host_decorators():
    with pytest.raises(ImproperlyConfigured, match="MIDDLEWARE"):
        with embedded(middleware=BASE_MIDDLEWARE, PREFIX="backoffice/helpdesk", REPLACE_ADMIN_GATE=True):
            pass


# --- Root view (server-rendered host) -------------------------------------------


def _templates():
    import inertia

    # The test settings do not install the inertia app; hosts do.
    inertia_templates = Path(inertia.__file__).resolve().parent / "templates"
    return [
        {
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "DIRS": [str(TEMPLATES_DIR), str(inertia_templates)],
            "APP_DIRS": True,
            "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
        }
    ]


def test_uses_the_root_view_on_embedded_pages_only(client):
    # The setup docs/embedding-admin.md shows for a Django template host.
    config = embed.embed_admin(
        prefix="backoffice/helpdesk",
        middleware=["django.contrib.admin.views.decorators.staff_member_required"],
        root_view="backoffice/escalated.html",
    )
    with override_settings(TEMPLATES=_templates(), INERTIA_LAYOUT="backoffice/default_layout.html"):
        with embedded(middleware=BASE_MIDDLEWARE, **config):
            user = admin()
            DepartmentFactory().agents.add(user)
            client.force_login(user)

            page = client.get("/backoffice/helpdesk/macros/")
            other = client.get("/support/agent/")

    html = page.content.decode()
    assert page.status_code == 200
    assert "Host Back Office" in html
    assert 'class="active" aria-current="page">Macros</a>' in html
    assert 'href="/backoffice/helpdesk/reports/"' in html
    assert '"component": "Escalated/Admin/Macros/Index"' in html or "Escalated/Admin/Macros/Index" in html
    assert "default-inertia-layout" not in html

    assert other.status_code == 200
    assert "default-inertia-layout" in other.content.decode()
    assert "Host Back Office" not in other.content.decode()


# --- iframe mode ----------------------------------------------------------------


IFRAME_STACK = [
    EMBED_MIDDLEWARE,
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "tests.embed_host.HostFramingHeadersMiddleware",
    *BASE_MIDDLEWARE,
]


@pytest.fixture
def iframe_mode():
    config = {
        **LAYOUT,
        "MODE": "iframe",
        "FRAME_ANCESTORS": ["https://admin.example.com", "*", "https://*.example.com", "https://x.test/path"],
    }
    with embedded(middleware=IFRAME_STACK, **config):
        yield


def test_iframe_mode_lets_the_listed_origins_frame_embedded_pages(client, iframe_mode):
    client.force_login(admin())

    response = client.get("/backoffice/helpdesk/tags/", **INERTIA)

    assert response.status_code == 200
    assert not response.has_header("X-Frame-Options")
    policies = [policy.strip() for policy in response["Content-Security-Policy"].split(",")]
    assert policies == ["default-src 'self'", "frame-ancestors 'self' https://admin.example.com"]
    assert json.loads(response.content)["props"]["escalated"]["embed"]["allowed_origins"] == [
        "https://admin.example.com"
    ]
    assert json.loads(response.content)["props"]["escalated"]["embed"]["mode"] == "iframe"


def test_iframe_mode_leaves_every_other_response_alone(client, iframe_mode):
    user = admin()
    DepartmentFactory().agents.add(user)
    client.force_login(user)

    response = client.get("/support/agent/", **INERTIA)

    assert response["X-Frame-Options"] == "DENY"
    assert response["Content-Security-Policy"] == "default-src 'self'"


def test_iframe_headers_are_set_even_without_the_outer_middleware(client):
    config = {**LAYOUT, "MODE": "iframe", "FRAME_ANCESTORS": "https://admin.example.com, https://ops.example.com:8443"}
    stack = ["django.middleware.clickjacking.XFrameOptionsMiddleware", *BASE_MIDDLEWARE]
    with embedded(middleware=stack, **config):
        client.force_login(admin())
        response = client.get("/backoffice/helpdesk/tags/", **INERTIA)

    assert not response.has_header("X-Frame-Options")
    assert response["Content-Security-Policy"] == (
        "frame-ancestors 'self' https://admin.example.com https://ops.example.com:8443"
    )


def test_layout_mode_adds_no_framing_headers(client):
    stack = [EMBED_MIDDLEWARE, "django.middleware.clickjacking.XFrameOptionsMiddleware", *BASE_MIDDLEWARE]
    with embedded(middleware=stack, **LAYOUT):
        client.force_login(admin())
        response = client.get("/backoffice/helpdesk/tags/", **INERTIA)

    assert response["X-Frame-Options"] == "DENY"
    assert not response.has_header("Content-Security-Policy")


# --- Configuration ----------------------------------------------------------------


def test_is_off_by_default():
    assert embed.enabled() is False
    assert embed.config() == {
        "ENABLED": False,
        "MODE": "layout",
        "PREFIX": "admin/support",
        "MIDDLEWARE": None,
        "REPLACE_ADMIN_GATE": False,
        "LAYOUT": None,
        "ROOT_VIEW": None,
        "FRAME_ANCESTORS": [],
    }


def test_reads_the_environment_when_the_setting_leaves_a_key_out(monkeypatch):
    monkeypatch.setenv("ESCALATED_EMBED", "true")
    monkeypatch.setenv("ESCALATED_EMBED_MODE", "iframe")
    monkeypatch.setenv("ESCALATED_EMBED_PREFIX", "/ops/help/")
    monkeypatch.setenv("ESCALATED_EMBED_FRAME_ANCESTORS", "https://a.example, https://b.example")

    assert embed.enabled() is True
    assert embed.mode() == "iframe"
    assert embed.prefix() == "ops/help"
    assert embed.frame_ancestors() == ["https://a.example", "https://b.example"]

    with override_settings(ESCALATED={"EMBED": {"ENABLED": False, "mode": "layout"}}):
        assert embed.enabled() is False
        assert embed.mode() == "layout"


def test_embed_admin_builds_the_setting():
    assert embed.embed_admin(
        prefix="backoffice/helpdesk",
        middleware=["django.contrib.admin.views.decorators.staff_member_required"],
        layout="Layouts/AdminLayout",
        mode="iframe",
        frame_ancestors=["https://admin.example.com"],
    ) == {
        "ENABLED": True,
        "MODE": "iframe",
        "PREFIX": "backoffice/helpdesk",
        "MIDDLEWARE": ["django.contrib.admin.views.decorators.staff_member_required"],
        "REPLACE_ADMIN_GATE": False,
        "LAYOUT": "Layouts/AdminLayout",
        "ROOT_VIEW": None,
        "FRAME_ANCESTORS": ["https://admin.example.com"],
    }

    with pytest.raises(ValueError, match="mode"):
        embed.embed_admin(mode="popup")
    with pytest.raises(ValueError, match="middleware"):
        embed.embed_admin(replace_admin_gate=True)


def test_frame_ancestors_keeps_exact_http_origins_only():
    listed = [
        "https://admin.example.com",
        "https://Admin.Example.com/",
        "http://localhost:8000",
        "*",
        "https://*.example.com",
        "https://admin.example.com/path",
        "https://user:pw@admin.example.com",
        "javascript:alert(1)",
        "admin.example.com",
        "",
    ]
    with override_settings(ESCALATED={"EMBED": {"FRAME_ANCESTORS": listed}}):
        assert embed.frame_ancestors() == ["https://admin.example.com", "http://localhost:8000"]


def test_a_check_warns_when_embedding_is_on_but_the_admin_is_not_mounted():
    from escalated.checks import check_embed

    with embedded(middleware=BASE_MIDDLEWARE, urlconf="tests.urls", **LAYOUT):
        warnings = check_embed(None)

    assert [warning.id for warning in warnings] == ["escalated.W001"]


def test_a_check_warns_when_iframe_mode_misses_the_outer_middleware():
    from escalated.checks import check_embed

    with embedded(middleware=BASE_MIDDLEWARE, MODE="iframe", **LAYOUT):
        ids = [warning.id for warning in check_embed(None)]
    with embedded(middleware=[EMBED_MIDDLEWARE, *BASE_MIDDLEWARE], MODE="iframe", **LAYOUT):
        clean = check_embed(None)

    assert ids == ["escalated.W002"]
    assert clean == []


# --- SDK plugin admin pages ---------------------------------------------------------


class _Bridge:
    """A booted SDK bridge with one plugin page."""

    def get_plugin_urls(self):
        from escalated.bridge.route_registrar import RouteRegistrar

        registrar = RouteRegistrar(self)
        registrar.register_all({"crm": {"pages": [{"route": "settings", "component": "Settings"}]}})
        return registrar.get_url_patterns()


def test_sdk_plugin_admin_pages_move_with_the_admin():
    from unittest.mock import patch

    from tests.embed_host import reload_urls

    name = "escalated:escalated.plugin.crm.page.settings"
    try:
        with patch("escalated.bridge.plugin_bridge.get_bridge", return_value=_Bridge()):
            with embedded(middleware=BASE_MIDDLEWARE, **LAYOUT):
                embedded_url = reverse(name)
                rows = {row["name"]: row for row in route_table()}
            standalone_url = reverse(name)
    finally:
        # Rebuild the URLconf without the stand-in bridge.
        reload_urls()

    assert embedded_url == "/backoffice/helpdesk/plugins/crm/settings"
    assert rows[name]["layers"][0] == "escalated/embed.py:embedded"
    # Where the standalone admin has always put them (the package's own prefix
    # inside the include).
    assert standalone_url == "/support/support/admin/plugins/crm/settings"
