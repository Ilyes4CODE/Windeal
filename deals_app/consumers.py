# App: deals_app | File: consumers.py
"""
WebSocket consumer that streams real-time events to a single authenticated user.

Each user joins a private group ``user_<uuid>``. Server-side code pushes events
to that group via ``deals_app.services`` (see ``notify`` / ``send_realtime``).

Outbound frames (server → client) all share the shape::

    { "type": "<event>", "data": { ... } }

Event types currently emitted:
  - ``connection``   — handshake confirmation on connect
  - ``notification`` — a new persisted Notification row
  - ``redemption``   — a real-time redemption event (business + client)
  - ``payment``      — payment status change (pending / approved / rejected)
  - ``pong``         — reply to a client ``ping``

Inbound frames (client → server) supported:
  - ``{"type": "ping"}``           → server replies ``{"type": "pong"}``
  - ``{"type": "mark_read", "id": "<uuid>"}`` → marks a notification read
  - ``{"type": "redeem", "qr_token": "<token>"}`` → **business only.** Redeems a
    scanned QR token live and replies with ``{"type": "redeem_result", ...}``.
    On success the standard ``redemption`` + ``notification`` frames are also
    broadcast to both the business and the student.
"""
import json

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if user is None or not getattr(user, "is_authenticated", False):
            # 4401 = application-level "unauthorized"
            await self.close(code=4401)
            return

        self.user = user
        self.group_name = f"user_{user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        unread = await self._unread_count()
        await self.send_json({
            "type": "connection",
            "data": {
                "status": "connected",
                "user_id": str(user.id),
                "role": user.role,
                "unread_count": unread,
            },
        })

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        try:
            payload = json.loads(text_data or "{}")
        except (json.JSONDecodeError, TypeError):
            await self.send_json({"type": "error", "data": {"detail": "Invalid JSON."}})
            return

        action = payload.get("type")
        if action == "ping":
            await self.send_json({"type": "pong", "data": {}})
        elif action == "mark_read":
            ok = await self._mark_read(payload.get("id"))
            await self.send_json({"type": "mark_read", "data": {"id": payload.get("id"), "ok": ok}})
        elif action == "redeem":
            await self._handle_redeem(payload.get("qr_token"))
        else:
            await self.send_json({"type": "error", "data": {"detail": "Unknown action."}})

    # ── Redeem a QR token over the socket (business only) ────────────────────────
    async def _handle_redeem(self, qr_token):
        if self.user.role != "business":
            await self.send_json({"type": "redeem_result", "data": {
                "ok": False, "code": "forbidden",
                "message": "Only business accounts can redeem QR codes.",
            }})
            return
        if not qr_token:
            await self.send_json({"type": "redeem_result", "data": {
                "ok": False, "code": "validation_error",
                "message": "qr_token is required.",
            }})
            return

        result = await self._do_redeem(qr_token)
        await self.send_json({"type": "redeem_result", "data": {
            "ok":         result["ok"],
            "code":       result["code"],
            "message":    result["message"],
            "redemption": result["data"],
        }})

    # ── Group event handlers (server → client) ──────────────────────────────────
    # Names map from the "type" key used in group_send (dots become underscores).

    async def notification_message(self, event):
        await self.send_json({"type": "notification", "data": event["payload"]})

    async def redemption_event(self, event):
        await self.send_json({"type": "redemption", "data": event["payload"]})

    async def payment_event(self, event):
        await self.send_json({"type": "payment", "data": event["payload"]})

    # ── Helpers ────────────────────────────────────────────────────────────────
    async def send_json(self, data):
        await self.send(text_data=json.dumps(data, default=str))

    @database_sync_to_async
    def _unread_count(self):
        from .models import Notification
        return Notification.objects.filter(user=self.user, is_read=False).count()

    @database_sync_to_async
    def _mark_read(self, notification_id):
        from .models import Notification
        if not notification_id:
            return False
        updated = Notification.objects.filter(id=notification_id, user=self.user).update(is_read=True)
        return bool(updated)

    @database_sync_to_async
    def _do_redeem(self, qr_token):
        from .services import redeem_token
        return redeem_token(self.user, qr_token)
