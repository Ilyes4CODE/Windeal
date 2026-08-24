# App: deals_app | File: serializers.py
from decimal import Decimal
from rest_framework import serializers
from .models import Deal, Favorite, RedemptionToken, Redemption, Notification, DealRating
from admin_app.models import Category, SubscriptionPlan
from auth_app.models import BusinessProfile
from auth_app.serializers import split_coords


class RateDealSerializer(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5,
                help_text="1 to 5 stars.")


# ─── Categories (public) ──────────────────────────────────────────────────────

def _req_lang(context):
    request = context.get("request") if context else None
    if request:
        raw = request.headers.get("Accept-Language", "en")[:2].lower()
        return raw if raw in ("en", "ar", "fr") else "en"
    return "en"


class PublicCategorySerializer(serializers.ModelSerializer):
    name     = serializers.SerializerMethodField()
    icon_url = serializers.SerializerMethodField()

    class Meta:
        model  = Category
        fields = ["id", "name", "icon_url"]

    def get_name(self, obj):
        # Localised to the Accept-Language header (falls back to the default name).
        return obj.localized_name(_req_lang(self.context))

    def get_icon_url(self, obj):
        request = self.context.get("request")
        if obj.photo and request:
            return request.build_absolute_uri(obj.photo.url)
        if obj.photo:
            return obj.photo.url
        return None


# ─── Deals (client side: list) ────────────────────────────────────────────────

