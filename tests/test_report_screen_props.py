"""The report screens are handed the props they actually read.

A page name that resolves is not a screen that works. Inertia passes props by
name, and a name the component does not declare is not passed at all -- it lands
on the root element as an attribute. The screen renders its defaults, which for
a report is zeroes and empty charts, on a 200, and that is indistinguishable
from a quiet period.

Every view in ``advanced_reports`` used to send ``{"data": ..., "filters": ...}``,
which no report component reads. All nine screens were empty, and six of them
rendered page names the frontend does not ship at all.

The manifest at tests/fixtures/escalated-pages.json publishes what each
component declares. This asserts the response against it, in both directions.
"""

import json
from pathlib import Path

import pytest
from django.urls import reverse

MANIFEST = Path(__file__).resolve().parent / "fixtures" / "escalated-pages.json"

# Inertia shares these with every page; they are not a screen's own business and
# no component declares them.
SHARED_PROPS = {"errors", "auth", "current_user", "flash", "escalated", "plugin_ui"}

SCREENS = [
    ("escalated:admin_reports_sla_trends", "Escalated/Admin/Reports/SlaTrends"),
    ("escalated:admin_reports_response_times", "Escalated/Admin/Reports/ResponseTimes"),
    ("escalated:admin_reports_resolution_times", "Escalated/Admin/Reports/ResolutionTimes"),
    ("escalated:admin_reports_agent_ranking", "Escalated/Admin/Reports/AgentRanking"),
    ("escalated:admin_reports_cohorts", "Escalated/Admin/Reports/Cohorts"),
    ("escalated:admin_reports_comparison", "Escalated/Admin/Reports/Comparison"),
]

REDIRECTS = [
    ("escalated:admin_reports_frt_distribution", "escalated:admin_reports_response_times"),
    ("escalated:admin_reports_frt_trends", "escalated:admin_reports_response_times"),
    ("escalated:admin_reports_frt_by_agent", "escalated:admin_reports_response_times"),
    ("escalated:admin_reports_resolution_distribution", "escalated:admin_reports_resolution_times"),
    ("escalated:admin_reports_resolution_trends", "escalated:admin_reports_resolution_times"),
    ("escalated:admin_reports_cohort", "escalated:admin_reports_cohorts"),
]


def manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def get_screen(client, route):
    """Ask for the JSON form of the page.

    The full-page render needs INERTIA_LAYOUT, which the test settings do not
    set, and it is not what is being checked here -- the props are the same
    either way. The request carries no asset version, which matches the default
    and so avoids the 409 that would read here as a screen sending no props.
    """
    response = client.get(reverse(route), HTTP_X_INERTIA="true")

    assert response.status_code == 200, f"{route} answered {response.status_code}"

    return json.loads(response.content)


@pytest.mark.django_db
@pytest.mark.parametrize(("route", "page"), SCREENS)
def test_sends_every_prop_the_screen_declares_and_nothing_it_does_not(client, admin_user, route, page):
    client.force_login(admin_user)

    body = get_screen(client, route)

    assert body["component"] == page

    declared = manifest()["props"][page]["props"]
    sent = set(body["props"]) - SHARED_PROPS

    missing = sorted(set(declared) - sent)
    unread = sorted(sent - set(declared))

    assert missing == [], (
        f"{page} declares props this response never sends, so they render as their defaults:\n  " + "\n  ".join(missing)
    )
    assert unread == [], (
        f"{page} is sent props it does not declare, so they are dropped on the root element:\n  " + "\n  ".join(unread)
    )


@pytest.mark.django_db
@pytest.mark.parametrize(("route", "target"), REDIRECTS)
def test_still_answers_the_paths_that_are_now_other_screens(client, admin_user, route, target):
    # They were in the URLs long enough to be linked, so they redirect rather
    # than 404.
    client.force_login(admin_user)

    response = client.get(reverse(route))

    assert response.status_code == 302
    assert response["Location"] == reverse(target)


def test_the_manifest_describes_props_at_all():
    # A fixture that lost its props would make every case above pass by
    # comparing two empty sets.
    data = manifest()

    assert "props" in data
    assert len(data["props"]) > 50
    assert data["props"]["Escalated/Admin/Reports/AgentRanking"]["props"] == ["agents", "period_days"]
