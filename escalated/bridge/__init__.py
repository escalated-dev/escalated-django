"""
escalated.bridge — Django Plugin Bridge
========================================

Connects the Django host to the Node.js ``@escalated-dev/plugin-runtime``
subprocess via JSON-RPC 2.0 over stdio.

Public surface
--------------
    from escalated.bridge import get_bridge, PluginBridge

    bridge = get_bridge()
    bridge.dispatch_action("ticket.created", {"id": 42})
    value  = bridge.apply_filter("ticket.subject", "Help needed")
    result = bridge.call_endpoint("my-plugin", "GET", "/settings")
"""

from escalated.bridge.plugin_bridge import PluginBridge, get_bridge
from escalated.bridge.plugin_store_record import PluginStoreRecord

__all__ = [
    "PluginBridge",
    "get_bridge",
    "PluginStoreRecord",
]
