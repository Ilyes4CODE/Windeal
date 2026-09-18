# App: auth_app | File: urls.py
from django.urls import path
from . import views

urlpatterns = [
    # ── Registration ──────────────────────────────────────────────────────────
    path("register/client/",   views.register_client,    name="register_client"),
    path("register/business/", views.register_business,  name="register_business"),
    path("register/admin/",    views.register_admin,     name="register_admin"),

    # ── Email OTP auth ────────────────────────────────────────────────────────
    path("email/send-otp/",     views.send_email_otp,     name="send_email_otp"),
    path("email/verify-login/", views.verify_email_login, name="verify_email_login"),

    # ── Social auth (Google / Apple) ──────────────────────────────────────────
    path("social/google/",           views.google_auth,             name="google_auth"),
    path("social/apple/",            views.apple_auth,              name="apple_auth"),
    path("social/complete-profile/", views.social_complete_profile, name="social_complete_profile"),

    # ── Passwordless auth (client + business) ─────────────────────────────────
    path("check/",             views.check_user,         name="check_user"),
    path("login/",             views.passwordless_login, name="passwordless_login"),

    # ── Admin auth (password-based) ───────────────────────────────────────────
    path("login/admin/",       views.admin_login,        name="admin_login"),

    # ── Session ───────────────────────────────────────────────────────────────
    path("logout/",            views.logout,             name="logout"),

    # ── Profile ───────────────────────────────────────────────────────────────
    path("profile/",           views.get_profile,        name="get_profile"),
    path("profile/update/",    views.update_profile,     name="update_profile"),

    # ── Subscription & payment ────────────────────────────────────────────────
    path("payment/upload/",    views.upload_payment,          name="upload_payment"),
    path("subscription/status/", views.get_subscription_status, name="subscription_status"),
]