import re
from datetime import UTC, datetime
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from app.core.config import settings

HTTP_HEADERS = {"User-Agent": "MagicVibe/0.1"}


def _source_index_url(source_url: str) -> str:
    parsed = urlparse(source_url)
    path = parsed.path.rsplit("/", 1)[0] + "/"
    return parsed._replace(path=path, params="", query="", fragment="").geturl()


def _source_file_name(source_url: str) -> str:
    return urlparse(source_url).path.rsplit("/", 1)[-1]


def _parse_index_timestamp(value: str) -> int:
    return int(datetime.strptime(value, "%Y-%b-%d %H:%M").replace(tzinfo=UTC).timestamp())


def _find_source_file_timestamp(html: str, source_url: str) -> int:
    source_file_name = _source_file_name(source_url)
    source_index_url = _source_index_url(source_url)
    escaped_name = re.escape(source_file_name)
    table_pattern = re.compile(
        rf"<a\b[^>]*href=[\"'](?P<href>[^\"']+)[\"'][^>]*>\s*{escaped_name}\s*</a>"
        rf".*?<td\b[^>]*class=[\"']date[\"'][^>]*>\s*"
        rf"(?P<timestamp>\d{{4}}-[A-Za-z]{{3}}-\d{{2}}\s+\d{{2}}:\d{{2}})",
        re.IGNORECASE | re.DOTALL,
    )
    plain_pattern = re.compile(
        rf"<a\b[^>]*href=[\"'](?P<href>[^\"']+)[\"'][^>]*>\s*{escaped_name}\s*</a>"
        rf"\s+(?P<size>\S+(?:\s+\S+)?)\s+"
        rf"(?P<timestamp>\d{{4}}-[A-Za-z]{{3}}-\d{{2}}\s+\d{{2}}:\d{{2}})",
        re.IGNORECASE,
    )
    for pattern in (table_pattern, plain_pattern):
        for match in pattern.finditer(html):
            href = match.group("href")
            if urljoin(source_index_url, href).endswith(source_file_name):
                return _parse_index_timestamp(match.group("timestamp"))
    raise ValueError(f"Could not find {source_file_name!r} in MTGJSON source index")


def get_catalog_source_index_updated_at(
    source_url: str = settings.catalog_source_url,
) -> int:
    request = Request(_source_index_url(source_url), headers=HTTP_HEADERS)
    with urlopen(request, timeout=8) as response:  # noqa: S310
        html = response.read().decode("utf-8", errors="replace")
    return _find_source_file_timestamp(html, source_url)
