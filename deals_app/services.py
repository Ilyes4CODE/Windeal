# App: deals_app | File: services.py
"""
Real-time event helpers.

These are the *only* functions the rest of the codebase should call to emit
notifications / real-time events. They:

  1. persist a ``Notification`` row (so it survives disconnects and appears in
     ``GET /api/notifications/``), and
  2. push a live frame over the channel layer to the user's private group.

Everything is safe to call from synchronous view code — the channel-layer send
is wrapped in ``async_to_sync`` and any transport error is swallowed so a
WebSocket hiccup can never break the HTTP request that triggered it.
"""
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import Notification

logger = logging.getLogger(__name__)


def _group(user_id):
    return f"user_{user_id}"


def _send(user_id, message):
    """Fire a message at a user's group. Never raises."""
    try:
        layer = get_channel_layer()
        if layer is None:
            return
        async_to_sync(layer.group_send)(_group(user_id), message)
    except Exception:  # pragma: no cover - transport failures must not break HTTP
        logger.exception("Failed to push realtime message to user %s", user_id)


def notify(user, title, body="", ntype="system", persist=True, extra=None):
    """
    Persist a notification and push it live.

    Returns the created ``Notification`` (or ``None`` when ``persist=False``).
    """
    from .serializers import NotificationSerializer

    notification = None
    if persist:
        notification = Notification.objects.create(
            user=user, title=title, body=body, type=ntype,
        )
        payload = NotificationSerializer(notification).data
    else:
        payload = {"title": title, "body": body, "type": ntype}

    if extra:
        payload = {**payload, **extra}

    _send(user.id, {"type": "notification.message", "payload": payload})
    return notification


def send_realtime(user, event, data):
    """
    Push a live-only event (not persisted as a Notification).

    ``event`` maps to a consumer handler: ``"redemption"`` → ``redemption_event``,
    ``"payment"`` → ``payment_event``.
    """
    handler = {
        "redemption": "redemption.event",
        "payment":    "payment.event",
    }.get(event)
    if handler is None:
        return
    _send(user.id, {"type": handler, "payload": data})
