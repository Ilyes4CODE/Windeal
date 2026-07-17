# WINDEAL — Mobile Integration Guide

Everything the mobile app needs to talk to the WINDEAL backend, plus the
**changes required right now** (see [Action required](#action-required)).

---

## Base URLs

| Environment | REST API | WebSocket |
| --- | --- | --- |
| **Production** | `https://api.windeal.company` | `wss://api.windeal.company` |
| Local dev | `http://127.0.0.1:8000` | `ws://127.0.0.1:8000` |

Interactive docs (try any endpoint live): **<https://api.windeal.company/api/docs/>**

---

## Action required

Three things must change in the app. Everything else is backwards-compatible.

### 1. Send `city` when registering a business ⚠️

Without it, `location_name` comes back **`null`**. The server cannot invent a
place name from coordinates.

### 2. Send the **real** `latitude` / `longitude`, as separate fields ⚠️

Every business currently registers with the **identical hardcoded** coordinates
`36.7525, 3.0420`, packed into `address` as text. Two problems:

- Coordinates in `address` → they were never stored as real coordinates. *(The
  server now auto-recovers them, so this no longer breaks — but stop doing it.)*
- **Hardcoded** coords mean every business sits at the same point, which makes
  **Nearby**, `distance_km`, and the 80 km `availability` check meaningless.

Send the location the business actually picked (map picker / GPS).

### 3. Read `data.results` on `featured/` and `favorites/` 💥 breaking

Those two endpoints used to return a bare array in `data`. They now return an
object — see [Deals](#deals-client).

---

## Response format

Every endpoint returns the same envelope:

```json
{ "success": true, "message": "…", "data": { … } }
```

On error:

```json
{ "success": false, "message": "Human readable reason", "errors": { "field": ["…"] } }
```

Always branch on the HTTP status; use `message` for user-facing text.

### Headers

| Header | Value |
| --- | --- |
| `Authorization` | `Bearer <access_token>` (all endpoints except register/login/check) |
| `Accept-Language` | `en` \| `ar` \| `fr` — localises every `message` |
| `Content-Type` | `application/json`, or `multipart/form-data` for uploads |

---

## Auth

Clients and businesses are **passwordless** — phone only. Admins use a password.

### Step 1 — check the phone

```json
POST /api/auth/check/
{ "phone": "+213555123456" }

→ { "data": { "exists": true, "is_banned": false, "role": "client" } }
```

If `exists=false` → go to registration. If `is_banned=true` → stop, show support message.

### Step 2 — login

```json
POST /api/auth/login/
{ "phone": "+213555123456" }

→ { "data": { "tokens": { "access": "…", "refresh": "…" }, "role": "client", … } }
```

Store `access` (API + WebSocket) and `refresh`.

### Register a client

```json
POST /api/auth/register/client/
{
  "phone": "+213555123456",
  "full_name": "Yacine Boudiaf",
  "wilaya": "Alger",
  "email": "optional@example.com",
  "school": "optional"
}
```
Required: `phone`, `full_name`, `wilaya`. Returns tokens (auto-login).

### Register a business ⚠️ read this carefully

```json
POST /api/auth/register/business/
{
  "phone": "+213555000111",
  "business_name": "tech zone",
  "city": "Alger",
  "address": "12 Rue Didouche Mourad",
  "latitude": "36.7525",
  "longitude": "3.0420",
  "description": "optional",
  "category_id": "optional-uuid"
}
```

### Logout

```json
POST /api/auth/logout/
{ "refresh": "<refresh_token>" }
```

---

## Business location — the rules

| Field | Type | Meaning |
| --- | --- | --- |
| `latitude` / `longitude` | **numbers, separate fields** | Map pin + all distance maths (Nearby, `distance_km`, coverage) |
| `address` | free text | Human-readable street/place — returned to clients as **`location_name`** |
| `city` | free text | Fallback for `location_name` when `address` is empty |

`location_name` resolves: **`address` → `city` → `null`**.

**Rules**
1. `latitude` and `longitude` must be sent **together** (both or neither) — one without the other is a `400`.
2. Never put coordinates in `address`. It's shown to users as a place name.
3. Registering a business with **no location at all** is rejected:
   > *Latitude and longitude are required for a business. Send them as separate numeric fields, not inside 'address'.*
4. Same rules apply to profile update.

✅ `{"city": "Alger", "address": "12 Rue Didouche Mourad", "latitude": "36.7525", "longitude": "3.0420"}`
❌ `{"address": "36.7525, 3.0420"}`

---

## Deals (client)

### List / search

```
GET /api/deals/?category_id=<uuid>&search=<text>&lat=36.75&lng=3.04&page=1&page_size=20
```

```json
{ "data": { "count": 9, "page": 1, "page_size": 20, "results": [ … ] } }
```

### Home sections

| Endpoint | Notes |
| --- | --- |
| `GET /api/deals/featured/?lat=&lng=&category_id=&limit=` | Admin-picked, highest rating first |
| `GET /api/deals/nearby/?lat=&lng=&km=&category_id=&limit=` | **`lat`/`lng` required**, nearest first, adds `distance_km`; `km` filters by radius |
| `GET /api/deals/favorites/?lat=&lng=` | The user's saved deals |

💥 **All three return an object, not an array:**

```json
{ "data": { "availability": true, "count": 3, "results": [ … ] } }
```

### `availability`

Send the user's `lat`/`lng` and the response includes `availability`:

- `true` → at least one active offer within **80 km** of the user.
- `false` → **unsupported area** — show a "WINDEAL isn't in your area yet" state.
- Omitting `lat`/`lng` → defaults to `true`.

The deals are still returned either way — `availability` never filters the list.

### Deal object

```json
{
  "id": "uuid",
  "item_name": "Free Espresso",
  "item_description": "Buy one get one",
  "item_image": "https://api.windeal.company/media/deals/x.jpg",
  "category_name": "Café",
  "rating": "0.00",
  "business_name": "tech zone",
  "location_name": "Alger",
  "latitude": 36.7525,
  "longitude": 3.042,
  "discount_amount": "50%",
  "old_price": "2000.00",
  "new_price": "1000.00",
  "is_favorite": false,
  "is_featured": true,
  "distance_km": 1.2,
  "expiry_date": "2026-07-31",
  "is_active": true,
  "created_at": "2026-07-17T10:43:35Z"
}
```

`distance_km` is only populated by `nearby/`. Currency is **DZD**.

### Favorites

```json
POST /api/deals/favorites/toggle/
{ "deal_id": "uuid" }

→ { "data": { "deal_id": "uuid", "is_favorite": true } }
```

---

## Offers (business)

| Method | Endpoint |
| --- | --- |
| `GET` | `/api/business/offers/` |
| `POST` | `/api/business/offers/create/` (multipart for `image`) |
| `GET`/`PATCH`/`DELETE` | `/api/business/offers/<id>/` |
| `PATCH` | `/api/business/offers/<id>/toggle/` (flip `is_active`) |

```
POST /api/business/offers/create/     (multipart/form-data)
title=Free Espresso
description=Buy one get one
old_price=2000
new_price=1000
category_id=<uuid>
expiry_date=2026-07-31
is_active=true
image=<file>
```

> **Don't send `discount_value`** — it's read-only and **auto-calculated** from
> `old_price`/`new_price` (2000 → 1000 = `"50%"`). Anything you send is ignored.
> It's returned as `discount_amount` on the client side.

### Dashboard & analytics

```
GET /api/business/dashboard/
→ { "data": { "redemptions_today": 3, "redemptions_trend": "+50%",
              "active_offers_count": 4, "recent_activities": [ … ] } }

GET /api/business/analytics/?period=7d          # 7d | 30d | all
→ { "data": { "chart_data": [{ "date": "…", "count": 2 }],
              "top_performing_offers": [ … ] } }
```

---

## QR redemption

### Student generates the code

```json
POST /api/deals/generate-code/
{ "deal_id": "uuid" }

→ { "data": { "qr_token": "secure_hash", "expires_in": 600 } }
```

- Requires an **ACTIVE WINDEAL+ subscription** → otherwise `402`.
- Token is **one-time** and expires in **10 minutes**. Render `qr_token` as the QR.

### Business scans & redeems

**Preferred — over the WebSocket** (live scan screen, no HTTP refresh):

```json
send:    { "type": "redeem", "qr_token": "<scanned>" }
receive: { "type": "redeem_result",
           "data": { "ok": true, "code": "success",
                     "message": "Redemption successful.",
                     "redemption": { "student_name": "…", "deal_name": "…", … } } }
```

Failure codes: `not_found`, `used`, `expired`, `wrong_business`, `no_subscription`, `forbidden`, `validation_error`.

**Or over REST** (identical logic):

```json
POST /api/business/redeem/
{ "qr_token": "…" }
```

---

## Real-time (WebSocket)

**There is ONE socket.** It carries notifications, redemptions and payments —
don't open one per feature.

```
wss://api.windeal.company/ws/notifications/?token=<ACCESS_TOKEN>
```

A bad/expired token, banned or inactive account → handshake rejected with `403`.
On success the server immediately sends a `connection` frame.

### Server → client frames

Every frame is `{ "type": "<event>", "data": { … } }`:

| `type` | When |
| --- | --- |
| `connection` | On connect — `{ status, user_id, role, unread_count }` |
| `notification` | New notification (also persisted in `GET /api/notifications/`) |
| `redemption` | A deal was redeemed — sent to **both** the business and the student |
| `payment` | Payment status changed (pending / approved / rejected) |
| `redeem_result` | Reply to your `redeem` request |
| `pong` | Reply to `ping` |

### Client → server frames

| Send | Effect |
| --- | --- |
| `{"type":"ping"}` | → `{"type":"pong"}` (keep-alive) |
| `{"type":"mark_read","id":"<uuid>"}` | Mark a notification read |
| `{"type":"redeem","qr_token":"<t>"}` | **Business only** — redeem a scanned QR |

```js
const ws = new WebSocket(`wss://api.windeal.company/ws/notifications/?token=${accessToken}`);

ws.onmessage = (e) => {
  const { type, data } = JSON.parse(e.data);
  switch (type) {
    case "connection":    setUnread(data.unread_count); break;
    case "notification":  addNotification(data);        break;
    case "redemption":    updateActivityFeed(data);     break;
    case "payment":       updateSubscription(data);     break;
    case "redeem_result": data.ok ? showSuccess(data.redemption) : showError(data.message); break;
  }
};
```

Reconnect with backoff on drop, and send `ping` periodically to keep the socket alive.

---

## Subscription (WINDEAL+)

```
GET  /api/subscription/plans/            → id, title, price, discount_label, duration_months, billing_detail
POST /api/subscription/upgrade/          (multipart) plan_id, payment_method, reference_number, receipt_image
GET  /api/subscription/payment-history/  → id, transaction_date, amount, payment_method,
                                           subscription_plan, reference_number, status
GET  /api/auth/subscription/status/      → FREE | PENDING | ACTIVE | EXPIRED
```

After `upgrade/`, status becomes **PENDING** until an admin approves — the user
gets a live `payment` frame + notification when it flips to **ACTIVE**.

Redemption requires **ACTIVE**.

---

## Profile & account

```
GET    /api/user/profile/
PATCH  /api/user/profile/update/        (json or multipart for profile_picture)
DELETE /api/user/account/delete/
GET    /api/notifications/
PATCH  /api/notifications/<id>/read/
```

Client fields: `full_name`, `email`, `wilaya`, `school`, `city`, `profile_picture`.
Business fields: `business_name`, `description`, `category_id`, `address`,
`website`, `latitude`, `longitude`, `city`, `email`, `profile_picture`.

---

## Common mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| `location_name` is `null` | No `city` and no `address` sent | Send `city` at registration |
| `location_name` shows `"36.75, 3.04"` | Coordinates put in `address` | Send them as `latitude`/`longitude` |
| `latitude`/`longitude` are `null` | Never sent | Send both, as separate numeric fields |
| Deal missing from **Nearby** / `availability:false` | Business has no/hardcoded coords | Send the real picked location |
| `featured`/`favorites` list is empty in the app | Reading `data` as an array | Read **`data.results`** |
| `400` on business register | Only one of lat/lng sent, or neither | Send both together |
| `402` on `generate-code/` | No active subscription | Subscribe first |
| Images don't load | — | `item_image` is already an absolute `https://` URL — use it as-is |
| WebSocket `403` | Bad/expired token, or banned user | Re-login and reconnect |
