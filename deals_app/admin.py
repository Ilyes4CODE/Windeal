# App: deals_app | File: admin.py
from django.contrib import admin
from django.utils.html import format_html

from .models import Deal, Favorite, RedemptionToken, Redemption, Notification


@admin.register(Deal)
class DealAdmin(admin.ModelAdmin):
    list_display  = ("title", "business", "category", "discount_value",
                     "old_price", "new_price", "is_active", "created_at")
    list_filter   = ("is_active", "category")
    search_fields = ("title", "description", "business__phone",
                     "business__business_profile__business_name")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display  = ("user", "deal", "created_at")
    search_fields = ("user__phone", "deal__title")
    readonly_fields = ("id", "created_at")


@admin.register(RedemptionToken)
class RedemptionTokenAdmin(admin.ModelAdmin):
    list_display  = ("short_token", "user", "deal", "is_used", "expires_at", "created_at")
    list_filter   = ("is_used",)
    search_fields = ("user__phone", "deal__title", "token")
    readonly_fields = ("id", "token", "created_at", "used_at")

    @admin.display(description="Token")
    def short_token(self, obj):
        return format_html('<code style="font-size:11px">{}</code>', (obj.token or "")[:10] + "…")


@admin.register(Redemption)
class RedemptionAdmin(admin.ModelAdmin):
    list_display  = ("deal", "student", "business", "status", "created_at")
    list_filter   = ("status",)
    search_fields = ("student__phone", "business__phone", "deal__title")
    readonly_fields = ("id", "created_at")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display  = ("title", "user", "type", "is_read", "created_at")
    list_filter   = ("type", "is_read")
    search_fields = ("title", "body", "user__phone")
    readonly_fields = ("id", "created_at")
