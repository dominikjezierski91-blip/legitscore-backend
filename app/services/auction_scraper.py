"""
Serwis do pobierania zdjęć z aukcji (Vinted, Allegro, eBay).
Pobiera obrazy i zwraca je jako bajty do zapisu jako assets.
"""

import json
import logging
import re
from typing import List, Tuple
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

ALLOWED_DOMAINS = ["vinted", "allegro", "ebay"]

# User-Agent przeglądarki - niektóre serwisy blokują boty
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
}


class AuctionScraperError(Exception):
    """Błąd podczas pobierania zdjęć z aukcji."""
    pass


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


def _extract_images_from_html(html: str, base_url: str) -> List[str]:
    """
    Wyciąga URL-e obrazów z HTML strony.
    Szuka w: og:image, ld+json, img tags.
    """
    images: List[str] = []
    seen: set = set()

    def add_image(url: str) -> None:
        if not url or url in seen:
            return
        # Normalizuj URL
        if url.startswith("//"):
            url = "https:" + url
        elif url.startswith("/"):
            from urllib.parse import urljoin
            url = urljoin(base_url, url)
        # Filtruj tylko obrazy
        if any(ext in url.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"]):
            if url not in seen:
                seen.add(url)
                images.append(url)

    # 1. og:image meta tags
    og_pattern = r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']'
    og_pattern2 = r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']'
    for pattern in [og_pattern, og_pattern2]:
        for match in re.finditer(pattern, html, re.IGNORECASE):
            add_image(match.group(1))

    # 2. application/ld+json (structured data)
    ld_pattern = r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>'
    for match in re.finditer(ld_pattern, html, re.IGNORECASE | re.DOTALL):
        try:
            data = json.loads(match.group(1))
            _extract_images_from_json(data, add_image)
        except json.JSONDecodeError:
            continue

    # 3. img tags - szukaj dużych obrazów produktu
    # Vinted używa data-src lub src
    img_patterns = [
        r'<img[^>]+(?:data-src|src)=["\']([^"\']+)["\']',
        r'srcset=["\']([^"\']+)["\']',
    ]
    for pattern in img_patterns:
        for match in re.finditer(pattern, html, re.IGNORECASE):
            url = match.group(1)
            # srcset może zawierać wiele URL-i
            if " " in url and "," in url:
                for part in url.split(","):
                    part = part.strip().split(" ")[0]
                    add_image(part)
            else:
                add_image(url.split(" ")[0])

    # Filtruj małe obrazy (ikony, avatary)
    filtered = []
    for img in images:
        img_lower = img.lower()
        # Pomijaj małe obrazy
        if any(skip in img_lower for skip in ["avatar", "icon", "logo", "thumb", "50x", "100x", "32x", "64x"]):
            continue
        filtered.append(img)

    return filtered


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


async def fetch_auction_images(url: str) -> List[Tuple[bytes, str]]:
    """
    Pobiera zdjęcia z aukcji.
    Zwraca listę krotek (bytes, filename).
    """
    url = validate_auction_url(url)
    logger.info("Pobieranie zdjęć z aukcji: %s", url)

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

        # Wyciągnij URL-e obrazów
        image_urls = _extract_images_from_html(html, url)
        logger.info("Znaleziono %d obrazów na stronie", len(image_urls))

        if not image_urls:
            raise AuctionScraperError(
                "Nie znaleziono zdjęć na stronie. Sprawdź czy link jest prawidłowy."
            )

        # Pobierz obrazy (max 15)
        images: List[Tuple[bytes, str]] = []
        for i, img_url in enumerate(image_urls[:15]):
            try:
                img_response = await client.get(img_url, headers=BROWSER_HEADERS)
                img_response.raise_for_status()

                # Określ rozszerzenie
                content_type = img_response.headers.get("content-type", "")
                if "jpeg" in content_type or "jpg" in content_type:
                    ext = ".jpg"
                elif "png" in content_type:
                    ext = ".png"
                elif "webp" in content_type:
                    ext = ".webp"
                else:
                    # Spróbuj z URL
                    if ".png" in img_url.lower():
                        ext = ".png"
                    elif ".webp" in img_url.lower():
                        ext = ".webp"
                    else:
                        ext = ".jpg"

                filename = f"auction_image_{i+1}{ext}"
                images.append((img_response.content, filename))
                logger.debug("Pobrano obraz %d: %s", i+1, img_url[:100])

            except Exception as e:
                logger.warning("Nie udało się pobrać obrazu %s: %s", img_url[:100], e)
                continue

        if not images:
            raise AuctionScraperError(
                "Nie udało się pobrać żadnego zdjęcia z aukcji."
            )

        logger.info("Pobrano %d zdjęć z aukcji", len(images))
        return images
