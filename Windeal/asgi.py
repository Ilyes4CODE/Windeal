"""
ASGI config for Windeal project.

Routes plain HTTP through Django's ASGI app and WebSocket traffic through
Channels, authenticated with JWT (see ``deals_app.ws_auth.JWTAuthMiddleware``).

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Windeal.settings")

# Initialise Django before importing anything that touches models / settings.
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402

from deals_app.ws_auth import JWTAuthMiddleware  # noqa: E402
from deals_app.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    # The socket is authenticated by JWT (deals_app.ws_auth.JWTAuthMiddleware):
    # a valid access token is required to connect. We deliberately do NOT wrap
    # this in AllowedHostsOriginValidator — mobile clients (Flutter) and other
    # non-browser tools don't send an `Origin` header, and origin validation
    # rejects them with HTTP 403 whenever ALLOWED_HOSTS isn't "*" (i.e. in
    # production). Origin checks defend against cookie-based cross-site WS
    # hijacking, which doesn't apply here since auth is a bearer token in the
    # query string, not a cookie.
    "websocket": JWTAuthMiddleware(
        URLRouter(websocket_urlpatterns)
    ),
})
