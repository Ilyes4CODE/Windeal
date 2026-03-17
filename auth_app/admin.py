# App: auth_app | File: admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.utils import timezone
from .models import User, ClientProfile, BusinessProfile


# ─── Inlines ──────────────────────────────────────────────────────────────────

class ClientProfileInline(admin.StackedInline):
    model        = ClientProfile
    extra        = 0
    verbose_name = "Client Profile"
    # Updated: full_name, email, wilaya, school (date_of_birth removed)
    fields       = ("full_name", "email", "wilaya", "school")
    can_delete   = False


class BusinessProfileInline(admin.StackedInline):
    model        = BusinessProfile
    extra        = 0
    verbose_name = "Business Profile"
    fields       = (
        "business_name", "description", "category",
        "address", "website",
        "latitude", "longitude",
        "is_active",
    )
    can_delete = False


# ─── User Admin ───────────────────────────────────────────────────────────────

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering      = ("-created_at",)
    list_display  = (
        "phone", "email", "role_badge", "city",
        "verified_icon", "active_icon", "banned_icon",
        "subscription_badge", "subscription_end",
        "created_at",
    )
    list_filter   = ("role", "is_verified", "is_active", "is_banned", "subscription_status")
    search_fields = ("phone", "email", "city")
    readonly_fields  = ("id", "created_at", "updated_at", "last_login")
    list_per_page    = 25
    date_hierarchy   = "created_at"

    fieldsets = (
        ("Identity", {
            "fields": ("id", "phone", "email", "password"),
        }),
        ("Role & Status", {
            "fields": ("role", "is_verified", "is_active", "is_banned", "is_staff", "is_superuser"),
        }),
        ("Profile", {
            "fields": ("profile_picture", "city"),
        }),
        ("Subscription", {
            "fields": ("subscription_status", "subscription_end", "current_plan"),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at", "last_login"),
            "classes": ("collapse",),
        }),
        ("Permissions", {
            "fields": ("groups", "user_permissions"),
            "classes": ("collapse",),
        }),
    )

    add_fieldsets = (
        ("New User", {
            "classes": ("wide",),
            "fields": ("phone", "role", "password1", "password2", "is_verified", "is_active"),
        }),
    )

    def get_inlines(self, request, obj=None):
        if obj is None:
            return []
        if obj.role == "client":
            return [ClientProfileInline]
        if obj.role == "business":
            return [BusinessProfileInline]
        return []

    # ── Display helpers ──────────────────────────────────────────────────────

    @admin.display(description="Role")
    def role_badge(self, obj):
        colors = {
            "admin":    ("#ffb300", "#1a1200"),
            "business": ("#7c4dff", "#f3e5f5"),
            "client":   ("#00b4ff", "#e3f2fd"),
        }
        bg, fg = colors.get(obj.role, ("#555", "#fff"))
        return format_html(
            '<span style="background:{};color:{};padding:2px 8px;'
            'border-radius:4px;font-size:11px;font-weight:600">{}</span>',
            bg, fg, obj.role.upper()
        )

    @admin.display(description="Verified", boolean=False)
    def verified_icon(self, obj):
        return format_html(
            '<span style="color:{}">&#{}</span>',
            "#00e676" if obj.is_verified else "#ef5350",
            "10004"   if obj.is_verified else "10008",
        )

    @admin.display(description="Active", boolean=False)
    def active_icon(self, obj):
        return format_html(
            '<span style="color:{}">&#{}</span>',
            "#00e676" if obj.is_active else "#ef5350",
            "10004"   if obj.is_active else "10008",
        )

    @admin.display(description="Banned", boolean=False)
    def banned_icon(self, obj):
        if obj.is_banned:
            return format_html(
                '<span style="background:#ef5350;color:#fff;padding:2px 8px;'
                'border-radius:4px;font-size:11px;font-weight:600">BANNED</span>'
            )
        return format_html('<span style="color:#4a6080;font-size:11px">—</span>')

    @admin.display(description="Subscription")
    def subscription_badge(self, obj):
        colors = {
            "FREE":    ("#607d8b", "#fff"),
            "PENDING": ("#ffb300", "#1a1200"),
            "ACTIVE":  ("#00e676", "#003300"),
            "EXPIRED": ("#ef5350", "#fff"),
        }
        bg, fg = colors.get(obj.subscription_status, ("#555", "#fff"))
        return format_html(
            '<span style="background:{};color:{};padding:2px 8px;'
            'border-radius:4px;font-size:11px;font-weight:600">{}</span>',
            bg, fg, obj.subscription_status
        )

    # ── Bulk actions ─────────────────────────────────────────────────────────

    actions = [
        "mark_verified", "mark_unverified",
        "activate_users", "deactivate_users",
        "ban_users", "unban_users",
        "reset_subscription",
    ]

    @admin.action(description="✅ Mark selected users as verified")
    def mark_verified(self, request, queryset):
        updated = queryset.update(is_verified=True)
        self.message_user(request, f"{updated} user(s) marked as verified.")

    @admin.action(description="❌ Mark selected users as unverified")
    def mark_unverified(self, request, queryset):
        updated = queryset.update(is_verified=False)
        self.message_user(request, f"{updated} user(s) marked as unverified.")

    @admin.action(description="🟢 Activate selected users")
    def activate_users(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} user(s) activated.")

    @admin.action(description="🔴 Deactivate selected users")
    def deactivate_users(self, request, queryset):
        updated = queryset.exclude(role="admin").update(is_active=False)
        self.message_user(request, f"{updated} user(s) deactivated.")

    @admin.action(description="🚫 Ban selected users")
    def ban_users(self, request, queryset):
        updated = queryset.exclude(role="admin").update(is_banned=True)
        self.message_user(request, f"{updated} user(s) banned.")

    @admin.action(description="🔓 Unban selected users")
    def unban_users(self, request, queryset):
        updated = queryset.update(is_banned=False)
        self.message_user(request, f"{updated} user(s) unbanned.")

    @admin.action(description="🔄 Reset subscription to FREE")
    def reset_subscription(self, request, queryset):
        updated = queryset.update(
            subscription_status="FREE",
            subscription_end=None,
            current_plan=None,
        )
        self.message_user(request, f"{updated} user(s) subscription reset to FREE.")


