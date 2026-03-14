# App: auth_app | File: views.py
from django.utils import timezone
from django.db import transaction
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from drf_spectacular.utils import (
    extend_schema,
    OpenApiParameter, OpenApiExample, OpenApiResponse,
    inline_serializer,
)
from drf_spectacular.types import OpenApiTypes
from rest_framework import serializers as drf_serializers
import datetime

from .models import User, ClientProfile, BusinessProfile
from .serializers import (
    ClientRegisterSerializer,
    BusinessRegisterSerializer,
    VerifyAccountSerializer,
    LoginSerializer,
    UpdateClientProfileSerializer,
    UpdateBusinessProfileSerializer,
    UploadPaymentSerializer,
)
from admin_app.models import SubscriptionPlan, Payment, Category
from core.messages import get_message
from core.decorators import _authenticate_request

_LANG_HEADER = OpenApiParameter(
    name="Accept-Language",
    location=OpenApiParameter.HEADER,
    description="Response language. Supported: `en` (default), `ar`, `fr`.",
    required=False,
    type=OpenApiTypes.STR,
    examples=[
        OpenApiExample("English", value="en"),
        OpenApiExample("Arabic", value="ar"),
        OpenApiExample("French", value="fr"),
    ],
)

_AUTH_HEADER = OpenApiParameter(
    name="Authorization",
    location=OpenApiParameter.HEADER,
    description="JWT Bearer token. Format: `Bearer <access_token>`",
    required=True,
    type=OpenApiTypes.STR,
)


def _lang(request):
    raw = request.headers.get("Accept-Language", "en")[:2].lower()
    return raw if raw in ("en", "ar", "fr") else "en"


def _ok(data=None, msg_key=None, lang="en", http_status=status.HTTP_200_OK):
    payload = {"success": True}
    if msg_key:
        payload["message"] = get_message(msg_key, lang)
    if data is not None:
        payload["data"] = data
    return Response(payload, status=http_status)


def _err(msg_key=None, lang="en", http_status=status.HTTP_400_BAD_REQUEST, errors=None):
    payload = {"success": False}
    if msg_key:
        payload["message"] = get_message(msg_key, lang)
    if errors:
        payload["errors"] = errors
    return Response(payload, status=http_status)


def _get_tokens(user):
    refresh = RefreshToken.for_user(user)
    return {"refresh": str(refresh), "access": str(refresh.access_token)}


