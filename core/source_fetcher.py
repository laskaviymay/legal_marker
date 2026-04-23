from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


@dataclass(frozen=True)
class OfficialRegistrySource:
    source: str
    label: str
    page_url: str
    fallback_urls: tuple[str, ...]
    allowed_extensions: tuple[str, ...]


OFFICIAL_REGISTRY_SOURCES: dict[str, OfficialRegistrySource] = {
    "foreign_agents": OfficialRegistrySource(
        source="foreign_agents",
        label="Иноагенты",
        page_url="https://minjust.gov.ru/ru/pages/reestr-inostryannykh-agentov/",
        fallback_urls=(),
        allowed_extensions=(".xlsx", ".xls"),
    ),
    "undesirable_organizations": OfficialRegistrySource(
        source="undesirable_organizations",
        label="Нежелательные организации",
        page_url=(
            "https://minjust.gov.ru/ru/pages/"
            "perechen-inostrannyh-i-mezhdunarodnyh-organizacij-deyatelnost-kotoryh-"
            "priznana-nezhelatelnoj-na-territorii-rossijskoj-federacii/"
        ),
        fallback_urls=(),
        allowed_extensions=(".xlsx", ".xls"),
    ),
    "extremist_materials": OfficialRegistrySource(
        source="extremist_materials",
        label="Экстремистские материалы",
        page_url="https://minjust.gov.ru/uploaded/files/exportfsm.docx",
        fallback_urls=(
            "https://minjust.gov.ru/ru/subscription/rss/extremist_materials/",
            "https://minjust.gov.ru/ru/extremist-materials/",
        ),
        allowed_extensions=(".docx", ".xlsx", ".xls"),
    ),
    "rosfinmonitoring": OfficialRegistrySource(
        source="rosfinmonitoring",
        label="Росфинмониторинг",
        page_url="https://fedsfm.ru/documents/terrorists-catalog-portal-act",
        fallback_urls=(),
        allowed_extensions=(".xlsx", ".xls", ".docx", ".html"),
    ),
}


class _HrefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attributes = dict(attrs)
        href = (attributes.get("href") or "").strip()
        if href:
            self.hrefs.append(href)


def official_registry_sources() -> dict[str, OfficialRegistrySource]:
    return OFFICIAL_REGISTRY_SOURCES


def extract_download_url(source: str, page_url: str, content: str, content_type: str) -> str | None:
    spec = OFFICIAL_REGISTRY_SOURCES[source]
    stripped = content.lstrip()
    if _looks_like_xml(content_type, stripped):
        return _extract_from_xml(spec, page_url, content)
    return _extract_from_html(spec, page_url, content)


def archive_download(
    archive_root: Path,
    source: str,
    original_url: str,
    payload: bytes,
    content_type: str,
    content_disposition: str = "",
    fetched_at: datetime | None = None,
) -> Path:
    fetched_at = fetched_at or datetime.now()
    target_dir = archive_root / fetched_at.strftime("%Y-%m-%d") / source
    target_dir.mkdir(parents=True, exist_ok=True)

    stem = _safe_stem_from_url(original_url) or source
    extension = _extension_from_response(original_url, content_type, content_disposition)
    target = target_dir / f"{fetched_at:%H%M%S}_{stem}{extension}"
    counter = 1
    while target.exists():
        target = target_dir / f"{fetched_at:%H%M%S}_{stem}_{counter}{extension}"
        counter += 1
    target.write_bytes(payload)
    return target


def fetch_official_registry_source(source: str, archive_root: Path, timeout: int = 45) -> Path:
    spec = OFFICIAL_REGISTRY_SOURCES[source]
    errors: list[str] = []
    fetched_at = datetime.now()

    for page_url in (spec.page_url, *spec.fallback_urls):
        try:
            page_payload, content_type, content_disposition, final_url = _download(page_url, timeout=timeout)
            archive_download(
                archive_root / "raw_pages",
                source,
                final_url,
                page_payload,
                content_type,
                content_disposition=content_disposition,
                fetched_at=fetched_at,
            )

            if _looks_like_supported_payload(final_url, content_type, spec.allowed_extensions):
                return archive_download(
                    archive_root,
                    source,
                    final_url,
                    page_payload,
                    content_type,
                    content_disposition=content_disposition,
                    fetched_at=fetched_at,
                )

            page_text = page_payload.decode("utf-8", errors="ignore")
            download_url = extract_download_url(source, final_url, page_text, content_type)
            if not download_url:
                continue

            payload, downloaded_content_type, downloaded_content_disposition, downloaded_url = _download(
                download_url,
                timeout=timeout,
            )
            return archive_download(
                archive_root,
                source,
                downloaded_url,
                payload,
                downloaded_content_type,
                content_disposition=downloaded_content_disposition,
                fetched_at=fetched_at,
            )
        except Exception as exc:
            errors.append(f"{page_url}: {exc}")

    joined_errors = "\n".join(errors) if errors else "не удалось определить причину"
    raise RuntimeError(f"Не удалось скачать официальный реестр {spec.label}.\n{joined_errors}")


