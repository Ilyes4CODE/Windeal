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
from django.db import transaction
from django.utils import timezone

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


# ── Redemption core ───────────────────────────────────────────────────────────

def redeem_token(business_user, qr_token):
    """
    Validate and redeem a QR token on behalf of ``business_user``.

    Shared by the HTTP endpoint (``POST /api/business/redeem/``) and the
    WebSocket ``redeem`` action so both paths behave identically.

    On success it:
      - marks the token used (one-time) and creates a ``Redemption`` row, and
      - broadcasts ``redemption`` + ``notification`` frames to **both** the
        business and the student in real time.

    Returns a plain dict (never raises for business errors)::

        {
          "ok": bool,
          "code": "success"|"not_found"|"used"|"expired"|"wrong_business"|"no_subscription",
          "message": str,
          "data": {…event…} | None,
          "http_status": int,          # convenience for the REST view
        }
    """
    from .models import RedemptionToken, Redemption

    base = {"ok": False, "data": None}
    try:
        token = (
            RedemptionToken.objects
            .select_related("user", "user__client_profile", "deal", "deal__business")
            .get(token=qr_token)
        )
    except RedemptionToken.DoesNotExist:
        return {**base, "code": "not_found",
                "message": "QR token not found.", "http_status": 400}

    if token.is_used:
        return {**base, "code": "used",
                "message": "QR token already used.", "http_status": 400}
    if timezone.now() >= token.expires_at:
        return {**base, "code": "expired",
                "message": "QR token has expired.", "http_status": 400}
    if token.deal.business_id != business_user.id:
        return {**base, "code": "wrong_business",
                "message": "This deal does not belong to your business.", "http_status": 403}
    if token.user.subscription_status != "ACTIVE":
        return {**base, "code": "no_subscription",
                "message": "Student does not hold an active WINDEAL+ subscription.", "http_status": 402}

    with transaction.atomic():
        token.is_used = True
        token.used_at = timezone.now()
        token.save(update_fields=["is_used", "used_at"])
        redemption = Redemption.objects.create(
            business=business_user, student=token.user, deal=token.deal,
            token=token, status="VERIFIED",
        )

    student_name = (
        token.user.client_profile.full_name
        if hasattr(token.user, "client_profile") and token.user.client_profile.full_name
        else token.user.phone
    )
    business_name = (
        business_user.business_profile.business_name
        if hasattr(business_user, "business_profile") and business_user.business_profile.business_name
        else business_user.phone
    )

    event_data = {
        "redemption_id": str(redemption.id),
        "student_name":  student_name,
        "business_name": business_name,
        "deal_name":     token.deal.title,
        "deal_id":       str(token.deal.id),
        "status":        redemption.status,
        "timestamp":     redemption.created_at,
    }

    # Real-time broadcast to both parties (business dashboard + student).
    send_realtime(business_user, "redemption", event_data)
    notify(
        business_user,
        title="New redemption",
        body=f"{student_name} redeemed '{token.deal.title}'.",
        ntype="redemption",
        extra={"redemption": event_data},
    )
    notify(
        token.user,
        title="Deal redeemed",
        body=f"You redeemed '{token.deal.title}' at {business_name}. Enjoy!",
        ntype="redemption",
        extra={"redemption": event_data},
    )
    send_realtime(token.user, "redemption", event_data)

    return {"ok": True, "code": "success",
            "message": "Redemption successful.",
            "data": event_data, "http_status": 200}
