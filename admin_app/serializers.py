# App: admin_app | File: serializers.py
from rest_framework import serializers
from .models import Category, SubscriptionPlan, Payment
from auth_app.models import User


def _e(en, ar, fr):
    return {"en": en, "ar": ar, "fr": fr}


ERRORS = {
    "category_name_short":      _e("Category name must be at least 2 characters.",               "يجب أن يكون اسم الفئة حرفين على الأقل.",                   "Le nom de la catégorie doit comporter au moins 2 caractères."),
    "category_name_exists":     _e("A category with this name already exists.",                  "فئة بهذا الاسم موجودة مسبقاً.",                             "Une catégorie avec ce nom existe déjà."),
    "plan_name_short":          _e("Plan name must be at least 2 characters.",                   "يجب أن يكون اسم الخطة حرفين على الأقل.",                   "Le nom du plan doit comporter au moins 2 caractères."),
    "plan_price_zero":          _e("Price must be greater than zero.",                           "يجب أن يكون السعر أكبر من الصفر.",                         "Le prix doit être supérieur à zéro."),
    "plan_duration_zero":       _e("Duration days must be greater than zero.",                   "يجب أن تكون مدة الأيام أكبر من الصفر.",                    "Le nombre de jours de durée doit être supérieur à zéro."),
    "rejection_reason_missing": _e("A rejection reason is required when rejecting a payment.",   "سبب الرفض مطلوب عند رفض الدفع.",                           "Une raison de rejet est requise lors du rejet d'un paiement."),
}


def _get_lang(context):
    request = context.get("request") if context else None
    if request:
        raw = request.headers.get("Accept-Language", "en")[:2].lower()
        return raw if raw in ("en", "ar", "fr") else "en"
    return "en"


def _err(key, context):
    lang = _get_lang(context)
    return ERRORS[key].get(lang, ERRORS[key]["en"])


class CategorySerializer(serializers.ModelSerializer):
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ["id", "name", "photo", "photo_url", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "photo_url", "created_at", "updated_at"]
        extra_kwargs = {"photo": {"write_only": True, "required": False}}

    def get_photo_url(self, obj):
        request = self.context.get("request")
        if obj.photo and request:
            return request.build_absolute_uri(obj.photo.url)
        if obj.photo:
            return obj.photo.url
        return None

    def validate_name(self, value):
        if len(value.strip()) < 2:
            raise serializers.ValidationError(_err("category_name_short", self.context))
        qs = Category.objects.filter(name__iexact=value.strip())
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(_err("category_name_exists", self.context))
        return value.strip()


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    duration_type_display = serializers.CharField(source="get_duration_type_display", read_only=True)
    target_role_display = serializers.CharField(source="get_target_role_display", read_only=True)

    class Meta:
        model = SubscriptionPlan
        fields = [
            "id",
            "name",
            "description",
            "price",
            "duration_type",
            "duration_type_display",
            "duration_days",
            "target_role",
            "target_role_display",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "duration_type_display", "target_role_display", "created_at", "updated_at"]

    def validate_name(self, value):
        if len(value.strip()) < 2:
            raise serializers.ValidationError(_err("plan_name_short", self.context))
        return value.strip()

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError(_err("plan_price_zero", self.context))
        return value

    def validate_duration_days(self, value):
        if value <= 0:
            raise serializers.ValidationError(_err("plan_duration_zero", self.context))
        return value


class SubscriptionPlanMinimalSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = ["id", "name", "price", "duration_type", "duration_days", "target_role"]


class PaymentUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "phone", "email", "role", "city"]


class PaymentSerializer(serializers.ModelSerializer):
    user = PaymentUserSerializer(read_only=True)
    plan = SubscriptionPlanMinimalSerializer(read_only=True)
    reviewed_by_phone = serializers.CharField(source="reviewed_by.phone", read_only=True)
    receipt_url = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = [
            "id",
            "user",
            "plan",
            "amount",
            "receipt",
            "receipt_url",
            "status",
            "reviewed_by_phone",
            "rejection_reason",
            "created_at",
            "reviewed_at",
        ]
        read_only_fields = [
            "id",
            "user",
            "plan",
            "receipt_url",
            "reviewed_by_phone",
            "created_at",
            "reviewed_at",
        ]
        extra_kwargs = {"receipt": {"write_only": True}}

    def get_receipt_url(self, obj):
        request = self.context.get("request")
        if obj.receipt and request:
            return request.build_absolute_uri(obj.receipt.url)
        if obj.receipt:
            return obj.receipt.url
        return None


class ApprovePaymentSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["approve", "reject"])
    rejection_reason = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        if data["action"] == "reject" and not data.get("rejection_reason", "").strip():
            raise serializers.ValidationError(
                {"rejection_reason": _err("rejection_reason_missing", self.context)}
            )
        return data


class AdminUserListSerializer(serializers.ModelSerializer):
    current_plan_name = serializers.CharField(source="current_plan.name", read_only=True)
    client_profile = serializers.SerializerMethodField()
    business_profile = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "phone",
            "email",
            "role",
            "city",
            "profile_picture",
            "subscription_status",
            "subscription_end",
            "current_plan_name",
            "is_verified",
            "is_active",
            "is_banned",
            "created_at",
            "client_profile",
            "business_profile",
        ]
        read_only_fields = fields

    def get_client_profile(self, obj):
        if obj.role == "client" and hasattr(obj, "client_profile"):
            p = obj.client_profile
            return {
                "full_name": p.full_name,
                "email":     p.email,
                "wilaya":    p.wilaya,
                "school":    p.school,
            }
        return None

    def get_business_profile(self, obj):
        if obj.role == "business" and hasattr(obj, "business_profile"):
            bp = obj.business_profile
            return {
                "business_name": bp.business_name,
                "description": bp.description,
                "category_id": str(bp.category.id) if bp.category else None,
                "category_name": bp.category.name if bp.category else None,
                "address": bp.address,
                "website": bp.website,
                "latitude": str(bp.latitude) if bp.latitude is not None else None,
                "longitude": str(bp.longitude) if bp.longitude is not None else None,
                "is_active": bp.is_active,
            }
        return None


class AdminSetSubscriptionSerializer(serializers.Serializer):
    subscription_status = serializers.ChoiceField(choices=["FREE", "PENDING", "ACTIVE", "EXPIRED"])