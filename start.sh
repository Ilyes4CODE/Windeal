#!/usr/bin/env bash
# WebSocket support requires an ASGI server. Daphne serves both HTTP and WS.
# (Gunicorn/WSGI cannot handle WebSocket connections.)
daphne -b 0.0.0.0 -p "${PORT:-8000}" Windeal.asgi:application
