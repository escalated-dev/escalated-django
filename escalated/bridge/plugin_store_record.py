"""
PluginStoreRecord — persistent key/value store for SDK plugins.

Each SDK plugin gets its own isolated namespace (plugin name + collection).
The ``data`` column stores arbitrary JSON, allowing plugins to persist
structured objects without needing their own database tables.

The ``__config__`` collection / ``__config__`` key is reserved for the
plugin configuration blob (ctx.config.*).
"""

from django.db import models

from escalated.conf import get_table_name


class PluginStoreRecord(models.Model):
    """
    A single record in the per-plugin key/value store.

    Fields
    ------
    plugin:
        The plugin name that owns this record (e.g. ``my-crm-plugin``).
    collection:
        Logical grouping within the plugin (e.g. ``contacts``, ``sync_state``).
        The special value ``__config__`` is used internally for plugin config.
    key:
        Optional string key within the collection.  For config records both
        ``collection`` and ``key`` are ``__config__``.
    data:
        The JSON payload.
    """

    plugin = models.CharField(max_length=255, db_index=True)
    collection = models.CharField(max_length=255, db_index=True)
    key = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    data = models.JSONField(default=None, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = get_table_name("plugin_store")
        ordering = ["id"]
        indexes = [
            models.Index(
                fields=["plugin", "collection", "key"],
                name="idx_plugin_store_lookup",
            ),
        ]
        verbose_name = "Plugin Store Record"
        verbose_name_plural = "Plugin Store Records"

    def __str__(self) -> str:
        return f"{self.plugin}/{self.collection}/{self.key}"
