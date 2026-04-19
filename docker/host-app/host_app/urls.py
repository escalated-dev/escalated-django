from django.contrib import admin
from django.urls import include, path

from . import demo_views

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("demo", demo_views.picker, name="demo_picker"),
    path("demo/login/<int:user_id>", demo_views.login_as, name="demo_login"),
    path("demo/logout", demo_views.logout_view, name="demo_logout"),
    path("", demo_views.home, name="home"),
    path("support/", include("escalated.urls")),
]
