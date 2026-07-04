# App: deals_app | File: views.py
"""
Client-side, business-side, subscription, notification and profile-passthrough
endpoints required by the WINDEAL API spec (v1.2).
"""
import datetime as dt
import math
from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Count, F, Value, FloatField, ExpressionWrapper
from django.db.models.functions import TruncDate
from django.utils import timezone

from rest_framework import status, serializers as drf_serializers
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response

from drf_spectacular.utils import (
    extend_schema, OpenApiParameter, OpenApiExample, OpenApiResponse,
    inline_serializer,
)
from drf_spectacular.types import OpenApiTypes

from admin_app.models import Category, SubscriptionPlan, Payment
from auth_app.models import User, ClientProfile, BusinessProfile
from core.decorators import (
    _authenticate_request, login_required, client_required, business_required,
)
from core.messages import get_message

from .models import Deal, Favorite, RedemptionToken, Redemption, Notification
from .services import notify, send_realtime, redeem_token
from .serializers import (
    PublicCategorySerializer,
    DealListSerializer,
    BusinessOfferSerializer,
    SubscriptionPlanPublicSerializer,
    SubscriptionUpgradeSerializer,
    NotificationSerializer,
    GenerateCodeSerializer,
    RedeemSerializer,
    ToggleFavoriteSerializer,
    PaymentHistorySerializer,
)


# ─── Shared helpers ───────────────────────────────────────────────────────────

_LANG = OpenApiParameter(name="Accept-Language", location=OpenApiParameter.HEADER,
                         description="en / ar / fr", required=False, type=OpenApiTypes.STR)
_AUTH = OpenApiParameter(name="Authorization", location=OpenApiParameter.HEADER,
                         description="Bearer <token>", required=True, type=OpenApiTypes.STR)


def _lang(request):
    raw = request.headers.get("Accept-Language", "en")[:2].lower()
    return raw if raw in ("en", "ar", "fr") else "en"


def _ok(data=None, msg_key=None, lang="en", http_status=status.HTTP_200_OK, message=None):
    payload = {"success": True}
    if msg_key:
        payload["message"] = get_message(msg_key, lang)
    if message:
        payload["message"] = message
    if data is not None:
        payload["data"] = data
    return Response(payload, status=http_status)


def _err(msg_key=None, lang="en", http_status=status.HTTP_400_BAD_REQUEST, errors=None, message=None):
    payload = {"success": False}
    if msg_key:
        payload["message"] = get_message(msg_key, lang)
    if message:
        payload["message"] = message
    if errors:
        payload["errors"] = errors
    return Response(payload, status=http_status)


def _haversine_km(lat1, lon1, lat2, lon2):
    """Approximate distance between two coordinates in km."""
    try:
        lat1, lon1, lat2, lon2 = map(float, (lat1, lon1, lat2, lon2))
    except (TypeError, ValueError):
        return None
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                           CLIENT SIDE                                    ║
# ╚══════════════════════════════════════════════════════════════════════════╝

@extend_schema(
    tags=["Client — Categories"],
    summary="List deal categories",
    description=(
        "Returns the list of active deal categories shown on the home screen.\n\n"
        "**Auth required.**"
    ),
    parameters=[_LANG, _AUTH],
    responses={200: OpenApiResponse(description="Categories returned.")},
)
@api_view(["GET"])
@login_required
def list_categories(request):
    lang = _lang(request)
    qs = Category.objects.filter(is_active=True).order_by("name")
    data = PublicCategorySerializer(qs, many=True, context={"request": request}).data
    return _ok(data=data, msg_key="category_fetched", lang=lang)


