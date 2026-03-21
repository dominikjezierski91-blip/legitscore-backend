"""
Serwis do pobierania zdjęć z aukcji (Vinted, Allegro, eBay).
Pobiera obrazy i zwraca je jako bajty do zapisu jako assets.
"""

import json
import logging
import re
from typing import Dict, List, Tuple
from urllib.parse import urlparse, urljoin

import httpx

logger = logging.getLogger(__name__)

ALLOWED_DOMAINS = ["vinted", "allegro", "ebay"]

# User-Agent przeglądarki - niektóre serwisy blokują boty
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
}

# Słowa wskazujące na miniatury/ikony – pomijamy
_SKIP_WORDS = ["avatar", "icon", "logo", "thumb", "50x", "100x", "32x", "64x"]

# Zaufane domeny CDN obrazów dla znanych providerów (bez wymogu rozszerzenia pliku)
_TRUSTED_IMAGE_DOMAINS = ["images.vinted.net", "images1.vinted.net", "images2.vinted.net"]


class AuctionScraperError(Exception):
    """Błąd podczas pobierania zdjęć z aukcji."""
    pass


def detect_provider(url: str) -> str:
    """
    Wykrywa dostawcę (Vinted, Allegro, eBay) na podstawie URL.
    Zwraca nazwę dostawcy lub 'unknown'.
    """
    try:
        parsed = urlparse(url)
        domain_lower = parsed.netloc.lower()
        if "vinted" in domain_lower:
            return "vinted"
        elif "allegro" in domain_lower:
            return "allegro"
        elif "ebay" in domain_lower:
            return "ebay"
    except Exception:
        pass
    return "unknown"


def validate_auction_url(url: str) -> str:
    """
    Waliduje URL aukcji. Sprawdza czy domena jest dozwolona.
    Zwraca znormalizowany URL lub rzuca wyjątek.
    """
    if not url or not url.strip():
        raise AuctionScraperError("URL nie może być pusty")

    url = url.strip()

    # Sprawdź czy to prawidłowy URL
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise AuctionScraperError("Nieprawidłowy format URL")
    except Exception:
        raise AuctionScraperError("Nieprawidłowy format URL")

    # Sprawdź domenę
    domain_lower = parsed.netloc.lower()
    is_allowed = any(allowed in domain_lower for allowed in ALLOWED_DOMAINS)

    if not is_allowed:
        raise AuctionScraperError(
            f"Nieobsługiwana domena. Dozwolone: Vinted, Allegro, eBay"
        )

    return url


def _normalize_image_url(raw_url: str, base_url: str) -> str | None:
    """
    Normalizuje raw URL obrazu:
    - usuwa trailing backslash i whitespace (częsty problem z Vinted srcset)
    - rozwiązuje URL-e względne
    - zwraca None jeśli URL jest nieprawidłowy
    """
    if not raw_url:
        return None
    url = raw_url.strip().rstrip("\\").rstrip()
    if not url:
        return None
    if url.startswith("//"):
        url = "https:" + url
    elif url.startswith("/"):
        url = urljoin(base_url, url)
    if not url.startswith("http"):
        return None
    return url


def _is_image_url(url: str) -> bool:
    """
    Sprawdza czy URL wskazuje na obraz.
    Akceptuje:
    - URL-e z rozszerzeniem .jpg/.jpeg/.png/.webp w ścieżce
    - Zaufane domeny CDN (np. images.vinted.net) bez rozszerzenia
    """
    url_lower = url.lower()
    # Zaufane CDN - zawsze obrazy (np. .../f800 bez rozszerzenia)
    for domain in _TRUSTED_IMAGE_DOMAINS:
        if domain in url_lower:
            return True
    # Sprawdź rozszerzenie w ścieżce (bez query params)
    path = url_lower.split("?")[0]
    return any(ext in path for ext in [".jpg", ".jpeg", ".png", ".webp"])


def _parse_srcset(srcset_value: str) -> List[str]:
    """
    Wyciąga URL-e z wartości atrybutu srcset.
    Format: "url1 descriptor, url2 descriptor, ..."
    Descriptor to np. "1x", "2x", "320w".
    """
    urls = []
    for entry in srcset_value.split(","):
        entry = entry.strip()
        if not entry:
            continue
        # Pierwsza część (przed spacją) to URL; reszta to descriptor (1x, 320w, itp.)
        raw_url = entry.split()[0] if entry else ""
        if raw_url:
            urls.append(raw_url)
    return urls


def _vinted_photo_id(url: str) -> str | None:
    """
    Wyciąga photo ID z Vinted CDN URL dla celów deduplikacji.
    Przykład: .../t/06_00ac5_CqZPvpnnh2DY.../f800/... → '06_00ac5_CqZPvpnnh2DY...'
    """
    m = re.search(r'/t/([^/]+)/', url)
    return m.group(1) if m else None


