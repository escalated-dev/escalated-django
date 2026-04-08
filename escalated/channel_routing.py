"""
Django Channels routing for Escalated real-time events.

Usage (in your project's routing.py):

    from channels.routing import ProtocolTypeRouter, URLRouter
    from escalated.channel_routing import websocket_urlpatterns

    application = ProtocolTypeRouter({
        "websocket": URLRouter(websocket_urlpatterns),
    })

This module only defines the URL patterns; the consumer implementation
follows.  If Django Channels is not installed, this module is a no-op.
"""

websocket_urlpatterns = []

try:
    from channels.generic.websocket import JsonWebsocketConsumer

    class EscalatedEventConsumer(JsonWebsocketConsumer):
        """
        WebSocket consumer for Escalated real-time events.

        Clients connect and join a group for a specific ticket
        (e.g. ``/ws/escalated/ticket/42/``).
        """

        def connect(self):
            self.ticket_id = self.scope["url_route"]["kwargs"]["ticket_id"]
            self.group_name = f"ticket.{self.ticket_id}"

            # Authorization: user must be authenticated
            user = self.scope.get("user")
            if user is None or not user.is_authenticated:
                self.close()
                return

            from asgiref.sync import async_to_sync

            async_to_sync(self.channel_layer.group_add)(self.group_name, self.channel_name)
            self.accept()

        def disconnect(self, close_code):
            if hasattr(self, "group_name"):
                from asgiref.sync import async_to_sync

                async_to_sync(self.channel_layer.group_discard)(self.group_name, self.channel_name)

        def escalated_event(self, event):
            """Handle an event broadcast to this group."""
            self.send_json(
                {
                    "event_type": event.get("event_type"),
                    "payload": event.get("payload"),
                }
            )

    from django.urls import re_path

    websocket_urlpatterns = [
        re_path(r"ws/escalated/ticket/(?P<ticket_id>\d+)/$", EscalatedEventConsumer.as_asgi()),
    ]

except ImportError:
    # Django Channels not installed — routing is empty, which is fine.
    pass
