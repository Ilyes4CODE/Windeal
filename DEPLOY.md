# Deploying WINDEAL to a Hostinger VPS (Ubuntu 24.04)

Step-by-step production deployment for the WINDEAL backend on a Hostinger KVM
VPS. Target stack:

```
Internet ──► Nginx (TLS 443)
                ├─ /static/  ─► files on disk
                ├─ /media/   ─► files on disk
                └─ everything else (HTTP + /ws/ WebSockets) ─► Daphne (127.0.0.1:8000)
                                                                   │
                                              PostgreSQL ◄─────────┤
                                                   Redis ◄─────────┘  (Channels layer)
```

Daphne (ASGI) serves **both** the REST API and the WebSockets. PostgreSQL is the
database, Redis backs the real-time channel layer, Nginx terminates TLS and
serves static/media files.

> Replace `187.77.171.86` with your VPS IP and `api.windeal.company` with your domain
> everywhere below. If you don't have a domain yet you can start with the IP and
> add TLS later (WebSockets will be `ws://` instead of `wss://` until then).

---

## 0. Before you start

- **(Recommended) Point a domain at the VPS.** In your DNS provider add an `A`
  record: `api.windeal.company → 187.77.171.86`. TLS/HTTPS needs a domain.
- Have your VPS root password (or set up an SSH key in hPanel → SSH keys).

---

## 1. Connect via SSH

From your PC (PowerShell or the hPanel **Terminal** button):

```sh
ssh root@187.77.171.86
```

---

## 2. Install system packages

```sh
apt update && apt upgrade -y
apt install -y python3-venv python3-pip git nginx postgresql redis-server \
               libpq-dev build-essential ufw
systemctl enable --now postgresql redis-server nginx
```

---

## 3. Create a non-root app user

Running the app as a dedicated user is safer than root.

```sh
adduser --system --group --home /home/windeal windeal
```

---

## 4. Create the PostgreSQL database

```sh
sudo -u postgres psql <<'SQL'
CREATE DATABASE windeal;
CREATE USER windeal WITH PASSWORD 'STRONG_DB_PASSWORD';
ALTER ROLE windeal SET client_encoding TO 'utf8';
ALTER ROLE windeal SET default_transaction_isolation TO 'read committed';
ALTER ROLE windeal SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE windeal TO windeal;
\c windeal
GRANT ALL ON SCHEMA public TO windeal;
SQL
```

Use your own strong password and keep it — it goes into `.env` next.

---

## 5. Get the code and install dependencies

```sh
cd /home/windeal
git clone https://github.com/Ilyes4CODE/Windeal.git
cd Windeal

python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
```

---

## 6. Create the `.env` file

```sh
cp .env.example .env
# generate a secret key:
./venv/bin/python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
nano .env
```

Fill it in (matching the DB password and domain/IP):

```ini
DJANGO_SECRET_KEY=<paste the generated key>
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=api.windeal.company,187.77.171.86
DJANGO_CSRF_TRUSTED_ORIGINS=https://api.windeal.company
DATABASE_URL=postgres://windeal:STRONG_DB_PASSWORD@127.0.0.1:5432/windeal
REDIS_URL=redis://127.0.0.1:6379/0
DJANGO_CORS_ALLOW_ALL=True
DJANGO_HSTS_SECONDS=0
```

---

## 7. Migrate, collect static, create an admin

```sh
cd /home/windeal/Windeal
./venv/bin/python manage.py migrate
./venv/bin/python manage.py collectstatic --no-input
./venv/bin/python manage.py createsuperuser   # phone + password for admin login

# hand ownership to the app user
chown -R windeal:windeal /home/windeal/Windeal
```

---

## 8. Run Daphne as a systemd service

Create the service:

```sh
nano /etc/systemd/system/windeal.service
```

