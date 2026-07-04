# App: admin_app | File: views.py
from django.utils import timezone
from django.db import transaction
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import (
    extend_schema, OpenApiParameter, OpenApiExample, OpenApiResponse,
)
from drf_spectacular.types import OpenApiTypes
import datetime

from .models import Category, SubscriptionPlan, Payment
from .serializers import (
    CategorySerializer, SubscriptionPlanSerializer,
    PaymentSerializer, ApprovePaymentSerializer,
    AdminUserListSerializer, AdminSetSubscriptionSerializer,
)
from auth_app.models import User
from deals_app.models import Deal
from deals_app.serializers import AdminDealSerializer, FeatureDealSerializer
from core.messages import get_message
from core.decorators import admin_required
from deals_app.services import notify, send_realtime

_LANG = OpenApiParameter(name="Accept-Language", location=OpenApiParameter.HEADER, description="en / ar / fr", required=False, type=OpenApiTypes.STR)
_AUTH = OpenApiParameter(name="Authorization", location=OpenApiParameter.HEADER, description="Bearer <admin_token>", required=True, type=OpenApiTypes.STR)


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


# ─── Categories ───────────────────────────────────────────────────────────────

@extend_schema(
    tags=["Admin — Categories"],
    summary="List all categories / Create a new category",
    description="**GET** — List all categories.\n\n**POST** — Create a new category with optional photo.\n\n**Requires:** Admin token.",
    request=CategorySerializer,
    parameters=[_LANG, _AUTH],
    responses={200: OpenApiResponse(description="List returned."), 201: OpenApiResponse(description="Created.")},
    examples=[OpenApiExample("Create", request_only=True, value={"name": "Café", "is_active": True})],
)
@api_view(["GET", "POST"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@admin_required
def categories(request):
    lang = _lang(request)

    if request.method == "GET":
        qs = Category.objects.all().order_by("-created_at")
        serializer = CategorySerializer(qs, many=True, context={"request": request})
        return _ok(data=serializer.data, msg_key="category_fetched", lang=lang)

    serializer = CategorySerializer(data=request.data, context={"request": request})
    if not serializer.is_valid():
        return _err("validation_error", lang, errors=serializer.errors)
    serializer.save()
    return _ok(data=serializer.data, msg_key="category_created", lang=lang, http_status=status.HTTP_201_CREATED)


@extend_schema(
    tags=["Admin — Categories"],
    summary="Retrieve / Update / Delete a category",
    description="**GET** · **PATCH** · **DELETE** a single category by UUID.\n\n**Requires:** Admin token.",
    parameters=[_LANG, _AUTH, OpenApiParameter("category_id", OpenApiTypes.UUID, OpenApiParameter.PATH)],
    request=CategorySerializer,
    responses={200: OpenApiResponse(description="OK."), 404: OpenApiResponse(description="Not found.")},
)
@api_view(["GET", "PATCH", "DELETE"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@admin_required
def category_detail(request, category_id):
    lang = _lang(request)
    try:
        category = Category.objects.get(id=category_id)
    except Category.DoesNotExist:
        return _err("not_found", lang, status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        return _ok(data=CategorySerializer(category, context={"request": request}).data, msg_key="category_fetched", lang=lang)
    if request.method == "PATCH":
        serializer = CategorySerializer(category, data=request.data, partial=True, context={"request": request})
        if not serializer.is_valid():
            return _err("validation_error", lang, errors=serializer.errors)
        serializer.save()
        return _ok(data=serializer.data, msg_key="category_updated", lang=lang)
    category.delete()
    return _ok(msg_key="category_deleted", lang=lang)


# ─── Plans ────────────────────────────────────────────────────────────────────

@extend_schema(
    tags=["Admin — Plans"],
    summary="List all plans / Create a new subscription plan",
    description="**GET** — All plans.\n\n**POST** — Create a new plan.\n\n**Requires:** Admin token.",
    request=SubscriptionPlanSerializer,
    parameters=[_LANG, _AUTH],
    responses={200: OpenApiResponse(description="List."), 201: OpenApiResponse(description="Created.")},
    examples=[OpenApiExample("Create monthly plan", request_only=True, value={
        "name": "Monthly", "price": "500.00", "duration_type": "monthly",
        "duration_days": 30, "target_role": "client", "is_active": True,
    })],
)
@api_view(["GET", "POST"])
@parser_classes([JSONParser])
@admin_required
def plans(request):
    lang = _lang(request)

    if request.method == "GET":
        qs = SubscriptionPlan.objects.all().order_by("-created_at")
        return _ok(data=SubscriptionPlanSerializer(qs, many=True, context={"request": request}).data, msg_key="plan_fetched", lang=lang)

    serializer = SubscriptionPlanSerializer(data=request.data, context={"request": request})
    if not serializer.is_valid():
        return _err("validation_error", lang, errors=serializer.errors)
    serializer.save()
    return _ok(data=serializer.data, msg_key="plan_created", lang=lang, http_status=status.HTTP_201_CREATED)


@extend_schema(
    tags=["Admin — Plans"],
    summary="Retrieve / Update / Delete a plan",
    description="**GET** · **PATCH** · **DELETE** a plan by UUID.\n\n**Requires:** Admin token.",
    parameters=[_LANG, _AUTH, OpenApiParameter("plan_id", OpenApiTypes.UUID, OpenApiParameter.PATH)],
    request=SubscriptionPlanSerializer,
    responses={200: OpenApiResponse(description="OK."), 404: OpenApiResponse(description="Not found.")},
)
@api_view(["GET", "PATCH", "DELETE"])
@parser_classes([JSONParser])
@admin_required
def plan_detail(request, plan_id):
    lang = _lang(request)
    try:
        plan = SubscriptionPlan.objects.get(id=plan_id)
    except SubscriptionPlan.DoesNotExist:
        return _err("not_found", lang, status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        return _ok(data=SubscriptionPlanSerializer(plan, context={"request": request}).data, msg_key="plan_fetched", lang=lang)
    if request.method == "PATCH":
        serializer = SubscriptionPlanSerializer(plan, data=request.data, partial=True, context={"request": request})
        if not serializer.is_valid():
            return _err("validation_error", lang, errors=serializer.errors)
        serializer.save()
        return _ok(data=serializer.data, msg_key="plan_updated", lang=lang)
    plan.delete()
    return _ok(msg_key="plan_deleted", lang=lang)


# ─── Payments ─────────────────────────────────────────────────────────────────

@extend_schema(
    tags=["Admin — Payments"],
    summary="List PENDING payment receipts",
    description="Returns only payments with status `PENDING`.\n\n**Requires:** Admin token.",
    parameters=[_LANG, _AUTH],
    responses={200: OpenApiResponse(description="List returned.")},
)
@api_view(["GET"])
@admin_required
def pending_payments(request):
    lang = _lang(request)
    qs = Payment.objects.filter(status="PENDING").select_related("user", "plan").order_by("-created_at")
    return _ok(data=PaymentSerializer(qs, many=True, context={"request": request}).data, msg_key="payments_fetched", lang=lang)


@extend_schema(
    tags=["Admin — Payments"],
    summary="List all payments (all statuses)",
    description="Full payment history.\n\n**Requires:** Admin token.",
    parameters=[_LANG, _AUTH],
    responses={200: OpenApiResponse(description="List returned.")},
)
@api_view(["GET"])
@admin_required
def all_payments(request):
    lang = _lang(request)
    qs = Payment.objects.all().select_related("user", "plan", "reviewed_by").order_by("-created_at")
    return _ok(data=PaymentSerializer(qs, many=True, context={"request": request}).data, msg_key="payments_fetched", lang=lang)


@extend_schema(
    tags=["Admin — Payments"],
    summary="Approve or reject a payment receipt",
    description=(
        "Reviews a pending payment.\n\n"
        "`action=approve` → activates subscription.\n\n"
        "`action=reject` → requires `rejection_reason`.\n\n"
        "**Requires:** Admin token."
    ),
    request=ApprovePaymentSerializer,
    parameters=[_LANG, _AUTH, OpenApiParameter("payment_id", OpenApiTypes.UUID, OpenApiParameter.PATH)],
    responses={
        200: OpenApiResponse(description="Reviewed."),
        400: OpenApiResponse(description="Already reviewed or missing reason."),
        404: OpenApiResponse(description="Not found."),
    },
    examples=[
        OpenApiExample("Approve", request_only=True, value={"action": "approve"}),
        OpenApiExample("Reject",  request_only=True, value={"action": "reject", "rejection_reason": "Blurry image."}),
    ],
)
@api_view(["POST"])
@parser_classes([JSONParser])
@admin_required
def review_payment(request, payment_id):
    lang = _lang(request)
    try:
        payment = Payment.objects.select_related("user", "plan").get(id=payment_id)
    except Payment.DoesNotExist:
        return _err("not_found", lang, status.HTTP_404_NOT_FOUND)

    if payment.status != "PENDING":
        return _err("payment_already_reviewed", lang)

    serializer = ApprovePaymentSerializer(data=request.data, context={"request": request})
    if not serializer.is_valid():
        return _err("validation_error", lang, errors=serializer.errors)

    action = serializer.validated_data["action"]

    with transaction.atomic():
        payment.reviewed_by  = request.user
        payment.reviewed_at  = timezone.now()

        if action == "approve":
            payment.status = "APPROVED"
            payment.save()
            user = payment.user
            plan = payment.plan
            end  = timezone.now() + datetime.timedelta(days=plan.duration_days)
            user.subscription_status = "ACTIVE"
            user.subscription_end    = end
            user.current_plan        = plan
            user.save(update_fields=["subscription_status", "subscription_end", "current_plan"])

            payment_data = {
                "payment_id":          str(payment.id),
                "status":              payment.status,
                "plan":                plan.name if plan else None,
                "subscription_status": user.subscription_status,
                "subscription_end":    end,
            }
            send_realtime(user, "payment", payment_data)
            notify(
                user,
                title="Subscription activated",
                body=f"Your WINDEAL+ subscription ('{plan.name}') is now active.",
                ntype="subscription",
                extra={"payment": payment_data},
            )
            return _ok(data={"payment_id": str(payment.id), "subscription_end": end}, msg_key="payment_approved", lang=lang)

        payment.status           = "REJECTED"
        payment.rejection_reason = serializer.validated_data.get("rejection_reason", "")
        payment.save()
        user = payment.user
        if user.subscription_status == "PENDING":
            user.subscription_status = "FREE"
            user.save(update_fields=["subscription_status"])

        payment_data = {
            "payment_id":          str(payment.id),
            "status":              payment.status,
            "rejection_reason":    payment.rejection_reason,
            "subscription_status": user.subscription_status,
        }
        send_realtime(user, "payment", payment_data)
        notify(
            user,
            title="Payment rejected",
            body=payment.rejection_reason or "Your payment could not be verified. Please try again.",
            ntype="payment",
            extra={"payment": payment_data},
        )
        return _ok(msg_key="payment_rejected", lang=lang)


# ─── Users ────────────────────────────────────────────────────────────────────

@extend_schema(
    tags=["Admin — Users"],
    summary="List all users (clients and businesses)",
    description=(
        "Returns all non-admin users. Filter with `?role=client` or `?role=business`.\n\n"
        "Response includes `is_banned` field for each user.\n\n"
        "**Requires:** Admin token."
    ),
    parameters=[
        _LANG, _AUTH,
        OpenApiParameter("role", OpenApiTypes.STR, OpenApiParameter.QUERY,
                         description="Filter by role: `client` or `business`.", required=False),
    ],
    responses={200: OpenApiResponse(description="List returned.")},
)
@api_view(["GET"])
@admin_required
def list_users(request):
    lang = _lang(request)
    role = request.query_params.get("role")
    qs   = User.objects.exclude(role="admin").order_by("-created_at")
    if role:
        qs = qs.filter(role=role)
    return _ok(data=AdminUserListSerializer(qs, many=True, context={"request": request}).data, msg_key="users_fetched", lang=lang)


@extend_schema(
    tags=["Admin — Users"],
    summary="Toggle user active/inactive status",
    description="Flips `is_active`. Deactivated users cannot log in.\n\n**Requires:** Admin token.",
    request=None,
    parameters=[_LANG, _AUTH, OpenApiParameter("user_id", OpenApiTypes.UUID, OpenApiParameter.PATH)],
    responses={200: OpenApiResponse(description="Toggled."), 404: OpenApiResponse(description="Not found.")},
)
@api_view(["PATCH"])
@parser_classes([JSONParser])
@admin_required
def toggle_user(request, user_id):
    lang = _lang(request)
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return _err("not_found", lang, status.HTTP_404_NOT_FOUND)

    user.is_active = not user.is_active
    user.save(update_fields=["is_active"])
    return _ok(data={"is_active": user.is_active}, msg_key="user_toggled", lang=lang)


@extend_schema(
    tags=["Admin — Users"],
    summary="Ban or unban a user",
    description=(
        "Toggles the `is_banned` flag on a user.\n\n"
        "- **Banned users** are blocked from login (`/api/auth/check/` returns `is_banned=true`) "
        "and all protected endpoints return `403`.\n"
        "- This endpoint **toggles** — if the user is currently banned, calling this unbans them, and vice versa.\n\n"
        "**Cannot ban admin accounts.**\n\n"
        "**Requires:** Admin token."
    ),
    request=None,
    parameters=[_LANG, _AUTH, OpenApiParameter("user_id", OpenApiTypes.UUID, OpenApiParameter.PATH)],
    responses={
        200: OpenApiResponse(
            description="Ban status toggled.",
            examples=[
                OpenApiExample("Banned",   value={"success": True, "message": "User has been banned.",   "data": {"is_banned": True}}),
                OpenApiExample("Unbanned", value={"success": True, "message": "User has been unbanned.", "data": {"is_banned": False}}),
            ],
        ),
        403: OpenApiResponse(description="Cannot ban admin accounts."),
        404: OpenApiResponse(description="User not found."),
    },
)
@api_view(["PATCH"])
@parser_classes([JSONParser])
@admin_required
def ban_user(request, user_id):
    lang = _lang(request)
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return _err("not_found", lang, status.HTTP_404_NOT_FOUND)

    if user.role == "admin":
        return Response(
            {"success": False, "message": "Cannot ban admin accounts."},
            status=status.HTTP_403_FORBIDDEN,
        )

    user.is_banned = not user.is_banned
    user.save(update_fields=["is_banned"])
    msg_key = "user_banned" if user.is_banned else "user_unbanned"
    return _ok(data={"is_banned": user.is_banned}, msg_key=msg_key, lang=lang)


@extend_schema(
    tags=["Admin — Deals"],
    summary="List all deals (for featuring control)",
    description=(
        "Returns all deals across every business so an admin can choose which to feature.\n\n"
        "Optional filters: `?featured=true|false`, `?search=` (title), `?is_active=true|false`.\n\n"
        "**Requires:** Admin token."
    ),
    parameters=[
        _LANG, _AUTH,
        OpenApiParameter("featured", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False,
                         description="Filter by featured state: true / false."),
        OpenApiParameter("is_active", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False,
                         description="Filter by active state: true / false."),
        OpenApiParameter("search", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False,
                         description="Search by deal title."),
    ],
    responses={200: OpenApiResponse(response=AdminDealSerializer(many=True), description="Deals returned.")},
)
@api_view(["GET"])
@admin_required
def deals(request):
    lang = _lang(request)
    qs = Deal.objects.select_related("category", "business", "business__business_profile").order_by("-created_at")

    featured = request.query_params.get("featured")
    if featured is not None:
        qs = qs.filter(is_featured=str(featured).lower() in ("1", "true", "yes"))

    is_active = request.query_params.get("is_active")
    if is_active is not None:
        qs = qs.filter(is_active=str(is_active).lower() in ("1", "true", "yes"))

    search = request.query_params.get("search")
    if search:
        qs = qs.filter(title__icontains=search)

    return _ok(data=AdminDealSerializer(qs, many=True, context={"request": request}).data, lang=lang)


@extend_schema(
    tags=["Admin — Deals"],
    summary="Set or toggle a deal's featured flag",
    description=(
        "Marks a deal as featured or not. Send `{\"is_featured\": true}` to set it explicitly, "
        "or send an empty body to toggle the current value.\n\n"
        "**Requires:** Admin token."
    ),
    request=FeatureDealSerializer,
    parameters=[_LANG, _AUTH, OpenApiParameter("deal_id", OpenApiTypes.UUID, OpenApiParameter.PATH)],
    responses={
        200: OpenApiResponse(response=AdminDealSerializer, description="Updated."),
        404: OpenApiResponse(description="Not found."),
    },
    examples=[
        OpenApiExample("Set featured", request_only=True, value={"is_featured": True}),
        OpenApiExample("Toggle", request_only=True, value={}),
    ],
)
@api_view(["PATCH"])
@parser_classes([JSONParser])
@admin_required
def feature_deal(request, deal_id):
    lang = _lang(request)
    try:
        deal = Deal.objects.select_related("category", "business", "business__business_profile").get(id=deal_id)
    except Deal.DoesNotExist:
        return _err("not_found", lang, status.HTTP_404_NOT_FOUND)

    if "is_featured" in request.data:
        deal.is_featured = str(request.data.get("is_featured")).lower() in ("1", "true", "yes", "True")
    else:
        deal.is_featured = not deal.is_featured
    deal.save(update_fields=["is_featured"])
    return _ok(data=AdminDealSerializer(deal, context={"request": request}).data, lang=lang)


@extend_schema(
    tags=["Admin — Users"],
    summary="Manually set a user's subscription status",
    description=(
        "Override subscription status. Valid values: `FREE`, `PENDING`, `ACTIVE`, `EXPIRED`.\n\n"
        "Setting to anything other than `ACTIVE` clears `subscription_end`.\n\n"
        "**Requires:** Admin token."
    ),
    request=AdminSetSubscriptionSerializer,
    parameters=[_LANG, _AUTH, OpenApiParameter("user_id", OpenApiTypes.UUID, OpenApiParameter.PATH)],
    responses={200: OpenApiResponse(description="Updated."), 400: OpenApiResponse(description="Invalid value."), 404: OpenApiResponse(description="Not found.")},
    examples=[
        OpenApiExample("Reset to FREE",    request_only=True, value={"subscription_status": "FREE"}),
        OpenApiExample("Set to EXPIRED",   request_only=True, value={"subscription_status": "EXPIRED"}),
    ],
)
@api_view(["PATCH"])
@parser_classes([JSONParser])
@admin_required
def set_subscription(request, user_id):
    lang = _lang(request)
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return _err("not_found", lang, status.HTTP_404_NOT_FOUND)

    serializer = AdminSetSubscriptionSerializer(data=request.data, context={"request": request})
    if not serializer.is_valid():
        return _err("validation_error", lang, errors=serializer.errors)

    new_status = serializer.validated_data["subscription_status"]
    user.subscription_status = new_status
    if new_status != "ACTIVE":
        user.subscription_end = None
    user.save(update_fields=["subscription_status", "subscription_end"])
    return _ok(data={"subscription_status": user.subscription_status}, msg_key="subscription_updated", lang=lang)