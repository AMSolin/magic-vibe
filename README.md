# Magic Vibe

Magic Vibe is a local collection manager for Magic: The Gathering cards. It helps
track collections, players, physical decks, wish decks, catalog data, and cached
card imagery for personal use.

## Stack

- Backend: FastAPI, SQLAlchemy 2.x, Pydantic v2, SQLite
- Frontend: Vue 3, TypeScript, Vite, PrimeVue, Pinia, Vue Router

## Layout

```text
backend/   FastAPI application and database models
frontend/  Vue application
```

## Data and Assets

Magic Vibe uses public Magic: The Gathering catalog and card resources from:

- [MTGJSON](https://mtgjson.com/) for bulk card catalog data.
- [Scryfall](https://scryfall.com/) for card details, card images, and mana
  symbol data.
- [Keyrune](https://keyrune.andrewgioia.com/index.html) for Magic set symbols.

Card catalog databases, user data, downloaded MTGJSON files, and cached
Scryfall assets are created locally under `backend/data/`. They are not included
in this repository.

## Quick Start on Ubuntu

These steps are intended for a fresh Ubuntu 24.04 server or local Linux machine.
Install system packages as an administrator, then run the application as a
regular user, not as `root`.

### 1. System Requirements

Magic Vibe requires:

- Python 3.12 or newer.
- Python virtual environment support.
- Git.
- Node.js 20 LTS or newer.
- npm.
- nginx for production static serving and reverse proxying.

On Ubuntu 24.04, install the required system packages as `root` or a user with
`sudo`:

```bash
sudo apt update
sudo apt install -y ca-certificates curl git nginx python3 python3-venv
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

Check the installed versions:

```bash
python3 --version
git --version
node --version
npm --version
```

If `apt` reports a pending kernel upgrade or deferred service restarts, finish
the setup first and schedule a server reboot before relying on the deployment
for regular use.

### 2. Project Setup

Run the project as a regular user.

Clone the repository:

```bash
git clone https://github.com/AMSolin/magic-vibe.git
cd magic-vibe
```

Create the backend virtual environment and install Python dependencies:

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
```

Install frontend dependencies:

```bash
cd ../frontend
npm install
```

### 3. Temporary VPS Smoke Test

This mode is useful for the first external browser check on a VPS with a public
IP address. It runs development servers and should not be used as the permanent
production setup.

Run the backend on all network interfaces:

```bash
cd ../backend
. .venv/bin/activate
fastapi dev app/main.py --host 0.0.0.0 --port 8000
```

In another terminal, run the frontend on all network interfaces:

```bash
cd frontend
npm run dev -- --host 0.0.0.0 --port 5173
```

Open the application in a browser:

```text
http://<server-public-ip>:5173/
```

Check the backend health endpoint:

```bash
curl http://127.0.0.1:8000/health
```

After the first launch, open the Admin page to initialize local user data and
download/rebuild the Magic card catalog.

### 4. Production Deployment

The production setup uses:

- backend: systemd service bound to `127.0.0.1:8000`;
- frontend: static production build copied to `/var/www/magic-vibe`;
- nginx: public HTTP entry point on port `80`, serving frontend files and
  proxying API requests to the backend.

Build the frontend as the regular application user:

```bash
cd /home/magicvibe/magic-vibe/frontend
npm run build
```

Copy the built frontend to a web-readable directory as `root` or a user with
`sudo`:

```bash
sudo install -d -m 755 -o root -g root /var/www/magic-vibe
sudo rm -rf /var/www/magic-vibe/*
sudo cp -a /home/magicvibe/magic-vibe/frontend/dist/. /var/www/magic-vibe/
sudo chown -R root:root /var/www/magic-vibe
sudo find /var/www/magic-vibe -type d -exec chmod 755 {} \;
sudo find /var/www/magic-vibe -type f -exec chmod 644 {} \;
```

Create `/etc/systemd/system/magic-vibe-backend.service`:

```ini
[Unit]
Description=Magic Vibe FastAPI backend
After=network.target

[Service]
Type=simple
User=magicvibe
Group=magicvibe
WorkingDirectory=/home/magicvibe/magic-vibe/backend
ExecStart=/home/magicvibe/magic-vibe/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

If a previous smoke test left an empty `backend/data/user_data.db`, remove that
zero-byte file before starting the service. The Admin API will create a real
database in the next step.

Enable and start the backend:

```bash
sudo systemctl daemon-reload
sudo systemctl enable magic-vibe-backend.service
sudo systemctl restart magic-vibe-backend.service
sudo systemctl status magic-vibe-backend.service --no-pager
curl http://127.0.0.1:8000/health
```

Create `/etc/nginx/sites-available/magic-vibe`:

```nginx
server {
    listen 80 default_server;
    listen [::]:80 default_server;

    server_name _;

    root /var/www/magic-vibe;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location = /health {
        proxy_pass http://127.0.0.1:8000/health;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

Enable the nginx site:

```bash
sudo ln -sfn /etc/nginx/sites-available/magic-vibe /etc/nginx/sites-enabled/magic-vibe
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

Initialize local user data after the backend is running:

```bash
curl -X POST http://127.0.0.1:8000/api/admin/user-data/recreate
curl http://127.0.0.1:8000/api/admin/user-data
```

Verify the public HTTP deployment:

```bash
curl http://127.0.0.1/
curl http://127.0.0.1/health
curl http://127.0.0.1/api/workspace/players
```

Then open the application in a browser:

```text
http://<server-public-ip>/
```

## Development

Backend:

```bash
cd backend
python -m venv .venv
pip install -e ".[dev]"
fastapi dev app/main.py
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## License

Magic Vibe's original source code is licensed under the MIT License. See
[`LICENSE`](LICENSE).

Magic Vibe is unofficial Fan Content. It is not approved, endorsed, sponsored,
or affiliated with Wizards of the Coast.

Magic: The Gathering, Magic, MTG, Wizards of the Coast, card names, card text,
mana symbols, set symbols, card images, and other related game materials are
property of Wizards of the Coast LLC and their respective rights holders.

This project may cache or display Magic: The Gathering card data, symbols, and
images obtained through Scryfall, MTGJSON, and Keyrune. Those materials remain
subject to the terms, policies, and rights of their respective owners and data
providers.