def _build_user_data(user, request=None):
    data = {
        "tokens": _get_tokens(user),
        "id": str(user.id),
        "phone": user.phone,
        "email": user.email,
        "role": user.role,
        "city": user.city,
        "profile_picture": (
            request.build_absolute_uri(user.profile_picture.url)
            if user.profile_picture and request
            else (user.profile_picture.url if user.profile_picture else None)
        ),
        "subscription_status": user.subscription_status,
        "subscription_end": user.subscription_end,
        "is_verified": user.is_verified,
        "created_at": user.created_at,
    }
    if user.role == "client" and hasattr(user, "client_profile"):
        p = user.client_profile
        data["profile"] = {
            "first_name": p.first_name,
            "last_name": p.last_name,
            "date_of_birth": p.date_of_birth,
        }
    elif user.role == "business" and hasattr(user, "business_profile"):
        bp = user.business_profile
        data["profile"] = {
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
    return data


def _check_subscription_expiry(user):
    if user.subscription_status == "ACTIVE" and user.subscription_end:
        if timezone.now() > user.subscription_end:
            user.subscription_status = "EXPIRED"
            user.save(update_fields=["subscription_status"])


# ─── Registration ─────────────────────────────────────────────────────────────

@extend_schema(
    tags=["Auth — Client"],
    summary="Register a new client account",
    description=(
        "Creates a new client user account. The account is created with `is_verified=false`. "
        "Your SMS/OTP provider should handle phone verification on the client side. "
        "Once the user has verified their phone, call `POST /api/auth/verify/` to activate the account.\n\n"
        "**No authentication required.**"
    ),
    request=ClientRegisterSerializer,
    parameters=[_LANG_HEADER],
    responses={
        201: OpenApiResponse(
            description="Account created successfully. Account is inactive until verified.",
            examples=[OpenApiExample(
                "Success",
                value={
                    "success": True,
                    "message": "Account created successfully. Please verify OTP.",
                    "data": {"phone": "+213555123456", "is_verified": False},
                },
            )],
        ),
        400: OpenApiResponse(description="Validation error — phone already registered or invalid format."),
    },
    examples=[
        OpenApiExample(
            "Client registration body",
            request_only=True,
            value={
                "phone": "+213555123456",
                "password": "securePass123",
                "first_name": "Yacine",
                "last_name": "Boudiaf",
                "city": "Algiers",
                "date_of_birth": "1995-06-15",
            },
        )
    ],
)
@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def register_client(request):
    lang = _lang(request)
    serializer = ClientRegisterSerializer(data=request.data, context={"request": request})
    if not serializer.is_valid():
        return _err("validation_error", lang, errors=serializer.errors)

    data = serializer.validated_data
    phone = data["phone"]

    with transaction.atomic():
        user = User.objects.create_user(
            phone=phone,
            role="client",
            password=data["password"],
            city=data.get("city", ""),
            is_verified=False,
        )
        ClientProfile.objects.create(
            user=user,
            first_name=data["first_name"],
            last_name=data["last_name"],
            date_of_birth=data.get("date_of_birth"),
        )

    return _ok(
        data={"phone": phone, "is_verified": False},
        msg_key="user_created",
        lang=lang,
        http_status=status.HTTP_201_CREATED,
    )


@extend_schema(
    tags=["Auth — Business"],
    summary="Register a new business account",
    description=(
        "Creates a new business user account. The account is created with `is_verified=false`. "
        "Your SMS/OTP provider should handle phone verification on the client side. "
        "Once the user has verified their phone, call `POST /api/auth/verify/` to activate the account.\n\n"
        "The `latitude` and `longitude` fields are used to place the business pin on Google Maps in the mobile app. "
        "Both must be provided together or omitted together.\n\n"
        "**No authentication required.**"
    ),
    request=BusinessRegisterSerializer,
    parameters=[_LANG_HEADER],
    responses={
        201: OpenApiResponse(
            description="Business account created. Inactive until verified.",
            examples=[OpenApiExample(
                "Success",
                value={
                    "success": True,
                    "message": "Account created successfully. Please verify OTP.",
                    "data": {"phone": "+213555000111", "is_verified": False},
                },
            )],
        ),
        400: OpenApiResponse(description="Validation error — phone exists, coordinate out of range, etc."),
    },
    examples=[
        OpenApiExample(
            "Business registration body",
            request_only=True,
            value={
                "phone": "+213555000111",
                "password": "securePass456",
                "business_name": "Café El Djazair",
                "description": "Traditional Algerian coffee house.",
                "category_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                "city": "Algiers",
                "address": "12 Rue Didouche Mourad, Algiers",
                "website": "https://caffeldjazair.dz",
                "latitude": "36.737232",
                "longitude": "3.086472",
            },
        )
    ],
)
@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def register_business(request):
    lang = _lang(request)
    serializer = BusinessRegisterSerializer(data=request.data, context={"request": request})
    if not serializer.is_valid():
        return _err("validation_error", lang, errors=serializer.errors)

    data = serializer.validated_data
    phone = data["phone"]

    category = None
    if data.get("category_id"):
        try:
            category = Category.objects.get(id=data["category_id"], is_active=True)
        except Category.DoesNotExist:
            pass

    with transaction.atomic():
        user = User.objects.create_user(
            phone=phone,
            role="business",
            password=data["password"],
            city=data.get("city", ""),
            is_verified=False,
        )
        BusinessProfile.objects.create(
            user=user,
            business_name=data["business_name"],
            description=data.get("description", ""),
            category=category,
            address=data.get("address", ""),
            website=data.get("website", ""),
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
        )

    return _ok(
        data={"phone": phone, "is_verified": False},
        msg_key="user_created",
        lang=lang,
        http_status=status.HTTP_201_CREATED,
    )


# ─── Verification ─────────────────────────────────────────────────────────────

@extend_schema(
    tags=["Auth — Common"],
    summary="Verify account after phone confirmation",
    description=(
        "This endpoint is called **by the app developer** once their external SMS/OTP provider "
        "confirms the user has successfully verified their phone number.\n\n"
        "The backend does not handle OTP logic — that is entirely managed on your side "
        "(e.g. Firebase, Twilio, or any SMS gateway). Once you confirm verification on your end, "
        "call this endpoint with the user's phone number and the backend will set `is_verified=true`, "
        "activating the account and returning full user data with JWT tokens.\n\n"
        "**Errors:**\n"
        "- `400` if the phone number is not found\n"
        "- `400` if the account is already verified\n\n"
        "**No authentication required.**"
    ),
    request=VerifyAccountSerializer,
    parameters=[_LANG_HEADER],
    responses={
        200: OpenApiResponse(
            description="Account marked as verified. Full user object with JWT tokens returned.",
            examples=[OpenApiExample(
                "Success",
                value={
                    "success": True,
                    "message": "OTP verified successfully. Account is now active.",
                    "data": {
                        "tokens": {"access": "eyJ...", "refresh": "eyJ..."},
                        "id": "uuid",
                        "phone": "+213555123456",
                        "email": None,
                        "role": "client",
                        "city": "Algiers",
                        "profile_picture": None,
                        "subscription_status": "FREE",
                        "subscription_end": None,
                        "is_verified": True,
                        "created_at": "2026-01-01T10:00:00Z",
                        "profile": {
                            "first_name": "Yacine",
                            "last_name": "Boudiaf",
                            "date_of_birth": "1995-06-15",
                        },
                    },
                },
            )],
        ),
        400: OpenApiResponse(description="Phone not found, or account already verified."),
    },
    examples=[
        OpenApiExample(
            "Verify account body",
            request_only=True,
            value={"phone": "+213555123456"},
        )
    ],
)
@api_view(["POST"])
def verify_account(request):
    lang = _lang(request)
    serializer = VerifyAccountSerializer(data=request.data, context={"request": request})
    if not serializer.is_valid():
        return _err("validation_error", lang, errors=serializer.errors)

    phone = serializer.validated_data["phone"]
    user = User.objects.get(phone=phone)
    user.is_verified = True
    user.save(update_fields=["is_verified"])

    return _ok(data=_build_user_data(user, request), msg_key="otp_verified", lang=lang)


# ─── Auth ─────────────────────────────────────────────────────────────────────

@extend_schema(
    tags=["Auth — Common"],
    summary="Login — client, business, or admin",
    description=(
        "Authenticates any user and returns full user data with JWT tokens. "
        "The `identifier` field accepts either a **phone number** or an **email address**. "
        "Subscription expiry is automatically checked on every login.\n\n"
        "**No authentication required.**"
    ),
    request=LoginSerializer,
    parameters=[_LANG_HEADER],
    responses={
        200: OpenApiResponse(
            description="Login successful. Full user data + JWT tokens returned.",
            examples=[OpenApiExample(
                "Success",
                value={
                    "success": True,
                    "message": "Login successful.",
                    "data": {
                        "tokens": {"access": "eyJ...", "refresh": "eyJ..."},
                        "id": "uuid", "phone": "+213555123456",
                        "role": "client", "subscription_status": "ACTIVE",
                    },
                },
            )],
        ),
        401: OpenApiResponse(description="Wrong phone/email or password."),
        403: OpenApiResponse(description="Account not verified or inactive."),
    },
    examples=[
        OpenApiExample("Login with phone", request_only=True, value={"identifier": "+213555123456", "password": "securePass123"}),
        OpenApiExample("Login with email", request_only=True, value={"identifier": "user@example.com", "password": "securePass123"}),
    ],
)
@api_view(["POST"])
def login(request):
    lang = _lang(request)
    serializer = LoginSerializer(data=request.data, context={"request": request})
    if not serializer.is_valid():
        return _err("validation_error", lang, errors=serializer.errors)

    identifier = serializer.validated_data["identifier"]
    password = serializer.validated_data["password"]

    user = None
    lookup = {"email": identifier} if "@" in identifier else {"phone": identifier}
    try:
        u = User.objects.get(**lookup)
        if u.check_password(password):
            user = u
    except User.DoesNotExist:
        pass

    if user is None:
        return _err("login_failed", lang, status.HTTP_401_UNAUTHORIZED)
    if not user.is_verified:
        return _err("account_not_verified", lang, status.HTTP_403_FORBIDDEN)
    if not user.is_active:
        return _err("account_inactive", lang, status.HTTP_403_FORBIDDEN)

    _check_subscription_expiry(user)
    return _ok(data=_build_user_data(user, request), msg_key="login_success", lang=lang)


@extend_schema(
    tags=["Auth — Common"],
    summary="Logout — invalidate refresh token",
    description=(
        "Blacklists the provided refresh token so it can no longer be used. "
        "Send the refresh token in the request body.\n\n"
        "**No authentication required.**"
    ),
    request=inline_serializer(
        name="LogoutRequest",
        fields={"refresh": drf_serializers.CharField(help_text="The refresh token received at login.")},
    ),
    parameters=[_LANG_HEADER],
    responses={200: OpenApiResponse(description="Logged out successfully.")},
    examples=[
        OpenApiExample("Logout body", request_only=True, value={"refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."}),
    ],
)
@api_view(["POST"])
def logout(request):
    lang = _lang(request)
    try:
        refresh_token = request.data.get("refresh")
        if refresh_token:
            RefreshToken(refresh_token).blacklist()
    except Exception:
        pass
    return _ok(msg_key="logout_success", lang=lang)


@extend_schema(
    tags=["Auth — Common"],
    summary="Get current user profile",
    description=(
        "Returns the full profile of the currently authenticated user including role-specific data. "
        "For businesses, the response includes `latitude` and `longitude` for Google Maps.\n\n"
        "**Requires:** `Authorization: Bearer <access_token>`"
    ),
    parameters=[_LANG_HEADER, _AUTH_HEADER],
    responses={
        200: OpenApiResponse(description="Profile returned successfully."),
        401: OpenApiResponse(description="Missing or invalid token."),
    },
)
@api_view(["GET"])
def get_profile(request):
    lang = _lang(request)
    user, _ = _authenticate_request(request)
    if user is None:
        return _err("unauthorized", lang, status.HTTP_401_UNAUTHORIZED)
    _check_subscription_expiry(user)
    return _ok(data=_build_user_data(user, request), msg_key="profile_fetched", lang=lang)


@extend_schema(
    tags=["Auth — Common"],
    summary="Update current user profile",
    description=(
        "Partially updates the authenticated user's profile. Only send the fields you want to change.\n\n"
        "**Client fields:** `email`, `city`, `profile_picture`, `first_name`, `last_name`, `date_of_birth`\n\n"
        "**Business fields:** `email`, `city`, `profile_picture`, `business_name`, `description`, "
        "`category_id`, `address`, `website`, `latitude`, `longitude`\n\n"
        "`latitude` and `longitude` must always be provided **together**.\n\n"
        "**Requires:** `Authorization: Bearer <access_token>`"
    ),
    request=inline_serializer(
        name="UpdateProfileRequest",
        fields={
            "email": drf_serializers.EmailField(required=False),
            "city": drf_serializers.CharField(required=False),
            "profile_picture": drf_serializers.ImageField(required=False),
            "first_name": drf_serializers.CharField(required=False, help_text="[Client only]"),
            "last_name": drf_serializers.CharField(required=False, help_text="[Client only]"),
            "date_of_birth": drf_serializers.DateField(required=False, help_text="[Client only] YYYY-MM-DD"),
            "business_name": drf_serializers.CharField(required=False, help_text="[Business only]"),
            "description": drf_serializers.CharField(required=False, help_text="[Business only]"),
            "category_id": drf_serializers.UUIDField(required=False, help_text="[Business only]"),
            "address": drf_serializers.CharField(required=False, help_text="[Business only]"),
            "website": drf_serializers.URLField(required=False, help_text="[Business only]"),
            "latitude": drf_serializers.DecimalField(max_digits=9, decimal_places=6, required=False, help_text="[Business only] -90 to 90. Must come with longitude."),
            "longitude": drf_serializers.DecimalField(max_digits=9, decimal_places=6, required=False, help_text="[Business only] -180 to 180. Must come with latitude."),
        },
    ),
    parameters=[_LANG_HEADER, _AUTH_HEADER],
    responses={
        200: OpenApiResponse(description="Profile updated. Full updated user object returned."),
        400: OpenApiResponse(description="Validation error."),
        401: OpenApiResponse(description="Missing or invalid token."),
    },
    examples=[
        OpenApiExample("Update client name", request_only=True, value={"first_name": "Karim", "city": "Oran"}),
        OpenApiExample("Update business location", request_only=True, value={"latitude": "35.691544", "longitude": "-0.641449"}),
    ],
)
@api_view(["PATCH"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def update_profile(request):
    lang = _lang(request)
    user, _ = _authenticate_request(request)
    if user is None:
        return _err("unauthorized", lang, status.HTTP_401_UNAUTHORIZED)

    if user.role == "client":
        serializer = UpdateClientProfileSerializer(data=request.data, partial=True, context={"request": request})
    elif user.role == "business":
        serializer = UpdateBusinessProfileSerializer(data=request.data, partial=True, context={"request": request})
    else:
        return _err("unauthorized", lang, status.HTTP_403_FORBIDDEN)

    if not serializer.is_valid():
        return _err("validation_error", lang, errors=serializer.errors)

    data = serializer.validated_data

    if data.get("email"):
        if User.objects.filter(email=data["email"]).exclude(id=user.id).exists():
            return _err("email_exists", lang)
        user.email = data["email"]
    if "city" in data:
        user.city = data["city"]
    if "profile_picture" in data:
        user.profile_picture = data["profile_picture"]
    user.save()

    if user.role == "client":
        p = user.client_profile
        if "first_name" in data:
            p.first_name = data["first_name"]
        if "last_name" in data:
            p.last_name = data["last_name"]
        if "date_of_birth" in data:
            p.date_of_birth = data["date_of_birth"]
        p.save()
    elif user.role == "business":
        bp = user.business_profile
        if "business_name" in data:
            bp.business_name = data["business_name"]
        if "description" in data:
            bp.description = data["description"]
        if "address" in data:
            bp.address = data["address"]
        if "website" in data:
            bp.website = data["website"]
        if "latitude" in data:
            bp.latitude = data["latitude"]
        if "longitude" in data:
            bp.longitude = data["longitude"]
        if data.get("category_id"):
            try:
                bp.category = Category.objects.get(id=data["category_id"], is_active=True)
            except Category.DoesNotExist:
                pass
        bp.save()

    return _ok(data=_build_user_data(user, request), msg_key="profile_updated", lang=lang)


# ─── Payment ──────────────────────────────────────────────────────────────────

@extend_schema(
    tags=["Auth — Payment"],
    summary="Upload subscription payment receipt",
    description=(
        "Uploads a subscription payment receipt (image or PDF) for admin review. "
        "After uploading, the user's `subscription_status` is set to `PENDING`.\n\n"
        "**Receipt rules:** JPEG / PNG / PDF, max 5MB\n\n"
        "**Request format:** `multipart/form-data`\n\n"
        "**Requires:** `Authorization: Bearer <access_token>` (client or business only)"
    ),
    request=UploadPaymentSerializer,
    parameters=[_LANG_HEADER, _AUTH_HEADER],
    responses={
        201: OpenApiResponse(description="Receipt uploaded. Awaiting admin approval."),
        400: OpenApiResponse(description="Invalid plan, wrong file type/size, or validation failure."),
        401: OpenApiResponse(description="Missing or invalid token."),
        403: OpenApiResponse(description="Admin accounts cannot upload payments."),
    },
    examples=[
        OpenApiExample(
            "Payment upload (multipart)",
            request_only=True,
            value={"plan_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6", "amount": "500.00", "receipt": "<binary file>"},
        )
    ],
)
@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
def upload_payment(request):
    lang = _lang(request)
    user, _ = _authenticate_request(request)
    if user is None:
        return _err("unauthorized", lang, status.HTTP_401_UNAUTHORIZED)
    if user.role == "admin":
        return _err("unauthorized", lang, status.HTTP_403_FORBIDDEN)

    serializer = UploadPaymentSerializer(data=request.data, context={"request": request})
    if not serializer.is_valid():
        return _err("validation_error", lang, errors=serializer.errors)

    data = serializer.validated_data

    try:
        plan = SubscriptionPlan.objects.get(id=data["plan_id"], is_active=True)
    except SubscriptionPlan.DoesNotExist:
        return _err("invalid_plan", lang)

    if plan.target_role not in (user.role, "both"):
        return _err("invalid_plan", lang)

    payment = Payment.objects.create(
        user=user,
        plan=plan,
        amount=data["amount"],
        receipt=data["receipt"],
        status="PENDING",
    )
    user.subscription_status = "PENDING"
    user.save(update_fields=["subscription_status"])

    return _ok(
        data={
            "payment_id": str(payment.id),
            "status": payment.status,
            "plan": plan.name,
            "amount": str(payment.amount),
        },
        msg_key="payment_uploaded",
        lang=lang,
        http_status=status.HTTP_201_CREATED,
    )


@extend_schema(
    tags=["Auth — Payment"],
    summary="Get subscription status",
    description=(
        "Returns the current subscription status of the authenticated user. "
        "Expiry is automatically checked — if past `subscription_end`, status is set to `EXPIRED`.\n\n"
        "**States:** `FREE` · `PENDING` · `ACTIVE` · `EXPIRED`\n\n"
        "**Requires:** `Authorization: Bearer <access_token>`"
    ),
    parameters=[_LANG_HEADER, _AUTH_HEADER],
    responses={
        200: OpenApiResponse(
            description="Subscription info returned.",
            examples=[OpenApiExample(
                "Active",
                value={"success": True, "data": {"subscription_status": "ACTIVE", "subscription_end": "2026-05-01T00:00:00Z", "plan": "Monthly Plan"}},
            )],
        ),
        401: OpenApiResponse(description="Missing or invalid token."),
    },
)
@api_view(["GET"])
def get_subscription_status(request):
    lang = _lang(request)
    user, _ = _authenticate_request(request)
    if user is None:
        return _err("unauthorized", lang, status.HTTP_401_UNAUTHORIZED)
    _check_subscription_expiry(user)
    return _ok(
        data={
            "subscription_status": user.subscription_status,
            "subscription_end": user.subscription_end,
            "plan": user.current_plan.name if user.current_plan else None,
        },
        msg_key="subscription_status_fetched",
        lang=lang,
    )