# Project: windeal | File: windeal/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
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
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
