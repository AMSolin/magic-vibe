from fastapi import APIRouter

from app.api.routes import cards, collection, decks

api_router = APIRouter()
api_router.include_router(cards.router, prefix="/cards", tags=["cards"])
api_router.include_router(collection.router, prefix="/collection", tags=["collection"])
api_router.include_router(decks.router, prefix="/decks", tags=["decks"])