def _extract_images_from_html(html: str, base_url: str) -> Tuple[List[str], Dict]:
    """
    Wyciąga URL-e obrazów z HTML strony.
    Szuka w: og:image, ld+json, link[preload], img tags, srcset, inline scripts.

    Zwraca:
    - images: lista znormalizowanych URL-i obrazów (po filtracji)
    - diagnostics: słownik z informacjami diagnostycznymi (per-kandidat)
    """
    images: List[str] = []
    seen_urls: set = set()      # znormalizowane URL-e (bez ?s=... sygnatury) dla deduplikacji
    candidates: List[Dict] = []  # log wszystkich kandydatów

    def _dedup_key(url: str) -> str:
        """
        Klucz deduplikacji. Dla Vinted CDN: photo_id + rozmiar (bez sygnatury ?s=...).
        Pozwala deduplikować ten sam obraz pojawiający się wiele razy z różnymi sygnaturami.
        """
        url_lower = url.lower()
        if any(d in url_lower for d in _TRUSTED_IMAGE_DOMAINS):
            return url.split("?")[0]  # strip ?s=... signature
        return url

    def try_add(raw_url: str, source: str) -> None:
        normalized = _normalize_image_url(raw_url, base_url)
        if not normalized:
            candidates.append({
                "url": (raw_url or "")[:200],
                "source": source,
                "status": "dropped",
                "drop_reason": "invalid_url",
            })
            return

        url_lower = normalized.lower()

        # Filtruj miniatury/ikony po słowach kluczowych
        if any(w in url_lower for w in _SKIP_WORDS):
            candidates.append({
                "url": normalized[:200],
                "source": source,
                "status": "dropped",
                "drop_reason": "skip_word",
            })
            return

        # Sprawdź czy to URL obrazu
        if not _is_image_url(normalized):
            candidates.append({
                "url": normalized[:200],
                "source": source,
                "status": "dropped",
                "drop_reason": "filtered_extension",
            })
            return

        # Deduplikacja na kluczu kanonicznym (bez sygnatury Vinted)
        key = _dedup_key(normalized)
        if key in seen_urls:
            candidates.append({
                "url": normalized[:200],
                "source": source,
                "status": "dropped",
                "drop_reason": "duplicate",
            })
            return

        seen_urls.add(key)
        images.append(normalized)
        candidates.append({
            "url": normalized[:200],
            "source": source,
            "status": "used",
            "drop_reason": None,
        })

    # 1. og:image meta tags
    og_patterns = [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
    ]
    for pattern in og_patterns:
        for match in re.finditer(pattern, html, re.IGNORECASE):
            try_add(match.group(1), "og:image")

    # 2. application/ld+json (structured data)
    ld_pattern = r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>'
    for match in re.finditer(ld_pattern, html, re.IGNORECASE | re.DOTALL):
        try:
            data = json.loads(match.group(1))
            _extract_images_from_json(data, lambda u: try_add(u, "ld+json"))
        except json.JSONDecodeError:
            continue

    # 3. link[rel=preload][as=image] – Next.js/SSR pre-ładuje pierwsze zdjęcia w ten sposób
    link_preload_patterns = [
        r'<link[^>]+rel=["\']preload["\'][^>]+as=["\']image["\'][^>]+href=["\']([^"\']+)["\']',
        r'<link[^>]+as=["\']image["\'][^>]+rel=["\']preload["\'][^>]+href=["\']([^"\']+)["\']',
        r'<link[^>]+href=["\']([^"\']+)["\'][^>]+rel=["\']preload["\'][^>]+as=["\']image["\']',
    ]
    for pattern in link_preload_patterns:
        for match in re.finditer(pattern, html, re.IGNORECASE):
            try_add(match.group(1), "link_preload")

    # 4. img src / data-src (pojedynczy URL per tag)
    for match in re.finditer(r'<img[^>]+(?:data-src|src)=["\']([^"\']+)["\']', html, re.IGNORECASE):
        raw = match.group(1).split(" ")[0]
        try_add(raw, "img")

    # 5. srcset (właściwy parsing – każdy entry może być URL + descriptor)
    for match in re.finditer(r'srcset=["\']([^"\']+)["\']', html, re.IGNORECASE):
        for raw in _parse_srcset(match.group(1)):
            try_add(raw, "srcset")

    # 6. Inline <script> content — wyciąga pełnowymiarowe URL-e Vinted CDN (f800)
    #    Vinted (Next.js App Router / RSC) osadza pełną listę zdjęć w payloadach JS.
    #    Pozostałe zdjęcia galerii (powyżej fold) trafiają TYLKO tutaj, nie do <img>/<srcset>.
    #    Używamy rozmiaru /f800/ jako wskaźnika pełnowymiarowego zdjęcia produktu.
    script_contents = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL | re.IGNORECASE)
    for script_body in script_contents:
        # Szukaj URL-i zaufanych CDN tylko w scriptach (nie w ld+json – już obsługiwane)
        for m in re.finditer(
            r'https://images\d*\.vinted\.net/t/[^"\'<>\s\\]+/f800/[^"\'<>\s\\]+',
            script_body,
        ):
            try_add(m.group(0), "inline_script")

    # Podsumowanie diagnostyczne
    dropped = [c for c in candidates if c["status"] == "dropped"]
    drop_reasons: Dict[str, int] = {}
    for c in dropped:
        reason = c["drop_reason"] or "unknown"
        drop_reasons[reason] = drop_reasons.get(reason, 0) + 1

    diagnostics = {
        "assets_extracted_count": len(images),
        "candidates_total": len(candidates),
        "dropped_count": len(dropped),
        "drop_reasons_summary": drop_reasons,
        "candidates": candidates,
    }
    return images, diagnostics


