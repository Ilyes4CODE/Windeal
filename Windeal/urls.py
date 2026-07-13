# Project: windeal | File: windeal/urls.py
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.views.static import serve as media_serve
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)
from auth_app import views as auth_views

urlpatterns = [
    path("django-admin/", admin.site.urls),

    # ── Existing namespaced auth & admin endpoints ────────────────────────────
    path("api/auth/",  include("auth_app.urls")),
    path("api/admin/", include("admin_app.urls")),

    # ── New spec-aligned endpoints (categories, deals, business, subscription) ─
    path("api/", include("deals_app.urls")),

    # ── User profile aliases (match the spec's /user/profile/* paths) ─────────
    path("api/user/profile/",        auth_views.get_profile,    name="user_get_profile"),
    path("api/user/profile/update/", auth_views.update_profile, name="user_update_profile"),

    # ── OpenAPI / Swagger ─────────────────────────────────────────────────────
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/",   SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/",  SpectacularRedocView.as_view(url_name="schema"),   name="redoc"),
]

# ── Media files (uploaded images / receipts) ──────────────────────────────────
# django.conf.urls.static.static() only serves media when DEBUG=True, so in
# production (DEBUG=False) uploaded images 404. Serve them explicitly here so it
# works in both modes. Daphne runs as the media files' owner, which sidesteps the
# Nginx "can't read /home/<user>" permission problem entirely.
urlpatterns += [
    re_path(r"^media/(?P<path>.*)$", media_serve, {"document_root": settings.MEDIA_ROOT}),
]
