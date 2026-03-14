# App: auth_app | File: serializers.py
from rest_framework import serializers
from decimal import Decimal
from .models import User, ClientProfile, BusinessProfile


def _e(en, ar, fr):
    return {"en": en, "ar": ar, "fr": fr}


ERRORS = {
    "phone_digits_only":     _e("Phone number must contain digits only.",            "يجب أن يحتوي رقم الهاتف على أرقام فقط.",           "Le numéro de téléphone doit contenir uniquement des chiffres."),
    "phone_already_exists":  _e("Phone number already registered.",                  "رقم الهاتف مسجل مسبقاً.",                           "Ce numéro de téléphone est déjà enregistré."),
    "phone_not_found":       _e("No account found with this phone number.",          "لا يوجد حساب مرتبط بهذا الرقم.",                   "Aucun compte trouvé avec ce numéro de téléphone."),
    "already_verified":      _e("This account is already verified.",                 "هذا الحساب موثق مسبقاً.",                           "Ce compte est déjà vérifié."),
    "identifier_blank":      _e("Identifier cannot be blank.",                       "لا يمكن أن يكون المعرّف فارغاً.",                   "L'identifiant ne peut pas être vide."),
    "first_name_letters":    _e("First name must contain letters only.",             "يجب أن يحتوي الاسم الأول على أحرف فقط.",           "Le prénom doit contenir uniquement des lettres."),
    "last_name_letters":     _e("Last name must contain letters only.",              "يجب أن يحتوي اسم العائلة على أحرف فقط.",           "Le nom de famille doit contenir uniquement des lettres."),
    "business_name_short":   _e("Business name must be at least 2 characters.",      "يجب أن يكون اسم النشاط التجاري حرفين على الأقل.",  "Le nom de l'entreprise doit comporter au moins 2 caractères."),
    "receipt_type":          _e("Receipt must be a JPEG, PNG, or PDF file.",         "يجب أن يكون الإيصال ملف JPEG أو PNG أو PDF.",      "Le reçu doit être un fichier JPEG, PNG ou PDF."),
    "receipt_size":          _e("Receipt file must not exceed 5MB.",                 "يجب ألا يتجاوز حجم ملف الإيصال 5 ميجابايت.",      "Le fichier reçu ne doit pas dépasser 5 Mo."),
    "lat_range":             _e("Latitude must be between -90 and 90.",              "يجب أن يكون خط العرض بين -90 و 90.",               "La latitude doit être comprise entre -90 et 90."),
    "lng_range":             _e("Longitude must be between -180 and 180.",           "يجب أن يكون خط الطول بين -180 و 180.",             "La longitude doit être comprise entre -180 et 180."),
    "lat_required_with_lng": _e("Latitude is required when longitude is provided.",  "خط العرض مطلوب عند تقديم خط الطول.",               "La latitude est requise lorsque la longitude est fournie."),
    "lng_required_with_lat": _e("Longitude is required when latitude is provided.",  "خط الطول مطلوب عند تقديم خط العرض.",               "La longitude est requise lorsque la latitude est fournie."),
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


# ─── Read serializers ────────────────────────────────────────────────────────

class ClientProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientProfile
        fields = ["first_name", "last_name", "date_of_birth"]


class BusinessProfileSerializer(serializers.ModelSerializer):
    category_id = serializers.UUIDField(source="category.id", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    category_photo = serializers.SerializerMethodField()

    class Meta:
        model = BusinessProfile
        fields = [
            "business_name",
            "description",
            "category_id",
            "category_name",
            "category_photo",
            "address",
            "website",
            "latitude",
            "longitude",
            "is_active",
        ]

    def get_category_photo(self, obj):
        request = self.context.get("request")
        if obj.category and obj.category.photo:
            if request:
                return request.build_absolute_uri(obj.category.photo.url)
            return obj.category.photo.url
        return None


class UserReadSerializer(serializers.ModelSerializer):
    client_profile = ClientProfileSerializer(read_only=True)
    business_profile = BusinessProfileSerializer(read_only=True)
    current_plan_name = serializers.CharField(source="current_plan.name", read_only=True)
    current_plan_id = serializers.UUIDField(source="current_plan.id", read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "phone", "email", "role", "city", "profile_picture",
            "is_verified", "is_active",
            "subscription_status", "subscription_end",
            "current_plan_id", "current_plan_name",
            "created_at", "updated_at",
            "client_profile", "business_profile",
        ]
        read_only_fields = fields


# ─── Registration ─────────────────────────────────────────────────────────────

class ClientRegisterSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)
    password = serializers.CharField(write_only=True, min_length=6)
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    date_of_birth = serializers.DateField(required=False, allow_null=True)

    def validate_phone(self, value):
        if not value.lstrip("+").isdigit():
            raise serializers.ValidationError(_err("phone_digits_only", self.context))
        if User.objects.filter(phone=value).exists():
            raise serializers.ValidationError(_err("phone_already_exists", self.context))
        return value


class BusinessRegisterSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)
    password = serializers.CharField(write_only=True, min_length=6)
    business_name = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True)
    category_id = serializers.UUIDField(required=False, allow_null=True)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    address = serializers.CharField(max_length=300, required=False, allow_blank=True)
    website = serializers.URLField(required=False, allow_blank=True)
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)

    def validate_phone(self, value):
        if not value.lstrip("+").isdigit():
            raise serializers.ValidationError(_err("phone_digits_only", self.context))
        if User.objects.filter(phone=value).exists():
            raise serializers.ValidationError(_err("phone_already_exists", self.context))
        return value

    def validate_latitude(self, value):
        if value is not None and not (-90 <= float(value) <= 90):
            raise serializers.ValidationError(_err("lat_range", self.context))
        return value

    def validate_longitude(self, value):
        if value is not None and not (-180 <= float(value) <= 180):
            raise serializers.ValidationError(_err("lng_range", self.context))
        return value

    def validate(self, data):
        lat = data.get("latitude")
        lng = data.get("longitude")
        if lat is not None and lng is None:
            raise serializers.ValidationError({"longitude": _err("lng_required_with_lat", self.context)})
        if lng is not None and lat is None:
            raise serializers.ValidationError({"latitude": _err("lat_required_with_lng", self.context)})
        return data