@extend_schema(
    tags=["Client — Deals"],
    summary="List deals (Home/Explore)",
    description=(
        "Returns active deals with optional filters:\n"
        "- `category_id` — UUID of category\n"
        "- `search` — matches `item_name` (deal title) or `business_name`\n"
        "- `lat` & `lng` — when provided, results are sorted by distance (nearest first)\n\n"
        "**Auth required.**"
    ),
    parameters=[
        _LANG, _AUTH,
        OpenApiParameter("category_id", OpenApiTypes.UUID, OpenApiParameter.QUERY, required=False),
        OpenApiParameter("search",      OpenApiTypes.STR,  OpenApiParameter.QUERY, required=False),
        OpenApiParameter("lat",         OpenApiTypes.FLOAT, OpenApiParameter.QUERY, required=False),
        OpenApiParameter("lng",         OpenApiTypes.FLOAT, OpenApiParameter.QUERY, required=False),
        OpenApiParameter("page",        OpenApiTypes.INT,  OpenApiParameter.QUERY, required=False),
        OpenApiParameter("page_size",   OpenApiTypes.INT,  OpenApiParameter.QUERY, required=False),
    ],
    responses={200: OpenApiResponse(description="Deals returned.")},
)
@api_view(["GET"])
@login_required
def list_deals(request):
    lang = _lang(request)
    qs = Deal.objects.filter(is_active=True).select_related("category", "business", "business__business_profile")

    category_id = request.query_params.get("category_id")
    if category_id:
        qs = qs.filter(category_id=category_id)

    search = request.query_params.get("search")
    if search:
        qs = qs.filter(
            Q(title__icontains=search)
            | Q(business__business_profile__business_name__icontains=search)
        )

    featured = request.query_params.get("featured")
    if str(featured).lower() in ("1", "true", "yes"):
        qs = qs.filter(is_featured=True).order_by("-rating")

    deals = list(qs)

    lat = request.query_params.get("lat")
    lng = request.query_params.get("lng")
    if lat and lng:
        try:
            lat = float(lat); lng = float(lng)

            def _dist(d):
                bp = getattr(d.business, "business_profile", None)
                if not bp or bp.latitude is None or bp.longitude is None:
                    return float("inf")
                km = _haversine_km(lat, lng, bp.latitude, bp.longitude)
                return km if km is not None else float("inf")

            deals.sort(key=_dist)
        except ValueError:
            pass

    # Simple pagination
    try:
        page = max(1, int(request.query_params.get("page", 1)))
        page_size = max(1, min(100, int(request.query_params.get("page_size", 20))))
    except ValueError:
        page, page_size = 1, 20
    total = len(deals)
    start, end = (page - 1) * page_size, (page - 1) * page_size + page_size
    deals = deals[start:end]

    # Pre-compute favorites for the current user (avoids N+1)
    fav_ids = set()
    if getattr(request.user, "is_authenticated", False):
        fav_ids = set(
            Favorite.objects
                .filter(user=request.user, deal__in=deals)
                .values_list("deal_id", flat=True)
        )

    data = DealListSerializer(deals, many=True, context={"request": request, "favorite_ids": fav_ids}).data
    return _ok(
        data={
            "count": total,
            "page": page,
            "page_size": page_size,
            "results": data,
        },
        lang=lang,
    )


@extend_schema(
    tags=["Client — Deals"],
    summary="Featured deals section",
    description=(
        "Returns the **Featured Deals** section — a fixed home-screen section.\n\n"
        "Deals flagged as featured by an admin (`is_featured=true`) are returned first, "
        "ordered by rating (highest first).\n\n"
        "**Auth required.**"
    ),
    parameters=[
        _LANG, _AUTH,
        OpenApiParameter("category_id", OpenApiTypes.UUID, OpenApiParameter.QUERY, required=False),
        OpenApiParameter("limit", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False,
                         description="Max number of deals to return (default 20)."),
    ],
    responses={200: OpenApiResponse(
        response=DealListSerializer(many=True),
        description="Featured deals returned, highest rating first.",
    )},
)
@api_view(["GET"])
@login_required
def featured_deals(request):
    lang = _lang(request)
    qs = (
        Deal.objects.filter(is_active=True, is_featured=True)
            .select_related("category", "business", "business__business_profile")
            .order_by("-rating", "-created_at")
    )
    category_id = request.query_params.get("category_id")
    if category_id:
        qs = qs.filter(category_id=category_id)

    try:
        limit = max(1, min(100, int(request.query_params.get("limit", 20))))
    except (TypeError, ValueError):
        limit = 20
    deals = list(qs[:limit])

    fav_ids = set(
        Favorite.objects.filter(user=request.user, deal__in=deals).values_list("deal_id", flat=True)
    )
    data = DealListSerializer(deals, many=True,
                              context={"request": request, "favorite_ids": fav_ids}).data
    return _ok(data=data, lang=lang)


