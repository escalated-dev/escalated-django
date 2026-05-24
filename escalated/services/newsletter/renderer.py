"""Renders a NewsletterDelivery to themed HTML.

Hosts plug in a Markdown converter via ``ESCALATED["newsletter_markdown_renderer"]``
(any callable taking ``str -> str``). When unset, a minimal escape+paragraph
fallback is used. Themes are Django templates at
``escalated/newsletter_themes/<slug>.html``.
"""

from __future__ import annotations

import base64
import html
import re
from collections.abc import Callable
from urllib.parse import urlparse

from django.conf import settings
from django.template.loader import get_template

ALLOWED_SCHEMES = {"http", "https", "mailto", "tel"}


def _conf(key: str, default=None):
    return (getattr(settings, "ESCALATED", {}) or {}).get(key, default)


class NewsletterRenderer:
    def render(self, delivery) -> str:
        n = delivery.newsletter
        contact = delivery.contact
        body_md = n.body_markdown or (n.template.body_markdown if n.template_id and n.template else "")
        theme_slug = (
            n.theme
            or (n.template.theme if n.template_id and n.template else None)
            or _conf("newsletter_default_theme", "default")
        )

        body = self._markdown_to_html(body_md or "")
        body = self._resolve_merge_fields(body, contact, delivery)

        themed = self._render_theme(
            theme_slug,
            {
                "subject": n.subject,
                "body": body,
                "unsubscribe_url": self.unsubscribe_url(delivery),
                "view_in_browser_url": self.view_in_browser_url(delivery),
                "brand": self._brand(),
            },
        )

        if not _conf("newsletter_tracking_enabled", True):
            return themed

        themed = self._rewrite_links(themed, delivery)
        return self._inject_pixel(themed, delivery)

    def unsubscribe_url(self, delivery) -> str:
        return f"{self._base_url()}/escalated/n/u/{delivery.tracking_token}"

    def view_in_browser_url(self, delivery) -> str:
        return f"{self._base_url()}/escalated/n/v/{delivery.tracking_token}"

    # -----

    def _base_url(self) -> str:
        return (_conf("app_url", "http://localhost") or "http://localhost").rstrip("/")

    def _brand(self) -> dict:
        return {
            "name": _conf("app_name", "Support"),
            "accent": _conf("newsletter_brand_accent", "#2563eb"),
            "logo_url": _conf("newsletter_brand_logo_url"),
            "physical_address": _conf("newsletter_brand_physical_address"),
        }

    def _markdown_to_html(self, md: str) -> str:
        renderer: Callable[[str], str] | None = _conf("newsletter_markdown_renderer")
        if callable(renderer):
            return renderer(md)
        escaped = html.escape(md)
        paragraphs = escaped.split("\n\n")
        return "<p>" + "</p><p>".join(paragraphs) + "</p>"

    def _resolve_merge_fields(self, body: str, contact, delivery) -> str:
        def repl(match: re.Match[str]) -> str:
            path = match.group(1).strip()
            return html.escape(self._resolve_path(path, contact, delivery))

        return re.sub(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}", repl, body)

    def _resolve_path(self, path: str, contact, delivery) -> str:
        if path == "contact.name":
            return contact.name or ""
        if path == "contact.first_name":
            return (contact.name or "").split(" ")[0] if contact.name else ""
        if path == "contact.email":
            return contact.email or ""
        if path == "unsubscribe_url":
            return self.unsubscribe_url(delivery)
        if path == "view_in_browser_url":
            return self.view_in_browser_url(delivery)
        if path.startswith("contact.metadata."):
            key = path.split(".", 2)[2]
            return str((contact.metadata or {}).get(key, ""))
        return ""

    def _render_theme(self, slug: str, ctx: dict) -> str:
        try:
            template = get_template(f"escalated/newsletter_themes/{slug}.html")
        except Exception:
            template = get_template("escalated/newsletter_themes/default.html")
        return template.render(ctx)

    def _rewrite_links(self, body: str, delivery) -> str:
        unsub = self.unsubscribe_url(delivery)
        view = self.view_in_browser_url(delivery)

        def repl(match: re.Match[str]) -> str:
            attr_prefix, quote, href = match.group(1), match.group(2), match.group(3)
            if not href or href.startswith("#"):
                return match.group(0)
            scheme = urlparse(href).scheme.lower()
            if scheme not in ALLOWED_SCHEMES:
                return f"{attr_prefix}{quote}#{quote}"
            if scheme in {"mailto", "tel"}:
                return match.group(0)
            if href.startswith(unsub) or href.startswith(view):
                return match.group(0)
            encoded = base64.urlsafe_b64encode(href.encode()).decode().rstrip("=")
            tracked = f"{self._base_url()}/escalated/n/c/{delivery.tracking_token}?u={encoded}"
            return f"{attr_prefix}{quote}{tracked}{quote}"

        return re.sub(r'(<a\s[^>]*\bhref=)(["\'])(.*?)\2', repl, body, flags=re.IGNORECASE)

    def _inject_pixel(self, body: str, delivery) -> str:
        url = f"{self._base_url()}/escalated/n/o/{delivery.tracking_token}.gif"
        pixel = f'<img src="{html.escape(url)}" width="1" height="1" alt="" />'
        if "</body>" in body:
            return body.replace("</body>", f"{pixel}</body>")
        return body + pixel