```ini
[Unit]
Description=WINDEAL Daphne (ASGI: HTTP + WebSockets)
After=network.target postgresql.service redis-server.service

[Service]
User=windeal
Group=windeal
WorkingDirectory=/home/windeal/Windeal
ExecStart=/home/windeal/Windeal/venv/bin/daphne -b 127.0.0.1 -p 8000 Windeal.asgi:application
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Start it:

```sh
systemctl daemon-reload
systemctl enable --now windeal
systemctl status windeal --no-pager    # should say "active (running)"
```

The app loads config from `/home/windeal/Windeal/.env` automatically
(via `python-dotenv`).

---

## 9. Configure Nginx (reverse proxy + WebSocket upgrade)

```sh
nano /etc/nginx/sites-available/windeal
```

```nginx
server {
    listen 80;
    server_name api.windeal.company 187.77.171.86;

    client_max_body_size 20M;   # payment receipts / deal images

    location /static/ {
        alias /home/windeal/Windeal/staticfiles/;
    }
    location /media/ {
        alias /home/windeal/Windeal/media/;
    }

    # WebSockets — must send the Upgrade headers
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 3600s;   # keep long-lived sockets open
    }

    # Everything else (REST API, admin, docs)
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable it and reload:

```sh
ln -s /etc/nginx/sites-available/windeal /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
```

---

## 10. Firewall

```sh
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable
```

---

## 11. Enable HTTPS (TLS) — needs a domain

```sh
apt install -y certbot python3-certbot-nginx
certbot --nginx -d api.windeal.company
```

Certbot rewrites the Nginx config for port 443 and sets up auto-renewal. After
HTTPS works, optionally set `DJANGO_HSTS_SECONDS=31536000` in `.env` and
`systemctl restart windeal`.

Your endpoints are now:

- REST API:   `https://api.windeal.company/api/...`
- Swagger UI: `https://api.windeal.company/api/docs/`
- WebSocket:  `wss://api.windeal.company/ws/notifications/?token=<access>`
- Admin:      `https://api.windeal.company/django-admin/`

---

## 12. Smoke test

```sh
# from the server or your PC
curl -s https://api.windeal.company/api/schema/ -o /dev/null -w "%{http_code}\n"   # 200

# register a client, then hit an authed endpoint
curl -s -X POST https://api.windeal.company/api/auth/register/client/ \
  -H 'Content-Type: application/json' \
  -d '{"phone":"+213555111222","full_name":"Test","wilaya":"Alger"}'
```

For WebSockets, connect to `wss://api.windeal.company/ws/notifications/?token=<access>`
from the app (or the Python snippet in `README.md`).

---

## 13. Deploying updates later

```sh
cd /home/windeal/Windeal
sudo -u windeal git pull
./venv/bin/pip install -r requirements.txt          # if deps changed
./venv/bin/python manage.py migrate                 # if migrations changed
./venv/bin/python manage.py collectstatic --no-input
chown -R windeal:windeal /home/windeal/Windeal
systemctl restart windeal
```

> ⚠️ Always run `migrate` after pulling — new features (e.g. `is_featured`,
> payment fields) ship with migrations that must be applied or requests 500.

---

## 14. Backups

- Turn on **Snapshot & backups** in hPanel (the $3/mo daily backups the panel
  offers, or manual snapshots before big changes).
- Database dump on demand:
  ```sh
  sudo -u postgres pg_dump windeal > /root/windeal-$(date +%F).sql
  ```

---

## Troubleshooting

| Symptom | Check |
| --- | --- |
| 502 Bad Gateway | `systemctl status windeal` and `journalctl -u windeal -n 50` — Daphne likely crashed (bad `.env`, DB unreachable). |
| WebSocket won't connect | Confirm the `/ws/` Nginx block has the `Upgrade`/`Connection` headers; check the token is valid and `wss://` (not `ws://`) on HTTPS. |
| `DisallowedHost` error | Add the domain/IP to `DJANGO_ALLOWED_HOSTS` in `.env`, then `systemctl restart windeal`. |
| 400 on admin login over HTTPS | Add `https://your-domain` to `DJANGO_CSRF_TRUSTED_ORIGINS`. |
| Static files missing on admin | Re-run `collectstatic`; confirm the Nginx `/static/` alias path. |
| Uploads fail with 413 | Raise `client_max_body_size` in Nginx. |
| Real-time works then breaks under load | Ensure `REDIS_URL` is set so the channel layer isn't in-memory. |

### Useful commands

```sh
systemctl restart windeal          # restart the app
journalctl -u windeal -f           # live app logs
systemctl reload nginx             # reload Nginx after config edits
nginx -t                           # test Nginx config
```