@extend_schema(
    tags=["Client — Deals"],
    summary="Nearby deals section",
    description=(
        "Returns the **Nearby Deals** section — a fixed home-screen section.\n\n"
        "The mobile app sends the user's `lat` and `lng`. The backend computes the distance "
        "to each deal's business and returns deals sorted by nearest first, each annotated "
        "with `distance_km`.\n\n"
        "Pass `km` to only return deals within that radius (e.g. `km=10` → within 10 km). "
        "Deals whose business has no coordinates are excluded.\n\n"
        "**Auth required.**"
    ),
    parameters=[
        _LANG, _AUTH,
        OpenApiParameter("lat", OpenApiTypes.FLOAT, OpenApiParameter.QUERY, required=True,
                         description="User latitude."),
        OpenApiParameter("lng", OpenApiTypes.FLOAT, OpenApiParameter.QUERY, required=True,
                         description="User longitude."),
        OpenApiParameter("km", OpenApiTypes.FLOAT, OpenApiParameter.QUERY, required=False,
                         description="Radius filter in kilometres. Only deals within this distance are returned."),
        OpenApiParameter("category_id", OpenApiTypes.UUID, OpenApiParameter.QUERY, required=False),
        OpenApiParameter("limit", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False,
                         description="Max number of deals to return (default 50)."),
    ],
    responses={
        200: OpenApiResponse(response=DealListSerializer(many=True),
                             description="Nearby deals returned, nearest first."),
        400: OpenApiResponse(description="lat and lng are required and must be valid numbers."),
    },
)
@api_view(["GET"])
@login_required
def nearby_deals(request):
    lang = _lang(request)
    try:
        lat = float(request.query_params.get("lat"))
        lng = float(request.query_params.get("lng"))
    except (TypeError, ValueError):
        return _err(message="lat and lng query parameters are required and must be numbers.",
                    lang=lang, http_status=status.HTTP_400_BAD_REQUEST)

    radius_km = None
    raw_km = request.query_params.get("km")
    if raw_km not in (None, ""):
        try:
            radius_km = float(raw_km)
        except ValueError:
            return _err(message="km must be a number.", lang=lang,
                        http_status=status.HTTP_400_BAD_REQUEST)

    qs = Deal.objects.filter(is_active=True).select_related(
        "category", "business", "business__business_profile")
    category_id = request.query_params.get("category_id")
    if category_id:
        qs = qs.filter(category_id=category_id)

    # Compute distance for every deal that has coordinates.
    distances = {}
    candidates = []
    for d in qs:
        bp = getattr(d.business, "business_profile", None)
        if not bp or bp.latitude is None or bp.longitude is None:
            continue
        km = _haversine_km(lat, lng, bp.latitude, bp.longitude)
        if km is None:
            continue
        if radius_km is not None and km > radius_km:
            continue
        distances[d.id] = km
        candidates.append(d)

    candidates.sort(key=lambda d: distances[d.id])

    try:
        limit = max(1, min(200, int(request.query_params.get("limit", 50))))
    except (TypeError, ValueError):
        limit = 50
    candidates = candidates[:limit]

    fav_ids = set(
        Favorite.objects.filter(user=request.user, deal__in=candidates).values_list("deal_id", flat=True)
    )
    data = DealListSerializer(
        candidates, many=True,
        context={"request": request, "favorite_ids": fav_ids, "distances": distances},
    ).data
    return _ok(data={"radius_km": radius_km, "count": len(data), "results": data}, lang=lang)


@extend_schema(
    tags=["Client — Deals"],
    summary="Retrieve a single deal",
    description="Fetch full details of one deal by UUID.\n\n**Auth required.**",
    parameters=[_LANG, _AUTH, OpenApiParameter("deal_id", OpenApiTypes.UUID, OpenApiParameter.PATH)],
    responses={200: OpenApiResponse(description="Deal returned."), 404: OpenApiResponse(description="Not found.")},
)
@api_view(["GET"])
@login_required
def deal_detail(request, deal_id):
    lang = _lang(request)
    try:
        deal = Deal.objects.select_related("category", "business", "business__business_profile").get(id=deal_id, is_active=True)
    except Deal.DoesNotExist:
        return _err("not_found", lang, status.HTTP_404_NOT_FOUND)
    data = DealListSerializer(deal, context={"request": request}).data
    return _ok(data=data, lang=lang)


@extend_schema(
    tags=["Client — Favorites"],
    summary="Toggle favorite on a deal",
    description="Adds the deal to favorites if not present, removes it if it is.\n\n**Auth required.**",
    request=ToggleFavoriteSerializer,
    parameters=[_LANG, _AUTH],
    responses={
        200: OpenApiResponse(description="Toggle result returned."),
        404: OpenApiResponse(description="Deal not found."),
    },
    examples=[OpenApiExample("Toggle", request_only=True, value={"deal_id": "f2d4-..."})],
)
@api_view(["POST"])
@login_required
def toggle_favorite(request):
    lang = _lang(request)
    serializer = ToggleFavoriteSerializer(data=request.data)
    if not serializer.is_valid():
        return _err("validation_error", lang, errors=serializer.errors)

    deal_id = serializer.validated_data["deal_id"]
    try:
        deal = Deal.objects.get(id=deal_id)
    except Deal.DoesNotExist:
        return _err("not_found", lang, status.HTTP_404_NOT_FOUND)

    fav = Favorite.objects.filter(user=request.user, deal=deal).first()
    if fav:
        fav.delete()
        return _ok(data={"deal_id": str(deal.id), "is_favorite": False}, lang=lang)

    Favorite.objects.create(user=request.user, deal=deal)
    return _ok(data={"deal_id": str(deal.id), "is_favorite": True}, lang=lang)


