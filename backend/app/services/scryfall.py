import json
import mimetypes
import threading
from pathlib import Path
from time import monotonic, sleep
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.core.config import settings

_lock = threading.Lock()
_last_api_request = 0.0
_MIN_API_INTERVAL_SECONDS = 0.15


def _cache_root() -> Path:
    path = Path(settings.scryfall_cache_path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _request_bytes(url: str, *, accept: str) -> tuple[bytes, str | None]:
    global _last_api_request
    if url.startswith(settings.scryfall_api_url):
        with _lock:
            delay = _MIN_API_INTERVAL_SECONDS - (monotonic() - _last_api_request)
            if delay > 0:
                sleep(delay)
            request = Request(
                url,
                headers={
                    "Accept": accept,
                    "User-Agent": "MagicExplorer/0.1",
                },
            )
            with urlopen(request, timeout=15) as response:
                content = response.read()
                content_type = response.headers.get_content_type()
            _last_api_request = monotonic()
            return content, content_type
    request = Request(url, headers={"Accept": accept, "User-Agent": "MagicExplorer/0.1"})
    with urlopen(request, timeout=15) as response:
        return response.read(), response.headers.get_content_type()


def get_card_json(set_code: str, collector_number: str, language_code: str) -> dict:
    cache_path = _cache_root() / "cards" / f"{set_code.lower()}-{collector_number}-{language_code}.json"
    if not cache_path.is_file():
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        url = (
            f"{settings.scryfall_api_url}/cards/"
            f"{quote(set_code.lower())}/{quote(collector_number)}/{quote(language_code)}"
        )
        content, _ = _request_bytes(url, accept="application/json;q=0.9,*/*;q=0.8")
        cache_path.write_bytes(content)
    return json.loads(cache_path.read_text(encoding="utf-8"))


def _image_url(card: dict, version: str, face_order: int) -> str | None:
    faces = card.get("card_faces")
    if isinstance(faces, list) and len(faces) > face_order:
        face_uris = faces[face_order].get("image_uris")
        if isinstance(face_uris, dict):
            return face_uris.get(version)
    image_uris = card.get("image_uris")
    if isinstance(image_uris, dict):
        return image_uris.get(version)
    return None


def get_card_image(
    card: dict,
    *,
    scryfall_id: str,
    version: str,
    face_order: int = 0,
) -> tuple[Path, str]:
    url = _image_url(card, version, face_order)
    if url is None:
        raise ValueError("Scryfall card does not include an image")
    suffix = Path(url.split("?", 1)[0]).suffix or ".jpg"
    cache_path = _cache_root() / "images" / f"{scryfall_id}-{face_order}-{version}{suffix}"
    if not cache_path.is_file():
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        content, content_type = _request_bytes(url, accept="image/*")
        cache_path.write_bytes(content)
    else:
        content_type = None
    return cache_path, content_type or mimetypes.guess_type(cache_path.name)[0] or "image/jpeg"
