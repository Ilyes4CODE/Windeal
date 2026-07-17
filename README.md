# WINDEAL Backend

Django + DRF backend for **WINDEAL** — a mobile platform that helps users discover local discounts from businesses (cafés, restaurants, gyms, leisure spots) and redeem them via QR codes.

This document covers running the backend locally on **macOS** (Apple Silicon or Intel).

---

## Stack

| Layer            | Tech                                                       |
| ---------------- | ---------------------------------------------------------- |
| Language         | Python 3.10+                                               |
| Web framework    | Django 5.2                                                 |
| API framework    | Django REST Framework 3.16                                 |
| Auth             | JWT (djangorestframework-simplejwt) + passwordless         |
| OpenAPI / Docs   | drf-spectacular (Swagger UI + ReDoc)                       |
| Database (dev)   | SQLite                                                     |
| Database (prod)  | PostgreSQL (via `psycopg2-binary` + `dj-database-url`)     |
| File storage     | Local `media/` (uploaded images, receipts)                 |
| Static files     | WhiteNoise                                                 |
| Real-time        | Django Channels + Daphne (WebSockets, JWT-authed)          |
| ASGI server      | Daphne (serves HTTP **and** WebSockets)                     |

---

## Apps

| Django app   | Responsibility                                                                 |
| ------------ | ------------------------------------------------------------------------------ |
| `auth_app`   | Users (client / business / admin), profiles, JWT, passwordless login, payment receipts |
| `admin_app`  | Categories, subscription plans, payment review, user management                |
| `deals_app`  | Deals/offers, favorites, QR redemption, notifications, business dashboard, **WebSocket consumer + real-time services** |
| `core`       | Shared decorators, exception handler, localised messages (`en` / `ar` / `fr`)  |

---

## Prerequisites (macOS)

1. **Homebrew** — install from <https://brew.sh> if not already installed.
2. **Python 3.10+** — comes with most modern macOS releases; otherwise:
   ```sh
   brew install python@3.11
   ```
3. **Git**:
   ```sh
   brew install git
   ```
4. *(Optional, for Postgres in production)*
   ```sh
   brew install postgresql@15
   ```

> Apple Silicon note: Pillow & psycopg2-binary wheels both publish arm64 builds — no extra setup needed.

---

## 1. Clone the repo

```sh
git clone <YOUR_REPO_URL> windeal
cd windeal
```

The project root contains `manage.py`, `requirements.txt`, and the inner Django package `Windeal/`.

---

## 2. Create & activate a virtualenv

```sh
python3 -m venv venv
source venv/bin/activate
```

You should now see `(venv)` in your shell prompt. To exit later, run `deactivate`.

---

## 3. Install dependencies

```sh
pip install --upgrade pip
pip install -r requirements.txt
```

If you only want a dev install on Apple Silicon and `psycopg2-binary` fails to compile (rare on recent macOS), use:

```sh
pip install -r requirements.txt --only-binary=:all:
```

---

## 4. Apply database migrations

The default config uses SQLite, so no DB server is required for local dev.

```sh
python manage.py migrate
```

This creates `db.sqlite3` in the project root.

---

## 5. Create an admin user

Admins have password-based login and access to the admin endpoints + the Django admin panel.

```sh
python manage.py createsuperuser
```

You'll be asked for:
- **Phone** (used as the username, e.g. `+213555999000`)
- **Password**

---

## 6. Run the dev server

```sh
python manage.py runserver
```

By default it listens on `http://127.0.0.1:8000`.

To bind to all interfaces (e.g. to test from a phone on the same Wi-Fi):

```sh
python manage.py runserver 0.0.0.0:8000
```

---

## 7. Browse the API docs

| URL                                  | What it is                                              |
| ------------------------------------ | ------------------------------------------------------- |
| `http://127.0.0.1:8000/api/docs/`    | **Swagger UI** — interactive, sends real requests       |
| `http://127.0.0.1:8000/api/redoc/`   | ReDoc — read-only reference                             |
| `http://127.0.0.1:8000/api/schema/`  | Raw OpenAPI 3 schema (YAML)                             |
| `http://127.0.0.1:8000/django-admin/`| Django admin panel (login with the superuser)           |

To call protected endpoints from Swagger UI:

1. Register or login (passwordless: `POST /api/auth/login/` with `{"phone": "..."}`).
2. Copy the `data.tokens.access` value from the response.
3. Click **Authorize** in Swagger UI and paste it as `Bearer <token>`.

