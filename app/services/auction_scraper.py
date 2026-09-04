"""
Serwis do pobierania zdjęć z aukcji (Vinted, eBay, Kleinanzeigen).
Pobiera obrazy i zwraca je jako bajty do zapisu jako assets.

Allegro NIE jest obsługiwane — blokuje scraping na poziomie bot-detection
(HTTP 403 niezależnie od nagłówków, potwierdzone w produkcji) i nie ma
samoobsługowego, publicznego API (endpoint /offers/listing wymaga ręcznej
weryfikacji/whitelisty przez zespół Allegro).
"""

import json
import logging
import re
from typing import Dict, List, Tuple
from urllib.parse import urlparse, urljoin

import httpx

logger = logging.getLogger(__name__)

ALLOWED_DOMAINS = ["vinted", "ebay", "kleinanzeigen"]

# User-Agent przeglądarki - niektóre serwisy blokują boty
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
}

# Słowa wskazujące na miniatury/ikony – pomijamy
_SKIP_WORDS = ["avatar", "icon", "logo", "thumb", "50x", "100x", "32x", "64x"]

# Zaufane domeny CDN obrazów dla znanych providerów (bez wymogu rozszerzenia pliku)
_TRUSTED_IMAGE_DOMAINS = ["images.vinted.net", "images1.vinted.net", "images2.vinted.net", "img.kleinanzeigen.de"]


class AuctionScraperError(Exception):
    """Błąd podczas pobierania zdjęć z aukcji."""
    pass


def detect_provider(url: str) -> str:
    """
    Wykrywa dostawcę (Vinted, eBay, Kleinanzeigen) na podstawie URL.
    Zwraca nazwę dostawcy lub 'unknown'.
    """
    try:
        parsed = urlparse(url)
        domain_lower = parsed.netloc.lower()
        if "vinted" in domain_lower:
            return "vinted"
        elif "ebay" in domain_lower:
            return "ebay"
        elif "kleinanzeigen" in domain_lower:
            return "kleinanzeigen"
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
            f"Nieobsługiwana domena. Dozwolone: Vinted, eBay, Kleinanzeigen"
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


_VINTED_TIMESTAMP_RE = re.compile(r"/f800/(\d+)\.\w+")


def _filter_vinted_avatar_outliers(images: List[str], candidates: List[Dict]) -> List[str]:
    """
    Vinted preloaduje w <head> (rel=preload as=image) nie tylko zdjęcia galerii
    oferty, ale też awatar sprzedawcy — dane sekcji "user_info_header" (sidebar)
    są w tym samym payloadzie strony, a URL awatara pasuje do tego samego wzorca
    CDN co zdjęcia produktu (images*.vinted.net/t/.../f800/{timestamp}.webp), więc
    generyczna ekstrakcja (kroki og:image/link_preload/inline_script wyżej) nie
    odróżnia go od prawdziwego zdjęcia oferty.

    Prawdziwe zdjęcia oferty dzielą wspólny znacznik czasu uploadu (segment
    /f800/{timestamp}/ — wszystkie wgrane w tej samej turze); awatar sprzedawcy
    ma inny, bo wgrany kiedy indziej, niezależnie. Potwierdzone na realnym
    przypadku (case b545a7d4, ogłoszenie PSG/Dembélé, 2026-09-04): 6 zdjęć
    koszulki ze znacznikiem 1788519287, 1 awatar sprzedawcy ze znacznikiem
    1785782475 (zdjęcie Pepa Guardioli z pucharem Ligi Mistrzów, ustawione jako
    zdjęcie profilowe sprzedawcy) — trafił do analizy Agenta A jako rzekome
    7. zdjęcie koszulki.

    Odrzuca tylko odosobnione (singleton) znaczniki czasu, gdy istnieje wyraźnie
    dominująca grupa (≥3 zdjęcia) — celowo nie wymusza jednej grupy, żeby nie
    ryzykować odrzucenia prawdziwych zdjęć przy ogłoszeniu, do którego sprzedawca
    dograł zdjęcia w dwóch turach edycji (wtedy obie grupy mogą być realne).

    URL-e, z których nie da się wyciągnąć znacznika czasu (inny wariant
    rozmiaru CDN niż /f800/), są CAŁKOWICIE pomijane w tej analizie — nigdy
    nie trafiają do żadnej grupy i nigdy nie są odrzucane (QA, 2026-09-04:
    wspólny klucz "unknown" dla wszystkich niedopasowanych URL-i błędnie
    traktował je jak jedną grupę — mogło to zarówno odrzucić prawdziwe
    zdjęcie w innym wariancie rozmiaru, jak i przepuścić dwa niepowiązane
    obce zdjęcia, które przypadkiem skolidowały w tej samej grupie). To
    zachowanie jest spójne z resztą funkcji: wolimy nie odrzucić niczego,
    gdy nie mamy pewności, niż zaryzykować odrzucenie prawdziwego zdjęcia.
    """
    groups: Dict[str, List[str]] = {}
    for url in images:
        if "vinted.net" not in url.lower():
            continue
        m = _VINTED_TIMESTAMP_RE.search(url)
        if not m:
            continue
        groups.setdefault(m.group(1), []).append(url)

    if len(groups) <= 1:
        return images

    largest_size = max(len(urls) for urls in groups.values())
    if largest_size < 3:
        return images

    dropped_urls = {
        url
        for urls in groups.values()
        if len(urls) == 1
        for url in urls
    }
    if not dropped_urls:
        return images

    dropped_prefixes = {url[:200] for url in dropped_urls}
    for c in candidates:
        if c["status"] == "used" and c["url"] in dropped_prefixes:
            c["status"] = "dropped"
            c["drop_reason"] = "vinted_avatar_outlier"

    return [u for u in images if u not in dropped_urls]


