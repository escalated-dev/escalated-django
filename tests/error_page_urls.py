"""URLs for tests/integration/test_inertia_error_page.py: the package, plus
stand-in Escalated routes for failures the suite cannot otherwise provoke, and
one host route."""

from django.http import HttpResponse, HttpResponseNotFound
from django.urls import include, path


def _raise(request):
    raise RuntimeError("relation escalated_secret_table does not exist")


def _status(code):
    return lambda request: HttpResponse("upstream detail", status=code)


probe_patterns = (
    [
        path("419/", _status(419), name="probe_419"),
        path("429/", _status(429), name="probe_429"),
        path("500/", _raise, name="probe_500"),
        path("503/", _status(503), name="probe_503"),
    ],
    "escalated",
)

urlpatterns = [
    path("support/", include("escalated.urls")),
    path("support/probe/", include(probe_patterns, namespace="escalated_probe")),
    path("host/missing/", lambda request: HttpResponseNotFound("host page"), name="host_missing"),
]
