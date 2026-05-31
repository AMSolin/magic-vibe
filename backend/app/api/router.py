from fastapi import APIRouter

from app.api.routes import admin, cards, collection, collections, decks

api_router = APIRouter()
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(cards.router, prefix="/cards", tags=["cards"])
api_router.include_router(collection.router, prefix="/collection", tags=["collection"])
api_router.include_router(collections.router, prefix="/collections", tags=["collections"])
api_router.include_router(decks.router, prefix="/decks", tags=["decks"])
