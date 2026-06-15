import json
import mimetypes
import os
import threading
from hashlib import sha256
from pathlib import Path
from time import monotonic, sleep, time
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.core.config import settings

_lock = threading.Lock()
_symbols_update_lock = threading.Lock()
_last_api_request = 0.0
_MIN_API_INTERVAL_SECONDS = 0.15


def _cache_root() -> Path:
    path = Path(settings.scryfall_cache_path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _request_bytes(url: str, *, accept: str) -> tuple[bytes, str | None]:
    global _last_api_request
    with _lock:
        delay = _MIN_API_INTERVAL_SECONDS - (monotonic() - _last_api_request)
        if delay > 0:
            sleep(delay)
        request = Request(url, headers={"Accept": accept, "User-Agent": "MagicVibe/0.1"})
        with urlopen(request, timeout=15) as response:
            content = response.read()
            content_type = response.headers.get_content_type()
        _last_api_request = monotonic()
        return content, content_type


def _symbols_root() -> Path:
    path = _cache_root() / "symbols"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _symbols_manifest_path() -> Path:
    return _symbols_root() / "manifest.json"


def get_symbols_manifest() -> dict:
    manifest_path = _symbols_manifest_path()
    if not manifest_path.is_file():
        return {"updated_at": None, "symbols": {}}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def get_symbols_status() -> dict:
    manifest = get_symbols_manifest()
    return {
        "exists": bool(manifest["symbols"]),
        "symbol_count": len(manifest["symbols"]),
        "updated_at": manifest["updated_at"],
    }


def update_symbols_cache() -> dict:
    if not _symbols_update_lock.acquire(blocking=False):
        raise RuntimeError("Scryfall symbols cache update is already running")
    try:
        content, _ = _request_bytes(
            f"{settings.scryfall_api_url}/symbology",
            accept="application/json;q=0.9,*/*;q=0.8",
        )
        data = json.loads(content)
        symbols = data.get("data")
        if not isinstance(symbols, list):
            raise ValueError("Scryfall symbology response does not include a symbol list")

        svg_root = _symbols_root() / "svg"
        svg_root.mkdir(parents=True, exist_ok=True)
        existing_symbols = get_symbols_manifest()["symbols"]
        next_symbols: dict[str, dict[str, str]] = {}

        for item in symbols:
            symbol = item.get("symbol")
            svg_uri = item.get("svg_uri")
            if not isinstance(symbol, str) or not isinstance(svg_uri, str):
                raise ValueError("Scryfall symbology response includes an invalid symbol")

            existing = existing_symbols.get(symbol)
            filename = existing.get("file") if isinstance(existing, dict) else None
            if not isinstance(filename, str) or existing.get("svg_uri") != svg_uri:
                svg, content_type = _request_bytes(svg_uri, accept="image/svg+xml,image/*;q=0.9")
                if content_type not in {"image/svg+xml", "text/xml", "application/xml"}:
                    raise ValueError(f"Scryfall symbol {symbol} did not return an SVG file")
                if b"<svg" not in svg[:1024].lower():
                    raise ValueError(f"Scryfall symbol {symbol} did not return valid SVG content")
                filename = f"{sha256(svg).hexdigest()}.svg"
                svg_path = svg_root / filename
                if not svg_path.is_file():
                    temporary_path = svg_path.with_suffix(".tmp")
                    temporary_path.write_bytes(svg)
                    os.replace(temporary_path, svg_path)
            elif not (svg_root / filename).is_file():
                svg, content_type = _request_bytes(svg_uri, accept="image/svg+xml,image/*;q=0.9")
                if content_type != "image/svg+xml" or b"<svg" not in svg[:1024].lower():
                    raise ValueError(f"Scryfall symbol {symbol} did not return valid SVG content")
                filename = f"{sha256(svg).hexdigest()}.svg"
                svg_path = svg_root / filename
                temporary_path = svg_path.with_suffix(".tmp")
                temporary_path.write_bytes(svg)
                os.replace(temporary_path, svg_path)

            next_symbols[symbol] = {
                "file": filename,
                "svg_uri": svg_uri,
                "english": str(item.get("english") or symbol),
            }

        manifest = {"updated_at": int(time()), "symbols": next_symbols}
        manifest_path = _symbols_manifest_path()
        temporary_manifest_path = manifest_path.with_suffix(".tmp")
        temporary_manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary_manifest_path, manifest_path)
        return get_symbols_status()
    finally:
        _symbols_update_lock.release()


def get_symbol_file(filename: str) -> Path | None:
    if not filename.endswith(".svg") or Path(filename).name != filename:
        return None
    path = _symbols_root() / "svg" / filename
    return path if path.is_file() else None


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


def get_cached_card_json(set_code: str, collector_number: str, language_code: str) -> dict | None:
    cache_path = _cache_root() / "cards" / f"{set_code.lower()}-{collector_number}-{language_code}.json"
    if not cache_path.is_file():
        return None
    return json.loads(cache_path.read_text(encoding="utf-8"))


def get_cached_card_json_by_scryfall_id(scryfall_id: str) -> dict | None:
    cards_root = _cache_root() / "cards"
    if not cards_root.is_dir():
        return None
    for path in cards_root.glob("*.json"):
        if not path.is_file():
            continue
        try:
            card = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if card.get("id") == scryfall_id:
            return card
    return None


def get_card_json_for_image(set_code: str, collector_number: str, language_code: str) -> dict:
    try:
        card = get_card_json(set_code, collector_number, language_code)
    except HTTPError as error:
        if language_code == "en" or error.code != 404:
            raise
        return get_card_json(set_code, collector_number, "en")
    if language_code != "en" and card.get("image_status") == "placeholder":
        return get_card_json(set_code, collector_number, "en")
    return card


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


def get_cached_card_image(
    *,
    scryfall_id: str,
    version: str,
    face_order: int = 0,
) -> tuple[Path, str] | None:
    image_root = _cache_root() / "images"
    if not image_root.is_dir():
        return None
    prefix = f"{scryfall_id}-{face_order}-{version}"
    for path in image_root.glob(f"{prefix}.*"):
        if path.is_file():
            return path, mimetypes.guess_type(path.name)[0] or "image/jpeg"
    return None