def _extract_images_from_html(html: str, base_url: str) -> Tuple[List[str], Dict]:
    """
    Wyciąga URL-e obrazów z HTML strony.
    Szuka w: og:image, ld+json, link[preload], img tags, srcset, inline scripts.

    Zwraca:
    - images: lista znormalizowanych URL-i obrazów (po filtracji)
    - diagnostics: słownik z informacjami diagnostycznymi (per-kandidat)
    """
    # Kleinanzeigen: strona oferty zawiera dalej sekcję "könnte dich auch
    # interessieren" / "Andere Anzeigen" (podobne ogłoszenia) z miniaturkami
    # INNYCH, niepowiązanych ofert pod tym samym wzorcem URL CDN
    # (img.kleinanzeigen.de/api/v1/prod-ads/images/...). Ograniczamy całą
    # ekstrakcję (wszystkie kroki poniżej, nie tylko krok 0) do fragmentu HTML
    # w obrębie kontenera galerii — inaczej generyczne kroki (og:image/img/
    # srcset) też złapałyby te niepowiązane zdjęcia, skoro img.kleinanzeigen.de
    # jest zaufaną domeną CDN (patrz _TRUSTED_IMAGE_DOMAINS).
    #
    # Górną granicę cięcia wyznacza realny marker początku sekcji podobnych
    # ofert (nie sztywna liczba znaków) — sztywne okno zawodzi przy większej
    # liczbie zdjęć własnej galerii (każde zdjęcie to ~2000+ znaków markupu
    # w realnym HTML, więc oferta z ~10+ zdjęciami może wypaść poza dowolne
    # rozsądnie małe okno; potwierdzone na realnej ofercie z 12 zdjęciami,
    # gdzie fixed-window 20000 znaków cicho gubił 2 z nich). Fallback na
    # szerokie okno tylko gdy żaden marker nie występuje na stronie.
    _ka_gallery_start = html.find('class="vip-image-gallery')
    if _ka_gallery_start != -1:
        _ka_end_markers = ("könnte dich auch interessieren", "Andere Anzeigen")
        _ka_end = min(
            (idx for idx in (html.find(m, _ka_gallery_start) for m in _ka_end_markers) if idx != -1),
            default=-1,
        )
        if _ka_end == -1:
            logger.warning(
                "[SCRAPER] provider=kleinanzeigen brak markera końca galerii — używam szerokiego fallback okna"
            )
            _ka_end = _ka_gallery_start + 200000
        html = html[_ka_gallery_start:_ka_end]

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

    # 0. Kleinanzeigen CDN — normalizuj do pełnowymiarowego rozmiaru ($_59) zanim
    #    generyczne kroki (img/srcset/og:image) trafią na mniejsze warianty (np.
    #    $_35 z galerii miniatur) tego samego zdjęcia. Dedup po ścieżce bazowej
    #    (bez ?rule=...) sprawia, że ten wpis "wygrywa" i mniejsze warianty tego
    #    samego zdjęcia zostają odrzucone jako duplikaty. `html` jest już
    #    ograniczone do galerii tej oferty (patrz na górze funkcji).
    for m in re.finditer(
        r'https://img\.kleinanzeigen\.de/api/v1/prod-ads/images/[a-zA-Z0-9]+/[a-zA-Z0-9-]+',
        html,
    ):
        try_add(m.group(0) + "?rule=$_59.AUTO", "kleinanzeigen_fullsize")

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

    # Vinted: odsiej awatar sprzedawcy podszywający się pod zdjęcie oferty —
    # patrz _filter_vinted_avatar_outliers.
    images = _filter_vinted_avatar_outliers(images, candidates)

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


_EBAY_DOMAIN_MARKETPLACE = {
    "ebay.com": "EBAY_US",
    "ebay.co.uk": "EBAY_GB",
    "ebay.de": "EBAY_DE",
}


def _ebay_legacy_item_id(url: str) -> str | None:
    """Wyciąga legacy item ID z linku eBay (np. /itm/305716156524 lub /itm/Tytul/305716156524)."""
    match = re.search(r"/itm/(?:[^/?]+/)?(\d+)", url)
    return match.group(1) if match else None


