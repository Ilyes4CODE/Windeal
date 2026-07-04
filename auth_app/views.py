# App: auth_app | File: views.py
from django.utils import timezone
from django.db import transaction
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from drf_spectacular.utils import (
    extend_schema, OpenApiParameter, OpenApiExample, OpenApiResponse,
    inline_serializer,
)
from drf_spectacular.types import OpenApiTypes
from rest_framework import serializers as drf_serializers
import datetime

from .models import User, ClientProfile, BusinessProfile
from .serializers import (
    ClientRegisterSerializer,
    BusinessRegisterSerializer,
    CheckUserSerializer,
    PasswordlessLoginSerializer,
    AdminLoginSerializer,
    UpdateClientProfileSerializer,
    UpdateBusinessProfileSerializer,
    UploadPaymentSerializer,
)
from admin_app.models import SubscriptionPlan, Payment, Category
from core.messages import get_message
from core.decorators import _authenticate_request, admin_required

_LANG = OpenApiParameter(name="Accept-Language", location=OpenApiParameter.HEADER, description="en / ar / fr", required=False, type=OpenApiTypes.STR)
_AUTH = OpenApiParameter(name="Authorization", location=OpenApiParameter.HEADER, description="Bearer <token>", required=True, type=OpenApiTypes.STR)


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
        "id":    str(user.id),
        "phone": user.phone,
        "email": user.email,
        "role":  user.role,
        "city":  user.city,
        "profile_picture": (
            request.build_absolute_uri(user.profile_picture.url)
            if user.profile_picture and request
            else (user.profile_picture.url if user.profile_picture else None)
        ),
        "is_verified":       user.is_verified,
        "is_banned":         user.is_banned,
        "subscription_status": user.subscription_status,
        "subscription_end":    user.subscription_end,
        "created_at":          user.created_at,
    }
    if user.role == "client" and hasattr(user, "client_profile"):
        p = user.client_profile
        data["profile"] = {
            "full_name": p.full_name,
            "email":     p.email,
            "wilaya":    p.wilaya,
            "school":    p.school,
        }
    elif user.role == "business" and hasattr(user, "business_profile"):
        bp = user.business_profile
        data["profile"] = {
            "business_name": bp.business_name,
            "description":   bp.description,
            "category_id":   str(bp.category.id)   if bp.category else None,
            "category_name": bp.category.name       if bp.category else None,
            "address":       bp.address,
            "website":       bp.website,
            "latitude":      str(bp.latitude)  if bp.latitude  is not None else None,
            "longitude":     str(bp.longitude) if bp.longitude is not None else None,
            "is_active":     bp.is_active,
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
    summary="Register a new client account (passwordless)",
    description=(
        "Creates a new client account. No password needed — authentication is phone-based.\n\n"
        "The account is created with `is_verified=true` and `is_banned=false` by default.\n\n"
        "**Required fields:** `phone`, `full_name`, `wilaya`\n\n"
        "**Optional fields:** `email`, `school`\n\n"
        "**No authentication required.**"
    ),
    request=ClientRegisterSerializer,
    parameters=[_LANG],
    responses={
        201: OpenApiResponse(description="Account created. Returns full user data with JWT tokens."),
        400: OpenApiResponse(description="Validation error."),
    },
    examples=[
        OpenApiExample("Client register", request_only=True, value={
            "phone":     "+213555123456",
            "full_name": "Yacine Boudiaf",
            "email":     "yacine@example.com",
            "wilaya":    "Alger",
            "school":    "Université des Sciences et de la Technologie Houari Boumediene",
        }),
    ],
)
@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def register_client(request):
    lang = _lang(request)
    serializer = ClientRegisterSerializer(data=request.data, context={"request": request})
    if not serializer.is_valid():
        return _err("validation_error", lang, errors=serializer.errors)

    data  = serializer.validated_data
    phone = data["phone"]

    with transaction.atomic():
        user = User.objects.create_user(
            phone=phone,
            role="client",
            password=None,          # passwordless
            city=data.get("wilaya", ""),
            is_verified=True,
            is_active=True,
        )
        ClientProfile.objects.create(
            user=user,
            full_name=data["full_name"],
            email=data.get("email"),
            wilaya=data["wilaya"],
            school=data.get("school") or "",
        )

    return _ok(
        data=_build_user_data(user, request),
        msg_key="user_created",
        lang=lang,
        http_status=status.HTTP_201_CREATED,
    )


