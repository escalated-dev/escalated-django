"""Newsletter route patterns (registered when enable_newsletters is True)."""

from django.urls import path

from escalated.views import (
    newsletter_admin,
    newsletter_lists,
    newsletter_public,
    newsletter_settings,
    newsletter_templates,
    newsletter_webhooks,
)

# Static segments before {newsletter} catch-all (contract route ordering).
admin_newsletter_patterns = [
    path("admin/newsletters/", newsletter_admin.index, name="admin_newsletters_index"),
    path("admin/newsletters/new/", newsletter_admin.create, name="admin_newsletters_create"),
    path("admin/newsletters/preview/", newsletter_admin.preview, name="admin_newsletters_preview"),
    path("admin/newsletters/test/", newsletter_admin.test_send, name="admin_newsletters_test"),
    path("admin/newsletters/lists/", newsletter_lists.index, name="admin_newsletters_lists_index"),
    path("admin/newsletters/lists/new/", newsletter_lists.create, name="admin_newsletters_lists_create"),
    path("admin/newsletters/lists/<int:list_id>/", newsletter_lists.show, name="admin_newsletters_lists_show"),
    path(
        "admin/newsletters/lists/<int:list_id>/members/",
        newsletter_lists.add_member,
        name="admin_newsletters_lists_members_add",
    ),
    path(
        "admin/newsletters/lists/<int:list_id>/members/<int:contact_id>/",
        newsletter_lists.remove_member,
        name="admin_newsletters_lists_members_remove",
    ),
    path(
        "admin/newsletters/lists/<int:list_id>/import/",
        newsletter_lists.import_csv,
        name="admin_newsletters_lists_import",
    ),
    path("admin/newsletters/templates/", newsletter_templates.index, name="admin_newsletters_templates_index"),
    path("admin/newsletters/templates/new/", newsletter_templates.create, name="admin_newsletters_templates_create"),
    path(
        "admin/newsletters/templates/<int:template_id>/",
        newsletter_templates.show,
        name="admin_newsletters_templates_show",
    ),
    path("admin/newsletters/settings/", newsletter_settings.show, name="admin_newsletters_settings_show"),
    path("admin/newsletters/<int:newsletter_id>/", newsletter_admin.show, name="admin_newsletters_show"),
    path("admin/newsletters/<int:newsletter_id>/edit/", newsletter_admin.edit, name="admin_newsletters_edit"),
]

public_newsletter_patterns = [
    path("escalated/n/o/<str:token>/", newsletter_public.open_pixel, name="newsletters_public_open"),
    path("escalated/n/c/<str:token>/", newsletter_public.click, name="newsletters_public_click"),
    path("escalated/n/u/<str:token>/", newsletter_public.unsubscribe, name="newsletters_public_unsubscribe"),
    path("escalated/n/v/<str:token>/", newsletter_public.view_in_browser, name="newsletters_public_view"),
]

webhook_newsletter_patterns = [
    path("escalated/webhooks/newsletter/postmark/", newsletter_webhooks.postmark, name="newsletters_webhook_postmark"),
    path("escalated/webhooks/newsletter/mailgun/", newsletter_webhooks.mailgun, name="newsletters_webhook_mailgun"),
    path("escalated/webhooks/newsletter/ses/", newsletter_webhooks.ses, name="newsletters_webhook_ses"),
    path("escalated/webhooks/newsletter/sendgrid/", newsletter_webhooks.sendgrid, name="newsletters_webhook_sendgrid"),
]
