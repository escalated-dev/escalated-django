# Newsletters

## Newsletters (optional, disabled by default)

Admin-only broadcast feature for sending Markdown emails to contacts. Off by default — set `ESCALATED["enable_newsletters"] = True` to turn it on.

```python
# settings.py
ESCALATED = {
    "enable_newsletters": True,
    "app_url": "https://support.example.com",
    "newsletter_default_from": "hi@example.com",
    "newsletter_default_theme": "default",
    "newsletter_brand_accent": "#2563eb",
    "newsletter_brand_physical_address": "Acme Inc. · 123 Main St · Springfield USA",
    # Plug in a Markdown converter (markdown package, mistune, etc.)
    "newsletter_markdown_renderer": lambda md: __import__("markdown").markdown(md),
}
```

Schedule the dispatcher every minute (Celery beat, django-q, cron, etc.):

```python
from escalated.services.newsletter import NewsletterDispatcher

NewsletterDispatcher().dispatch_batch()
```

Custom themes go in `escalated/templates/escalated/newsletter_themes/<slug>.html`. The context receives `subject`, `body` (pre-rendered safe HTML), `unsubscribe_url`, `view_in_browser_url`, and `brand`.
