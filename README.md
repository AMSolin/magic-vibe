# Magic Explorer

Magic Explorer is a collection manager for Magic: The Gathering cards.

## Stack

- Backend: FastAPI, SQLAlchemy 2.x, Pydantic v2, SQLite
- Frontend: Vue 3, TypeScript, Vite, PrimeVue, Pinia, Vue Router

## Layout

```text
backend/   FastAPI application and database models
frontend/  Vue application
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
