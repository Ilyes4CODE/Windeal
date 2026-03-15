# App: admin_app | File: admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import Category, SubscriptionPlan, Payment


# ─── Category Admin ───────────────────────────────────────────────────────────

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display  = ("photo_thumb", "name", "active_badge", "business_count", "created_at")
    list_filter   = ("is_active",)
    search_fields = ("name",)
    readonly_fields = ("id", "photo_thumb_large", "created_at", "updated_at")
    list_per_page = 20

    fieldsets = (
        ("Category Info", {
            "fields": ("id", "name", "photo", "photo_thumb_large", "is_active"),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    actions = ["activate_categories", "deactivate_categories"]

    @admin.display(description="Photo")
    def photo_thumb(self, obj):
        if obj.photo:
            return format_html(
                '<img src="{}" style="width:40px;height:40px;object-fit:cover;border-radius:6px" />',
                obj.photo.url
            )
        return format_html('<span style="color:#666;font-size:11px">No photo</span>')

    @admin.display(description="Preview")
    def photo_thumb_large(self, obj):
        if obj.photo:
            return format_html(
                '<img src="{}" style="max-width:200px;max-height:200px;'
                'object-fit:cover;border-radius:8px" />',
                obj.photo.url
            )
        return "No photo uploaded."

    @admin.display(description="Status")
    def active_badge(self, obj):
        if obj.is_active:
            return format_html(
                '<span style="background:#00e676;color:#003300;padding:2px 8px;'
                'border-radius:4px;font-size:11px;font-weight:600">ACTIVE</span>'
            )
        return format_html(
            '<span style="background:#ef5350;color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:11px;font-weight:600">INACTIVE</span>'
        )

    @admin.display(description="Businesses")
    def business_count(self, obj):
        count = obj.businesses.count()
        return format_html('<strong>{}</strong>', count)

    @admin.action(description="✅ Activate selected categories")
    def activate_categories(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} category/categories activated.")

    @admin.action(description="❌ Deactivate selected categories")
    def deactivate_categories(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} category/categories deactivated.")


# ─── SubscriptionPlan Admin ───────────────────────────────────────────────────

@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display  = (
        "name", "price_display", "duration_type", "duration_days",
        "target_role_badge", "active_badge", "subscriber_count", "created_at",
    )
    list_filter   = ("duration_type", "target_role", "is_active")
    search_fields = ("name", "description")
    readonly_fields = ("id", "created_at", "updated_at")
    list_per_page = 20

    fieldsets = (
        ("Plan Info", {
            "fields": ("id", "name", "description"),
        }),
        ("Pricing & Duration", {
            "fields": ("price", "duration_type", "duration_days"),
        }),
        ("Targeting", {
            "fields": ("target_role", "is_active"),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    actions = ["activate_plans", "deactivate_plans"]

    @admin.display(description="Price")
    def price_display(self, obj):
        return format_html('<strong style="color:#00b4ff">{} DZD</strong>', obj.price)

    @admin.display(description="Status")
    def active_badge(self, obj):
        if obj.is_active:
            return format_html(
                '<span style="background:#00e676;color:#003300;padding:2px 8px;'
                'border-radius:4px;font-size:11px;font-weight:600">ACTIVE</span>'
            )
        return format_html(
            '<span style="background:#607d8b;color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:11px;font-weight:600">INACTIVE</span>'
        )

    @admin.display(description="Target")
    def target_role_badge(self, obj):
        colors = {
            "client":   ("#00b4ff", "#e3f2fd"),
            "business": ("#7c4dff", "#f3e5f5"),
            "both":     ("#00e676", "#003300"),
        }
        bg, fg = colors.get(obj.target_role, ("#555", "#fff"))
        return format_html(
            '<span style="background:{};color:{};padding:2px 8px;'
            'border-radius:4px;font-size:11px;font-weight:600">{}</span>',
            bg, fg, obj.target_role.upper()
        )

    @admin.display(description="Subscribers")
    def subscriber_count(self, obj):
        count = obj.subscribed_users.count()
        return format_html('<strong>{}</strong>', count)

    @admin.action(description="✅ Activate selected plans")
    def activate_plans(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} plan(s) activated.")

    @admin.action(description="❌ Deactivate selected plans")
    def deactivate_plans(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} plan(s) deactivated.")


# ─── Payment Admin ────────────────────────────────────────────────────────────

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display  = (
        "short_id", "user_phone", "user_role", "plan_name",
        "amount_display", "status_badge",
        "receipt_link", "reviewed_by_phone",
        "created_at", "reviewed_at",
    )
    list_filter   = ("status", "plan", "created_at")
    search_fields = ("user__phone", "user__email", "plan__name")
    readonly_fields = (
        "id", "user", "plan", "amount", "receipt",
        "receipt_preview", "reviewed_by", "reviewed_at", "created_at",
    )
    list_per_page = 20
    date_hierarchy = "created_at"

    fieldsets = (
        ("Payment Info", {
            "fields": ("id", "user", "plan", "amount"),
        }),
        ("Receipt", {
            "fields": ("receipt", "receipt_preview"),
        }),
        ("Review", {
            "fields": ("status", "reviewed_by", "reviewed_at", "rejection_reason"),
        }),
        ("Timestamps", {
            "fields": ("created_at",),
            "classes": ("collapse",),
        }),
    )

    actions = ["approve_payments", "reject_payments"]

    @admin.display(description="ID")
    def short_id(self, obj):
        return format_html(
            '<span style="font-family:monospace;font-size:11px;color:#7b93b4">{}</span>',
            str(obj.id)[:8] + "…"
        )

    @admin.display(description="User Phone")
    def user_phone(self, obj):
        return obj.user.phone if obj.user else "—"

    @admin.display(description="Role")
    def user_role(self, obj):
        if not obj.user:
            return "—"
        colors = {"client": "#00b4ff", "business": "#b39ddb", "admin": "#ffb300"}
        color  = colors.get(obj.user.role, "#fff")
        return format_html(
            '<span style="color:{};font-weight:600;font-size:11px">{}</span>',
            color, obj.user.role.upper()
        )

    @admin.display(description="Plan")
    def plan_name(self, obj):
        return obj.plan.name if obj.plan else "—"

    @admin.display(description="Amount")
    def amount_display(self, obj):
        return format_html('<strong style="color:#00b4ff">{} DZD</strong>', obj.amount)

    @admin.display(description="Status")
    def status_badge(self, obj):
        colors = {
            "PENDING":  ("#ffb300", "#1a1200"),
            "APPROVED": ("#00e676", "#003300"),
            "REJECTED": ("#ef5350", "#fff"),
        }
        bg, fg = colors.get(obj.status, ("#555", "#fff"))
        return format_html(
            '<span style="background:{};color:{};padding:2px 8px;'
            'border-radius:4px;font-size:11px;font-weight:600">{}</span>',
            bg, fg, obj.status
        )

    @admin.display(description="Receipt")
    def receipt_link(self, obj):
        if obj.receipt:
            return format_html(
                '<a href="{}" target="_blank" style="color:#00b4ff">'
                '📄 View</a>',
                obj.receipt.url
            )
        return "—"

    @admin.display(description="Receipt Preview")
    def receipt_preview(self, obj):
        if not obj.receipt:
            return "No receipt uploaded."
        url = obj.receipt.url
        if url.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            return format_html(
                '<img src="{}" style="max-width:300px;max-height:300px;'
                'object-fit:contain;border-radius:8px;border:1px solid #333" />',
                url
            )
        return format_html(
            '<a href="{}" target="_blank" style="color:#00b4ff">'
            '📄 Open PDF Receipt</a>',
            url
        )

    @admin.display(description="Reviewed By")
    def reviewed_by_phone(self, obj):
        return obj.reviewed_by.phone if obj.reviewed_by else "—"

    @admin.action(description="✅ Approve selected payments & activate subscriptions")
    def approve_payments(self, request, queryset):
        import datetime as dt
        pending = queryset.filter(status="PENDING")
        count   = 0
        for payment in pending.select_related("user", "plan"):
            if not payment.plan:
                continue
            payment.status      = "APPROVED"
            payment.reviewed_by = request.user
            payment.reviewed_at = timezone.now()
            payment.save(update_fields=["status", "reviewed_by", "reviewed_at"])

            end = timezone.now() + dt.timedelta(days=payment.plan.duration_days)
            payment.user.subscription_status = "ACTIVE"
            payment.user.subscription_end    = end
            payment.user.current_plan        = payment.plan
            payment.user.save(update_fields=["subscription_status", "subscription_end", "current_plan"])
            count += 1

        self.message_user(request, f"{count} payment(s) approved and subscriptions activated.")

    @admin.action(description="❌ Reject selected payments")
    def reject_payments(self, request, queryset):
        pending = queryset.filter(status="PENDING")
        count   = 0
        for payment in pending.select_related("user"):
            payment.status      = "REJECTED"
            payment.reviewed_by = request.user
            payment.reviewed_at = timezone.now()
            payment.rejection_reason = "Rejected via bulk action."
            payment.save(update_fields=["status", "reviewed_by", "reviewed_at", "rejection_reason"])

            if payment.user.subscription_status == "PENDING":
                payment.user.subscription_status = "FREE"
                payment.user.save(update_fields=["subscription_status"])
            count += 1

        self.message_user(request, f"{count} payment(s) rejected.")