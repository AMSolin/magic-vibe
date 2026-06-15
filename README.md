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
