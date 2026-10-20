import pytest
from django.test import RequestFactory

from escalated.models import EscalatedSetting
from escalated.widget_embed import WidgetOrigins

pytestmark = pytest.mark.usefixtures("widget_on")


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        ("https://Shop.Example.com", "https://shop.example.com"),
        ("https://shop.example.com/", "https://shop.example.com"),
        ("https://shop.example.com:443", "https://shop.example.com"),
        ("http://localhost:5173", "http://localhost:5173"),
        ("https://*.example.com", "https://*.example.com"),
        ("https://*.example.com:8443", "https://*.example.com:8443"),
        ("https://shop.example.com/checkout", None),
        ("https://shop.example.com?x=1", None),
        ("shop.example.com", None),
        ("*", None),
        ("https://*", None),
        ("https://a.*.example.com", None),
        ("ftp://shop.example.com", None),
        ("https://user@shop.example.com", None),
    ],
)
def test_normalises_admin_entered_origins_and_rejects_anything_else(entry, expected):
    assert WidgetOrigins.normalize_pattern(entry) == expected


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("origin", "allowed"),
    [
        ("https://shop.example.com", True),
        ("https://SHOP.example.com:443", True),
        ("http://shop.example.com", False),
        ("https://shop.example.com:8443", False),
        ("https://help.brand.test", True),
        ("https://a.b.brand.test", True),
        ("https://brand.test", False),
        ("https://notbrand.test", False),
        ("https://help.brand.test.evil.com", False),
        ("http://localhost:5173", True),
        ("http://localhost", False),
        ("null", False),
    ],
)
def test_matches_exact_origins_ports_and_subdomain_wildcards(settings, origin, allowed):
    settings.ESCALATED = {
        **settings.ESCALATED,
        "WIDGET_ALLOWED_ORIGINS": ["https://shop.example.com", "https://*.brand.test", "http://localhost:5173"],
    }

    assert WidgetOrigins.allows(origin) is allowed


@pytest.mark.django_db
def test_merges_the_config_list_with_the_admin_setting(settings):
    settings.ESCALATED = {**settings.ESCALATED, "WIDGET_ALLOWED_ORIGINS": ["https://shop.example.com"]}
    EscalatedSetting.set("widget_allowed_origins", "https://blog.example.com, https://bad.example.com/path\n")

    assert WidgetOrigins.configured() == ["https://shop.example.com", "https://blog.example.com"]


@pytest.mark.django_db
def test_config_list_may_be_a_comma_separated_string(settings):
    settings.ESCALATED = {
        **settings.ESCALATED,
        "WIDGET_ALLOWED_ORIGINS": "https://shop.example.com, https://*.brand.test",
    }

    assert WidgetOrigins.configured() == ["https://shop.example.com", "https://*.brand.test"]


@pytest.mark.parametrize(
    ("origin", "expected"),
    [
        (None, None),
        ("null", None),
        ("https://help.example.com", None),
        ("https://help.example.com:443", None),
        ("https://shop.example.com", "https://shop.example.com"),
        ("http://help.example.com", "http://help.example.com"),
    ],
)
def test_only_reports_an_origin_that_names_another_site(settings, origin, expected):
    settings.ALLOWED_HOSTS = ["help.example.com"]
    extra = {"HTTP_ORIGIN": origin} if origin is not None else {}
    request = RequestFactory().get("/support/widget/config/", secure=True, HTTP_HOST="help.example.com", **extra)

    assert WidgetOrigins.cross_origin(request) == expected
