# App: core | File: responses.py
from rest_framework.response import Response
from rest_framework import status
from .messages import get_message


def success_response(data=None, message_key=None, lang="en", status_code=status.HTTP_200_OK, extra=None):
    payload = {"success": True}
    if message_key:
        payload["message"] = get_message(message_key, lang)
    if data is not None:
        payload["data"] = data
    if extra:
        payload.update(extra)
    return Response(payload, status=status_code)


def error_response(message_key=None, lang="en", status_code=status.HTTP_400_BAD_REQUEST, errors=None, custom_message=None):
    payload = {"success": False}
    if message_key:
        payload["message"] = get_message(message_key, lang)
    elif custom_message:
        payload["message"] = custom_message
    if errors:
        payload["errors"] = errors
    return Response(payload, status=status_code)