@extend_schema(
    tags=["Client — Favorites"],
    summary="List the current user's favorite deals",
    description="Returns all deals the authenticated user has favorited.\n\n**Auth required.**",
    parameters=[_LANG, _AUTH],
    responses={200: OpenApiResponse(description="Favorites returned.")},
)
@api_view(["GET"])
@login_required
def list_favorites(request):
    lang = _lang(request)
    fav_ids = list(
        Favorite.objects.filter(user=request.user).values_list("deal_id", flat=True)
    )
    deals = (
        Deal.objects
            .filter(id__in=fav_ids, is_active=True)
            .select_related("category", "business", "business__business_profile")
            .order_by("-created_at")
    )
    data = DealListSerializer(
        deals, many=True,
        context={"request": request, "favorite_ids": set(fav_ids)},
    ).data
    return _ok(data=data, lang=lang)


# ─── QR token generation ──────────────────────────────────────────────────────

@extend_schema(
    tags=["QR Redemption"],
    summary="Student: generate QR redemption token",
    description=(
        "Generates a one-time secure token (`qr_token`) for redeeming a deal.\n\n"
        "- Expires after **10 minutes** (600s).\n"
        "- Requires an **ACTIVE WINDEAL+ subscription**.\n\n"
        "**Auth required (client).**"
    ),
    request=GenerateCodeSerializer,
    parameters=[_LANG, _AUTH],
    responses={
        201: OpenApiResponse(description="Token issued."),
        400: OpenApiResponse(description="Validation error."),
        402: OpenApiResponse(description="Subscription required."),
        404: OpenApiResponse(description="Deal not found."),
    },
)
@api_view(["POST"])
@client_required
def generate_redemption_code(request):
    lang = _lang(request)
    serializer = GenerateCodeSerializer(data=request.data)
    if not serializer.is_valid():
        return _err("validation_error", lang, errors=serializer.errors)

    if request.user.subscription_status != "ACTIVE":
        return _err(http_status=status.HTTP_402_PAYMENT_REQUIRED,
                    message="WINDEAL+ subscription required to redeem deals.")

    deal_id = serializer.validated_data["deal_id"]
    try:
        deal = Deal.objects.get(id=deal_id, is_active=True)
    except Deal.DoesNotExist:
        return _err("not_found", lang, status.HTTP_404_NOT_FOUND)

    token = RedemptionToken.objects.create(
        user=request.user,
        deal=deal,
        token=RedemptionToken.make_token(),
        expires_at=timezone.now() + dt.timedelta(seconds=600),
    )
    return _ok(
        data={"qr_token": token.token, "expires_in": 600, "deal_id": str(deal.id)},
        http_status=status.HTTP_201_CREATED,
        lang=lang,
    )


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                          BUSINESS SIDE                                   ║
# ╚══════════════════════════════════════════════════════════════════════════╝

# ─── Offers CRUD ──────────────────────────────────────────────────────────────

@extend_schema(
    tags=["Business — Offers"],
    summary="List my offers",
    description="Returns all offers owned by the authenticated business.\n\n**Auth required (business).**",
    parameters=[_LANG, _AUTH],
    responses={200: OpenApiResponse(description="Offers returned.")},
)
@api_view(["GET"])
@business_required
def list_offers(request):
    lang = _lang(request)
    qs = Deal.objects.filter(business=request.user).select_related("category").order_by("-created_at")
    return _ok(
        data=BusinessOfferSerializer(qs, many=True, context={"request": request}).data,
        lang=lang,
    )