---

## Real-time events (WebSocket)

The backend pushes live events over WebSocket in addition to persisting them as
notification rows (so `GET /api/notifications/` is never out of sync).

> **There is only ONE WebSocket endpoint** — `/ws/notifications/`. Despite the
> name, it is a **single multiplexed socket** that streams *all* real-time
> events: notifications, **redemptions**, and payment updates. You do **not**
> open a separate socket per feature — you connect once and branch on the
> frame's `type` field (see the tables below). Redemption events arrive as
> `{"type": "redemption", ...}` frames on this same socket.

> Real-time requires an **ASGI server** (Daphne). `python manage.py runserver`
> automatically uses Daphne because `daphne` is the first app in `INSTALLED_APPS`.
> In production run `./start.sh` (Daphne) — **not** Gunicorn/WSGI, which cannot
> serve WebSockets.

### Connecting

```
ws://127.0.0.1:8000/ws/notifications/?token=<ACCESS_TOKEN>
```

This one URL handles notifications, redemptions and payments alike.

Authentication (JWT access token) is accepted three ways, in priority order:
1. `?token=<access>` query parameter (works from browsers)
2. `Authorization: Bearer <access>` header (non-browser clients)
3. `Sec-WebSocket-Protocol: access_token, <access>`

A bad/expired token, a banned, or a deactivated account is rejected with an
HTTP `403` handshake. On success the server immediately sends a `connection`
frame with the current unread count.

### Frames (server → client)

Every frame has the shape `{ "type": "<event>", "data": { ... } }`:

| `type`         | When                                                             |
| -------------- | ---------------------------------------------------------------- |
| `connection`   | On connect — `{status, user_id, role, unread_count}`             |
| `notification` | A new persisted notification (serialized row + event `extra`)    |
| `redemption`   | Real-time redemption event (sent to both business and student)   |
| `payment`      | Payment status change (pending / approved / rejected)            |
| `redeem_result`| Reply to a business's `redeem` request (ack for the scan screen) |
| `pong`         | Reply to a client `ping`                                         |

### Frames (client → server)

| Send                                     | Effect                                    |
| ---------------------------------------- | ----------------------------------------- |
| `{"type": "ping"}`                       | Server replies `{"type": "pong"}`         |
| `{"type": "mark_read", "id": "<uuid>"}`  | Marks that notification read              |
| `{"type": "redeem", "qr_token": "<t>"}`  | **Business only.** Redeems a scanned QR live (see below) |

### Redeeming a QR over the socket (live scan screen)

The mobile business app should redeem **through the WebSocket** so the scan
screen updates instantly — no HTTP refresh. The REST endpoint
`POST /api/business/redeem/` still exists and runs identical logic, but the
socket path avoids a round-trip and reuses the already-open connection.

Business sends:

```json
{ "type": "redeem", "qr_token": "SdWWu6-iGiRJOzjt13Lc8Rfise…" }
```

Server replies **on the same socket** with an immediate ack:

```json
{
  "type": "redeem_result",
  "data": {
    "ok": true,
    "code": "success",
    "message": "Redemption successful.",
    "redemption": {
      "redemption_id": "8c1e…", "student_name": "WS Tester",
      "business_name": "WS Cafe", "deal_name": "WS Espresso",
      "deal_id": "71e8…", "status": "VERIFIED", "timestamp": "…"
    }
  }
}
```

On failure `ok` is `false` and `code` is one of `not_found`, `used`, `expired`,
`wrong_business`, `no_subscription`, `forbidden` (non-business), or
`validation_error` (missing token) — with a human-readable `message`.

On success the usual `redemption` + `notification` frames are **also** broadcast
to both the business and the student, so any other open screen updates too.

```js
// business scan screen
scanner.onScan = (qrToken) => ws.send(JSON.stringify({ type: "redeem", qr_token: qrToken }));

ws.onmessage = (e) => {
  const { type, data } = JSON.parse(e.data);
  if (type === "redeem_result") {
    data.ok ? showSuccess(data.redemption) : showError(data.message);
  } else if (type === "redemption") {
    prependToActivityFeed(data);   // live dashboard/list update
  }
};
```

### Which events fire