# ─── Verification ─────────────────────────────────────────────────────────────

class VerifyAccountSerializer(serializers.Serializer):
    """
    Called by the app developer once the external SMS/OTP provider confirms
    that the user has successfully verified their phone number on the client side.
    The backend simply marks the account as verified — no OTP logic here.
    """
    phone = serializers.CharField(max_length=20)

    def validate_phone(self, value):
        if not value.lstrip("+").isdigit():
            raise serializers.ValidationError(_err("phone_digits_only", self.context))
        try:
            user = User.objects.get(phone=value)
        except User.DoesNotExist:
            raise serializers.ValidationError(_err("phone_not_found", self.context))
        if user.is_verified:
            raise serializers.ValidationError(_err("already_verified", self.context))
        return value


# ─── Auth ─────────────────────────────────────────────────────────────────────

class LoginSerializer(serializers.Serializer):
    identifier = serializers.CharField(max_length=255, help_text="Phone number or email address")
    password = serializers.CharField(write_only=True, min_length=1)

    def validate_identifier(self, value):
        if not value.strip():
            raise serializers.ValidationError(_err("identifier_blank", self.context))
        return value.strip()


# ─── Profile update ───────────────────────────────────────────────────────────

class UpdateClientProfileSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    profile_picture = serializers.ImageField(required=False, allow_null=True)
    first_name = serializers.CharField(max_length=100, required=False)
    last_name = serializers.CharField(max_length=100, required=False)
    date_of_birth = serializers.DateField(required=False, allow_null=True)

    def validate_first_name(self, value):
        if value and not value.replace(" ", "").isalpha():
            raise serializers.ValidationError(_err("first_name_letters", self.context))
        return value

    def validate_last_name(self, value):
        if value and not value.replace(" ", "").isalpha():
            raise serializers.ValidationError(_err("last_name_letters", self.context))
        return value


class UpdateBusinessProfileSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    profile_picture = serializers.ImageField(required=False, allow_null=True)
    business_name = serializers.CharField(max_length=200, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    category_id = serializers.UUIDField(required=False, allow_null=True)
    address = serializers.CharField(max_length=300, required=False, allow_blank=True)
    website = serializers.URLField(required=False, allow_blank=True, allow_null=True)
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)

    def validate_business_name(self, value):
        if value is not None and len(value.strip()) < 2:
            raise serializers.ValidationError(_err("business_name_short", self.context))
        return value

    def validate_latitude(self, value):
        if value is not None and not (-90 <= float(value) <= 90):
            raise serializers.ValidationError(_err("lat_range", self.context))
        return value

    def validate_longitude(self, value):
        if value is not None and not (-180 <= float(value) <= 180):
            raise serializers.ValidationError(_err("lng_range", self.context))
        return value

    def validate(self, data):
        lat = data.get("latitude")
        lng = data.get("longitude")
        if lat is not None and lng is None:
            raise serializers.ValidationError({"longitude": _err("lng_required_with_lat", self.context)})
        if lng is not None and lat is None:
            raise serializers.ValidationError({"latitude": _err("lat_required_with_lng", self.context)})
        return data


# ─── Payment ──────────────────────────────────────────────────────────────────

class UploadPaymentSerializer(serializers.Serializer):
    plan_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))
    receipt = serializers.FileField()

    def validate_receipt(self, value):
        allowed_types = ["image/jpeg", "image/png", "image/jpg", "application/pdf"]
        if hasattr(value, "content_type") and value.content_type not in allowed_types:
            raise serializers.ValidationError(_err("receipt_type", self.context))
        if value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError(_err("receipt_size", self.context))
        return value