@extend_schema(
    tags=["Business — Offers"],
    summary="Create a new offer",
    description=(
        "Creates a new offer owned by the authenticated business.\n\n"
        "**Request format:** `multipart/form-data` (for image upload).\n\n"
        "**Auth required (business).**"
    ),
    request={"multipart/form-data": BusinessOfferSerializer},
    parameters=[_LANG, _AUTH],
    responses={201: OpenApiResponse(description="Offer created."), 400: OpenApiResponse(description="Validation error.")},
)
@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@business_required
def create_offer(request):
    lang = _lang(request)
    serializer = BusinessOfferSerializer(data=request.data, context={"request": request})
    if not serializer.is_valid():
        return _err("validation_error", lang, errors=serializer.errors)

    # Resolve category_id (sent as multipart 'category_id' or 'category' UUID)
    category = None
    cat_id = request.data.get("category_id") or request.data.get("category")
    if cat_id:
        try:
            category = Category.objects.get(id=cat_id, is_active=True)
        except Category.DoesNotExist:
            category = None

    # DRF's BooleanField treats a missing field in multipart/form-data as False
    # (HTML checkbox semantics), which would silently create inactive offers.
    # Honour the model default (active) when the client did not send is_active.
    if "is_active" not in request.data:
        serializer.validated_data["is_active"] = True

    deal = serializer.save(business=request.user, category=category)
    return _ok(
        data=BusinessOfferSerializer(deal, context={"request": request}).data,
        http_status=status.HTTP_201_CREATED,
        lang=lang,
    )