# ─── ClientProfile Admin ──────────────────────────────────────────────────────

@admin.register(ClientProfile)
class ClientProfileAdmin(admin.ModelAdmin):
    # Updated: full_name, wilaya, school — no date_of_birth, no first_name/last_name
    list_display  = ("full_name", "user_phone", "wilaya", "school")
    search_fields = ("full_name", "wilaya", "school", "user__phone", "email")
    list_filter   = ("wilaya",)
    list_per_page = 25

    fieldsets = (
        ("Profile", {
            "fields": ("user", "full_name", "email", "wilaya", "school"),
        }),
    )

    @admin.display(description="Phone")
    def user_phone(self, obj):
        return obj.user.phone


# ─── BusinessProfile Admin ────────────────────────────────────────────────────

@admin.register(BusinessProfile)
class BusinessProfileAdmin(admin.ModelAdmin):
    list_display  = (
        "business_name", "user_phone", "category",
        "city", "has_location", "is_active",
    )
    list_filter   = ("is_active", "category")
    search_fields = ("business_name", "user__phone", "address")
    readonly_fields = ("map_preview",)
    list_per_page   = 25

    fieldsets = (
        ("Business Info", {
            "fields": ("user", "business_name", "description", "category", "is_active"),
        }),
        ("Contact", {
            "fields": ("address", "website"),
        }),
        ("Location (Google Maps)", {
            "fields": ("latitude", "longitude", "map_preview"),
        }),
    )

    @admin.display(description="Phone")
    def user_phone(self, obj):
        return obj.user.phone

    @admin.display(description="City")
    def city(self, obj):
        return obj.user.city or "—"

    @admin.display(description="Has Location", boolean=True)
    def has_location(self, obj):
        return obj.latitude is not None and obj.longitude is not None

    @admin.display(description="Map Preview")
    def map_preview(self, obj):
        if obj.latitude is None or obj.longitude is None:
            return "No coordinates set."
        url = (
            f"https://www.google.com/maps?q={obj.latitude},{obj.longitude}"
            f"&z=15&output=embed"
        )
        return format_html(
            '<iframe src="{}" width="100%" height="300" style="border:0;border-radius:8px" '
            'loading="lazy" allowfullscreen></iframe>'
            '<br><a href="https://www.google.com/maps?q={},{}" target="_blank">'
            'Open in Google Maps ↗</a>',
            url, obj.latitude, obj.longitude
        )