| Trigger (HTTP)                                   | Who gets notified          | Types emitted              |
| ------------------------------------------------ | -------------------------- | -------------------------- |
| `POST /api/subscription/upgrade/` (or payment upload) | the payer            | `payment` + `notification` |
| Admin approves payment (`.../review/`)           | the payer                  | `payment` + `notification` |
| Admin rejects payment                            | the payer                  | `payment` + `notification` |
| `POST /api/business/redeem/` (deal redeemed)     | the business **and** the student | `redemption` + `notification` (to both) |

### Redemption event (example frame)

When a business scans a QR via `POST /api/business/redeem/`, **both** the
business's and the student's open sockets receive:

```json
{
  "type": "redemption",
  "data": {
    "redemption_id": "8c1e…",
    "student_name": "WS Tester",
    "business_name": "WS Cafe",
    "deal_name": "WS Espresso",
    "deal_id": "71e8…",
    "status": "VERIFIED",
    "timestamp": "2026-07-05T12:00:00Z"
  }
}
```

Client-side you branch on `type` — same socket, no extra connection:

```js
const ws = new WebSocket(`ws://127.0.0.1:8000/ws/notifications/?token=${accessToken}`);
ws.onmessage = (e) => {
  const { type, data } = JSON.parse(e.data);
  switch (type) {
    case "redemption":   updateRedemptionScreen(data); break; // deal scanned live
    case "notification": addNotification(data);        break;
    case "payment":      updateSubscription(data);      break;
    case "connection":   console.log("unread:", data.unread_count); break;
  }
};
```

### Quick WebSocket smoke test (Python)

```python
import asyncio, json, websockets

TOKEN = "<paste an access token>"

async def main():
    uri = f"ws://127.0.0.1:8000/ws/notifications/?token={TOKEN}"
    async with websockets.connect(uri, origin="http://127.0.0.1:8000") as ws:
        print("connected:", await ws.recv())
        await ws.send(json.dumps({"type": "ping"}))
        print("pong:", await ws.recv())
        # now trigger a redemption / payment from another client and watch:
        while True:
            print("event:", await ws.recv())

asyncio.run(main())
```

Then, in another terminal, redeem a deal or approve a payment — the frames arrive live.

> **Scaling note:** the default `CHANNEL_LAYERS` uses `InMemoryChannelLayer`,
> which only works within a **single** process. For multiple Daphne/worker
> processes, install `channels-redis` and point `CHANNEL_LAYERS` at Redis
> (a commented example is in `Windeal/settings.py`).

---

## Business location (`latitude` / `longitude` / `location_name`)

A business's location powers **Nearby**, `distance_km`, and the 80 km
[`availability`](#service-coverage-availability) check — so it must be stored
correctly. There are three distinct fields, and clients must not mix them up:

| Field | Type | Purpose |
| --- | --- | --- |
| `latitude` / `longitude` | **numbers** (sent as separate fields) | Map pin + all distance maths |
| `address` | free text | Human-readable street/place — returned to clients as **`location_name`** |
| `city` | free text | Fallback for `location_name` when `address` is empty |

`location_name` resolves as: **`address` → `city` → `null`**.

### ✅ Correct registration payload

```json
POST /api/auth/register/business/
{
  "phone": "+213555000111",
  "business_name": "tech zone",
  "city": "Alger",
  "address": "12 Rue Didouche Mourad",
  "latitude": "36.7525",
  "longitude": "3.0420"
}
```

### ❌ Common mistake — coordinates inside `address`

```json
{ "business_name": "cafee", "address": "36.7525, 3.0420" }   // don't do this
```

This leaves `latitude`/`longitude` **null** (so the business never appears in
Nearby and is invisible to the coverage check) and makes `location_name` render
as raw coordinates.

### How the backend protects against it

1. **Auto-recovery** — if `address` is a bare `"lat, lng"` string, the server
   parses it into the real `latitude`/`longitude` fields and clears the address
   (`split_coords` in `auth_app/serializers.py`). Applies to registration *and*
   profile update.
2. **`location_name` is sanitised** — it never returns raw coordinates, even for
   legacy rows still holding coords in `address`; it falls back to `city`.
3. **Coordinates are required** — registering a business with no location at all
   is rejected with `400`:
   > *Latitude and longitude are required for a business. Send them as separate
   > numeric fields, not inside 'address'.*

   `latitude` and `longitude` must always be sent **together**.

> Auto-recovery fixes the coordinates without any client change, but
> `location_name` still needs the client to send `city` (or a real `address`) —
> the server can't invent a place name.

### Backfilling legacy rows

For businesses already stored with coordinates in `address`:

```sh
./venv/bin/python manage.py shell <<'PY'
from auth_app.models import BusinessProfile
from auth_app.serializers import split_coords