@extend_schema(
    tags=["Business — Offers"],
    summary="Retrieve / Update / Delete one of my offers",
    description=(
        "**GET** · **PATCH** · **DELETE** an offer owned by the authenticated business.\n\n"
        "PATCH accepts multipart for image replacement.\n\n"
        "**Auth required (business).**"
    ),
    request={"multipart/form-data": BusinessOfferSerializer},
    parameters=[_LANG, _AUTH, OpenApiParameter("offer_id", OpenApiTypes.UUID, OpenApiParameter.PATH)],
    responses={
        200: OpenApiResponse(description="OK."),
        404: OpenApiResponse(description="Not found."),
        403: OpenApiResponse(description="Not your offer."),
    },
)
@api_view(["GET", "PATCH", "DELETE"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@business_required
def offer_detail(request, offer_id):
    lang = _lang(request)
    try:
        deal = Deal.objects.select_related("category").get(id=offer_id)
    except Deal.DoesNotExist:
        return _err("not_found", lang, status.HTTP_404_NOT_FOUND)
    if deal.business_id != request.user.id:
        return _err("unauthorized", lang, status.HTTP_403_FORBIDDEN)

    if request.method == "GET":
        return _ok(data=BusinessOfferSerializer(deal, context={"request": request}).data, lang=lang)

    if request.method == "PATCH":
        serializer = BusinessOfferSerializer(deal, data=request.data, partial=True, context={"request": request})
        if not serializer.is_valid():
            return _err("validation_error", lang, errors=serializer.errors)

        cat_id = request.data.get("category_id") or request.data.get("category")
        if cat_id:
            try:
                deal.category = Category.objects.get(id=cat_id, is_active=True)
            except Category.DoesNotExist:
                pass
        serializer.save()
        return _ok(data=BusinessOfferSerializer(deal, context={"request": request}).data, lang=lang)

    deal.delete()
    return _ok(message="Offer deleted.", lang=lang)


@extend_schema(
    tags=["Business — Offers"],
    summary="Toggle an offer's active status",
    description="Flips `is_active` on an offer.\n\n**Auth required (business).**",
    request=None,
    parameters=[_LANG, _AUTH, OpenApiParameter("offer_id", OpenApiTypes.UUID, OpenApiParameter.PATH)],
    responses={200: OpenApiResponse(description="Toggled."), 404: OpenApiResponse(description="Not found.")},
)
@api_view(["PATCH"])
@business_required
def toggle_offer(request, offer_id):
    lang = _lang(request)
    try:
        deal = Deal.objects.get(id=offer_id)
    except Deal.DoesNotExist:
        return _err("not_found", lang, status.HTTP_404_NOT_FOUND)
    if deal.business_id != request.user.id:
        return _err("unauthorized", lang, status.HTTP_403_FORBIDDEN)

    deal.is_active = not deal.is_active
    deal.save(update_fields=["is_active"])
    return _ok(data={"id": str(deal.id), "is_active": deal.is_active}, lang=lang)


# ─── Business dashboard ───────────────────────────────────────────────────────

@extend_schema(
    tags=["Business — Dashboard"],
    summary="Dashboard metrics",
    description=(
        "Returns key metrics for the business dashboard:\n"
        "- `redemptions_today` — count of redemptions today\n"
        "- `redemptions_trend` — string comparison vs yesterday (e.g. `+12%`)\n"
        "- `active_offers_count` — number of active offers\n"
        "- `recent_activities` — last 10 redemptions\n\n"
        "**Auth required (business).**"
    ),
    parameters=[_LANG, _AUTH],
    responses={200: OpenApiResponse(description="Dashboard returned.")},
)
@api_view(["GET"])
@business_required
def business_dashboard(request):
    lang = _lang(request)
    today = timezone.now().date()
    yesterday = today - dt.timedelta(days=1)

    qs = Redemption.objects.filter(business=request.user)
    today_count = qs.filter(created_at__date=today).count()
    yest_count  = qs.filter(created_at__date=yesterday).count()

    if yest_count == 0:
        trend = "+100%" if today_count > 0 else "0%"
    else:
        diff = today_count - yest_count
        pct  = round((diff / yest_count) * 100)
        trend = f"{'+' if pct >= 0 else ''}{pct}%"

    active_offers = Deal.objects.filter(business=request.user, is_active=True).count()

    recent = (
        qs.select_related("student", "student__client_profile", "deal")
          .order_by("-created_at")[:10]
    )
    recent_data = []
    for r in recent:
        student_name = (
            r.student.client_profile.full_name
            if hasattr(r.student, "client_profile") and r.student.client_profile.full_name
            else r.student.phone
        )
        recent_data.append({
            "id":           str(r.id),
            "student_name": student_name,
            "offer_name":   r.deal.title,
            "timestamp":    r.created_at,
            "status":       r.status,
        })

    return _ok(
        data={
            "redemptions_today":   today_count,
            "redemptions_trend":   trend,
            "active_offers_count": active_offers,
            "recent_activities":   recent_data,
        },
        lang=lang,
    )


@extend_schema(
    tags=["Business — Dashboard"],
    summary="Business analytics",
    description=(
        "Analytics for the business dashboard, segmented by `period`:\n"
        "- `7d` — last 7 days (default)\n- `30d` — last 30 days\n- `all` — full history\n\n"
        "**Auth required (business).**"
    ),
    parameters=[
        _LANG, _AUTH,
        OpenApiParameter("period", OpenApiTypes.STR, OpenApiParameter.QUERY,
                         description="7d | 30d | all", required=False),
    ],
    responses={200: OpenApiResponse(description="Analytics returned.")},
)
@api_view(["GET"])
@business_required
def business_analytics(request):
    lang = _lang(request)
    period = request.query_params.get("period", "7d").lower()

    qs = Redemption.objects.filter(business=request.user)
    now = timezone.now()
    if period == "7d":
        qs = qs.filter(created_at__gte=now - dt.timedelta(days=7))
    elif period == "30d":
        qs = qs.filter(created_at__gte=now - dt.timedelta(days=30))
    # 'all' = no extra filter

    chart_data = list(
        qs.annotate(date=TruncDate("created_at"))
          .values("date")
          .annotate(count=Count("id"))
          .order_by("date")
    )
    chart_data = [{"date": str(row["date"]), "count": row["count"]} for row in chart_data]

    top = (
        qs.values("deal__id", "deal__title")
          .annotate(count=Count("id"))
          .order_by("-count")[:5]
    )
    top_data = [
        {"offer_id": str(row["deal__id"]), "offer_name": row["deal__title"], "count": row["count"], "trend": ""}
        for row in top
    ]

    return _ok(
        data={"chart_data": chart_data, "top_performing_offers": top_data, "period": period},
        lang=lang,
    )


# ─── QR scan & redeem ─────────────────────────────────────────────────────────

@extend_schema(
    tags=["QR Redemption"],
    summary="Business: scan & redeem QR token",
    description=(
        "Validates a QR token sent by the student. On success, marks the token used and creates "
        "a `Redemption` audit entry.\n\n"
        "**Validation:**\n"
        "- token must exist, not be used, and not be expired\n"
        "- the deal must belong to the authenticated business\n"
        "- the student must hold an active WINDEAL+ subscription\n\n"
        "**Auth required (business).**"
    ),
    request=RedeemSerializer,
    parameters=[_LANG, _AUTH],
    responses={
        200: OpenApiResponse(description="Token redeemed."),
        400: OpenApiResponse(description="Token invalid / expired / used."),
        402: OpenApiResponse(description="Student has no active subscription."),
        403: OpenApiResponse(description="Deal does not belong to this business."),
    },
)
@api_view(["POST"])
@business_required
def redeem_qr(request):
    """
    REST redemption. Kept for compatibility; the mobile app should prefer the
    WebSocket ``redeem`` action (same logic) so the scan screen updates live
    without an HTTP round-trip. Both paths share ``services.redeem_token``.
    """
    lang = _lang(request)
    serializer = RedeemSerializer(data=request.data)
    if not serializer.is_valid():
        return _err("validation_error", lang, errors=serializer.errors)

    result = redeem_token(request.user, serializer.validated_data["qr_token"])
    if not result["ok"]:
        return _err(message=result["message"], lang=lang, http_status=result["http_status"])
    return _ok(data=result["data"], message=result["message"], lang=lang)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                     SUBSCRIPTION (CLIENT/BUSINESS)                       ║
# ╚══════════════════════════════════════════════════════════════════════════╝

@extend_schema(
    tags=["Subscription"],
    summary="List public subscription plans",
    description="Returns active subscription plans available for purchase.\n\n**Auth required.**",
    parameters=[_LANG, _AUTH,
                OpenApiParameter("role", OpenApiTypes.STR, OpenApiParameter.QUERY,
                                 description="Filter by target_role: client / business", required=False)],
    responses={200: OpenApiResponse(description="Plans returned.")},
)
@api_view(["GET"])
@login_required
def list_subscription_plans(request):
    lang = _lang(request)
    qs = SubscriptionPlan.objects.filter(is_active=True).order_by("price")
    role = request.query_params.get("role") or (request.user.role if request.user.role in ("client", "business") else None)
    if role:
        qs = qs.filter(Q(target_role=role) | Q(target_role="both"))
    return _ok(data=SubscriptionPlanPublicSerializer(qs, many=True, context={"request": request}).data, lang=lang)


@extend_schema(
    tags=["Subscription"],
    summary="Submit payment receipt for subscription upgrade",
    description=(
        "Uploads a payment receipt and moves the user's subscription to `PENDING` until admin approval.\n\n"
        "**Request format:** `multipart/form-data`.\n\n"
        "**Auth required (client/business).**"
    ),
    request={"multipart/form-data": SubscriptionUpgradeSerializer},
    parameters=[_LANG, _AUTH],
    responses={
        201: OpenApiResponse(description="Receipt uploaded."),
        400: OpenApiResponse(description="Validation error."),
    },
)
@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
@login_required
def subscription_upgrade(request):
    lang = _lang(request)
    user = request.user
    if user.role == "admin":
        return _err("unauthorized", lang, status.HTTP_403_FORBIDDEN)

    serializer = SubscriptionUpgradeSerializer(data=request.data, context={"request": request})
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
        user=user, plan=plan, amount=plan.price,
        receipt=data["receipt_image"], status="PENDING",
        payment_method=data.get("payment_method", ""),
        reference_number=data.get("reference_number", ""),
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
    # ── Real-time: payment now pending review ─────────────────────────────────
    send_realtime(user, "payment", payment_data)
    notify(
        user,
        title="Payment received",
        body=f"Your payment for '{plan.name}' is under review. Verification in progress (12-24h).",
        ntype="payment",
        extra={"payment": payment_data},
    )

    return _ok(
        data=payment_data,
        message="Verification in progress (12-24h).",
        http_status=status.HTTP_201_CREATED,
        lang=lang,
    )


@extend_schema(
    tags=["Subscription"],
    summary="Payment history",
    description=(
        "Returns the authenticated user's subscription payment history, newest first.\n\n"
        "Each item contains:\n"
        "- `id` — UUID of the payment\n"
        "- `transaction_date` — ISO-8601 submission timestamp\n"
        "- `amount` — paid amount\n"
        "- `payment_method` — how the user paid (may be empty)\n"
        "- `subscription_plan` — plan name\n"
        "- `reference_number` — user-supplied reference (may be empty)\n"
        "- `status` — `PENDING` · `APPROVED` · `REJECTED`\n\n"
        "**Auth required (client/business).**"
    ),
    parameters=[_LANG, _AUTH],
    responses={200: OpenApiResponse(
        response=inline_serializer(
            name="PaymentHistoryResponse",
            fields={
                "success": drf_serializers.BooleanField(default=True),
                "data": PaymentHistorySerializer(many=True),
            },
        ),
        description="Payment history returned.",
        examples=[
            OpenApiExample("History", value={
                "success": True,
                "data": [
                    {
                        "id": "3f1c2d4e-5a6b-4c7d-8e9f-0a1b2c3d4e5f",
                        "transaction_date": "2026-06-07T10:15:30Z",
                        "amount": "550.00",
                        "payment_method": "BaridiMob",
                        "subscription_plan": "Monthly",
                        "reference_number": "TX-99812",
                        "status": "APPROVED",
                    },
                ],
            }),
        ],
    )},
)
@api_view(["GET"])
@login_required
def payment_history(request):
    lang = _lang(request)
    qs = (
        Payment.objects.filter(user=request.user)
            .select_related("plan")
            .order_by("-created_at")
    )
    return _ok(data=PaymentHistorySerializer(qs, many=True).data, lang=lang)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                            NOTIFICATIONS                                 ║
# ╚══════════════════════════════════════════════════════════════════════════╝

@extend_schema(
    tags=["Notifications"],
    summary="List current user's notifications",
    description=(
        "Returns notifications for the authenticated user, newest first.\n\n"
        "Each notification object contains:\n"
        "- `id` — UUID of the notification\n"
        "- `title` — short headline\n"
        "- `body` — full message text (may be empty)\n"
        "- `type` — one of `system`, `payment`, `subscription`, `deal`, `redemption`\n"
        "- `is_read` — whether the user has read it\n"
        "- `created_at` — ISO-8601 timestamp\n\n"
        "**Auth required.**"
    ),
    parameters=[_LANG, _AUTH],
    responses={
        200: OpenApiResponse(
            response=inline_serializer(
                name="NotificationListResponse",
                fields={
                    "success": drf_serializers.BooleanField(default=True),
                    "data": NotificationSerializer(many=True),
                },
            ),
            description="Notifications returned.",
            examples=[
                OpenApiExample("Notifications list", value={
                    "success": True,
                    "data": [
                        {
                            "id": "9b2f1c6e-3a4d-4c8e-9f1a-2b3c4d5e6f70",
                            "title": "Payment approved",
                            "body": "Your WINDEAL+ subscription is now active until 2026-07-07.",
                            "type": "payment",
                            "is_read": False,
                            "created_at": "2026-06-07T10:15:30Z",
                        },
                        {
                            "id": "1a2b3c4d-5e6f-4071-8a9b-0c1d2e3f4a5b",
                            "title": "Welcome to WINDEAL",
                            "body": "Browse local deals and redeem them with QR codes.",
                            "type": "system",
                            "is_read": True,
                            "created_at": "2026-06-06T08:00:00Z",
                        },
                    ],
                }),
            ],
        ),
    },
)
@api_view(["GET"])
@login_required
def list_notifications(request):
    lang = _lang(request)
    qs = Notification.objects.filter(user=request.user)
    return _ok(data=NotificationSerializer(qs, many=True).data, lang=lang)


@extend_schema(
    tags=["Notifications"],
    summary="Mark a notification as read",
    description=(
        "Sets `is_read=true` on one notification owned by the authenticated user "
        "and returns the updated notification object.\n\n"
        "The returned object contains: `id`, `title`, `body`, `type`, `is_read`, `created_at`.\n\n"
        "**Auth required.**"
    ),
    request=None,
    parameters=[_LANG, _AUTH, OpenApiParameter("notification_id", OpenApiTypes.UUID, OpenApiParameter.PATH)],
    responses={
        200: OpenApiResponse(
            response=inline_serializer(
                name="NotificationReadResponse",
                fields={
                    "success": drf_serializers.BooleanField(default=True),
                    "data": NotificationSerializer(),
                },
            ),
            description="Updated.",
            examples=[
                OpenApiExample("Marked read", value={
                    "success": True,
                    "data": {
                        "id": "9b2f1c6e-3a4d-4c8e-9f1a-2b3c4d5e6f70",
                        "title": "Payment approved",
                        "body": "Your WINDEAL+ subscription is now active until 2026-07-07.",
                        "type": "payment",
                        "is_read": True,
                        "created_at": "2026-06-07T10:15:30Z",
                    },
                }),
            ],
        ),
        404: OpenApiResponse(description="Not found."),
    },
)
@api_view(["PATCH"])
@login_required
def mark_notification_read(request, notification_id):
    lang = _lang(request)
    try:
        n = Notification.objects.get(id=notification_id, user=request.user)
    except Notification.DoesNotExist:
        return _err("not_found", lang, status.HTTP_404_NOT_FOUND)
    n.is_read = True
    n.save(update_fields=["is_read"])
    return _ok(data=NotificationSerializer(n).data, lang=lang)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                       USER PROFILE PASSTHROUGH                           ║
# ╚══════════════════════════════════════════════════════════════════════════╝

@extend_schema(
    tags=["User — Account"],
    summary="Delete current user account",
    description=(
        "Permanently deletes the authenticated user's account and all owned data.\n\n"
        "**Auth required.**"
    ),
    parameters=[_LANG, _AUTH],
    responses={
        200: OpenApiResponse(description="Account deleted."),
        401: OpenApiResponse(description="Not authenticated."),
    },
)
@api_view(["DELETE"])
@login_required
def delete_account(request):
    lang = _lang(request)
    user = request.user
    user.delete()
    return _ok(message="Account deleted successfully.", lang=lang)
