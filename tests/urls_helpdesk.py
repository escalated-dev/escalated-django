"""A host that mounts Escalated somewhere other than /support/."""

from django.urls import include, path

urlpatterns = [
    path("helpdesk/", include("escalated.urls")),
]
