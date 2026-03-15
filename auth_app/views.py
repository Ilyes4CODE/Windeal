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
from core.decorators import _authenticate_request, admin_required

_LANG_HEADER = OpenApiParameter(
    name="Accept-Language",
    location=OpenApiParameter.HEADER,
    description="Response language. Supported: `en` (default), `ar`, `fr`.",
    required=False,
    type=OpenApiTypes.STR,
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


# ─── Client Registration ──────────────────────────────────────────────────────

@extend_schema(
    tags=["Auth — Client"],
    summary="Register a new client account",
    description=(
        "Creates a new client user account with `is_verified=false`. "
        "Call `POST /api/auth/verify/` once your SMS provider confirms the user.\n\n"
        "**No authentication required.**"
    ),
    request=ClientRegisterSerializer,
    parameters=[_LANG_HEADER],
    responses={
        201: OpenApiResponse(description="Account created. Inactive until verified."),
        400: OpenApiResponse(description="Validation error."),
    },
    examples=[
        OpenApiExample(
            "Client registration",
            request_only=True,
            value={"phone": "+213555123456", "password": "securePass123",
                   "first_name": "Yacine", "last_name": "Boudiaf", "city": "Algiers"},
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
            phone=phone, role="client",
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
        msg_key="user_created", lang=lang,
        http_status=status.HTTP_201_CREATED,
    )


# ─── Business Registration ────────────────────────────────────────────────────

@extend_schema(
    tags=["Auth — Business"],
    summary="Register a new business account",
    description=(
        "Creates a new business account with `is_verified=false`. "
        "`latitude` and `longitude` are used for Google Maps pin — must be provided together.\n\n"
        "**No authentication required.**"
    ),
    request=BusinessRegisterSerializer,
    parameters=[_LANG_HEADER],
    responses={
        201: OpenApiResponse(description="Business account created."),
        400: OpenApiResponse(description="Validation error."),
    },
    examples=[
        OpenApiExample(
            "Business registration",
            request_only=True,
            value={"phone": "+213555000111", "password": "securePass456",
                   "business_name": "Café El Djazair", "city": "Algiers",
                   "latitude": "36.737232", "longitude": "3.086472"},
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
            phone=phone, role="business",
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
        msg_key="user_created", lang=lang,
        http_status=status.HTTP_201_CREATED,
    )


# ─── Admin Registration ───────────────────────────────────────────────────────

@extend_schema(
    tags=["Auth — Admin"],
    summary="Create a new admin account",
    description=(
        "Creates a new admin user. **Only callable by an existing authenticated admin.**\n\n"
        "The new account is created with `role=admin`, `is_verified=true`, and `is_active=true` immediately — "
        "no OTP or verification step is needed.\n\n"
        "**Requires:** `Authorization: Bearer <admin_access_token>`"
    ),
    request=inline_serializer(
        name="AdminRegisterRequest",
        fields={
            "phone":      drf_serializers.CharField(help_text="Phone number of the new admin."),
            "password":   drf_serializers.CharField(help_text="Password (min 6 characters)."),
            "first_name": drf_serializers.CharField(help_text="First name."),
            "last_name":  drf_serializers.CharField(required=False, help_text="Last name (optional)."),
        },
    ),
    parameters=[_LANG_HEADER, _AUTH_HEADER],
    responses={
        201: OpenApiResponse(description="Admin account created successfully."),
        400: OpenApiResponse(description="Phone already registered or validation error."),
        401: OpenApiResponse(description="Not authenticated."),
        403: OpenApiResponse(description="Only admins can create other admins."),
    },
    examples=[
        OpenApiExample(
            "Create admin",
            request_only=True,
            value={"phone": "+213555999000", "password": "adminPass123",
                   "first_name": "Riad", "last_name": "Belkacem"},
        )
    ],
)
@api_view(["POST"])
@parser_classes([JSONParser])
@admin_required
def register_admin(request):
    lang = _lang(request)

    phone      = request.data.get("phone", "").strip()
    password   = request.data.get("password", "")
    first_name = request.data.get("first_name", "").strip()
    last_name  = request.data.get("last_name", "Admin").strip()

    if not phone or not password or not first_name:
        return _err("validation_error", lang,
                    errors={"detail": "phone, password, and first_name are required."})

    if not phone.lstrip("+").isdigit():
        return _err("validation_error", lang,
                    errors={"phone": "Phone must contain digits only."})

    if len(password) < 6:
        return _err("validation_error", lang,
                    errors={"password": "Password must be at least 6 characters."})

    if User.objects.filter(phone=phone).exists():
        return _err("phone_exists", lang)

    with transaction.atomic():
        user = User.objects.create_user(
            phone=phone,
            role="admin",
            password=password,
            is_verified=True,
            is_active=True,
            is_staff=True,
        )
        ClientProfile.objects.create(
            user=user,
            first_name=first_name,
            last_name=last_name,
        )

    return _ok(
        data={
            "id": str(user.id),
            "phone": user.phone,
            "role": user.role,
            "is_verified": user.is_verified,
        },
        msg_key="user_created",
        lang=lang,
        http_status=status.HTTP_201_CREATED,
    )


# ─── Verify Account ───────────────────────────────────────────────────────────

@extend_schema(
    tags=["Auth — Common"],
    summary="Verify account after phone confirmation",
    description=(
        "Called by the app developer once their external SMS provider confirms verification. "
        "Sets `is_verified=true` and returns JWT tokens.\n\n"
        "**No authentication required.**"
    ),
    request=VerifyAccountSerializer,
    parameters=[_LANG_HEADER],
    responses={
        200: OpenApiResponse(description="Account verified. Full user + tokens returned."),
        400: OpenApiResponse(description="Phone not found or already verified."),
    },
    examples=[OpenApiExample("Verify", request_only=True, value={"phone": "+213555123456"})],
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


# ─── Login ────────────────────────────────────────────────────────────────────

@extend_schema(
    tags=["Auth — Common"],
    summary="Login — client, business, or admin",
    description=(
        "Authenticates any user. `identifier` accepts phone or email. "
        "Returns full user data with JWT tokens and `role` field for frontend routing.\n\n"
        "**No authentication required.**"
    ),
    request=LoginSerializer,
    parameters=[_LANG_HEADER],
    responses={
        200: OpenApiResponse(description="Login successful."),
        401: OpenApiResponse(description="Wrong credentials."),
        403: OpenApiResponse(description="Account not verified or inactive."),
    },
    examples=[
        OpenApiExample("Phone login",  request_only=True, value={"identifier": "+213555123456", "password": "pass"}),
        OpenApiExample("Email login",  request_only=True, value={"identifier": "user@example.com", "password": "pass"}),
    ],
)
@api_view(["POST"])
def login(request):
    lang = _lang(request)
    serializer = LoginSerializer(data=request.data, context={"request": request})
    if not serializer.is_valid():
        return _err("validation_error", lang, errors=serializer.errors)

    identifier = serializer.validated_data["identifier"]
    password   = serializer.validated_data["password"]

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


# ─── Logout ───────────────────────────────────────────────────────────────────

@extend_schema(
    tags=["Auth — Common"],
    summary="Logout — invalidate refresh token",
    description="Blacklists the provided refresh token.\n\n**No authentication required.**",
    request=inline_serializer(
        name="LogoutRequest",
        fields={"refresh": drf_serializers.CharField(help_text="The refresh token.")},
    ),
    parameters=[_LANG_HEADER],
    responses={200: OpenApiResponse(description="Logged out.")},
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


# ─── Profile ──────────────────────────────────────────────────────────────────

@extend_schema(
    tags=["Auth — Common"],
    summary="Get current user profile",
    description="Returns full profile of the authenticated user.\n\n**Requires:** `Authorization: Bearer <token>`",
    parameters=[_LANG_HEADER, _AUTH_HEADER],
    responses={
        200: OpenApiResponse(description="Profile returned."),
        401: OpenApiResponse(description="Not authenticated."),
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
        "Partial update. Client fields: `email`, `city`, `profile_picture`, `first_name`, `last_name`, `date_of_birth`. "
        "Business fields: above + `business_name`, `description`, `category_id`, `address`, `website`, `latitude`, `longitude`.\n\n"
        "**Requires:** `Authorization: Bearer <token>`"
    ),
    request=inline_serializer(
        name="UpdateProfileRequest",
        fields={
            "email":         drf_serializers.EmailField(required=False),
            "city":          drf_serializers.CharField(required=False),
            "profile_picture": drf_serializers.ImageField(required=False),
            "first_name":    drf_serializers.CharField(required=False, help_text="[Client only]"),
            "last_name":     drf_serializers.CharField(required=False, help_text="[Client only]"),
            "date_of_birth": drf_serializers.DateField(required=False, help_text="[Client only]"),
            "business_name": drf_serializers.CharField(required=False, help_text="[Business only]"),
            "description":   drf_serializers.CharField(required=False, help_text="[Business only]"),
            "category_id":   drf_serializers.UUIDField(required=False, help_text="[Business only]"),
            "address":       drf_serializers.CharField(required=False, help_text="[Business only]"),
            "website":       drf_serializers.URLField(required=False, help_text="[Business only]"),
            "latitude":      drf_serializers.DecimalField(max_digits=9, decimal_places=6, required=False, help_text="[Business only]"),
            "longitude":     drf_serializers.DecimalField(max_digits=9, decimal_places=6, required=False, help_text="[Business only]"),
        },
    ),
    parameters=[_LANG_HEADER, _AUTH_HEADER],
    responses={
        200: OpenApiResponse(description="Profile updated."),
        400: OpenApiResponse(description="Validation error."),
        401: OpenApiResponse(description="Not authenticated."),
    },
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
        if "first_name" in data: p.first_name = data["first_name"]
        if "last_name"  in data: p.last_name  = data["last_name"]
        if "date_of_birth" in data: p.date_of_birth = data["date_of_birth"]
        p.save()
    elif user.role == "business":
        bp = user.business_profile
        if "business_name" in data: bp.business_name = data["business_name"]
        if "description"   in data: bp.description   = data["description"]
        if "address"       in data: bp.address        = data["address"]
        if "website"       in data: bp.website        = data["website"]
        if "latitude"      in data: bp.latitude       = data["latitude"]
        if "longitude"     in data: bp.longitude      = data["longitude"]
        if data.get("category_id"):
            try:
                bp.category = Category.objects.get(id=data["category_id"], is_active=True)
            except Category.DoesNotExist:
                pass
        bp.save()

    return _ok(data=_build_user_data(user, request), msg_key="profile_updated", lang=lang)


# ─── Payment Upload ───────────────────────────────────────────────────────────

@extend_schema(
    tags=["Auth — Payment"],
    summary="Upload subscription payment receipt",
    description=(
        "Upload a JPEG/PNG/PDF receipt (max 5MB). Sets `subscription_status=PENDING`.\n\n"
        "**Request format:** `multipart/form-data`\n\n"
        "**Requires:** `Authorization: Bearer <token>` (client or business)"
    ),
    request=UploadPaymentSerializer,
    parameters=[_LANG_HEADER, _AUTH_HEADER],
    responses={
        201: OpenApiResponse(description="Receipt uploaded."),
        400: OpenApiResponse(description="Invalid plan or file error."),
        401: OpenApiResponse(description="Not authenticated."),
        403: OpenApiResponse(description="Admins cannot upload payments."),
    },
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
        user=user, plan=plan,
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
        msg_key="payment_uploaded", lang=lang,
        http_status=status.HTTP_201_CREATED,
    )


# ─── Subscription Status ──────────────────────────────────────────────────────

@extend_schema(
    tags=["Auth — Payment"],
    summary="Get subscription status",
    description=(
        "Returns current subscription status. Expiry auto-checked on call.\n\n"
        "**States:** `FREE` · `PENDING` · `ACTIVE` · `EXPIRED`\n\n"
        "**Requires:** `Authorization: Bearer <token>`"
    ),
    parameters=[_LANG_HEADER, _AUTH_HEADER],
    responses={200: OpenApiResponse(description="Subscription info returned.")},
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
        msg_key="subscription_status_fetched", lang=lang,
    )