# ─── Business Registration ────────────────────────────────────────────────────

@extend_schema(
    tags=["Auth — Business"],
    summary="Register a new business account (passwordless)",
    description=(
        "Creates a new business account. No password needed.\n\n"
        "Latitude and longitude must be sent together for Google Maps pin.\n\n"
        "**No authentication required.**"
    ),
    request=BusinessRegisterSerializer,
    parameters=[_LANG],
    responses={
        201: OpenApiResponse(description="Business account created. Returns full user data with JWT tokens."),
        400: OpenApiResponse(description="Validation error."),
    },
    examples=[
        OpenApiExample("Business register", request_only=True, value={
            "phone":         "+213555000111",
            "business_name": "Café El Djazair",
            "city":          "Alger",
            "latitude":      "36.737232",
            "longitude":     "3.086472",
        }),
    ],
)
@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def register_business(request):
    lang = _lang(request)
    serializer = BusinessRegisterSerializer(data=request.data, context={"request": request})
    if not serializer.is_valid():
        return _err("validation_error", lang, errors=serializer.errors)

    data  = serializer.validated_data
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
            password=None,          # passwordless
            city=data.get("city", ""),
            is_verified=True,
            is_active=True,
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
        data=_build_user_data(user, request),
        msg_key="user_created",
        lang=lang,
        http_status=status.HTTP_201_CREATED,
    )


# ─── Admin Registration ───────────────────────────────────────────────────────

@extend_schema(
    tags=["Auth — Admin"],
    summary="Create a new admin account (admin only)",
    description=(
        "Creates a new admin with a password. Only callable by an existing admin.\n\n"
        "**Requires:** `Authorization: Bearer <admin_token>`"
    ),
    request=inline_serializer("AdminRegisterRequest", fields={
        "phone":      drf_serializers.CharField(),
        "password":   drf_serializers.CharField(),
        "first_name": drf_serializers.CharField(),
        "last_name":  drf_serializers.CharField(required=False),
    }),
    parameters=[_LANG, _AUTH],
    responses={
        201: OpenApiResponse(description="Admin created."),
        400: OpenApiResponse(description="Validation error."),
        401: OpenApiResponse(description="Not authenticated."),
        403: OpenApiResponse(description="Not admin."),
    },
)
@api_view(["POST"])
@parser_classes([JSONParser])
@admin_required
def register_admin(request):
    lang       = _lang(request)
    phone      = request.data.get("phone", "").strip()
    password   = request.data.get("password", "")
    first_name = request.data.get("first_name", "").strip()
    last_name  = request.data.get("last_name",  "Admin").strip()

    if not phone or not password or not first_name:
        return _err("validation_error", lang,
                    errors={"detail": "phone, password, and first_name are required."})
    if not phone.lstrip("+").isdigit():
        return _err("validation_error", lang, errors={"phone": "Must contain digits only."})
    if len(password) < 6:
        return _err("validation_error", lang, errors={"password": "Min 6 characters."})
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
            full_name=f"{first_name} {last_name}".strip(),
            wilaya="—",
        )

    return _ok(
        data={"id": str(user.id), "phone": user.phone, "role": user.role},
        msg_key="user_created",
        lang=lang,
        http_status=status.HTTP_201_CREATED,
    )


# ─── Step 1: Check user existence + ban status ────────────────────────────────