def _ebay_marketplace_for_url(url: str) -> str:
    domain = urlparse(url).netloc.lower().removeprefix("www.")
    return _EBAY_DOMAIN_MARKETPLACE.get(domain, "EBAY_US")


async def _fetch_ebay_images_via_browse_api(url: str) -> Tuple[List[Tuple[bytes, str]], Dict]:
    """
    eBay blokuje scraping HTML oferty na poziomie bot-detection (HTTP 403
    niezależnie od nagłówków — potwierdzone w logach produkcyjnych). Zamiast
    tego pobiera oficjalne zdjęcia przez Browse API (get_item_by_legacy_id),
    tę samą integrację (OAuth2 client_credentials, wspólny token cache) co
    market_value_agent.estimate_via_ebay_browse().
    """
    from app.services.market_value_agent import _get_ebay_oauth_token

    item_id = _ebay_legacy_item_id(url)
    if not item_id:
        raise AuctionScraperError(
            "Nie rozpoznano numeru oferty w linku eBay. Sprawdź czy link jest prawidłowy."
        )

    token = await _get_ebay_oauth_token()
    if not token:
        raise AuctionScraperError(
            "Import z eBay jest chwilowo niedostępny (brak konfiguracji API)."
        )

    marketplace = _ebay_marketplace_for_url(url)

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(
                "https://api.ebay.com/buy/browse/v1/item/get_item_by_legacy_id",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-EBAY-C-MARKETPLACE-ID": marketplace,
                },
                params={"legacy_item_id": item_id},
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("eBay Browse API item lookup failed: %s", e)
            raise AuctionScraperError(
                f"Nie udało się pobrać oferty z eBay (HTTP {e.response.status_code})."
            )
        except httpx.RequestError as e:
            logger.error("eBay Browse API connection error: %s", e)
            raise AuctionScraperError("Nie udało się połączyć z eBay API.")
        except ValueError as e:
            logger.error("eBay Browse API returned non-JSON response: %s", e)
            raise AuctionScraperError("eBay zwrócił nieprawidłową odpowiedź.")

        try:
            image_urls: List[str] = []
            main_image = (data.get("image") or {}).get("imageUrl")
            if main_image:
                image_urls.append(main_image)
            for img in data.get("additionalImages") or []:
                img_url = (img or {}).get("imageUrl")
                if img_url and img_url not in image_urls:
                    image_urls.append(img_url)
        except (AttributeError, TypeError) as e:
            logger.error("eBay Browse API returned unexpected item shape: %s", e)
            raise AuctionScraperError("eBay zwrócił nieoczekiwany format danych oferty.")

        if not image_urls:
            raise AuctionScraperError("Nie znaleziono zdjęć w ofercie eBay.")

        images: List[Tuple[bytes, str]] = []
        download_log: List[Dict] = []
        candidates: List[Dict] = []
        drop_reasons_summary: Dict[str, int] = {}
        for i, img_url in enumerate(image_urls):
            try:
                img_response = await client.get(img_url, headers=BROWSER_HEADERS)
                img_response.raise_for_status()
                content_type = img_response.headers.get("content-type", "")
                if "png" in content_type:
                    ext = ".png"
                elif "webp" in content_type:
                    ext = ".webp"
                else:
                    ext = ".jpg"
                filename = f"auction_image_{i + 1}{ext}"
                images.append((img_response.content, filename))
                download_log.append({"url": img_url[:200], "filename": filename, "status": "ok"})
                candidates.append({
                    "url": img_url[:200],
                    "source": "ebay_api",
                    "status": "used",
                    "drop_reason": None,
                })
            except Exception as e:
                logger.warning("[SCRAPER] failed to download eBay image %s: %s", img_url[:100], e)
                download_log.append({"url": img_url[:200], "filename": None, "status": "failed", "error": str(e)})
                candidates.append({
                    "url": img_url[:200],
                    "source": "ebay_api",
                    "status": "dropped",
                    "drop_reason": "download_failed",
                })
                drop_reasons_summary["download_failed"] = drop_reasons_summary.get("download_failed", 0) + 1
                continue

        if not images:
            raise AuctionScraperError("Nie udało się pobrać żadnego zdjęcia z oferty eBay.")

        assets_extracted = len(image_urls)
        assets_passed = len(images)
        logger.info(
            "[SCRAPER] provider=ebay via_api=True item_id=%s marketplace=%s assets_downloaded=%d/%d",
            item_id, marketplace, assets_passed, assets_extracted,
        )

        return images, {
            "source_url": url,
            "provider": "ebay",
            "assets_extracted_count": assets_extracted,
            "assets_passed_to_model_count": assets_passed,
            "incomplete_image_set": assets_passed < assets_extracted,
            "drop_reasons_summary": drop_reasons_summary,
            "candidates_total": assets_extracted,
            "dropped_count": assets_extracted - assets_passed,
            "candidates": candidates,
            "download_log": download_log,
        }


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

    if provider == "ebay":
        return await _fetch_ebay_images_via_browse_api(url)

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
