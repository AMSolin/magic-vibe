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

Production deployment is planned as a separate setup: the backend should run as
a systemd service bound to `127.0.0.1`, the frontend should be served from a
production build, and nginx should expose the app on port 80/443.

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
