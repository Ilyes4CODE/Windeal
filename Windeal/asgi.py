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
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from deals_app.ws_auth import JWTAuthMiddleware  # noqa: E402
from deals_app.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(
        JWTAuthMiddleware(
            URLRouter(websocket_urlpatterns)
        )
    ),
})
