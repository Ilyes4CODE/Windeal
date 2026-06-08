# App: deals_app | File: urls.py
from django.urls import path
from . import views

urlpatterns = [
    # ── Client: Categories ────────────────────────────────────────────────────
    path("categories/",                       views.list_categories,        name="list_categories"),

    # ── Client: Deals (Home / Explore) ────────────────────────────────────────
    path("deals/",                            views.list_deals,             name="list_deals"),
    path("deals/featured/",                   views.featured_deals,         name="featured_deals"),
    path("deals/nearby/",                     views.nearby_deals,           name="nearby_deals"),
    path("deals/favorites/",                  views.list_favorites,         name="list_favorites"),
    path("deals/favorites/toggle/",           views.toggle_favorite,        name="toggle_favorite"),
    path("deals/generate-code/",              views.generate_redemption_code, name="generate_redemption_code"),
    path("deals/<uuid:deal_id>/",             views.deal_detail,            name="deal_detail"),

    # ── Business: Offers (CRUD) ──────────────────────────────────────────────
    path("business/offers/",                  views.list_offers,            name="list_offers"),
    path("business/offers/create/",           views.create_offer,           name="create_offer"),
    path("business/offers/<uuid:offer_id>/",  views.offer_detail,           name="offer_detail"),
    path("business/offers/<uuid:offer_id>/toggle/", views.toggle_offer,    name="toggle_offer"),

    # ── Business: Dashboard / Analytics / Redeem ─────────────────────────────
    path("business/dashboard/",               views.business_dashboard,     name="business_dashboard"),
    path("business/analytics/",               views.business_analytics,     name="business_analytics"),
    path("business/redeem/",                  views.redeem_qr,              name="redeem_qr"),

    # ── Subscription ─────────────────────────────────────────────────────────
    path("subscription/plans/",               views.list_subscription_plans, name="subscription_plans"),
    path("subscription/upgrade/",             views.subscription_upgrade,    name="subscription_upgrade"),
    path("subscription/payment-history/",     views.payment_history,         name="payment_history"),

    # ── Notifications ────────────────────────────────────────────────────────
    path("notifications/",                    views.list_notifications,         name="list_notifications"),
    path("notifications/<uuid:notification_id>/read/", views.mark_notification_read, name="mark_notification_read"),

    # ── User account passthrough ─────────────────────────────────────────────
    path("user/account/delete/",              views.delete_account,         name="delete_account"),
]
