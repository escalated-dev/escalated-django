"""
Custom ticket action registry.

Host projects register actions via the ``ESCALATED["TICKET_ACTIONS"]`` setting
(a list of action config dicts). Each visible action renders as a button on the
agent ticket screen; triggering it sends the ``custom_action_triggered`` signal
so the host can handle the work in a normal receiver.

Action config shape (all but ``key``/``label`` optional)::

    {
        "key": "sync-crm",                 # required, stable id
        "label": "Sync CRM",               # required
        "variant": "primary",              # primary | secondary | danger
        "visible": True,                   # bool or callable(ticket, user)
        "enabled": True,                   # bool or callable(ticket, user)
        "confirmation": "Are you sure?",   # str/None or callable
        "metadata": {"icon": "refresh-cw"}, # dict or callable
    }

Mirrors the Laravel TicketActionRegistry / NestJS reference.
"""


def _resolve(value, ticket, user):
    """Resolve a value that may be static or a callable(ticket, user)."""
    return value(ticket, user) if callable(value) else value


class TicketActionRegistry:
    def __init__(self):
        self._actions = {}

    def register(self, config):
        key = config.get("key")
        label = config.get("label")
        if not key or not label:
            raise ValueError('Ticket actions require both "key" and "label".')
        self._actions[key] = config

    def clear(self):
        self._actions = {}

    def find(self, key):
        return self._actions.get(key)

    def is_visible(self, config, ticket, user):
        return bool(_resolve(config.get("visible", True), ticket, user))

    def is_enabled(self, config, ticket, user):
        return bool(_resolve(config.get("enabled", True), ticket, user))

    def metadata(self, config, ticket, user):
        value = _resolve(config.get("metadata", {}), ticket, user)
        return value if isinstance(value, dict) else {}

    def visible_for(self, ticket, user):
        """
        Return the visible actions for a ticket/user, serialized for the UI.
        The view adds the ``url`` and ``method`` before sending to the client.
        """
        result = []
        for config in self._actions.values():
            if not self.is_visible(config, ticket, user):
                continue
            confirmation = _resolve(config.get("confirmation"), ticket, user)
            result.append(
                {
                    "key": config["key"],
                    "label": str(_resolve(config["label"], ticket, user)),
                    "variant": config.get("variant", "secondary"),
                    "confirmation": None if confirmation is None else str(confirmation),
                    "disabled": not self.is_enabled(config, ticket, user),
                    "metadata": self.metadata(config, ticket, user),
                }
            )
        return result

    def load_from_settings(self):
        """(Re)populate the registry from the ``TICKET_ACTIONS`` setting."""
        from escalated.conf import get_setting

        self.clear()
        for config in get_setting("TICKET_ACTIONS") or []:
            self.register(config)


# Module-level singleton.
registry = TicketActionRegistry()
