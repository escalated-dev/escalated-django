# Getting started

## Requirements

- Python 3.10+
- Django 5.2+
- Node.js 18+ (for frontend assets)

## Quick Start

```bash
pip install escalated-django
npm install @escalated-dev/escalated
```

### 1. Add to INSTALLED_APPS

```python
INSTALLED_APPS = [
    # ...
    "django.contrib.contenttypes",
    "inertia",
    "escalated",
]
```

### 2. Include URLs

```python
from django.urls import path, include

urlpatterns = [
    # ...
    path("support/", include("escalated.urls")),
]
```

### 3. Run migrations

```bash
python manage.py migrate escalated
```

Visit `/support` — you're live.

## Embedding the admin in your own admin panel (optional)

Escalated's standalone admin at `/support/admin/` is the default and needs no
setup. If your project already has an admin panel or back office, you can
instead mount Escalated's admin screens under your own prefix and view
decorators, render them inside your Vue + Inertia layout or your own Django
template (or an allow-listed iframe), and list Escalated's menu in your own
sidebar. It is off unless you turn it on:

```python
# settings.py
from escalated.embed import embed_admin

ESCALATED = {
    # ...
    "EMBED": embed_admin(
        prefix="admin/support",
        middleware=["django.contrib.admin.views.decorators.staff_member_required"],
        layout="Layouts/AdminLayout",
    ),
}

# urls.py: in place of path("support/", include("escalated.urls"))
urlpatterns = [path("", include("escalated.embed_urls"))]
```

URL names stay the same, Escalated's admin gate stays on unless you replace it,
and the agent panel, customer portal, widget and API do not move. See
[embedding the admin](embedding-admin.md).
