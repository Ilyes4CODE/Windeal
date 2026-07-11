# Project: windeal | File: windeal/settings.py
import os
from pathlib import Path
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from a .env file if present (production/server use).
# Locally, with no .env, the defaults below keep the dev experience unchanged.
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass


def _env_bool(name, default):
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _env_list(name, default=""):
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


# SECURITY: set DJANGO_SECRET_KEY in production. The default is dev-only.
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-zxss^k$!#u*#is4)g(^g=$mk20^50wt+emx^0#k$e))xztgn(r",
)

# SECURITY: set DJANGO_DEBUG=False in production.
DEBUG = _env_bool("DJANGO_DEBUG", True)

# e.g. DJANGO_ALLOWED_HOSTS="api.windeal.dz,187.77.171.86"
ALLOWED_HOSTS = _env_list("DJANGO_ALLOWED_HOSTS", "*")

# Needed for the Django admin / DRF over HTTPS behind Nginx.
# e.g. DJANGO_CSRF_TRUSTED_ORIGINS="https://api.windeal.dz"
CSRF_TRUSTED_ORIGINS = _env_list("DJANGO_CSRF_TRUSTED_ORIGINS", "")

INSTALLED_APPS = [
    # daphne must come first so it overrides the default runserver with the
    # ASGI/WebSocket-aware development server.
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "channels",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "drf_spectacular",
    "auth_app.apps.AuthAppConfig",
    "admin_app.apps.AdminAppConfig",
    "deals_app.apps.DealsAppConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
]

ROOT_URLCONF = "Windeal.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "Windeal.wsgi.application"
ASGI_APPLICATION = "Windeal.asgi.application"

# ── Channels (WebSockets) ─────────────────────────────────────────────────────
# In-memory layer works for local dev and a single-process deployment.
# Set REDIS_URL (e.g. "redis://127.0.0.1:6379/0") in production so multiple
# Daphne/worker processes share the channel layer. Requires: channels-redis.
REDIS_URL = os.environ.get("REDIS_URL", "").strip()
if REDIS_URL:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [REDIS_URL]},
        }
    }
else:
    CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"},
    }

# ── Database ──────────────────────────────────────────────────────────────────
# Set DATABASE_URL (e.g. "postgres://user:pass@127.0.0.1:5432/windeal") in
# production. Falls back to local SQLite when unset.
if os.environ.get("DATABASE_URL"):
    import dj_database_url
    DATABASES = {
        "default": dj_database_url.config(conn_max_age=600, ssl_require=False),
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "auth_app.User"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
    "EXCEPTION_HANDLER": "core.exceptions.custom_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(days=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# CORS: allow all by default (handy for a mobile app hitting the API directly).
# To lock down to specific web origins, set DJANGO_CORS_ALLOW_ALL=False and list
# DJANGO_CORS_ALLOWED_ORIGINS="https://app.windeal.dz,https://admin.windeal.dz".
CORS_ALLOW_ALL_ORIGINS = _env_bool("DJANGO_CORS_ALLOW_ALL", True)
CORS_ALLOWED_ORIGINS = _env_list("DJANGO_CORS_ALLOWED_ORIGINS", "")

# ── Production security hardening (only active when DEBUG=False) ───────────────
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    # Let Nginx/Certbot handle the redirect; enable HSTS once HTTPS is confirmed.
    SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", "0"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

SPECTACULAR_SETTINGS = {
    "TITLE": "WINDEAL API",
    "DESCRIPTION": (
        "WINDEAL is a mobile application that helps users discover local discounts "
        "from businesses (cafés, restaurants, gyms, leisure spots) and redeem them using QR codes.\n\n"
        "## Authentication\n"
        "All protected endpoints require a **Bearer JWT token** in the `Authorization` header:\n"
        "```\nAuthorization: Bearer <access_token>\n```\n\n"
        "## Language\n"
        "All error messages and responses are returned in **Arabic, English or French** "
        "based on the `Accept-Language` header. Supported values: `en`, `ar`, `fr`. "
        "Defaults to `en` if not provided or unrecognised.\n\n"
        "## User Roles\n"
        "- **client** — browse and redeem offers, manage subscription\n"
        "- **business** — manage offers, scan QR codes\n"
        "- **admin** — approve payments, manage users, categories and plans\n\n"
        "## Subscription States\n"
        "| State | Meaning |\n"
        "|---|---|\n"
        "| FREE | Default — no active subscription |\n"
        "| PENDING | Receipt uploaded, waiting for admin approval |\n"
        "| ACTIVE | Admin approved — full access |\n"
        "| EXPIRED | Subscription end date has passed (auto-detected) |"
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "CONTACT": {"name": "WINDEAL Backend", "email": "dev@windeal.app"},
    "LICENSE": {"name": "Private"},
    "SECURITY": [{"BearerAuth": []}],
    "COMPONENT_SPLIT_REQUEST": True,
    "SORT_OPERATIONS": False,
    "TAGS": [
        {"name": "Auth — Client", "description": "Registration, OTP, login and profile endpoints for client users."},
        {"name": "Auth — Business", "description": "Registration, OTP, login and profile endpoints for business users."},
        {"name": "Auth — Common", "description": "Shared auth endpoints (login, logout, OTP confirm, profile, subscription)."},
        {"name": "Auth — Payment", "description": "Payment receipt upload and subscription status for clients and businesses."},
        {"name": "Admin — Categories", "description": "Admin-only: create and manage business categories with photos."},
        {"name": "Admin — Plans", "description": "Admin-only: create and manage subscription plans (monthly, annual, etc.)."},
        {"name": "Admin — Payments", "description": "Admin-only: review, approve or reject subscription payment receipts."},
        {"name": "Admin — Users", "description": "Admin-only: list, activate/deactivate users and set subscription status."},
    ],
}