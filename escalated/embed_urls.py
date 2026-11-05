"""
The URLconf for a host that embeds Escalated's admin in its own admin panel
(optional; ADR 2026-11-05-embeddable-admin, docs/embedding-admin.md).

Include it at the site root in place of ``escalated.urls``::

    urlpatterns = [
        # path("support/", include("escalated.urls")),  # the standalone admin
        path("", include("escalated.embed_urls")),
    ]

It serves everything ``escalated.urls`` does under ``ESCALATED["ROUTE_PREFIX"]``
(``support/``), except the admin, which it serves under
``ESCALATED["EMBED"]["PREFIX"]`` (``admin/support/``) with the same URL names.
With embedding off it is the same as ``path("support/", include("escalated.urls"))``.
"""

from django.urls import include, path

from escalated import embed
from escalated import urls as escalated_urls
from escalated.conf import get_setting

app_name = "escalated"

_route_prefix = str(get_setting("ROUTE_PREFIX") or "").strip("/")

urlpatterns = []
if escalated_urls.embedded_admin_patterns:
    urlpatterns.append(path(f"{embed.prefix()}/", include(list(escalated_urls.embedded_admin_patterns))))
urlpatterns.append(path(f"{_route_prefix}/" if _route_prefix else "", include(list(escalated_urls.urlpatterns))))