def _download(url: str, timeout: int) -> tuple[bytes, str, str, str]:
    request = Request(url, headers=DEFAULT_HEADERS)
    with urlopen(request, timeout=timeout) as response:
        payload = response.read()
        content_type = response.headers.get("Content-Type", "")
        content_disposition = response.headers.get("Content-Disposition", "")
        return payload, content_type, content_disposition, response.geturl()


def _extract_from_html(spec: OfficialRegistrySource, page_url: str, content: str) -> str | None:
    parser = _HrefParser()
    parser.feed(content)
    direct_candidate = _best_candidate(spec, page_url, parser.hrefs)
    if direct_candidate is not None:
        return direct_candidate
    if spec.source in {"foreign_agents", "undesirable_organizations"}:
        export_candidate = _extract_minjust_registry_export_url(content)
        if export_candidate is not None:
            return export_candidate
    return None


def _extract_from_xml(spec: OfficialRegistrySource, page_url: str, content: str) -> str | None:
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return None
    candidates: list[str] = []
    for item in root.findall(".//item"):
        for tag_name in ("link",):
            link = (item.findtext(tag_name) or "").strip()
            if link:
                candidates.append(link)
        for enclosure in item.findall("enclosure"):
            url = (enclosure.attrib.get("url") or "").strip()
            if url:
                candidates.append(url)
    if not candidates:
        for link in root.findall(".//link"):
            value = (link.text or "").strip()
            if value:
                candidates.append(value)
    return _best_candidate(spec, page_url, candidates)


def _best_candidate(spec: OfficialRegistrySource, page_url: str, candidates: list[str]) -> str | None:
    ranked: list[tuple[int, int, str]] = []
    for index, candidate in enumerate(candidates):
        resolved = urljoin(page_url, candidate)
        extension = _url_extension(resolved)
        if extension not in spec.allowed_extensions:
            continue
        priority = spec.allowed_extensions.index(extension)
        ranked.append((priority, index, resolved))
    if not ranked:
        return None
    ranked.sort()
    return ranked[0][2]


def _extract_minjust_registry_export_url(content: str) -> str | None:
    base_match = re.search(r"ExternalApi\.setBaseUrl\(\s*['\"]([^'\"]+)['\"]\s*\)", content)
    id_match = re.search(r"let\s+id\s*=\s*['\"]([0-9a-fA-F-]{8,})['\"]", content)
    if not base_match or not id_match:
        return None
    base_url = base_match.group(1).rstrip("/")
    registry_id = id_match.group(1)
    return f"{base_url}/rest/registry/{registry_id}/export?"


def _looks_like_supported_payload(url: str, content_type: str, allowed_extensions: tuple[str, ...]) -> bool:
    extension = _extension_from_url_or_type(url, content_type)
    return extension in allowed_extensions


def _looks_like_xml(content_type: str, stripped_content: str) -> bool:
    lowered = content_type.lower()
    return (
        "xml" in lowered
        or "rss" in lowered
        or stripped_content.startswith("<?xml")
        or stripped_content.startswith("<rss")
    )


def _safe_stem_from_url(url: str) -> str:
    parsed = urlparse(url)
    stem = Path(parsed.path).stem or parsed.netloc or "download"
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._")
    return cleaned[:80] or "download"


def _url_extension(url: str) -> str:
    return Path(urlparse(url).path).suffix.lower()


def _extension_from_url_or_type(url: str, content_type: str) -> str:
    extension = _url_extension(url)
    if extension:
        return extension

    lowered = content_type.lower()
    mappings = (
        ("spreadsheetml.sheet", ".xlsx"),
        ("ms-excel", ".xls"),
        ("wordprocessingml.document", ".docx"),
        ("text/html", ".html"),
        ("application/rss+xml", ".xml"),
        ("application/xml", ".xml"),
        ("text/xml", ".xml"),
        ("application/json", ".json"),
        ("text/plain", ".txt"),
    )
    for marker, guessed_extension in mappings:
        if marker in lowered:
            return guessed_extension
    return ".bin"


def _extension_from_response(url: str, content_type: str, content_disposition: str) -> str:
    extension = _url_extension(url)
    if extension:
        return extension

    filename_match = re.search(r'filename="?([^";]+)"?', content_disposition, re.IGNORECASE)
    if filename_match:
        filename_extension = Path(filename_match.group(1)).suffix.lower()
        if filename_extension:
            return filename_extension

    return _extension_from_url_or_type(url, content_type)
