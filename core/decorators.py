# App: core | File: decorators.py
from functools import wraps
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from .messages import get_message


def _get_lang(request):
    lang = request.headers.get("Accept-Language", "en")[:2].lower()
    return lang if lang in ("en", "ar", "fr") else "en"


def _authenticate_request(request):
    auth = JWTAuthentication()
    try:
        result = auth.authenticate(request)
        if result is None:
            return None, None
        user, token = result
        return user, token
    except (InvalidToken, TokenError):
        return None, None


def _deny(message_key, lang, http_status):
    return Response(
        {"success": False, "message": get_message(message_key, lang)},
        status=http_status,
    )


def admin_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        lang = _get_lang(request)
        user, _ = _authenticate_request(request)
        if user is None:
            return _deny("unauthorized", lang, status.HTTP_401_UNAUTHORIZED)
        if user.role != "admin":
            return _deny("admin_only", lang, status.HTTP_403_FORBIDDEN)
        request.user = user
        return view_func(request, *args, **kwargs)
    return wrapper


def business_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        lang = _get_lang(request)
        user, _ = _authenticate_request(request)
        if user is None:
            return _deny("unauthorized", lang, status.HTTP_401_UNAUTHORIZED)
        if user.role != "business":
            return _deny("business_only", lang, status.HTTP_403_FORBIDDEN)
        request.user = user
        return view_func(request, *args, **kwargs)
    return wrapper


def client_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        lang = _get_lang(request)
        user, _ = _authenticate_request(request)
        if user is None:
            return _deny("unauthorized", lang, status.HTTP_401_UNAUTHORIZED)
        if user.role != "client":
            return _deny("client_only", lang, status.HTTP_403_FORBIDDEN)
        request.user = user
        return view_func(request, *args, **kwargs)
    return wrapper


def login_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        lang = _get_lang(request)
        user, _ = _authenticate_request(request)
        if user is None:
            return _deny("unauthorized", lang, status.HTTP_401_UNAUTHORIZED)
        request.user = user
        return view_func(request, *args, **kwargs)
    return wrapper


def admin_or_business_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        lang = _get_lang(request)
        user, _ = _authenticate_request(request)
        if user is None:
            return _deny("unauthorized", lang, status.HTTP_401_UNAUTHORIZED)
        if user.role not in ("admin", "business"):
            return _deny("unauthorized", lang, status.HTTP_403_FORBIDDEN)
        request.user = user
        return view_func(request, *args, **kwargs)
    return wrapper
