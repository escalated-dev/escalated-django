"""
Django Channels WebSocket consumer for live chat.

Provides real-time messaging via WebSocket connections. Falls back gracefully
when Django Channels is not installed (HTTP polling still works via views).
"""

try:
    from channels.generic.websocket import AsyncJsonWebsocketConsumer

    HAS_CHANNELS = True
except ImportError:
    HAS_CHANNELS = False

if HAS_CHANNELS:

    class ChatConsumer(AsyncJsonWebsocketConsumer):
        """
        WebSocket consumer for live chat sessions.

        URL: ws://host/ws/chat/<session_id>/

        Incoming messages:
            {"type": "chat.message", "body": "..."}
            {"type": "chat.typing", "is_typing": true/false}

        Outgoing messages:
            {"type": "chat.message", "body": "...", "sender_type": "...", "message_id": ..., "timestamp": "..."}
            {"type": "chat.typing", "sender_type": "...", "is_typing": true/false}
            {"type": "chat.ended", "ended_by": "..."}
            {"type": "chat.assigned", "agent_name": "..."}
        """

        async def connect(self):
            self.session_id = self.scope["url_route"]["kwargs"]["session_id"]
            self.room_group_name = f"chat_{self.session_id}"

            await self.channel_layer.group_add(self.room_group_name, self.channel_name)
            await self.accept()

        async def disconnect(self, close_code):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

        async def receive_json(self, content):
            msg_type = content.get("type", "")

            if msg_type == "chat.message":
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "chat_message",
                        "body": content.get("body", ""),
                        "sender_type": content.get("sender_type", "customer"),
                    },
                )
            elif msg_type == "chat.typing":
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "chat_typing",
                        "sender_type": content.get("sender_type", "customer"),
                        "is_typing": content.get("is_typing", False),
                    },
                )

        async def chat_message(self, event):
            await self.send_json(
                {
                    "type": "chat.message",
                    "body": event["body"],
                    "sender_type": event["sender_type"],
                    "message_id": event.get("message_id"),
                    "timestamp": event.get("timestamp"),
                }
            )

        async def chat_typing(self, event):
            await self.send_json(
                {
                    "type": "chat.typing",
                    "sender_type": event["sender_type"],
                    "is_typing": event["is_typing"],
                }
            )

        async def chat_ended(self, event):
            await self.send_json(
                {
                    "type": "chat.ended",
                    "ended_by": event.get("ended_by"),
                }
            )

        async def chat_assigned(self, event):
            await self.send_json(
                {
                    "type": "chat.assigned",
                    "agent_name": event.get("agent_name"),
                }
            )

else:
    # Stub when channels is not installed
    ChatConsumer = None
