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


def _check_banned(user, lang):
    """Returns a Response if the user is banned, otherwise None."""
    if getattr(user, "is_banned", False):
        return _deny("banned", lang, status.HTTP_403_FORBIDDEN)
    return None


# ── Decorators ────────────────────────────────────────────────────────────────

def admin_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        lang = _get_lang(request)
        user, _ = _authenticate_request(request)
        if user is None:
            return _deny("unauthorized", lang, status.HTTP_401_UNAUTHORIZED)
        if user.role != "admin":
            return _deny("admin_only", lang, status.HTTP_403_FORBIDDEN)
        # Admins cannot be banned (safety guard — skip banned check for admins)
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
        banned = _check_banned(user, lang)
        if banned:
            return banned
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
        banned = _check_banned(user, lang)
        if banned:
            return banned
        request.user = user
        return view_func(request, *args, **kwargs)
    return wrapper


def login_required(view_func):
    """Any authenticated user — bans are enforced."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        lang = _get_lang(request)
        user, _ = _authenticate_request(request)
        if user is None:
            return _deny("unauthorized", lang, status.HTTP_401_UNAUTHORIZED)
        if user.role != "admin":          # only check ban for non-admins
            banned = _check_banned(user, lang)
            if banned:
                return banned
        request.user = user
        return view_func(request, *args, **kwargs)
    return wrapper


def login_optional(view_func):
    """
    Authentication is OPTIONAL.

    - No token / invalid token  → request.user is set to ``None`` (anonymous);
      the view still runs (public access).
    - Valid token               → request.user is the authenticated user, so
      per-user fields (e.g. ``is_favorite``, ``my_rating``) can be computed.
    - Banned non-admin with a valid token → 403 (a banned user shouldn't get a
      personalised response).

    Use for public read endpoints that are richer when logged in but must also
    work for anonymous callers.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        lang = _get_lang(request)
        user, _ = _authenticate_request(request)
        if user is not None and user.role != "admin" and getattr(user, "is_banned", False):
            return _deny("banned", lang, status.HTTP_403_FORBIDDEN)
        request.user = user          # may be None → treated as anonymous downstream
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
        if user.role == "business":
            banned = _check_banned(user, lang)
            if banned:
                return banned
        request.user = user
        return view_func(request, *args, **kwargs)
    return wrapper