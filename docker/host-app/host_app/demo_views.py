import os

from django.contrib.auth import get_user_model, login, logout
from django.http import HttpResponse, HttpResponseNotFound
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods


def _is_demo() -> bool:
    return os.environ.get("APP_ENV") == "demo"


def home(request):
    if _is_demo():
        return redirect("demo_picker")
    return HttpResponse("Escalated Django demo host. Set APP_ENV=demo to enable /demo routes.", status=200)


def picker(request):
    if not _is_demo():
        return HttpResponseNotFound()
    User = get_user_model()
    users = User.objects.all().order_by("id")
    return render(request, "demo/picker.html", {"users": users})


@csrf_exempt
@require_http_methods(["POST"])
def login_as(request, user_id: int):
    if not _is_demo():
        return HttpResponseNotFound()
    User = get_user_model()
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return HttpResponseNotFound("No such demo user.")

    user.backend = "django.contrib.auth.backends.ModelBackend"
    login(request, user)
    if user.is_superuser or user.is_staff:
        return redirect("/support/admin/tickets/")
    return redirect("/support/tickets/")


@csrf_exempt
@require_http_methods(["POST"])
def logout_view(request):
    if not _is_demo():
        return HttpResponseNotFound()
    logout(request)
    return redirect("demo_picker")
