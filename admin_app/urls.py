# App: admin_app | File: urls.py
from django.urls import path
from . import views

urlpatterns = [
    # ── Categories ────────────────────────────────────────────────────────────
    path("categories/",                          views.categories,        name="admin_categories"),
    path("categories/<uuid:category_id>/",       views.category_detail,   name="admin_category_detail"),

    # ── Subscription plans ────────────────────────────────────────────────────
    path("plans/",                               views.plans,             name="admin_plans"),
    path("plans/<uuid:plan_id>/",                views.plan_detail,       name="admin_plan_detail"),

    # ── Payments ──────────────────────────────────────────────────────────────
    path("payments/pending/",                    views.pending_payments,  name="admin_pending_payments"),
    path("payments/all/",                        views.all_payments,      name="admin_all_payments"),
    path("payments/<uuid:payment_id>/review/",   views.review_payment,    name="admin_review_payment"),

    # ── Deals (featuring control) ──────────────────────────────────────────────
    path("deals/",                               views.deals,             name="admin_deals"),
    path("deals/<uuid:deal_id>/feature/",        views.feature_deal,      name="admin_feature_deal"),

    # ── Users ──────────────────────────────────────────────────────────────────
    path("users/",                               views.list_users,        name="admin_list_users"),
    path("users/<uuid:user_id>/toggle/",         views.toggle_user,       name="admin_toggle_user"),
    path("users/<uuid:user_id>/ban/",            views.ban_user,          name="admin_ban_user"),
    path("users/<uuid:user_id>/subscription/",   views.set_subscription,  name="admin_set_subscription"),
]