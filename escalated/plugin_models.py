"""
Plugin model for tracking installed/activated plugins in the database.
"""

from django.db import models

from escalated.conf import get_table_name


# ---------------------------------------------------------------------------
# Manager / QuerySet
# ---------------------------------------------------------------------------


class EscalatedPluginQuerySet(models.QuerySet):
    def active(self):
        """Return only active plugins."""
        return self.filter(is_active=True)

    def inactive(self):
        """Return only inactive plugins."""
        return self.filter(is_active=False)


class EscalatedPluginManager(models.Manager):
    def get_queryset(self):
        return EscalatedPluginQuerySet(self.model, using=self._db)

    def active(self):
        return self.get_queryset().active()

    def inactive(self):
        return self.get_queryset().inactive()


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class EscalatedPlugin(models.Model):
    """
    Tracks which plugins are installed and their activation state.

    The actual plugin code lives on disk (in the host app's plugins directory).
    This model stores the slug, cached manifest metadata, activation state,
    and an optional per-plugin JSON config blob.
    """

    slug = models.SlugField(
        max_length=255,
        unique=True,
        help_text="Unique identifier matching the plugin directory name.",
    )
    name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Human-readable plugin name (cached from plugin.json).",
    )
    version = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Plugin version string (cached from plugin.json).",
    )
    description = models.TextField(
        blank=True,
        default="",
        help_text="Short plugin description (cached from plugin.json).",
    )
    author = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Plugin author (cached from plugin.json).",
    )
    is_active = models.BooleanField(
        default=False,
        help_text="Whether this plugin is currently active.",
    )
    config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Per-plugin configuration stored as JSON.",
    )
    installed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this plugin was first installed.",
    )
    activated_at = models.DateTimeField(null=True, blank=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = EscalatedPluginManager()

    class Meta:
        db_table = get_table_name("plugins")
        ordering = ["slug"]
        verbose_name = "Plugin"
        verbose_name_plural = "Plugins"

    def __str__(self):
        status = "active" if self.is_active else "inactive"
        return f"{self.slug} ({status})"
