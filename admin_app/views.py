# App: admin_app | File: views.py
from django.utils import timezone
from django.db import transaction
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import (
    extend_schema,
    OpenApiParameter, OpenApiExample, OpenApiResponse,
    inline_serializer,
)
from drf_spectacular.types import OpenApiTypes
from rest_framework import serializers as drf_serializers
import datetime

from .models import Category, SubscriptionPlan, Payment
from .serializers import (
    CategorySerializer, SubscriptionPlanSerializer,
    PaymentSerializer, ApprovePaymentSerializer,
    AdminUserListSerializer, AdminSetSubscriptionSerializer,
)
from auth_app.models import User
from core.messages import get_message
from core.decorators import admin_required

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
    description="Admin JWT Bearer token. Format: `Bearer <access_token>`. Only admin accounts are accepted.",
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


@extend_schema(
    tags=["Admin — Categories"],
    summary="List all categories / Create a new category",
    description=(
        "**GET** — Returns a list of all business categories (active and inactive). "
        "Each category includes an absolute URL for its photo.\n\n"
        "**POST** — Creates a new category. The `name` must be unique (case-insensitive) and at least 2 characters. "
        "The `photo` is optional — upload as `multipart/form-data`.\n\n"
        "**Requires:** Admin JWT token."
    ),
    request=CategorySerializer,
    parameters=[_LANG_HEADER, _AUTH_HEADER],
    responses={
        200: OpenApiResponse(description="[GET] List of categories returned."),
        201: OpenApiResponse(description="[POST] Category created successfully."),
        400: OpenApiResponse(description="Validation error — name too short or already exists."),
        401: OpenApiResponse(description="Missing or invalid token."),
        403: OpenApiResponse(description="Not an admin account."),
    },
    examples=[
        OpenApiExample(
            "Create category body",
            request_only=True,
            value={"name": "Café", "is_active": True},
        ),
        OpenApiExample(
            "Category list response",
            response_only=True,
            value={
                "success": True, "message": "Categories fetched successfully.",
                "data": [
                    {"id": "uuid", "name": "Café", "photo_url": "http://localhost:8000/media/categories/cafe.jpg", "is_active": True, "created_at": "2026-01-01T10:00:00Z", "updated_at": "2026-01-01T10:00:00Z"},
                ],
            },
        ),
    ],
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
    description=(
        "**GET** — Returns a single category by its UUID.\n\n"
        "**PATCH** — Partially updates a category. You can change the `name`, `photo`, or `is_active` flag. "
        "Toggling `is_active=false` hides the category from business registration.\n\n"
        "**DELETE** — Permanently deletes the category. Businesses linked to this category will have their "
        "`category` field set to `null` (due to `SET_NULL`).\n\n"
        "**Requires:** Admin JWT token."
    ),
    parameters=[
        _LANG_HEADER, _AUTH_HEADER,
        OpenApiParameter("category_id", OpenApiTypes.UUID, OpenApiParameter.PATH, description="UUID of the category to operate on."),
    ],
    request=CategorySerializer,
    responses={
        200: OpenApiResponse(description="[GET / PATCH] Category data returned or updated."),
        204: OpenApiResponse(description="[DELETE] Category deleted."),
        404: OpenApiResponse(description="Category not found."),
    },
    examples=[
        OpenApiExample("Update category name", request_only=True, value={"name": "Restaurant"}),
        OpenApiExample("Deactivate category", request_only=True, value={"is_active": False}),
    ],
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
        serializer = CategorySerializer(category, context={"request": request})
        return _ok(data=serializer.data, msg_key="category_fetched", lang=lang)

    if request.method == "PATCH":
        serializer = CategorySerializer(category, data=request.data, partial=True, context={"request": request})
        if not serializer.is_valid():
            return _err("validation_error", lang, errors=serializer.errors)
        serializer.save()
        return _ok(data=serializer.data, msg_key="category_updated", lang=lang)

    category.delete()
    return _ok(msg_key="category_deleted", lang=lang)


@extend_schema(
    tags=["Admin — Plans"],
    summary="List all plans / Create a new subscription plan",
    description=(
        "**GET** — Returns all subscription plans including inactive ones.\n\n"
        "**POST** — Creates a new subscription plan. Plans are fully dynamic — no hardcoded tiers. "
        "The `duration_days` field is the exact number of days the subscription will be active after payment approval. "
        "Use `target_role` to restrict who can purchase the plan: `client`, `business`, or `both`.\n\n"
        "**Duration type options:** `monthly`, `quarterly`, `semi_annual`, `annual`, `custom`\n\n"
        "**Requires:** Admin JWT token."
    ),
    request=SubscriptionPlanSerializer,
    parameters=[_LANG_HEADER, _AUTH_HEADER],
    responses={
        200: OpenApiResponse(description="[GET] Plan list returned."),
        201: OpenApiResponse(description="[POST] Plan created."),
        400: OpenApiResponse(description="Validation error — price must be > 0, duration_days must be > 0."),
    },
    examples=[
        OpenApiExample(
            "Create monthly client plan",
            request_only=True,
            value={
                "name": "Monthly Plan",
                "description": "Access all premium offers for 30 days.",
                "price": "500.00",
                "duration_type": "monthly",
                "duration_days": 30,
                "target_role": "client",
                "is_active": True,
            },
        ),
        OpenApiExample(
            "Create annual business plan",
            request_only=True,
            value={
                "name": "Annual Business Plan",
                "description": "Publish unlimited offers for 365 days.",
                "price": "5000.00",
                "duration_type": "annual",
                "duration_days": 365,
                "target_role": "business",
                "is_active": True,
            },
        ),
    ],
)
@api_view(["GET", "POST"])
@parser_classes([JSONParser])
@admin_required
def plans(request):
    lang = _lang(request)

    if request.method == "GET":
        qs = SubscriptionPlan.objects.all().order_by("-created_at")
        serializer = SubscriptionPlanSerializer(qs, many=True, context={"request": request})
        return _ok(data=serializer.data, msg_key="plan_fetched", lang=lang)

    serializer = SubscriptionPlanSerializer(data=request.data, context={"request": request})
    if not serializer.is_valid():
        return _err("validation_error", lang, errors=serializer.errors)
    serializer.save()
    return _ok(data=serializer.data, msg_key="plan_created", lang=lang, http_status=status.HTTP_201_CREATED)


@extend_schema(
    tags=["Admin — Plans"],
    summary="Retrieve / Update / Delete a subscription plan",
    description=(
        "**GET** — Returns a single plan by UUID.\n\n"
        "**PATCH** — Partially updates the plan. You can change any field. "
        "Setting `is_active=false` prevents new users from subscribing to this plan but does not "
        "affect existing active subscriptions.\n\n"
        "**DELETE** — Permanently deletes the plan. Existing payments linked to this plan will "
        "have their `plan` field set to `null`.\n\n"
        "**Requires:** Admin JWT token."
    ),
    parameters=[
        _LANG_HEADER, _AUTH_HEADER,
        OpenApiParameter("plan_id", OpenApiTypes.UUID, OpenApiParameter.PATH, description="UUID of the subscription plan."),
    ],
    request=SubscriptionPlanSerializer,
    responses={
        200: OpenApiResponse(description="Plan data returned or updated."),
        404: OpenApiResponse(description="Plan not found."),
    },
    examples=[
        OpenApiExample("Update plan price", request_only=True, value={"price": "600.00"}),
        OpenApiExample("Deactivate plan", request_only=True, value={"is_active": False}),
    ],
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
        serializer = SubscriptionPlanSerializer(plan, context={"request": request})
        return _ok(data=serializer.data, msg_key="plan_fetched", lang=lang)

    if request.method == "PATCH":
        serializer = SubscriptionPlanSerializer(plan, data=request.data, partial=True, context={"request": request})
        if not serializer.is_valid():
            return _err("validation_error", lang, errors=serializer.errors)
        serializer.save()
        return _ok(data=serializer.data, msg_key="plan_updated", lang=lang)

    plan.delete()
    return _ok(msg_key="plan_deleted", lang=lang)


@extend_schema(
    tags=["Admin — Payments"],
    summary="List all PENDING payment receipts",
    description=(
        "Returns only payments with status `PENDING` — i.e. receipts that have been uploaded by users "
        "but not yet reviewed by an admin. This is the main queue the admin should monitor. "
        "Each entry includes the user details, plan info, and a URL to the uploaded receipt file.\n\n"
        "**Requires:** Admin JWT token."
    ),
    parameters=[_LANG_HEADER, _AUTH_HEADER],
    responses={200: OpenApiResponse(description="List of pending payments returned.")},
)
@api_view(["GET"])
@admin_required
def pending_payments(request):
    lang = _lang(request)
    qs = Payment.objects.filter(status="PENDING").select_related("user", "plan").order_by("-created_at")
    serializer = PaymentSerializer(qs, many=True, context={"request": request})
    return _ok(data=serializer.data, msg_key="payments_fetched", lang=lang)


@extend_schema(
    tags=["Admin — Payments"],
    summary="List all payments (all statuses)",
    description=(
        "Returns every payment record regardless of status (`PENDING`, `APPROVED`, `REJECTED`). "
        "Useful for full payment history. "
        "Results are ordered by creation date descending (newest first).\n\n"
        "**Requires:** Admin JWT token."
    ),
    parameters=[_LANG_HEADER, _AUTH_HEADER],
    responses={200: OpenApiResponse(description="Full payment history returned.")},
)
@api_view(["GET"])
@admin_required
def all_payments(request):
    lang = _lang(request)
    qs = Payment.objects.all().select_related("user", "plan", "reviewed_by").order_by("-created_at")
    serializer = PaymentSerializer(qs, many=True, context={"request": request})
    return _ok(data=serializer.data, msg_key="payments_fetched", lang=lang)


@extend_schema(
    tags=["Admin — Payments"],
    summary="Approve or reject a payment receipt",
    description=(
        "Reviews a single payment receipt. Only payments with status `PENDING` can be reviewed.\n\n"
        "**If `action = approve`:**\n"
        "- Payment status → `APPROVED`\n"
        "- User's `subscription_status` → `ACTIVE`\n"
        "- `subscription_end` is calculated as: `now + plan.duration_days`\n"
        "- `current_plan` is set on the user\n\n"
        "**If `action = reject`:**\n"
        "- Payment status → `REJECTED`\n"
        "- `rejection_reason` is saved (required when rejecting)\n"
        "- If the user's status was `PENDING`, it is reset to `FREE`\n\n"
        "**Requires:** Admin JWT token."
    ),
    request=ApprovePaymentSerializer,
    parameters=[
        _LANG_HEADER, _AUTH_HEADER,
        OpenApiParameter("payment_id", OpenApiTypes.UUID, OpenApiParameter.PATH, description="UUID of the payment to review."),
    ],
    responses={
        200: OpenApiResponse(
            description="Payment reviewed. Returns approval info or rejection confirmation.",
            examples=[
                OpenApiExample(
                    "Approve response",
                    value={"success": True, "message": "Payment approved. Subscription activated.", "data": {"payment_id": "uuid", "subscription_end": "2026-05-01T00:00:00Z"}},
                ),
                OpenApiExample(
                    "Reject response",
                    value={"success": True, "message": "Payment rejected."},
                ),
            ],
        ),
        400: OpenApiResponse(description="Payment already reviewed, or rejection_reason missing on reject action."),
        404: OpenApiResponse(description="Payment not found."),
    },
    examples=[
        OpenApiExample("Approve payment", request_only=True, value={"action": "approve"}),
        OpenApiExample("Reject payment", request_only=True, value={"action": "reject", "rejection_reason": "Receipt image is blurry and unreadable."}),
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
        payment.reviewed_by = request.user
        payment.reviewed_at = timezone.now()

        if action == "approve":
            payment.status = "APPROVED"
            payment.save()
            user = payment.user
            plan = payment.plan
            end = timezone.now() + datetime.timedelta(days=plan.duration_days)
            user.subscription_status = "ACTIVE"
            user.subscription_end = end
            user.current_plan = plan
            user.save(update_fields=["subscription_status", "subscription_end", "current_plan"])
            return _ok(
                data={"payment_id": str(payment.id), "subscription_end": end},
                msg_key="payment_approved",
                lang=lang,
            )

        payment.status = "REJECTED"
        payment.rejection_reason = serializer.validated_data.get("rejection_reason", "")
        payment.save()
        user = payment.user
        if user.subscription_status == "PENDING":
            user.subscription_status = "FREE"
            user.save(update_fields=["subscription_status"])
        return _ok(msg_key="payment_rejected", lang=lang)


@extend_schema(
    tags=["Admin — Users"],
    summary="List all users (clients and businesses)",
    description=(
        "Returns all registered users excluding admin accounts. "
        "Optionally filter by role using the `role` query parameter.\n\n"
        "**Query parameters:**\n"
        "- `role` (optional) — filter by `client` or `business`\n\n"
        "Each user object includes their profile details (client name or business info with coordinates), "
        "subscription status, and verification state.\n\n"
        "**Requires:** Admin JWT token."
    ),
    parameters=[
        _LANG_HEADER, _AUTH_HEADER,
        OpenApiParameter(
            "role", OpenApiTypes.STR, OpenApiParameter.QUERY,
            description="Filter users by role. Options: `client`, `business`.",
            required=False,
            examples=[
                OpenApiExample("Only clients", value="client"),
                OpenApiExample("Only businesses", value="business"),
            ],
        ),
    ],
    responses={200: OpenApiResponse(description="User list returned.")},
)
@api_view(["GET"])
@admin_required
def list_users(request):
    lang = _lang(request)
    role = request.query_params.get("role")
    qs = User.objects.exclude(role="admin").order_by("-created_at")
    if role:
        qs = qs.filter(role=role)
    serializer = AdminUserListSerializer(qs, many=True, context={"request": request})
    return _ok(data=serializer.data, msg_key="users_fetched", lang=lang)


@extend_schema(
    tags=["Admin — Users"],
    summary="Toggle user active/inactive status",
    description=(
        "Flips the `is_active` flag of a user. "
        "If the user is currently active, they will be deactivated and blocked from logging in. "
        "If inactive, they will be reactivated.\n\n"
        "No request body is needed — it simply toggles the current value.\n\n"
        "**Requires:** Admin JWT token."
    ),
    parameters=[
        _LANG_HEADER, _AUTH_HEADER,
        OpenApiParameter("user_id", OpenApiTypes.UUID, OpenApiParameter.PATH, description="UUID of the user to toggle."),
    ],
    responses={
        200: OpenApiResponse(
            description="User active status toggled.",
            examples=[
                OpenApiExample("Deactivated", value={"success": True, "message": "User status updated successfully.", "data": {"is_active": False}}),
                OpenApiExample("Reactivated", value={"success": True, "message": "User status updated successfully.", "data": {"is_active": True}}),
            ],
        ),
        404: OpenApiResponse(description="User not found."),
    },
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
    summary="Manually set a user's subscription status",
    description=(
        "Allows the admin to manually override a user's subscription status. "
        "Useful for edge cases such as manual refunds, testing, or resolving disputes.\n\n"
        "**Allowed values for `subscription_status`:** `FREE`, `PENDING`, `ACTIVE`, `EXPIRED`\n\n"
        "**Note:** Setting to `ACTIVE` via this endpoint does **not** set `subscription_end` — "
        "use the `/payments/<id>/review/` approve flow for proper activation with an end date. "
        "Setting to any value other than `ACTIVE` will clear the `subscription_end` date.\n\n"
        "**Requires:** Admin JWT token."
    ),
    request=AdminSetSubscriptionSerializer,
    parameters=[
        _LANG_HEADER, _AUTH_HEADER,
        OpenApiParameter("user_id", OpenApiTypes.UUID, OpenApiParameter.PATH, description="UUID of the user whose subscription to update."),
    ],
    responses={
        200: OpenApiResponse(
            description="Subscription status updated.",
            examples=[OpenApiExample(
                "Reset to FREE",
                value={"success": True, "message": "Subscription status updated successfully.", "data": {"subscription_status": "FREE"}},
            )],
        ),
        400: OpenApiResponse(description="Invalid subscription_status value."),
        404: OpenApiResponse(description="User not found."),
    },
    examples=[
        OpenApiExample("Set to FREE", request_only=True, value={"subscription_status": "FREE"}),
        OpenApiExample("Set to EXPIRED", request_only=True, value={"subscription_status": "EXPIRED"}),
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