class DealListSerializer(serializers.ModelSerializer):
    item_name        = serializers.CharField(source="title")
    item_description = serializers.CharField(source="description")
    item_image       = serializers.SerializerMethodField()
    category_name    = serializers.SerializerMethodField()
    business_name    = serializers.SerializerMethodField()
    location_name    = serializers.SerializerMethodField()
    latitude         = serializers.SerializerMethodField()
    longitude        = serializers.SerializerMethodField()
    discount_amount  = serializers.CharField(source="discount_value")
    is_favorite      = serializers.SerializerMethodField()
    distance_km      = serializers.SerializerMethodField()
    my_rating        = serializers.SerializerMethodField()

    class Meta:
        model  = Deal
        fields = [
            "id",
            "item_name", "item_description", "item_image",
            "category_name",
            "rating", "ratings_count", "my_rating",
            "business_name", "location_name",
            "latitude", "longitude",
            "discount_amount", "old_price", "new_price",
            "is_favorite",
            "is_featured",
            "distance_km",
            "expiry_date", "is_active",
            "created_at",
        ]

    # ── helpers ────────────────────────────────────────────────────────────────
    def get_item_image(self, obj):
        request = self.context.get("request")
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        if obj.image:
            return obj.image.url
        return None

    def get_category_name(self, obj):
        return obj.category.localized_name(_req_lang(self.context)) if obj.category else None

    def _business_profile(self, obj):
        return getattr(obj.business, "business_profile", None)

    def get_business_name(self, obj):
        bp = self._business_profile(obj)
        return bp.business_name if bp else None

    def get_location_name(self, obj):
        # Human-readable place shown in the app. Prefer the business address,
        # fall back to the city. Guard against legacy rows where a client stored
        # coordinates in `address` — never surface raw coords as a place name.
        bp = self._business_profile(obj)
        city = obj.business.city if obj.business else None
        if not bp:
            return city or None
        address = bp.address
        if address and split_coords(address):
            address = None
        return address or city or None

    def get_latitude(self, obj):
        bp = self._business_profile(obj)
        return float(bp.latitude) if bp and bp.latitude is not None else None

    def get_longitude(self, obj):
        bp = self._business_profile(obj)
        return float(bp.longitude) if bp and bp.longitude is not None else None

    def get_is_favorite(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return False
        # Optional perf hint: callers may pre-compute favorite_ids in context
        fav_ids = self.context.get("favorite_ids")
        if fav_ids is not None:
            return obj.id in fav_ids
        return Favorite.objects.filter(user=user, deal=obj).exists()

    def get_distance_km(self, obj):
        # Populated by the Nearby endpoint via context["distances"] = {deal_id: km}.
        distances = self.context.get("distances")
        if not distances:
            return None
        km = distances.get(obj.id)
        return round(km, 2) if km is not None else None

    def get_my_rating(self, obj):
        """The current user's own rating (1-5), or null if not logged in / not rated."""
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return None
        # Optional perf hint: callers may pre-compute my_rating_map in context.
        rating_map = self.context.get("my_rating_map")
        if rating_map is not None:
            return rating_map.get(obj.id)
        r = DealRating.objects.filter(user=user, deal=obj).values_list("rating", flat=True).first()
        return r


# ─── Business offers (CRUD) ───────────────────────────────────────────────────

class BusinessOfferSerializer(serializers.ModelSerializer):
    """
    Used by business owners to list/create/update their own offers.

    ``discount_value`` is **auto-calculated** from ``old_price`` and
    ``new_price`` (e.g. 2000 → 1000 = "50%") — it is read-only and any value
    the client sends is ignored.
    """
    image_url      = serializers.SerializerMethodField()
    category_name  = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model  = Deal
        fields = [
            "id",
            "title", "description",
            "image", "image_url",
            "category", "category_name",
            "discount_value",
            "old_price", "new_price",
            "rating",
            "expiry_date",
            "is_active",
            "is_featured",
            "is_blocked",
            "created_at", "updated_at",
        ]
        # discount_value is derived; is_featured/is_blocked are admin-controlled.
        read_only_fields = ["id", "image_url", "category_name", "discount_value",
                            "rating", "is_featured", "is_blocked", "created_at", "updated_at"]
        extra_kwargs = {
            "image":     {"write_only": True, "required": False, "allow_null": True},
            "category":  {"required": False, "allow_null": True},
        }

    def get_image_url(self, obj):
        request = self.context.get("request")
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        if obj.image:
            return obj.image.url
        return None

    def validate_title(self, value):
        if not value or len(value.strip()) < 2:
            raise serializers.ValidationError("Title must be at least 2 characters.")
        return value.strip()

    def validate(self, attrs):
        # Consider existing instance values so partial (PATCH) updates validate too.
        old_p = attrs.get("old_price", getattr(self.instance, "old_price", None))
        new_p = attrs.get("new_price", getattr(self.instance, "new_price", None))
        if old_p is not None and new_p is not None and new_p > old_p:
            raise serializers.ValidationError({"new_price": "New price must be less than or equal to old price."})
        return attrs

    @staticmethod
    def compute_discount(old_price, new_price):
        """
        Percentage saved, as a string like ``"50%"``.
        Returns ``""`` when it can't be computed (missing/zero old price, or
        the new price is not actually lower).
        """
        try:
            if old_price is None or new_price is None:
                return ""
            old_price = Decimal(str(old_price))
            new_price = Decimal(str(new_price))
            if old_price <= 0 or new_price >= old_price:
                return ""
            pct = (old_price - new_price) / old_price * Decimal(100)
            return f"{int(round(pct))}%"
        except Exception:
            return ""

    def _apply_discount(self, instance):
        discount = self.compute_discount(instance.old_price, instance.new_price)
        if instance.discount_value != discount:
            instance.discount_value = discount
            instance.save(update_fields=["discount_value"])

    def create(self, validated_data):
        validated_data.pop("discount_value", None)  # always derived, never client-set
        instance = super().create(validated_data)
        self._apply_discount(instance)
        return instance

    def update(self, instance, validated_data):
        validated_data.pop("discount_value", None)
        instance = super().update(instance, validated_data)
        self._apply_discount(instance)
        return instance


# ─── Subscription plans (client read-only) ────────────────────────────────────

class SubscriptionPlanPublicSerializer(serializers.ModelSerializer):
    title           = serializers.CharField(source="name")
    duration_months = serializers.SerializerMethodField()
    discount_label  = serializers.SerializerMethodField()
    billing_detail  = serializers.SerializerMethodField()

    class Meta:
        model  = SubscriptionPlan
        fields = ["id", "title", "price", "discount_label",
                  "duration_months", "duration_days", "billing_detail",
                  "target_role", "is_active"]

    def get_duration_months(self, obj):
        if obj.duration_type == "monthly":
            return 1
        if obj.duration_type == "quarterly":
            return 3
        if obj.duration_type == "semi_annual":
            return 6
        if obj.duration_type == "annual":
            return 12
        # custom — best-effort estimate from duration_days
        return max(1, round((obj.duration_days or 0) / 30))

    def get_discount_label(self, obj):
        if obj.duration_type == "monthly":
            return ""
        if obj.duration_type == "annual":
            return "Save 20%"
        if obj.duration_type == "semi_annual":
            return "Save 10%"
        return ""

    def get_billing_detail(self, obj):
        months = self.get_duration_months(obj)
        if months <= 1:
            return f"{obj.price} DZD billed monthly"
        return f"{obj.price} DZD billed every {months} months"


class SubscriptionUpgradeSerializer(serializers.Serializer):
    plan_id          = serializers.UUIDField()
    payment_method   = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    reference_number = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    receipt_image    = serializers.FileField()

    def validate_receipt_image(self, value):
        allowed = ["image/jpeg", "image/png", "image/jpg", "application/pdf"]
        if hasattr(value, "content_type") and value.content_type not in allowed:
            raise serializers.ValidationError("Receipt must be a JPEG, PNG, or PDF file.")
        if value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError("Receipt file must not exceed 5MB.")
        return value


# ─── Notifications ────────────────────────────────────────────────────────────

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Notification
        fields = ["id", "title", "body", "type", "is_read", "created_at"]
        read_only_fields = fields


# ─── QR generation / redemption ───────────────────────────────────────────────

class GenerateCodeSerializer(serializers.Serializer):
    deal_id = serializers.UUIDField()


class RedeemSerializer(serializers.Serializer):
    qr_token = serializers.CharField(max_length=256)


# ─── Toggle favorite ──────────────────────────────────────────────────────────

class ToggleFavoriteSerializer(serializers.Serializer):
    deal_id = serializers.UUIDField()


# ─── Payment history (client/business view of their own payments) ──────────────

class PaymentHistorySerializer(serializers.ModelSerializer):
    """User-facing view of a subscription payment, per the additional spec."""
    transaction_date  = serializers.DateTimeField(source="created_at", read_only=True)
    subscription_plan = serializers.CharField(source="plan.name", read_only=True, default=None)

    class Meta:
        from admin_app.models import Payment as _Payment
        model  = _Payment
        fields = [
            "id",
            "transaction_date",
            "amount",
            "payment_method",
            "subscription_plan",
            "reference_number",
            "status",
        ]
        read_only_fields = fields


# ─── Admin deal listing / featuring ───────────────────────────────────────────

class AdminDealSerializer(serializers.ModelSerializer):
    """Deal representation for the admin panel (featuring / block control + detail card)."""
    business_name  = serializers.SerializerMethodField()
    business_phone = serializers.SerializerMethodField()
    category_name  = serializers.SerializerMethodField()
    image_url      = serializers.SerializerMethodField()
    location_name  = serializers.SerializerMethodField()

    class Meta:
        model  = Deal
        fields = [
            "id", "title", "description", "image_url",
            "business_name", "business_phone", "category_name", "location_name",
            "discount_value", "old_price", "new_price",
            "rating", "ratings_count",
            "is_featured", "is_active", "is_blocked",
            "expiry_date", "created_at",
        ]
        read_only_fields = fields

    def get_business_name(self, obj):
        bp = getattr(obj.business, "business_profile", None)
        return bp.business_name if bp else (obj.business.phone if obj.business else None)

    def get_business_phone(self, obj):
        return obj.business.phone if obj.business else None

    def get_category_name(self, obj):
        return obj.category.localized_name(_req_lang(self.context)) if obj.category else None

    def get_image_url(self, obj):
        request = self.context.get("request")
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        if obj.image:
            return obj.image.url
        return None

    def get_location_name(self, obj):
        bp = getattr(obj.business, "business_profile", None)
        city = obj.business.city if obj.business else None
        if not bp:
            return city or None
        address = bp.address
        if address and split_coords(address):
            address = None
        return address or city or None


class FeatureDealSerializer(serializers.Serializer):
    is_featured = serializers.BooleanField(required=False,
        help_text="Explicit value to set. If omitted, the current flag is toggled.")


class BlockDealSerializer(serializers.Serializer):
    is_blocked = serializers.BooleanField(required=False,
        help_text="Explicit value to set. If omitted, the current block flag is toggled.")
