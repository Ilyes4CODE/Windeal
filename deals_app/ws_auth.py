# App: deals_app | File: ws_auth.py
"""
JWT authentication middleware for Channels WebSocket connections.

The browser WebSocket API cannot set custom headers, so the access token is
accepted from (in priority order):

  1. ``?token=<access>`` query-string parameter
  2. the ``Authorization: Bearer <access>`` header (for non-browser clients)
  3. the ``Sec-WebSocket-Protocol`` header (``["access_token", "<token>"]``)

On success ``scope["user"]`` is the authenticated ``User`` instance.
On failure ``scope["user"]`` is set to ``AnonymousUser``.
"""
from urllib.parse import parse_qs

from channels.middleware import BaseMiddleware
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser


@database_sync_to_async
def _get_user(token_str):
    from rest_framework_simplejwt.tokens import AccessToken
    from rest_framework_simplejwt.exceptions import TokenError
    from auth_app.models import User

    try:
        access = AccessToken(token_str)
        user_id = access["user_id"]
    except (TokenError, KeyError):
        return AnonymousUser()

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return AnonymousUser()

    # Banned or deactivated users cannot open a socket (admins exempt from ban).
    if getattr(user, "is_banned", False) and user.role != "admin":
        return AnonymousUser()
    if not user.is_active:
        return AnonymousUser()
    return user


def _extract_token(scope):
    # 1. query string ?token=
    qs = parse_qs(scope.get("query_string", b"").decode())
    if "token" in qs and qs["token"]:
        return qs["token"][0]

    # 2. Authorization header
    headers = dict(scope.get("headers", []))
    auth = headers.get(b"authorization")
    if auth:
        parts = auth.decode().split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1]

    # 3. Sec-WebSocket-Protocol: access_token, <token>
    proto = headers.get(b"sec-websocket-protocol")
    if proto:
        parts = [p.strip() for p in proto.decode().split(",")]
        if len(parts) >= 2 and parts[0] == "access_token":
            return parts[1]

    return None


class JWTAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        token = _extract_token(scope)
        scope["user"] = await _get_user(token) if token else AnonymousUser()
        return await super().__call__(scope, receive, send)