def _extract_images_from_json(data, add_fn) -> None:
    """Rekurencyjnie wyciąga obrazy z JSON-LD."""
    if isinstance(data, dict):
        for key, value in data.items():
            if key.lower() in ("image", "photo", "photos", "images"):
                if isinstance(value, str):
                    add_fn(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, str):
                            add_fn(item)
                        elif isinstance(item, dict) and "url" in item:
                            add_fn(item["url"])
            else:
                _extract_images_from_json(value, add_fn)
    elif isinstance(data, list):
        for item in data:
            _extract_images_from_json(item, add_fn)


async def fetch_auction_images(url: str) -> Tuple[List[Tuple[bytes, str]], Dict]:
    """
    Pobiera zdjęcia z aukcji.
    Zwraca krotkę:
    - images: lista krotek (bytes, filename)
    - ingestion_meta: słownik diagnostyczny z metadanymi ingestii
    """
    url = validate_auction_url(url)
    provider = detect_provider(url)
    logger.info("[SCRAPER] provider=%s url=%s", provider, url)

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        # Pobierz HTML strony
        try:
            response = await client.get(url, headers=BROWSER_HEADERS)
            response.raise_for_status()
            html = response.text
        except httpx.HTTPStatusError as e:
            logger.error("Błąd HTTP podczas pobierania strony: %s", e)
            raise AuctionScraperError(f"Nie udało się pobrać strony: HTTP {e.response.status_code}")
        except httpx.RequestError as e:
            logger.error("Błąd połączenia: %s", e)
            raise AuctionScraperError("Nie udało się połączyć ze stroną aukcji")

        # Wyciągnij URL-e obrazów z diagnostyką
        image_urls, extraction_diag = _extract_images_from_html(html, url)

        logger.info(
            "[SCRAPER] provider=%s assets_extracted=%d candidates_total=%d dropped=%d drop_reasons=%s",
            provider,
            extraction_diag["assets_extracted_count"],
            extraction_diag["candidates_total"],
            extraction_diag["dropped_count"],
            extraction_diag["drop_reasons_summary"],
        )

        if not image_urls:
            logger.warning("[SCRAPER] provider=%s NO_IMAGES_DETECTED url=%s", provider, url)
            raise AuctionScraperError(
                "Nie znaleziono zdjęć na stronie. Sprawdź czy link jest prawidłowy."
            )

        # Pobierz wszystkie obrazy galerii
        images: List[Tuple[bytes, str]] = []
        download_log: List[Dict] = []

        for i, img_url in enumerate(image_urls):
            try:
                img_response = await client.get(img_url, headers=BROWSER_HEADERS)
                img_response.raise_for_status()

                # Określ rozszerzenie na podstawie Content-Type (priorytet nad URL)
                content_type = img_response.headers.get("content-type", "")
                if "jpeg" in content_type or "jpg" in content_type:
                    ext = ".jpg"
                elif "png" in content_type:
                    ext = ".png"
                elif "webp" in content_type:
                    ext = ".webp"
                else:
                    # Fallback: próbuj z URL
                    if ".png" in img_url.lower():
                        ext = ".png"
                    elif ".webp" in img_url.lower():
                        ext = ".webp"
                    else:
                        ext = ".jpg"

                filename = f"auction_image_{i+1}{ext}"
                images.append((img_response.content, filename))
                download_log.append({"url": img_url[:200], "filename": filename, "status": "ok"})
                logger.debug("[SCRAPER] downloaded image %d: %s", i + 1, img_url[:100])

            except Exception as e:
                logger.warning("[SCRAPER] failed to download image %s: %s", img_url[:100], e)
                download_log.append({"url": img_url[:200], "filename": None, "status": "failed", "error": str(e)})
                continue

        if not images:
            logger.warning("[SCRAPER] provider=%s NO_IMAGES_DOWNLOADED url=%s", provider, url)
            raise AuctionScraperError(
                "Nie udało się pobrać żadnego zdjęcia z aukcji."
            )

        assets_passed = len(images)
        assets_extracted = len(image_urls)
        incomplete = assets_passed < assets_extracted

        logger.info(
            "[SCRAPER] provider=%s assets_downloaded=%d/%d incomplete_image_set=%s",
            provider,
            assets_passed,
            assets_extracted,
            incomplete,
        )

        ingestion_meta = {
            "source_url": url,
            "provider": provider,
            "assets_extracted_count": assets_extracted,
            "assets_passed_to_model_count": assets_passed,
            "incomplete_image_set": incomplete,
            "drop_reasons_summary": extraction_diag["drop_reasons_summary"],
            "candidates_total": extraction_diag["candidates_total"],
            "dropped_count": extraction_diag["dropped_count"],
            "candidates": extraction_diag["candidates"],
            "download_log": download_log,
        }

        return images, ingestion_meta
