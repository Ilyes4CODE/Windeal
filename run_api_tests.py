"""
Standalone end-to-end API test runner for the WINDEAL backend.

Runs against an ISOLATED test database (created and destroyed automatically) so
the real db.sqlite3 is never touched. Exercises every endpoint across
auth_app, admin_app and deals_app and prints a pass/fail report.

Run:  venv\Scripts\python.exe run_api_tests.py
"""
import os
import sys
import tempfile

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Windeal.settings")

import django
django.setup()

from django.conf import settings
# Send any uploaded media to a throwaway dir.
settings.MEDIA_ROOT = tempfile.mkdtemp(prefix="windeal_test_media_")

from django.test.runner import DiscoverRunner
from django.test.utils import setup_test_environment, teardown_test_environment
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from auth_app.models import User
from deals_app.models import Notification

# 1x1 PNG
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05"
    b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    mark = "PASS" if cond else "FAIL"
    line = f"[{mark}] {name}"
    if detail and not cond:
        line += f"  -> {detail}"
    print(line)


def body(resp):
    try:
        return resp.json()
    except Exception:
        return {}


def run():
    c = APIClient()

    # ── Seed first admin directly (register_admin itself needs an admin) ──────
    admin = User.objects.create_user(
        phone="+213100000000", role="admin", password="adminPass123",
        is_verified=True, is_active=True, is_staff=True, email="admin@windeal.app",
    )

    # ── AUTH: admin login ────────────────────────────────────────────────────
    r = c.post("/api/auth/login/admin/",
               {"identifier": "+213100000000", "password": "adminPass123"}, format="json")
    admin_token = body(r).get("data", {}).get("tokens", {}).get("access")
    check("POST /api/auth/login/admin/", r.status_code == 200 and admin_token, f"{r.status_code} {body(r)}")
    AUTH_ADMIN = {"HTTP_AUTHORIZATION": f"Bearer {admin_token}"}

    # ── AUTH: register admin (admin-only) ───────────────────────────────────
    r = c.post("/api/auth/register/admin/",
               {"phone": "+213100000001", "password": "secret9", "first_name": "Sec"},
               format="json", **AUTH_ADMIN)
    check("POST /api/auth/register/admin/", r.status_code == 201, f"{r.status_code} {body(r)}")

    # ── ADMIN: categories ────────────────────────────────────────────────────
    r = c.post("/api/admin/categories/", {"name": "Café", "is_active": True}, format="json", **AUTH_ADMIN)
    cat_id = body(r).get("data", {}).get("id")
    check("POST /api/admin/categories/", r.status_code == 201 and cat_id, f"{r.status_code} {body(r)}")

    r = c.get("/api/admin/categories/", **AUTH_ADMIN)
    check("GET /api/admin/categories/", r.status_code == 200, f"{r.status_code}")

    r = c.get(f"/api/admin/categories/{cat_id}/", **AUTH_ADMIN)
    check("GET /api/admin/categories/{id}/", r.status_code == 200, f"{r.status_code}")

    r = c.patch(f"/api/admin/categories/{cat_id}/", {"name": "Restaurant"}, format="json", **AUTH_ADMIN)
    check("PATCH /api/admin/categories/{id}/", r.status_code == 200, f"{r.status_code} {body(r)}")

    # ── ADMIN: plans ─────────────────────────────────────────────────────────
    r = c.post("/api/admin/plans/", {
        "name": "Monthly", "price": "500.00", "duration_type": "monthly",
        "duration_days": 30, "target_role": "both", "is_active": True,
    }, format="json", **AUTH_ADMIN)
    plan_id = body(r).get("data", {}).get("id")
    check("POST /api/admin/plans/", r.status_code == 201 and plan_id, f"{r.status_code} {body(r)}")

    r = c.get("/api/admin/plans/", **AUTH_ADMIN)
    check("GET /api/admin/plans/", r.status_code == 200, f"{r.status_code}")
    r = c.get(f"/api/admin/plans/{plan_id}/", **AUTH_ADMIN)
    check("GET /api/admin/plans/{id}/", r.status_code == 200, f"{r.status_code}")
    r = c.patch(f"/api/admin/plans/{plan_id}/", {"price": "550.00"}, format="json", **AUTH_ADMIN)
    check("PATCH /api/admin/plans/{id}/", r.status_code == 200, f"{r.status_code} {body(r)}")

    # ── AUTH: register client ────────────────────────────────────────────────
    r = c.post("/api/auth/register/client/", {
        "phone": "+213555123456", "full_name": "Yacine Boudiaf",
        "email": "yacine@example.com", "wilaya": "Alger",
    }, format="json")
    cdata = body(r).get("data", {})
    client_token = cdata.get("tokens", {}).get("access")
    client_id = cdata.get("id")
    check("POST /api/auth/register/client/", r.status_code == 201 and client_token, f"{r.status_code} {body(r)}")
    AUTH_CLIENT = {"HTTP_AUTHORIZATION": f"Bearer {client_token}"}

    # ── AUTH: register business ──────────────────────────────────────────────
    r = c.post("/api/auth/register/business/", {
        "phone": "+213555000111", "business_name": "Café El Djazair",
        "city": "Alger", "latitude": "36.737232", "longitude": "3.086472",
        "category_id": cat_id,
    }, format="json")
    bdata = body(r).get("data", {})
    biz_token = bdata.get("tokens", {}).get("access")
    biz_id = bdata.get("id")
    check("POST /api/auth/register/business/", r.status_code == 201 and biz_token, f"{r.status_code} {body(r)}")
    AUTH_BIZ = {"HTTP_AUTHORIZATION": f"Bearer {biz_token}"}

    # ── AUTH: passwordless check + login ─────────────────────────────────────
    r = c.post("/api/auth/check/", {"phone": "+213555123456"}, format="json")
    check("POST /api/auth/check/", r.status_code == 200 and body(r).get("data", {}).get("exists"), f"{r.status_code} {body(r)}")

    r = c.post("/api/auth/login/", {"phone": "+213555123456"}, format="json")
    check("POST /api/auth/login/", r.status_code == 200, f"{r.status_code} {body(r)}")

    # ── AUTH: profile ────────────────────────────────────────────────────────
    r = c.get("/api/auth/profile/", **AUTH_CLIENT)
    check("GET /api/auth/profile/", r.status_code == 200, f"{r.status_code}")
    r = c.patch("/api/auth/profile/update/", {"full_name": "Yacine B."}, format="json", **AUTH_CLIENT)
    check("PATCH /api/auth/profile/update/", r.status_code == 200, f"{r.status_code} {body(r)}")
    r = c.get("/api/user/profile/", **AUTH_CLIENT)
    check("GET /api/user/profile/ (alias)", r.status_code == 200, f"{r.status_code}")
    r = c.patch("/api/user/profile/update/", {"city": "Oran"}, format="json", **AUTH_CLIENT)
    check("PATCH /api/user/profile/update/ (alias)", r.status_code == 200, f"{r.status_code}")

    # ── BUSINESS: offers ─────────────────────────────────────────────────────
    img = SimpleUploadedFile("deal.png", PNG, content_type="image/png")
    r = c.post("/api/business/offers/create/", {
        "title": "50% off coffee", "description": "Limited time",
        "category": cat_id, "discount_value": "50%",
        "old_price": "200.00", "new_price": "100.00", "image": img,
    }, format="multipart", **AUTH_BIZ)
    offer_id = body(r).get("data", {}).get("id")
    check("POST /api/business/offers/create/", r.status_code == 201 and offer_id, f"{r.status_code} {body(r)}")

    r = c.get("/api/business/offers/", **AUTH_BIZ)
    check("GET /api/business/offers/", r.status_code == 200, f"{r.status_code}")
    r = c.get(f"/api/business/offers/{offer_id}/", **AUTH_BIZ)
    check("GET /api/business/offers/{id}/", r.status_code == 200, f"{r.status_code}")
    r = c.patch(f"/api/business/offers/{offer_id}/", {"description": "Updated"}, format="multipart", **AUTH_BIZ)
    check("PATCH /api/business/offers/{id}/", r.status_code == 200, f"{r.status_code} {body(r)}")
    r = c.patch(f"/api/business/offers/{offer_id}/toggle/", **AUTH_BIZ)
    check("PATCH /api/business/offers/{id}/toggle/", r.status_code == 200, f"{r.status_code}")
    # toggle back to active so client-side listing finds it
    c.patch(f"/api/business/offers/{offer_id}/toggle/", **AUTH_BIZ)

    # ── CLIENT: categories / deals / favorites ───────────────────────────────
    r = c.get("/api/categories/", **AUTH_CLIENT)
    check("GET /api/categories/", r.status_code == 200, f"{r.status_code}")
    r = c.get("/api/deals/", **AUTH_CLIENT)
    check("GET /api/deals/", r.status_code == 200, f"{r.status_code}")
    r = c.get(f"/api/deals/{offer_id}/", **AUTH_CLIENT)
    check("GET /api/deals/{id}/", r.status_code == 200, f"{r.status_code} {body(r)}")
    r = c.post("/api/deals/favorites/toggle/", {"deal_id": offer_id}, format="json", **AUTH_CLIENT)
    check("POST /api/deals/favorites/toggle/", r.status_code == 200 and body(r).get("data", {}).get("is_favorite") is True, f"{r.status_code} {body(r)}")
    r = c.get("/api/deals/favorites/", **AUTH_CLIENT)
    check("GET /api/deals/favorites/", r.status_code == 200, f"{r.status_code}")

    # ── SUBSCRIPTION: plans + upgrade (client uploads receipt) ───────────────
    r = c.get("/api/subscription/plans/", **AUTH_CLIENT)
    check("GET /api/subscription/plans/", r.status_code == 200, f"{r.status_code}")

    receipt = SimpleUploadedFile("receipt.png", PNG, content_type="image/png")
    r = c.post("/api/subscription/upgrade/", {
        "plan_id": plan_id, "receipt_image": receipt,
        "payment_method": "BaridiMob", "reference_number": "TX-99812",
    }, format="multipart", **AUTH_CLIENT)
    check("POST /api/subscription/upgrade/", r.status_code == 201, f"{r.status_code} {body(r)}")

    # also exercise the auth_app payment/upload endpoint with the business user
    receipt2 = SimpleUploadedFile("receipt2.png", PNG, content_type="image/png")
    r = c.post("/api/auth/payment/upload/", {
        "plan_id": plan_id, "amount": "550.00", "receipt": receipt2,
    }, format="multipart", **AUTH_BIZ)
    check("POST /api/auth/payment/upload/", r.status_code == 201, f"{r.status_code} {body(r)}")

    r = c.get("/api/auth/subscription/status/", **AUTH_CLIENT)
    check("GET /api/auth/subscription/status/", r.status_code == 200, f"{r.status_code}")

    # ── ADMIN: payments review ───────────────────────────────────────────────
    r = c.get("/api/admin/payments/pending/", **AUTH_ADMIN)
    pending = body(r).get("data", [])
    check("GET /api/admin/payments/pending/", r.status_code == 200 and len(pending) >= 1, f"{r.status_code}")
    r = c.get("/api/admin/payments/all/", **AUTH_ADMIN)
    check("GET /api/admin/payments/all/", r.status_code == 200, f"{r.status_code}")

    # approve the client's payment so they become ACTIVE
    client_payment = next((p for p in pending if p["user"]["id"] == client_id), pending[0])
    r = c.post(f"/api/admin/payments/{client_payment['id']}/review/",
               {"action": "approve"}, format="json", **AUTH_ADMIN)
    check("POST /api/admin/payments/{id}/review/ (approve)", r.status_code == 200, f"{r.status_code} {body(r)}")

    # ── QR redemption flow (needs ACTIVE client) ─────────────────────────────
    r = c.post("/api/deals/generate-code/", {"deal_id": offer_id}, format="json", **AUTH_CLIENT)
    qr_token = body(r).get("data", {}).get("qr_token")
    check("POST /api/deals/generate-code/", r.status_code == 201 and qr_token, f"{r.status_code} {body(r)}")

    r = c.post("/api/business/redeem/", {"qr_token": qr_token}, format="json", **AUTH_BIZ)
    check("POST /api/business/redeem/", r.status_code == 200, f"{r.status_code} {body(r)}")

    # ── BUSINESS: dashboard + analytics ──────────────────────────────────────
    r = c.get("/api/business/dashboard/", **AUTH_BIZ)
    check("GET /api/business/dashboard/", r.status_code == 200, f"{r.status_code}")
    r = c.get("/api/business/analytics/?period=7d", **AUTH_BIZ)
    check("GET /api/business/analytics/", r.status_code == 200, f"{r.status_code}")

    # ── ADMIN: deals featuring control ───────────────────────────────────────
    r = c.get("/api/admin/deals/", **AUTH_ADMIN)
    check("GET /api/admin/deals/", r.status_code == 200 and len(body(r).get("data", [])) >= 1, f"{r.status_code}")
    r = c.patch(f"/api/admin/deals/{offer_id}/feature/", {"is_featured": True}, format="json", **AUTH_ADMIN)
    check("PATCH /api/admin/deals/{id}/feature/ (set)", r.status_code == 200 and body(r).get("data", {}).get("is_featured") is True, f"{r.status_code} {body(r)}")
    r = c.get("/api/admin/deals/?featured=true", **AUTH_ADMIN)
    check("GET /api/admin/deals/?featured=true", r.status_code == 200 and len(body(r).get("data", [])) >= 1, f"{r.status_code}")

    # ── CLIENT: featured section ─────────────────────────────────────────────
    r = c.get("/api/deals/featured/", **AUTH_CLIENT)
    fdata = body(r).get("data", [])
    featured_ok = any(d["id"] == offer_id and d.get("is_featured") for d in fdata)
    check("GET /api/deals/featured/ (contains featured deal)", r.status_code == 200 and featured_ok, f"{r.status_code} {fdata[:1]}")

    # ── CLIENT: nearby section (business is at 36.737232, 3.086472) ───────────
    r = c.get("/api/deals/nearby/?lat=36.737232&lng=3.086472&km=10", **AUTH_CLIENT)
    ndata = body(r).get("data", {}).get("results", [])
    near_ok = any(d["id"] == offer_id for d in ndata) and ndata and ndata[0].get("distance_km") is not None
    check("GET /api/deals/nearby/?km=10 (finds nearby + distance_km)", r.status_code == 200 and near_ok, f"{r.status_code} {ndata[:1]}")
    # far point with tiny radius -> excluded
    r = c.get("/api/deals/nearby/?lat=0&lng=0&km=1", **AUTH_CLIENT)
    far_excluded = all(d["id"] != offer_id for d in body(r).get("data", {}).get("results", []))
    check("GET /api/deals/nearby/ km radius excludes far deals", r.status_code == 200 and far_excluded, f"{r.status_code}")
    # missing lat/lng -> 400
    r = c.get("/api/deals/nearby/", **AUTH_CLIENT)
    check("GET /api/deals/nearby/ without lat/lng -> 400", r.status_code == 400, f"{r.status_code}")

    # ── SUBSCRIPTION: payment history ────────────────────────────────────────
    r = c.get("/api/subscription/payment-history/", **AUTH_CLIENT)
    hist = body(r).get("data", [])
    hist_fields_ok = hist and set(["id", "transaction_date", "amount", "payment_method", "subscription_plan", "reference_number", "status"]).issubset(hist[0].keys())
    check("GET /api/subscription/payment-history/ (fields present)", r.status_code == 200 and hist_fields_ok, f"{r.status_code} {hist[:1]}")

    # ── NOTIFICATIONS (the focus of the Swagger fix) ─────────────────────────
    notif = Notification.objects.create(
        user_id=client_id, title="Payment approved",
        body="Your WINDEAL+ subscription is now active.", type="payment",
    )
    r = c.get("/api/notifications/", **AUTH_CLIENT)
    nlist = body(r).get("data", [])
    fields_ok = nlist and set(["id", "title", "body", "type", "is_read", "created_at"]).issubset(nlist[0].keys())
    check("GET /api/notifications/ (body fields present)", r.status_code == 200 and fields_ok, f"{r.status_code} {nlist[:1]}")

    r = c.patch(f"/api/notifications/{notif.id}/read/", **AUTH_CLIENT)
    read_ok = body(r).get("data", {}).get("is_read") is True
    check("PATCH /api/notifications/{id}/read/", r.status_code == 200 and read_ok, f"{r.status_code} {body(r)}")

    # ── ADMIN: users management ──────────────────────────────────────────────
    r = c.get("/api/admin/users/", **AUTH_ADMIN)
    check("GET /api/admin/users/", r.status_code == 200, f"{r.status_code}")
    r = c.get("/api/admin/users/?role=client", **AUTH_ADMIN)
    check("GET /api/admin/users/?role=client", r.status_code == 200, f"{r.status_code}")
    r = c.patch(f"/api/admin/users/{biz_id}/toggle/", **AUTH_ADMIN)
    check("PATCH /api/admin/users/{id}/toggle/", r.status_code == 200, f"{r.status_code}")
    c.patch(f"/api/admin/users/{biz_id}/toggle/", **AUTH_ADMIN)  # re-activate
    r = c.patch(f"/api/admin/users/{biz_id}/ban/", **AUTH_ADMIN)
    check("PATCH /api/admin/users/{id}/ban/", r.status_code == 200, f"{r.status_code} {body(r)}")
    c.patch(f"/api/admin/users/{biz_id}/ban/", **AUTH_ADMIN)  # unban
    r = c.patch(f"/api/admin/users/{client_id}/subscription/",
                {"subscription_status": "FREE"}, format="json", **AUTH_ADMIN)
    check("PATCH /api/admin/users/{id}/subscription/", r.status_code == 200, f"{r.status_code} {body(r)}")

    # ── Negative checks: auth enforcement ────────────────────────────────────
    r = c.get("/api/notifications/")
    check("Unauthenticated GET /api/notifications/ -> 401", r.status_code == 401, f"{r.status_code}")
    r = c.get("/api/admin/users/", **AUTH_CLIENT)
    check("Client hitting admin endpoint -> 403", r.status_code == 403, f"{r.status_code}")

    # ── Logout + delete account ──────────────────────────────────────────────
    refresh = cdata.get("tokens", {}).get("refresh")
    r = c.post("/api/auth/logout/", {"refresh": refresh}, format="json")
    check("POST /api/auth/logout/", r.status_code == 200, f"{r.status_code}")

    # delete the business account (separate user, keeps things clean)
    r = c.delete("/api/user/account/delete/", **AUTH_BIZ)
    check("DELETE /api/user/account/delete/", r.status_code == 200, f"{r.status_code} {body(r)}")


def main():
    setup_test_environment()
    runner = DiscoverRunner(verbosity=0)
    old_config = runner.setup_databases()
    try:
        run()
    finally:
        runner.teardown_databases(old_config)
        teardown_test_environment()

    total = len(results)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = total - passed
    print("\n" + "=" * 60)
    print(f"  RESULT: {passed}/{total} passed, {failed} failed")
    print("=" * 60)
    if failed:
        print("\nFailures:")
        for name, ok, detail in results:
            if not ok:
                print(f"  - {name}: {detail}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
