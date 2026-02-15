from django.urls import include, path

urlpatterns = [
    path("support/", include("escalated.urls")),
]
