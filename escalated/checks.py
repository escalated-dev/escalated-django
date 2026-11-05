"""System checks for embedding the admin in the host's admin panel (ADR 2026-11-05)."""

from django.conf import settings
from django.core.checks import Warning, register

EMBED_MIDDLEWARE = "escalated.middleware.EscalatedEmbedMiddleware"


@register()
def check_embed(app_configs, **kwargs):
    from escalated import embed

    if not embed.enabled():
        return []

    warnings = []
    if not _admin_is_mounted():
        warnings.append(
            Warning(
                "Embedding the admin is on, but the admin is not mounted under ESCALATED['EMBED']['PREFIX'].",
                hint='Include escalated.embed_urls at the site root: path("", include("escalated.embed_urls")), '
                'in place of path("support/", include("escalated.urls")).',
                id="escalated.W001",
            )
        )
    if embed.mode() == "iframe" and list(getattr(settings, "MIDDLEWARE", []))[:1] != [EMBED_MIDDLEWARE]:
        warnings.append(
            Warning(
                "iframe mode: add escalated.middleware.EscalatedEmbedMiddleware first in MIDDLEWARE.",
                hint="It sets the frame-ancestors policy after every other middleware, so none can undo it.",
                id="escalated.W002",
            )
        )
    return warnings


def _admin_is_mounted() -> bool:
    from django.urls import NoReverseMatch, reverse

    from escalated import embed
    from escalated import urls as escalated_urls

    for pattern in escalated_urls.embedded_admin_patterns[:1]:
        try:
            return reverse(f"escalated:{pattern.name}").startswith(embed.base_url() + "/")
        except NoReverseMatch:
            return False
    return True