@extend_schema(
    tags=["Auth — Passwordless"],
    summary="Step 1 — Check if phone exists and account is not banned",
    description=(
        "First step of the passwordless login flow for **clients and businesses**.\n\n"
        "Send the user's phone number. The response tells you:\n"
        "- `exists` — whether an account with this phone is registered\n"
        "- `is_banned` — whether the account has been banned by an admin\n"
        "- `role` — the role of the account (`client` or `business`)\n\n"
        "If `exists=false` or `is_banned=true`, **do not proceed to step 2**.\n\n"
        "**No authentication required.**"
    ),
    request=CheckUserSerializer,
    parameters=[_LANG],
    responses={
        200: OpenApiResponse(
            description="Check result.",
            examples=[
                OpenApiExample("User found, not banned", value={
                    "success": True,
                    "message": "Account found.",
                    "data": {"exists": True, "is_banned": False, "role": "client", "phone": "+213555123456"},
                }),
                OpenApiExample("User not found", value={
                    "success": True,
                    "data": {"exists": False, "is_banned": False, "role": None, "phone": "+213555000000"},
                }),
                OpenApiExample("User banned", value={
                    "success": False,
                    "message": "Your account has been banned. Please contact support.",
                    "data": {"exists": True, "is_banned": True, "role": "client"},
                }),
            ],
        ),
    },
    examples=[
        OpenApiExample("Check phone", request_only=True, value={"phone": "+213555123456"}),
    ],
)
@api_view(["POST"])
def check_user(request):
    lang = _lang(request)
    serializer = CheckUserSerializer(data=request.data, context={"request": request})
    if not serializer.is_valid():
        return _err("validation_error", lang, errors=serializer.errors)

    phone = serializer.validated_data["phone"]

    try:
        user = User.objects.get(phone=phone)
    except User.DoesNotExist:
        return _ok(
            data={"exists": False, "is_banned": False, "role": None, "phone": phone},
            lang=lang,
        )

    if user.is_banned:
        return Response(
            {
                "success": False,
                "message": get_message("account_banned", lang),
                "data": {"exists": True, "is_banned": True, "role": user.role},
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    if not user.is_active:
        return _err("account_inactive", lang, status.HTTP_403_FORBIDDEN)

    return _ok(
        data={"exists": True, "is_banned": False, "role": user.role, "phone": phone},
        msg_key="user_exists",
        lang=lang,
    )


# ─── Step 2: Passwordless login (client + business) ───────────────────────────

@extend_schema(
    tags=["Auth — Passwordless"],
    summary="Step 2 — Passwordless login, returns tokens and user data",
    description=(
        "Second step of the passwordless login flow. **Only call this after step 1 confirms "
        "`exists=true` and `is_banned=false`.**\n\n"
        "Send the phone number. The backend returns the full user object plus JWT tokens.\n\n"
        "This endpoint also auto-expires subscriptions if `subscription_end` has passed.\n\n"
        "**Do not use this endpoint for admin login** — use `POST /api/auth/login/admin/` instead.\n\n"
        "**No authentication required.**"
    ),
    request=PasswordlessLoginSerializer,
    parameters=[_LANG],
    responses={
        200: OpenApiResponse(
            description="Login successful. Full user data + JWT tokens returned.",
            examples=[OpenApiExample("Success", value={
                "success": True,
                "message": "Login successful.",
                "data": {
                    "tokens": {"access": "eyJ...", "refresh": "eyJ..."},
                    "id": "uuid", "phone": "+213555123456", "role": "client",
                    "is_banned": False,
                    "subscription_status": "FREE",
                    "profile": {"full_name": "Yacine Boudiaf", "wilaya": "Alger", "school": "USTHB"},
                },
            })],
        ),
        400: OpenApiResponse(description="Phone not found."),
        403: OpenApiResponse(description="Account is banned or inactive."),
    },
    examples=[
        OpenApiExample("Passwordless login", request_only=True, value={"phone": "+213555123456"}),
    ],
)
@api_view(["POST"])
def passwordless_login(request):
    lang = _lang(request)
    serializer = PasswordlessLoginSerializer(data=request.data, context={"request": request})
    if not serializer.is_valid():
        return _err("validation_error", lang, errors=serializer.errors)

    phone = serializer.validated_data["phone"]

    try:
        user = User.objects.get(phone=phone)
    except User.DoesNotExist:
        return _err("user_not_found", lang, status.HTTP_400_BAD_REQUEST)

    if user.is_banned:
        return _err("account_banned", lang, status.HTTP_403_FORBIDDEN)
    if not user.is_active:
        return _err("account_inactive", lang, status.HTTP_403_FORBIDDEN)
    if user.role == "admin":
        # Admins must use the admin login endpoint with password
        return _err("unauthorized", lang, status.HTTP_403_FORBIDDEN)

    _check_subscription_expiry(user)
    return _ok(data=_build_user_data(user, request), msg_key="login_success", lang=lang)


# ─── Admin login (password-based) ────────────────────────────────────────────

@extend_schema(
    tags=["Auth — Admin"],
    summary="Admin login — phone/email + password",
    description=(
        "Password-based login for admin accounts only.\n\n"
        "The `identifier` field accepts either a **phone number** or an **email address**.\n\n"
        "Returns full user data with JWT tokens.\n\n"
        "**No authentication required.**"
    ),
    request=AdminLoginSerializer,
    parameters=[_LANG],
    responses={
        200: OpenApiResponse(description="Login successful."),
        401: OpenApiResponse(description="Wrong credentials."),
        403: OpenApiResponse(description="Not an admin account."),
    },
    examples=[
        OpenApiExample("Admin login", request_only=True, value={"identifier": "+213555999000", "password": "adminPass123"}),
    ],
)
@api_view(["POST"])
def admin_login(request):
    lang = _lang(request)
    serializer = AdminLoginSerializer(data=request.data, context={"request": request})
    if not serializer.is_valid():
        return _err("validation_error", lang, errors=serializer.errors)

    identifier = serializer.validated_data["identifier"]
    password   = serializer.validated_data["password"]

    user   = None
    lookup = {"email": identifier} if "@" in identifier else {"phone": identifier}
    try:
        u = User.objects.get(**lookup)
        if u.check_password(password):
            user = u
    except User.DoesNotExist:
        pass

    if user is None:
        return _err("login_failed", lang, status.HTTP_401_UNAUTHORIZED)
    if user.role != "admin":
        return _err("admin_only", lang, status.HTTP_403_FORBIDDEN)
    if not user.is_active:
        return _err("account_inactive", lang, status.HTTP_403_FORBIDDEN)

    return _ok(data=_build_user_data(user, request), msg_key="login_success", lang=lang)


# ─── Logout ───────────────────────────────────────────────────────────────────

@extend_schema(
    tags=["Auth — Common"],
    summary="Logout — blacklist refresh token",
    description="Blacklists the provided refresh token.\n\n**No authentication required.**",
    request=inline_serializer("LogoutRequest", fields={
        "refresh": drf_serializers.CharField(help_text="The refresh token from login."),
    }),
    parameters=[_LANG],
    responses={200: OpenApiResponse(description="Logged out.")},
    examples=[OpenApiExample("Logout", request_only=True, value={"refresh": "eyJ..."})],
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


# ─── Get profile ──────────────────────────────────────────────────────────────

@extend_schema(
    tags=["Auth — Common"],
    summary="Get current user profile",
    description=(
        "Returns full profile of the authenticated user.\n\n"
        "**Requires:** `Authorization: Bearer <token>`"
    ),
    parameters=[_LANG, _AUTH],
    responses={
        200: OpenApiResponse(description="Profile returned."),
        401: OpenApiResponse(description="Not authenticated."),
        403: OpenApiResponse(description="Account banned."),
    },
)
@api_view(["GET"])
def get_profile(request):
    lang = _lang(request)
    user, _ = _authenticate_request(request)
    if user is None:
        return _err("unauthorized", lang, status.HTTP_401_UNAUTHORIZED)
    if user.role != "admin" and user.is_banned:
        return _err("account_banned", lang, status.HTTP_403_FORBIDDEN)
    _check_subscription_expiry(user)
    return _ok(data=_build_user_data(user, request), msg_key="profile_fetched", lang=lang)


# ─── Update profile ───────────────────────────────────────────────────────────

@extend_schema(
    tags=["Auth — Common"],
    summary="Update current user profile",
    description=(
        "Partial update. Only send the fields you want to change.\n\n"
        "**Client fields:** `full_name`, `email`, `wilaya`, `school`, `city`, `profile_picture`\n\n"
        "**Business fields:** `email`, `city`, `profile_picture`, `business_name`, `description`, "
        "`category_id`, `address`, `website`, `latitude`, `longitude`\n\n"
        "**Requires:** `Authorization: Bearer <token>`"
    ),
    request=inline_serializer("UpdateProfileRequest", fields={
        "full_name":       drf_serializers.CharField(required=False,  help_text="[Client only] Full name."),
        "email":           drf_serializers.EmailField(required=False),
        "wilaya":          drf_serializers.CharField(required=False,  help_text="[Client only] Province/wilaya."),
        "school":          drf_serializers.CharField(required=False,  help_text="[Client only] School or university."),
        "city":            drf_serializers.CharField(required=False),
        "profile_picture": drf_serializers.ImageField(required=False),
        "business_name":   drf_serializers.CharField(required=False,  help_text="[Business only]"),
        "description":     drf_serializers.CharField(required=False,  help_text="[Business only]"),
        "category_id":     drf_serializers.UUIDField(required=False,  help_text="[Business only]"),
        "address":         drf_serializers.CharField(required=False,  help_text="[Business only]"),
        "website":         drf_serializers.URLField(required=False,   help_text="[Business only]"),
        "latitude":        drf_serializers.DecimalField(max_digits=9, decimal_places=6, required=False, help_text="[Business only]"),
        "longitude":       drf_serializers.DecimalField(max_digits=9, decimal_places=6, required=False, help_text="[Business only]"),
    }),
    parameters=[_LANG, _AUTH],
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
    if user.role != "admin" and user.is_banned:
        return _err("account_banned", lang, status.HTTP_403_FORBIDDEN)

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
        if "full_name" in data: p.full_name = data["full_name"]
        if "email"     in data: p.email     = data["email"]
        if "wilaya"    in data: p.wilaya    = data["wilaya"]
        if "school"    in data: p.school    = data["school"]
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


# ─── Payment upload ───────────────────────────────────────────────────────────

@extend_schema(
    tags=["Auth — Payment"],
    summary="Upload subscription payment receipt",
    description=(
        "Upload a JPEG/PNG/PDF receipt (max 5MB). Sets `subscription_status=PENDING`.\n\n"
        "**Request format:** `multipart/form-data`\n\n"
        "**Requires:** `Authorization: Bearer <token>` (client or business)"
    ),
    request=UploadPaymentSerializer,
    parameters=[_LANG, _AUTH],
    responses={
        201: OpenApiResponse(description="Receipt uploaded."),
        400: OpenApiResponse(description="Invalid plan or file error."),
        401: OpenApiResponse(description="Not authenticated."),
        403: OpenApiResponse(description="Admins cannot upload. Banned users blocked."),
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
    if user.is_banned:
        return _err("account_banned", lang, status.HTTP_403_FORBIDDEN)

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

    payment_data = {
        "payment_id":          str(payment.id),
        "status":              payment.status,
        "plan":                plan.name,
        "amount":              str(payment.amount),
        "subscription_status": user.subscription_status,
    }
    # Real-time: payment now pending review (persisted notification + live push)
    from deals_app.services import notify, send_realtime
    send_realtime(user, "payment", payment_data)
    notify(
        user,
        title="Payment received",
        body=f"Your payment for '{plan.name}' is under review. Awaiting admin approval.",
        ntype="payment",
        extra={"payment": payment_data},
    )

    return _ok(
        data=payment_data,
        msg_key="payment_uploaded",
        lang=lang,
        http_status=status.HTTP_201_CREATED,
    )


# ─── Subscription status ──────────────────────────────────────────────────────

@extend_schema(
    tags=["Auth — Payment"],
    summary="Get subscription status",
    description=(
        "Returns current subscription state. Expiry is auto-checked on every call.\n\n"
        "**States:** `FREE` · `PENDING` · `ACTIVE` · `EXPIRED`\n\n"
        "**Requires:** `Authorization: Bearer <token>`"
    ),
    parameters=[_LANG, _AUTH],
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
            "subscription_end":    user.subscription_end,
            "plan": user.current_plan.name if user.current_plan else None,
        },
        msg_key="subscription_status_fetched",
        lang=lang,
    )