for bp in BusinessProfile.objects.select_related("user"):
    coords = split_coords(bp.address)
    if not coords:
        continue
    bp.latitude, bp.longitude = coords
    bp.address = ""                       # so location_name falls back to city
    bp.save(update_fields=["latitude", "longitude", "address"])
    if not bp.user.city:
        bp.user.city = "Alger"            # adjust per business
        bp.user.save(update_fields=["city"])
    print("fixed:", bp.business_name, bp.latitude, bp.longitude)
PY
```

## Automatic discount

When a business creates or updates an offer, **`discount_value` is calculated
automatically** from `old_price` and `new_price` — the business never types it.

```
discount_value = round((old_price - new_price) / old_price * 100) + "%"
```

- `old_price = 2000`, `new_price = 1000` → `"50%"`
- `discount_value` is **read-only**: any value the client sends is ignored.
- It is recomputed on every price change (including partial `PATCH` — e.g.
  updating only `new_price` recomputes against the stored `old_price`).
- If `old_price`/`new_price` are missing, zero, or the new price isn't lower,
  `discount_value` is `""`.

Clients read it as `discount_amount` in the deal list (e.g. `GET /api/deals/`).

## Service coverage (`availability`)

The three home-screen deal sections — **`/api/deals/featured/`**,
**`/api/deals/nearby/`** and **`/api/deals/favorites/`** — return an
`availability` boolean so the app can show a *"WINDEAL isn't in your area yet"*
state.

- The app sends the user's `lat` & `lng`.
- `availability` is **`true`** if at least one **active offer** exists within
  **80 km** of the user (nearest business ≤ 80 km).
- `availability` is **`false`** when the nearest active offer is farther than
  80 km — the user is in an unsupported area.
- Either way the endpoint **still returns its deals** — `availability` is purely
  an extra flag; it never filters the list.
- If `lat`/`lng` are omitted, `availability` defaults to **`true`** (coverage
  can't be determined, so the app isn't blocked).

The coverage radius is `COVERAGE_RADIUS_KM = 80.0` in `deals_app/views.py`.

**Response shape** for these three endpoints:

```json
{
  "success": true,
  "data": {
    "availability": false,
    "count": 3,
    "results": [ { …deal… }, … ]
  }
}
```

> Note: `featured` and `favorites` previously returned a bare list in `data`;
> they now return the `{ availability, count, results }` object above (nearby
> already returned an object — it just gained the `availability` key). Update
> any client that read `data` as an array to read `data.results`.

## Endpoint summary

All endpoints are JSON unless flagged as `multipart/form-data` (for file uploads).
Authenticated endpoints require `Authorization: Bearer <access_token>`.

### Auth & onboarding
| Method | Path                              | Purpose                                                       |
| ------ | --------------------------------- | ------------------------------------------------------------- |
| POST   | `/api/auth/register/client/`      | Register a client (passwordless)                              |
| POST   | `/api/auth/register/business/`    | Register a business (passwordless)                            |
| POST   | `/api/auth/register/admin/`       | Create another admin (admin-only)                             |
| POST   | `/api/auth/check/`                | Step 1 of login: does this phone exist? is it banned?         |
| POST   | `/api/auth/login/`                | Step 2 of login: returns JWT tokens + user data               |
| POST   | `/api/auth/login/admin/`          | Admin login (phone/email + password)                          |
| POST   | `/api/auth/logout/`               | Blacklist the refresh token                                   |

### Profile (shared)
| Method | Path                              | Purpose                       |
| ------ | --------------------------------- | ----------------------------- |
| GET    | `/api/auth/profile/`              | Get current user              |
| PATCH  | `/api/auth/profile/update/`       | Update current user           |
| GET    | `/api/user/profile/`              | Alias (matches API spec path) |
| POST   | `/api/user/profile/update/`       | Alias (matches API spec path) |
| DELETE | `/api/user/account/delete/`       | Permanently delete account    |

### Subscription
| Method | Path                              | Purpose                                                          |
| ------ | --------------------------------- | ---------------------------------------------------------------- |
| GET    | `/api/subscription/plans/`        | List public plans (filtered by user role)                        |
| POST   | `/api/subscription/upgrade/`      | Upload receipt → status becomes `PENDING` (multipart/form-data)  |
| GET    | `/api/subscription/payment-history/` | Current user's payment history (date, amount, method, plan, status) |
| POST   | `/api/auth/payment/upload/`       | Alternative payment upload (legacy path)                         |
| GET    | `/api/auth/subscription/status/`  | Get current subscription state                                   |

### Client side
| Method | Path                              | Purpose                                                                                |
| ------ | --------------------------------- | -------------------------------------------------------------------------------------- |
| GET    | `/api/categories/`                | List active deal categories                                                            |
| GET    | `/api/deals/`                     | List deals (filters: `category_id`, `search`, `featured`, `lat`, `lng`; paginated)     |
| GET    | `/api/deals/featured/`            | Featured-deals home section (admin-flagged, highest rating first; `category_id`, `lat`, `lng`, `limit`). Response includes [`availability`](#service-coverage-availability). |
| GET    | `/api/deals/nearby/`              | Deals near a point — **requires** `lat` & `lng`; optional `km` radius, `category_id`, `limit` (nearest first). Response includes [`availability`](#service-coverage-availability). |
| GET    | `/api/deals/<id>/`                | Retrieve one deal                                                                      |
| POST   | `/api/deals/favorites/toggle/`    | Add or remove the deal from favorites                                                  |
| GET    | `/api/deals/favorites/`           | List the current user's favorite deals (`lat`, `lng` → `availability`). Response includes [`availability`](#service-coverage-availability). |
| POST   | `/api/deals/generate-code/`       | Generate a one-time QR redemption token (requires ACTIVE WINDEAL+)                     |

### Business side
| Method | Path                                       | Purpose                                                                  |
| ------ | ------------------------------------------ | ------------------------------------------------------------------------ |
| GET    | `/api/business/offers/`                    | List my offers                                                           |
| POST   | `/api/business/offers/create/`             | Create a new offer (multipart/form-data for image). `discount_value` is **auto-calculated** from `old_price`/`new_price` — see [Automatic discount](#automatic-discount). |
| GET    | `/api/business/offers/<id>/`               | Retrieve one of my offers                                                |
| PATCH  | `/api/business/offers/<id>/`               | Update one of my offers                                                  |
| DELETE | `/api/business/offers/<id>/`               | Delete one of my offers                                                  |
| PATCH  | `/api/business/offers/<id>/toggle/`        | Toggle `is_active` on an offer                                           |
| GET    | `/api/business/dashboard/`                 | Dashboard metrics (today's redemptions, trend, active offers, activity)  |
| GET    | `/api/business/analytics/?period=7d`       | Analytics (`period`: `7d` / `30d` / `all`)                               |
| POST   | `/api/business/redeem/`                    | Scan & redeem a QR token (REST). **Prefer the WebSocket `redeem` action** for a live scan screen — see [Redeeming a QR over the socket](#redeeming-a-qr-over-the-socket-live-scan-screen). |

### Notifications
| Method | Path                                    | Purpose                       |
| ------ | --------------------------------------- | ----------------------------- |
| GET    | `/api/notifications/`                   | List current user notifications |
| PATCH  | `/api/notifications/<id>/read/`         | Mark a notification as read   |
| WS     | `/ws/notifications/?token=<access>`     | Real-time notification / **redemption** / payment stream — single multiplexed socket (see [Real-time events](#real-time-events-websocket)) |

### Admin (admin role required)
| Method        | Path                                                  | Purpose                                  |
| ------------- | ----------------------------------------------------- | ---------------------------------------- |
| GET / POST    | `/api/admin/categories/`                              | List / create category                   |
| GET / PATCH / DELETE | `/api/admin/categories/<id>/`                  | Retrieve / update / delete category      |
| GET / POST    | `/api/admin/plans/`                                   | List / create plan                       |
| GET / PATCH / DELETE | `/api/admin/plans/<id>/`                       | Retrieve / update / delete plan          |
| GET           | `/api/admin/payments/pending/`                        | List pending payment receipts            |
| GET           | `/api/admin/payments/all/`                            | List all payments                        |
| POST          | `/api/admin/payments/<id>/review/`                    | Approve / reject a payment               |
| GET           | `/api/admin/deals/`                                   | List all deals across businesses (filters `featured`, `is_active`, `search`) |
| PATCH         | `/api/admin/deals/<id>/feature/`                      | Set/toggle a deal's `is_featured` flag   |
| GET           | `/api/admin/users/`                                   | List users (filter `?role=...`)          |
| PATCH         | `/api/admin/users/<id>/toggle/`                       | Toggle `is_active`                       |
| PATCH         | `/api/admin/users/<id>/ban/`                          | Toggle `is_banned`                       |
| PATCH         | `/api/admin/users/<id>/subscription/`                 | Force-set subscription status            |

All responses follow:

```json
{ "success": true, "message": "…", "data": { … } }
```

Errors return `success: false` with a localised `message` and optional `errors` map. Set the `Accept-Language` header to `en` / `ar` / `fr` to switch language.

---

## Working with media uploads

Uploaded files (deal images, profile pictures, payment receipts, category icons) are saved under `media/`. The dev server serves them at `/media/...`.

To clear uploads while developing:

```sh
rm -rf media/
```

---

## Resetting the database

```sh
rm db.sqlite3
python manage.py migrate
python manage.py createsuperuser
```

---

## Switching to Postgres (optional)

The settings default to SQLite but `dj-database-url` and `psycopg2-binary` are installed. To use Postgres:

1. Create a database:
   ```sh
   brew services start postgresql@15
   createdb windeal
   ```
2. Set an env var **before** running `manage.py`:
   ```sh
   export DATABASE_URL="postgres://$(whoami)@localhost:5432/windeal"
   ```
3. In `Windeal/settings.py`, replace the `DATABASES` block with:
   ```python
   import dj_database_url
   DATABASES = {
       "default": dj_database_url.config(
           default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
           conn_max_age=600,
       )
   }
   ```
4. Run `python manage.py migrate`.

---

## Running tests

```sh
python manage.py test
```

To run a single app:

```sh
python manage.py test deals_app
```

---

## Production-ish run on macOS (Daphne / ASGI)

Because the app serves WebSockets, run it under **Daphne** (ASGI), not Gunicorn:

```sh
python manage.py collectstatic --no-input
daphne -b 0.0.0.0 -p 8000 Windeal.asgi:application
```

(This is exactly what `start.sh` runs in the deploy.)

> Gunicorn/WSGI (`gunicorn Windeal.wsgi:application`) still works for the REST
> API but **drops WebSocket connections** — use Daphne if you need real-time.

---

## Common issues on macOS

| Symptom                                                          | Fix                                                                                                  |
| ---------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `command not found: python`                                      | Use `python3` (and `python3 -m venv venv`). Some macOS installs don't symlink `python`.              |
| `ssl.SSLCertVerificationError` on `pip install`                  | Run `/Applications/Python\ 3.x/Install\ Certificates.command` once.                                  |
| `psycopg2-binary` build fails                                    | Run `pip install --upgrade pip wheel`, then retry. Or skip Postgres and stick with SQLite for dev.   |
| Port 8000 already in use                                         | Run `lsof -i :8000` to find the PID, then `kill <pid>` — or pass a different port to `runserver`.    |
| `OSError: [Errno 24] Too many open files` when uploading         | Increase the macOS limit: `ulimit -n 4096` in the current shell.                                     |
| Pillow can't open uploaded image                                 | macOS occasionally strips EXIF — ensure the source file is a real JPEG/PNG, not a HEIC.              |

---

## Project layout

```
.
├── manage.py
├── requirements.txt
├── build.sh                 # deploy hook: pip install + migrate + collectstatic
├── start.sh                 # deploy hook: gunicorn entrypoint
├── db.sqlite3               # dev DB (gitignored in prod)
├── media/                   # uploaded files (gitignored)
├── Windeal/                 # Django project (settings, urls, wsgi)
│   ├── settings.py
│   └── urls.py
├── auth_app/                # users + auth + payments upload
├── admin_app/               # admin: categories, plans, payment review, user management
├── deals_app/               # deals/offers, favorites, QR redemption, notifications, business dashboard
└── core/                    # decorators, custom exception handler, localised messages
```

---

## Quick smoke test (curl)

```sh
# Register a client
curl -X POST http://127.0.0.1:8000/api/auth/register/client/ \
  -H 'Content-Type: application/json' \
  -d '{"phone":"+213555111222","full_name":"Test","wilaya":"Alger"}'

# Log in (passwordless)
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/auth/login/ \
  -H 'Content-Type: application/json' \
  -d '{"phone":"+213555111222"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['tokens']['access'])")

# Use the token
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/categories/
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/deals/
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/subscription/plans/
```

If those return `{"success": true, ...}`, the backend is up and the auth flow is working end-to-end.
