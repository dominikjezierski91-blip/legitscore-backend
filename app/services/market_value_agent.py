"""
Market Value Agent — szacuje wartość rynkową koszulki piłkarskiej.

Źródła:
  - Gemini 2.5 z Google Search Grounding (Vinted, Allegro, eBay)
  - eBay Browse API (item_summary/search, OAuth2 client_credentials) gdy
    EBAY_APP_ID + EBAY_CERT_ID_PRD dostępne — patrz estimate_via_ebay_browse().
    Stara Finding API (estimate_via_ebay, findCompletedItems) jest trwale
    zablokowana na poziomie platformy eBay dla tego klucza (HTTP 418 z proxy
    eBay niezależnie od auth) — zostawiona nieużywana jako punkt odniesienia.
"""
import json
import logging
import os
import re
import statistics
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# Przybliżone kursy walut → PLN
_FX_TO_PLN: Dict[str, float] = {
    "PLN": 1.0,
    "EUR": 4.25,
    "GBP": 5.0,
    "USD": 3.9,
}

_SKIP_VALUES = {"nieustalone", "unknown", "brak", "—", "n/a", "", None}

# Mapowanie verdict_category → frazy wyszukiwania
_VERDICT_SEARCH_TERMS: dict = {
    "oryginalna_sklepowa": "oryginalna sklepowa authentic retail",
    "meczowa": "match worn player issue meczowa",
    "oficjalna_replika": "oficjalna replika replica",
    "edycja_limitowana": "limited edition edycja limitowana",
    "treningowa_custom": "treningowa training",
    "podrobka": "oryginalna",
}

# Frazy w tytule oferty, których obecność oznacza, że to NA PEWNO inny tier
# cenowy niż werdykt tej koszulki — mimo że oferta pasuje po klubie/sezonie
# (np. wyszukiwanie znajdzie zarówno meczowe, jak i replikowe koszulki tego
# samego klubu i sezonu). Bez tego filtra jedna źle dobrana oferta potrafi
# mocno zaniżyć/zawyżyć medianę (koszulka meczowa jest zwykle kilkukrotnie
# droższa niż oficjalna replika tego samego klubu/sezonu). Filtrujemy tylko
# te trzy kategorie, dla których pomylenie tieru ma duży wpływ cenowy —
# celowo NIE filtrujemy edycja_limitowana/treningowa_custom/podrobka, gdzie
# sygnał w tytule jest zbyt niejednoznaczny żeby bezpiecznie odrzucać oferty.
_VERDICT_EXCLUDE_KEYWORDS: dict = {
    "meczowa": ["replica", "replika", "fan version", "fan edition"],
    "oryginalna_sklepowa": ["replica", "replika", "fan version", "fan edition", "match worn", "player issue", "player version"],
    "oficjalna_replika": ["match worn", "player issue", "player version", "match issued"],
}


def _filter_listings_by_category(listings: List[Dict], verdict_category: str) -> List[Dict]:
    """Odrzuca oferty, których tytuł wyraźnie wskazuje na inny tier cenowy niż
    werdykt (patrz _VERDICT_EXCLUDE_KEYWORDS). Brak dopasowania kategorii w
    mapie = brak filtrowania (zwraca listings bez zmian)."""
    exclude_keywords = _VERDICT_EXCLUDE_KEYWORDS.get((verdict_category or "").strip())
    if not exclude_keywords:
        return listings
    filtered = []
    for listing in listings:
        title_lower = (listing.get("title") or "").lower()
        if any(kw in title_lower for kw in exclude_keywords):
            continue
        filtered.append(listing)
    return filtered


# eBay Browse API robi luźne dopasowanie tekstowe (q=...), nie wymaga zgodności
# WSZYSTKICH słów zapytania — dla popularnego klubu/marki potrafi więc zwrócić
# koszulki z zupełnie innych sezonów i wariantów (domowa/wyjazdowa/trzecia) tego
# samego klubu. _filter_listings_by_category powyżej łapie tylko pomyloną
# kategorię (replika vs meczowa); to nie chroni przed pomyloną edycją tego
# samego tieru. Efekt: zaniżona mediana, bo próbka jest zdominowana przez
# niedopasowane, zwykle tańsze oferty — a jedyna trafna, poprawnie wyceniona
# oferta bywa dodatkowo odrzucana przez _reject_outliers jako rzekomy outlier,
# skoro reszta próbki jest zaniżona. Znaleziono na case'ie Bayern/Ribéry
# 2015/2016 (raport 20260902-6d29c75e): 8/10 ofert eBay miało inny sezon lub
# wariant, mediana wyszła 234 PLN przy realnej ofercie ~680 PLN.
_SEASON_PAIR_RE = re.compile(r"(\d{2,4})\s*[/\-]\s*(\d{2,4})")

# Granice sensownego roku sezonu — bez tego "104/110" (rozmiarówka dziecięca,
# EU height-based sizing) parsowałoby się jako rzekomy sezon "(104, 110)" i
# fałszywie odrzucało poprawnie dopasowaną ofertę tylko dlatego, że rozmiar w
# tytule wystąpił przed sezonem (np. "Kids 104/110 Bayern Munich 2015/2016").
_SEASON_MIN_YEAR = 1900
_SEASON_MAX_YEAR = 2035

_KIT_TYPE_CONFLICT_KEYWORDS: Dict[str, List[str]] = {
    "domowa": ["away", "wyjazdowa", "third", "trzecia", "alternate", "gk", "goalkeeper", "bramkarska"],
    "wyjazdowa": ["home", "domowa", "third", "trzecia", "alternate", "gk", "goalkeeper", "bramkarska"],
    "trzecia": ["home", "domowa", "away", "wyjazdowa", "gk", "goalkeeper", "bramkarska"],
    "bramkarska": ["home", "domowa", "away", "wyjazdowa", "third", "trzecia"],
}


def _normalize_season_year(raw: str) -> int:
    year = int(raw)
    if year < 100:
        return 2000 + year if year <= 50 else 1900 + year
    return year


def _parse_season_pair(text: str) -> Optional[tuple]:
    """Wyciąga pierwszą PRAWDOPODOBNĄ parę lat sezonu (np. '2015/2016' → (2015, 2016),
    '15/16' → (2015, 2016)) z tekstu — iteruje po wszystkich dopasowaniach regexu i
    zwraca pierwsze mieszczące się w sensownym zakresie roku (patrz _SEASON_MIN_YEAR/
    _SEASON_MAX_YEAR), żeby np. rozmiarówka dziecięca ('104/110') występująca przed
    sezonem w tytule nie przesłoniła właściwej pary. Zwraca None, gdy nie znaleziono
    żadnej wiarygodnej pary — brak informacji o sezonie w tytule NIE jest traktowany
    jako konflikt (patrz _filter_listings_by_relevance)."""
    for match in _SEASON_PAIR_RE.finditer(text):
        start = _normalize_season_year(match.group(1))
        end = _normalize_season_year(match.group(2))
        if end < start:
            continue
        if not (_SEASON_MIN_YEAR <= start <= _SEASON_MAX_YEAR and _SEASON_MIN_YEAR <= end <= _SEASON_MAX_YEAR):
            continue
        return (start, end)
    return None


def _filter_listings_by_relevance(listings: List[Dict], subject: Dict[str, Any]) -> List[Dict]:
    """Odrzuca oferty, których tytuł jawnie wskazuje na INNY sezon lub INNY wariant
    (domowa/wyjazdowa/trzecia/bramkarska) niż deklarowany w analizie. Filtrujemy
    tylko na twardej sprzeczności — brak sezonu/wariantu w tytule NIE jest powodem
    odrzucenia, tylko jawna niezgodność (np. deklarowana '2015/2016', tytuł mówi
    '2018/2019'; deklarowana 'domowa', tytuł mówi 'away')."""
    season = str(subject.get("season") or "").strip()
    model = str(subject.get("model") or "").strip().lower()

    declared_season = _parse_season_pair(season) if season else None
    conflict_keywords = next(
        (kws for prefix, kws in _KIT_TYPE_CONFLICT_KEYWORDS.items() if model.startswith(prefix)),
        None,
    )

    if not declared_season and not conflict_keywords:
        return listings

    filtered = []
    for listing in listings:
        title_lower = (listing.get("title") or "").lower()
        if declared_season:
            listing_season = _parse_season_pair(title_lower)
            if listing_season and listing_season != declared_season:
                continue
        if conflict_keywords and any(kw in title_lower for kw in conflict_keywords):
            continue
        filtered.append(listing)
    return filtered


def _get_client() -> Optional[genai.Client]:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None
    return genai.Client(api_key=api_key)


def build_search_query(report_data: Dict[str, Any]) -> str:
    """Buduje query wyszukiwania na podstawie wszystkich dostępnych parametrów raportu."""
    subject = report_data.get("subject") or {}
    verdict = report_data.get("verdict") or {}
    parts: List[str] = []

    for field in ["club", "season", "brand"]:
        val = subject.get(field)
        if val and str(val).lower().strip() not in _SKIP_VALUES:
            parts.append(str(val).strip())

    model = subject.get("model")
    if model and str(model).lower().strip() not in _SKIP_VALUES:
        parts.append(str(model).strip())

    player = subject.get("player_name")
    if player and str(player).lower().strip() not in _SKIP_VALUES:
        parts.append(str(player).strip())
    number = subject.get("player_number")
    if number and str(number).lower().strip() not in _SKIP_VALUES:
        parts.append(f"#{str(number).strip()}")

    verdict_cat = (verdict.get("verdict_category") or "").strip()
    if verdict_cat and verdict_cat in _VERDICT_SEARCH_TERMS:
        parts.append(_VERDICT_SEARCH_TERMS[verdict_cat])

    parts.append("koszulka piłkarska")
    return " ".join(parts)


def build_ebay_search_query(report_data: Dict[str, Any]) -> str:
    """Buduje krótsze, samo-angielskie zapytanie pod eBay Browse API —
    osobno od build_search_query() (używanego dla Gemini, gdzie dłuższe,
    wielojęzyczne zapytanie pomaga, bo Gemini szuka też po Vinted.pl/Allegro.pl).

    eBay Browse API robi zwykłe dopasowanie tekstowe (nie semantyczne) — długie
    zapytanie z polskimi słowami-wypełniaczami (kategoria werdyktu, wariant
    domowa/wyjazdowa, "koszulka piłkarska") rozmywa trafność i wypycha dobrze
    dopasowane oferty poza wyniki. Potwierdzone na case'ie PSG/Messi (raport
    20260903-238a181d): pełne zapytanie nie znalazło REALNEJ, aktywnej oferty
    użytkownika (1500 PLN) na żadnym z przeszukiwanych rynków — krótkie
    zapytanie (klub + sezon + gracz + numer) znalazło ją od razu, na 1. miejscu.
    Kategoria werdyktu i wariant (domowa/wyjazdowa/trzecia) są i tak
    egzekwowane po fakcie przez _filter_listings_by_category/_filter_listings_by_relevance,
    więc pominięcie ich w samym zapytaniu nie osłabia filtrowania."""
    subject = report_data.get("subject") or {}
    parts: List[str] = []

    for field in ["club", "season", "brand"]:
        val = subject.get(field)
        if val and str(val).lower().strip() not in _SKIP_VALUES:
            parts.append(str(val).strip())

    player = subject.get("player_name")
    if player and str(player).lower().strip() not in _SKIP_VALUES:
        parts.append(str(player).strip())
    number = subject.get("player_number")
    if number and str(number).lower().strip() not in _SKIP_VALUES:
        parts.append(f"#{str(number).strip()}")

    return " ".join(parts)


def to_pln(price: float, currency: str) -> float:
    rate = _FX_TO_PLN.get((currency or "PLN").upper().strip(), 1.0)
    return round(price * rate, 2)


def _extract_json(text: str) -> Optional[Dict]:
    """Wyłuskuje JSON z odpowiedzi Gemini (obsługuje grounding + markdown)."""
    text = text.strip()

    # 1. JSON w bloku kodu markdown
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass

    # 2. Bezpośredni JSON
    try:
        return json.loads(text)
    except Exception:
        pass

    # 3. Wyodrębnij { ... } z dowolnego tekstu
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end])
        except Exception:
            pass

    return None


async def estimate_via_gemini(report_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Szacuje wartość rynkową — dwa kroki:
    1. Google Search Grounding → naturalny tekst z cenami
    2. Ekstrakcja JSON (bez grounding, response_mime_type=application/json)
    """
    import asyncio

    client = _get_client()
    if client is None:
        return {"error": "Brak klucza Gemini API", "sample_size": 0, "listings": []}

    query = build_search_query(report_data)
    if not query.replace("koszulka piłkarska", "").strip():
        return {"error": "Za mało danych do wyceny (brak klubu/sezonu/gracza).", "sample_size": 0, "listings": []}

    # Flash — pro z grounding+JSON zwraca parts=None
    model = os.getenv("MARKET_VALUE_MODEL", "models/gemini-2.5-flash")

    verdict_cat = ((report_data.get("verdict") or {}).get("verdict_category") or "").strip()
    verdict_context = {
        "oryginalna_sklepowa": "Szukaj oryginalnych koszulek sklepowych (authentic retail). NIE szukaj replik ani podróbek.",
        "meczowa": "Szukaj koszulek meczowych (match worn, match issued, player issue). To są najdroższe egzemplarze.",
        "oficjalna_replika": "Szukaj oficjalnych replik (replica, fan version). NIE szukaj wersji player/authentic.",
        "edycja_limitowana": "Szukaj edycji limitowanych (limited edition, special edition).",
        "treningowa_custom": "Szukaj koszulek treningowych lub customowych.",
        "podrobka": "Koszulka to prawdopodobnie podróbka. Szukaj cen ORYGINALNYCH koszulek jako punkt odniesienia.",
    }.get(verdict_cat, "Szukaj tej koszulki piłkarskiej.")

    search_prompt = (
        f'Znajdź aktualne ceny koszulki piłkarskiej: "{query}". {verdict_context} '
        f"Szukaj na Vinted.pl, Allegro.pl i eBay. Priorytet: zakończone transakcje (sprzedane); "
        f"jeśli brak, użyj aktywnych ofert. Podaj minimum 3 konkretne ceny z podaniem źródła, tytułu i kwoty. "
        f"Always provide specific prices in numbers. If you find prices in GBP or USD, convert them to PLN "
        f"(1 GBP = {_FX_TO_PLN['GBP']:.0f} PLN, 1 USD = {_FX_TO_PLN['USD']:.1f} PLN) and include the converted PLN value. "
        f"If you cannot find any specific auction prices with numbers — return empty listings array, "
        f"do not describe the search process."
    )

    loop = asyncio.get_running_loop()

    # Krok 1: Szukaj z grounding → naturalny tekst
    # Gemini z grounding czasem zwraca parts=None — retry z uproszczonym promptem
    search_text = ""
    prompts_to_try = [
        search_prompt,
        f"{query} cena PLN kupię sprzedam koszulka",
        f'football shirt "{query.split(" oryginalna")[0]}" price buy sell',
    ]
    for attempt, prompt in enumerate(prompts_to_try):
        try:
            search_resp = await client.aio.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    temperature=0.1,
                ),
            )
            search_text = search_resp.text or ""
        except Exception:
            logger.exception("Market value: Gemini search attempt %d failed for query: %s", attempt + 1, query)
        if search_text.strip():
            break
        logger.warning("Market value: pusta odpowiedź (próba %d/%d) dla query: %s", attempt + 1, len(prompts_to_try), query)

    if not search_text.strip():
        return {"error": "Brak wyników wyszukiwania.", "sample_size": 0, "listings": []}

    # Krok 2: Zamień tekst → JSON (bez grounding, z response_mime_type)
    extract_prompt = (
        f"Na podstawie poniższych danych o cenach koszulki piłkarskiej, zwróć ustrukturyzowany JSON.\n\n"
        f"Dane z wyszukiwania:\n{search_text}\n\n"
        f"Kursy walut: EUR=4.25, GBP=5.0, USD=3.9. Przelicz wszystkie ceny na PLN.\n"
        f"Uwzględnij zarówno sprzedane transakcje jak i aktywne oferty.\n"
        f"Ustaw sample_size na liczbę pozycji w listings. Wylicz median_pln jako medianę cen.\n"
        f"Jeśli nie ma ŻADNYCH cen w danych powyżej, dopiero wtedy ustaw sample_size=0 i listings=[].\n"
        f"Nie wymyślaj cen — tylko te które są w danych powyżej."
    )

    json_schema = {
        "type": "OBJECT",
        "properties": {
            "listings": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "source": {"type": "STRING"},
                        "price_original": {"type": "NUMBER"},
                        "currency_original": {"type": "STRING"},
                        "price_pln": {"type": "NUMBER"},
                        "title": {"type": "STRING"},
                    },
                },
            },
            "median_pln": {"type": "NUMBER"},
            "range_min_pln": {"type": "NUMBER"},
            "range_max_pln": {"type": "NUMBER"},
            "sample_size": {"type": "INTEGER"},
            "confidence": {"type": "STRING"},
        },
        "required": ["listings", "median_pln", "range_min_pln", "range_max_pln", "sample_size"],
    }

    try:
        extract_resp = await loop.run_in_executor(
            None,
            lambda: client.models.generate_content(
                model=model,
                contents=extract_prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=json_schema,
                    temperature=0.0,
                ),
            ),
        )
        text = extract_resp.text or ""
        result = _extract_json(text)
        if result is None:
            logger.warning("Market value: błąd ekstrakcji JSON dla query: %s | %r", query, text[:200])
            return {"error": "Nieprawidłowa odpowiedź modelu.", "sample_size": 0, "listings": []}
        result["source"] = "gemini"
        result.setdefault("query_used", query)
        logger.info("Market value OK: query=%s sample_size=%s median_pln=%s", query, result.get("sample_size"), result.get("median_pln"))
        return result
    except Exception:
        logger.exception("Market value: Gemini JSON extract failed for query: %s", query)
        return {"error": "Nie udało się przetworzyć wyników.", "sample_size": 0, "listings": []}


_ebay_token_cache: Dict[str, Any] = {"token": None, "expires_at": 0.0}
_ebay_token_lock = None  # leniwie tworzony asyncio.Lock (patrz _get_ebay_oauth_token)

# Finding API (stara) filtrowała po walucie EUR globalnie, przeszukując cały
# eBay. Browse API wymaga jednego marketplace per request — żeby nie zawężać
# realnie zasięgu, odpytujemy kilka głównych rynków równolegle i łączymy wyniki.
# EBAY_PL dodany po tym, jak realna aktywna oferta usera (case 20260903-238a181d,
# 1500 PLN, wystawiona na ebay.pl) w ogóle nie była widoczna w wynikach — dla
# polskiego produktu z polskimi użytkownikami polski rynek eBay musi być
# przeszukiwany, nie tylko GB/DE/US.
_EBAY_MARKETPLACES = ["EBAY_GB", "EBAY_DE", "EBAY_US", "EBAY_PL"]


async def _get_ebay_oauth_token() -> Optional[str]:
    """
    OAuth2 client_credentials dla eBay Browse API. Token cache w pamięci
    procesu (ważność ~2h) — bez tego każda wycena robiłaby dodatkowy round-trip.
    Lock zapobiega "thundering herd" (kilka równoległych wycen odświeżających
    token jednocześnie po wygaśnięciu cache).
    """
    import asyncio
    import base64
    import time
    import httpx

    global _ebay_token_lock
    if _ebay_token_lock is None:
        _ebay_token_lock = asyncio.Lock()

    async with _ebay_token_lock:
        now = time.time()
        if _ebay_token_cache["token"] and now < _ebay_token_cache["expires_at"] - 60:
            return _ebay_token_cache["token"]

        app_id = os.getenv("EBAY_APP_ID")
        cert_id = os.getenv("EBAY_CERT_ID_PRD")
        if not app_id or not cert_id:
            return None

        credentials = base64.b64encode(f"{app_id}:{cert_id}".encode()).decode()
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    "https://api.ebay.com/identity/v1/oauth2/token",
                    headers={
                        "Authorization": f"Basic {credentials}",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data={
                        "grant_type": "client_credentials",
                        "scope": "https://api.ebay.com/oauth/api_scope",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            logger.exception("eBay OAuth token request failed")
            return None

        token = data.get("access_token")
        if not token:
            return None
        _ebay_token_cache["token"] = token
        _ebay_token_cache["expires_at"] = now + data.get("expires_in", 7200)
        return token


async def _search_ebay_marketplace(query: str, token: str, marketplace: str) -> List[Dict]:
    """Pojedyncze zapytanie item_summary/search dla jednego marketplace."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.ebay.com/buy/browse/v1/item_summary/search",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-EBAY-C-MARKETPLACE-ID": marketplace,
                },
                params={
                    "q": query,
                    "limit": "10",
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        logger.exception("eBay Browse API call failed (marketplace=%s) for query: %s", marketplace, query)
        return []

    listings = []
    for item in data.get("itemSummaries") or []:
        try:
            price = item.get("price") or {}
            value = float(price.get("value", 0))
            if value <= 0:
                continue
            currency = price.get("currency") or "GBP"
            title = item.get("title", "")
            listings.append({
                "source": "ebay",
                "price_original": value,
                "currency_original": currency,
                "price_pln": to_pln(value, currency),
                "title": title[:80],
            })
        except Exception:
            continue

    return listings


async def estimate_via_ebay_browse(query: str) -> List[Dict]:
    """
    eBay Browse API (item_summary/search) — produkcyjne, realne dane, ale tylko
    aktywne oferty (Browse API nie wspiera wyszukiwania sprzedanych — filtr
    soldItemsOnly jest przez eBay jawnie odrzucany, errorId 12002). To spójne
    z estimate_via_gemini(), która też sięga po aktywne oferty gdy brak
    sprzedanych transakcji, więc nie zmienia to metodologii wyceny.

    Odpytuje kilka głównych marketplace'ów eBay równolegle (Browse API wymaga
    jednego marketplace per request, w przeciwieństwie do starej Finding API,
    która przeszukiwała cały eBay filtrując po walucie) i łączy wyniki.

    Wymaga EBAY_APP_ID (produkcyjny App ID) + EBAY_CERT_ID_PRD w env — jeśli
    brak (np. środowisko bez skonfigurowanych kluczy), zwraca [] i wycena
    spada z powrotem na sam Gemini.
    """
    import asyncio

    token = await _get_ebay_oauth_token()
    if not token:
        return []

    results = await asyncio.gather(
        *(_search_ebay_marketplace(query, token, mp) for mp in _EBAY_MARKETPLACES),
        return_exceptions=True,
    )
    listings: List[Dict] = []
    for r in results:
        if isinstance(r, list):
            listings.extend(r)

    logger.info("eBay Browse API: %d wyników (marketplaces=%s) dla query: %s", len(listings), _EBAY_MARKETPLACES, query)
    return listings


async def estimate_via_ebay(query: str) -> List[Dict]:
    """
    NIEUŻYWANE od migracji na Browse API (patrz estimate_via_ebay_browse) —
    zostawione jako punkt odniesienia/rollback. eBay Finding API
    (findCompletedItems) jest trwale zablokowana na poziomie platformy dla
    tego klucza: HTTP 418 z ebay-proxy-server niezależnie od auth, potwierdzone
    bezpośrednim testem nawet z ważnym Bearer tokenem.
    """
    import httpx

    app_id = os.getenv("EBAY_APP_ID")
    if not app_id:
        return []

    is_sandbox = "SBX" in app_id.upper()
    base_url = (
        "https://svcs.sandbox.ebay.com/services/search/FindingService/v1"
        if is_sandbox
        else "https://svcs.ebay.com/services/search/FindingService/v1"
    )

    params = {
        "OPERATION-NAME": "findCompletedItems",
        "SERVICE-VERSION": "1.0.0",
        "SECURITY-APPNAME": app_id,
        "RESPONSE-DATA-FORMAT": "JSON",
        "keywords": query,
        "categoryId": "11725",  # Soccer-International Clubs (nieużywane — patrz docstring, zostawione dla historii)
        "itemFilter(0).name": "SoldItemsOnly",
        "itemFilter(0).value": "true",
        "itemFilter(1).name": "Currency",
        "itemFilter(1).value": "EUR",
        "sortOrder": "EndTimeSoonest",
        "paginationInput.entriesPerPage": "20",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(base_url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        logger.exception("eBay API call failed for query: %s", query)
        return []

    try:
        items = (
            data.get("findCompletedItemsResponse", [{}])[0]
            .get("searchResult", [{}])[0]
            .get("item", [])
        )
    except Exception:
        return []

    listings = []
    for item in items:
        try:
            price_eur = float(
                item.get("sellingStatus", [{}])[0]
                .get("convertedCurrentPrice", [{}])[0]
                .get("__value__", 0)
            )
            title = item.get("title", [""])[0]
            listings.append({
                "source": "ebay",
                "price_original": price_eur,
                "currency_original": "EUR",
                "price_pln": to_pln(price_eur, "EUR"),
                "title": title[:80],
            })
        except Exception:
            continue

    logger.info("eBay Finding API: %d wyników dla query: %s (sandbox=%s)", len(listings), query, is_sandbox)
    return listings



# ============================================================
# CONFIDENCE-AWARE MATCHING — spec 2026-09-03
# ============================================================
#
# Poprzednie podejście (mediana z top-3 najdrożej wycenionych ofert) naprawiło
# systematyczne zaniżanie ceny (Bayern/Ribéry, PSG/Messi), ale wprowadziło nowy
# problem: gdy zapisana wartość sama była błędna (np. Cubarsí: 168 zł ze
# skrajnie cienkiej próbki sprzed tej poprawki), bramka "nie aktualizuj gdy
# odchylenie >50%" blokowała jej korektę tak samo jak chroniłaby dobrą wartość
# przed zaszumieniem — nie było jak odróżnić "nowa wartość to szum" od "stara
# wartość była błędem, a nowa go naprawia".
#
# Nowe podejście: decyzja o nadpisaniu zależy od JAKOŚCI nowej próbki
# (confidence: high/medium/low), nie od samego odchylenia ceny. Silna próbka
# nadpisuje bezwarunkowo (także starą błędną wartość); słaba próbka nigdy nie
# nadpisuje wartości o wyższej pewności. Do tego: filtr dopasowania per-oferta
# (match_score) zamiast brania tylko kilku najdrożej wycenionych — teraz
# WSZYSTKIE dobrze dopasowane oferty wchodzą do estymaty, jakość dopasowania
# jest wymuszona wcześniej, nie przez wybór "kilku najlepszych po cenie".

_MATCH_MIN = 0.6

# eBay Browse API zwraca WYŁĄCZNIE oferty aktywne (soldItemsOnly jest przez
# eBay jawnie odrzucany, errorId 12002 — patrz docstring estimate_via_ebay_browse).
# "eBay sold" (waga 1.0 w oryginalnym pomyśle) jest więc nieosiągalne przy
# obecnej integracji — świadomie pominięte, nie przeoczone.
_SOURCE_SCORE_EBAY = 0.8
_SOURCE_SCORE_VINTED_ALLEGRO = 0.6
_SOURCE_SCORE_GEMINI_GENERIC = 0.5


def _source_score(listing: Dict) -> float:
    source = str(listing.get("source") or "").lower()
    if "vinted" in source or "allegro" in source:
        return _SOURCE_SCORE_VINTED_ALLEGRO
    if "ebay" in source:
        return _SOURCE_SCORE_EBAY
    return _SOURCE_SCORE_GEMINI_GENERIC  # Gemini-derived, źródło nieokreślone


# Polskie "ł"/"Ł" (i kilka innych europejskich liter częstych w nazwiskach
# piłkarzy) nie mają kanonicznej dekompozycji NFKD — to samodzielne litery, nie
# litera bazowa + znak kombinujący, więc unicodedata.normalize("NFKD", ...) ich
# nie rusza (w przeciwieństwie do ą/ć/ę/ń/ó/ś/ź/ż, które NFKD poprawnie
# rozkłada). Znalezione przez QA/review 2026-09-04 przy okazji fixu na
# Ribéry/Cubarsí — jawna mapa na wypadek liter, których NFKD nie obsłuży.
_NON_NFKD_LETTER_MAP = str.maketrans({
    "ł": "l", "Ł": "L",  # polski
    "đ": "d", "Đ": "D",  # chorwacki/serbski (np. Đorđe)
    "ø": "o", "Ø": "O",  # duński/norweski
})


def _strip_diacritics(text: str) -> str:
    """Usuwa znaki diakrytyczne (Ribéry→Ribery, Cubarsí→Cubarsi, Łukasz→Lukasz)
    — tytuły ofert są zwykle po angielsku bez diakrytyków, podczas gdy nazwiska
    w subject (pochodzące z analizy AI) je zachowują. Bez tego dokładne
    dopasowanie zawodnika w tytule zawodziłoby regularnie."""
    text = text.translate(_NON_NFKD_LETTER_MAP)
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def _title_club_component(title_lower: str, subject: Dict[str, Any]) -> float:
    """1.0 gdy KTÓRYKOLWIEK znaczący token nazwy klubu występuje w tytule, 0.2
    gdy żaden (patrz code review 2026-09-04: 0.5 był zbyt łagodny — brak klubu
    W OGÓLE w tytule to mocny sygnał złego dopasowania, nie powinien ledwo
    obniżać wyniku). Sprawdza WSZYSTKIE tokeny, nie tylko najdłuższy — nazwy
    klubów w subject bywają spolszczone (np. "Bayern Monachium", "Real
    Madryt"), a tytuły ofert są zwykle po angielsku ("Bayern Munich").
    Najdłuższy token to tu często właśnie ta spolszczona nazwa miasta
    ("Monachium"), która nigdy nie wystąpi w angielskim tytule — sprawdzanie
    tylko jego dawało fałszywe 0.5 nawet dla oczywistego dopasowania klubu."""
    club = str(subject.get("club") or "").strip()
    if not club or club.lower() in _SKIP_VALUES:
        return 1.0  # brak deklarowanego klubu — nie karzemy za jego brak w tytule
    tokens = [_strip_diacritics(t.lower()) for t in re.split(r"\s+", club) if len(t) > 2]
    if not tokens:
        return 1.0
    return 1.0 if any(t in title_lower for t in tokens) else 0.2


# Lookbehind (?<![A-Za-z0-9]) wymaga że przed prefiksem NIE ma litery/cyfry —
# bez tego "no"/"nr" dopasowywało się jako podciąg dłuższego słowa (np. "piano.7"
# fałszywie trafiało jako "pia" + "no.7", znalezione przez code review 2026-09-04).
_PLAYER_NUMBER_RE_TEMPLATE = r"(?<![A-Za-z0-9])(?:#|no\.?\s*|nr\.?\s*){num}\b"


def _title_player_component(title_lower: str, subject: Dict[str, Any]) -> float:
    player = str(subject.get("player_name") or "").strip()
    if not player or player.lower() in _SKIP_VALUES:
        return 1.0
    player_norm = _strip_diacritics(player.lower())
    title_norm = _strip_diacritics(title_lower)
    if player_norm in title_norm:
        return 1.0
    number = str(subject.get("player_number") or "").strip()
    if number and number not in _SKIP_VALUES:
        # łapie "#7", "No.7", "No 7", "Nr7", "nr 7" — nie samą gołą liczbę
        # (za duże ryzyko fałszywego trafienia na rozmiar/cenę).
        if re.search(_PLAYER_NUMBER_RE_TEMPLATE.format(num=re.escape(number)), title_lower):
            return 1.0
    return 0.7  # personalizacja bywa pominięta w samym tytule mimo że jest na koszulce — kara, nie dyskwalifikacja


def _match_score(listing: Dict, subject: Dict[str, Any]) -> float:
    """Liczy match_score ∈ [0,1] dla oferty, która JUŻ przeszła twarde bramki
    kategorii/sezonu/wariantu (_filter_listings_by_category,
    _filter_listings_by_relevance — wołane PRZED tym w estimate_market_value;
    zły sezon/wariant/tier odrzuca ofertę CAŁKOWICIE, nie obniża wyniku —
    to dokładnie ten mechanizm, który naprawił Bayern/Ribéry i PSG/Messi, więc
    nie zamieniamy go na "miękkie" ważenie w match_score).

    Blend: 60% dopasowanie tytułu (klub + zawodnik), 40% wiarygodność źródła.
    Wagi 50/50 z pierwszej wersji (code review 2026-09-04) sprawiały, że
    match_score był matematycznie bezwładny dla eBay/Vinted/Allegro — nawet
    kompletnie niedopasowany tytuł (błąd klubu I zawodnika) i tak przechodził
    próg dzięki samej wysokiej wiarygodności źródła, więc realnie filtrowały
    tylko twarde bramki, nie sam match_score. Przy 60/40 + zaostrzonej karze za
    brak klubu w tytule (_title_club_component: 0.2 zamiast 0.5), zupełnie
    niedopasowany tytuł faktycznie odpada nawet dla eBay, a legalne
    dopasowania z pominiętą personalizacją (częsty, niegroźny przypadek)
    nadal przechodzą komfortowo."""
    title_lower = str(listing.get("title") or "").lower()
    title_component = (
        _title_club_component(title_lower, subject) + _title_player_component(title_lower, subject)
    ) / 2
    return 0.6 * title_component + 0.4 * _source_score(listing)


_CONF_HIGH_N = 3
_CONF_HIGH_SPREAD = 0.35
_CONF_MED_SPREAD = 0.6


def _compute_confidence(n: int, spread: float) -> str:
    if n >= _CONF_HIGH_N and spread <= _CONF_HIGH_SPREAD:
        return "high"
    if n == 2 or (n >= _CONF_HIGH_N and spread <= _CONF_MED_SPREAD):
        return "medium"
    return "low"


def _estimate_from_matched(matched: List[Dict]) -> Dict[str, Any]:
    """Liczy price/low/high/matched_count/confidence z listy JUŻ dopasowanych
    ofert (po twardych bramkach + match_score >= _MATCH_MIN). price = mediana,
    low/high = 25./75. percentyl (dla n=1: wszystkie trzy równe tej jednej
    cenie, confidence='low'). Spec 2026-09-03 §5-6."""
    priced = sorted(l["price_pln"] for l in matched if l.get("price_pln"))
    n = len(priced)
    if n == 0:
        return {"price": None, "low": None, "high": None, "matched_count": 0, "confidence": "low", "listings": []}
    if n == 1:
        p = round(priced[0])
        return {"price": p, "low": p, "high": p, "matched_count": 1, "confidence": "low", "listings": matched}
    price = statistics.median(priced)
    q1, _, q3 = statistics.quantiles(priced, n=4, method="inclusive")
    spread = (q3 - q1) / price if price else 1.0
    return {
        "price": round(price),
        "low": round(q1),
        "high": round(q3),
        "matched_count": n,
        "confidence": _compute_confidence(n, spread),
        "listings": matched,
    }


_CONF_RANK = {"low": 0, "medium": 1, "high": 2}
_DEV_TOL = 0.35
# Domyślna ranga gdy stored_confidence jest None (cena zapisana, ale bez
# wypełnionej kolumny confidence — dotyczy WSZYSTKICH pozycji kolekcji od
# razu po tej migracji, zanim backfill_market_values.py --apply ją uzupełni).
# Świadomie 'medium', NIE 'low' (patrz code review 2026-09-04): domyślne 'low'
# pozwalało pojedynczej słabej ofercie nadpisać istniejącą, realną cenę w tym
# przejściowym okresie — dokładnie ten sam wzorzec błędu (Cubarsí), tylko
# odtworzony przez lukę w kolejności wdrożenia zamiast przez próbkę danych.
_UNKNOWN_STORED_CONF_RANK = _CONF_RANK["medium"]


def should_update_market_value(
    stored_price: Optional[float],
    stored_confidence: Optional[str],
    new_price: Optional[float],
    new_confidence: str,
    new_matched_count: int,
) -> bool:
    """Decyzja o nadpisaniu zapisanej wyceny — zależy od JAKOŚCI nowej próbki
    (confidence), NIE od samego odchylenia ceny. Silna próbka nadpisuje
    bezwarunkowo (także starą błędną wartość); słaba próbka nigdy nie nadpisuje
    wartości o wyższej pewności. Spec 2026-09-03 §7.

    Reguły (new_confidence decyduje o gałęzi):
    - brak dopasowanych ofert → nie aktualizuj.
    - high → aktualizuj bezwarunkowo, nawet przy dużym odchyleniu od stored
      (to jedyny sposób, żeby silna próbka mogła skorygować starą błędną
      wartość — Ribéry 185→365, Cubarsí 168→608).
    - medium → aktualizuj jeśli odchylenie ≤ _DEV_TOL, albo jeśli stored jest
      co najwyżej tak samo pewne (medium/low/brak).
    - low → aktualizuj tylko jeśli stored jest puste albo też 'low' (nic
      lepszego nie ma) — nigdy nie nadpisuje medium/high (chroni przed skokiem
      z 1 losowej oferty). stored_confidence=None (cena jest, ale confidence
      jeszcze nieznane) traktowane jako 'medium', NIE 'low' — patrz
      _UNKNOWN_STORED_CONF_RANK."""
    if not new_matched_count or new_price is None:
        return False
    if new_confidence == "high":
        return True
    if stored_price is None:
        return True
    deviation = abs(new_price - stored_price) / stored_price if stored_price else 1.0
    if new_confidence == "medium":
        if deviation <= _DEV_TOL:
            return True
        return _CONF_RANK.get(stored_confidence, _UNKNOWN_STORED_CONF_RANK) <= _CONF_RANK["medium"]
    # new_confidence == "low"
    return _CONF_RANK.get(stored_confidence, _UNKNOWN_STORED_CONF_RANK) == 0


async def refresh_stale_market_values(max_items: int = 50) -> int:
    """
    Odświeża wyceny dla pozycji kolekcji starszych niż 7 dni.
    Wywoływana przez daily task o północy (sam task odpala się codziennie,
    ale każda pozycja jest realnie odświeżana raz na 7 dni — cena używanej
    koszulki nie zmienia się z dnia na dzień, więc częstszy refresh tylko
    zużywałby niepotrzebnie darmowy limit Gemini Search Grounding).
    """
    from datetime import timedelta
    from app.services.database import SessionLocal, CollectionItem, log_market_value_history

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    db = SessionLocal()
    refreshed = 0
    try:
        # Staleness liczona po market_value_last_attempt_at, NIE po
        # market_value_updated_at — inaczej pozycja z trwale słabym rynkiem
        # (matched_count=0/low za każdym razem) kwalifikowałaby się do
        # odświeżenia codziennie zamiast raz na 7 dni.
        items = (
            db.query(CollectionItem)
            .filter(
                CollectionItem.verdict_category != "podrobka",
                (CollectionItem.market_value_last_attempt_at == None) |  # noqa: E711
                (CollectionItem.market_value_last_attempt_at < cutoff),
            )
            .limit(max_items)
            .all()
        )
        for item in items:
            try:
                report_data = {
                    "subject": {
                        "club": item.club,
                        "season": item.season,
                        "brand": item.brand,
                        "player_name": item.player_name,
                        "player_number": item.player_number,
                        "model": item.model_type,
                    },
                    "verdict": {"verdict_category": item.verdict_category},
                }
                result = await estimate_market_value(report_data)
                applied = should_update_market_value(
                    item.market_value_pln, item.market_value_confidence,
                    result.get("price"), result.get("confidence", "low"), result.get("matched_count", 0),
                )
                log_market_value_history(
                    db, item.id, result.get("price"), result.get("low"), result.get("high"),
                    result.get("confidence"), result.get("matched_count", 0), applied,
                )
                if applied:
                    item.market_value_pln = result.get("price")
                    item.market_value_range_min = result.get("low")
                    item.market_value_range_max = result.get("high")
                    item.market_value_sample_size = result.get("matched_count")
                    item.market_value_confidence = result.get("confidence")
                    item.market_value_source = result.get("source") or "gemini"
                    item.market_value_updated_at = datetime.now(timezone.utc)
                    refreshed += 1
                item.market_value_last_attempt_at = datetime.now(timezone.utc)
            except Exception:
                logger.exception("Daily refresh failed for item %s", item.id)
        db.commit()
    finally:
        db.close()
    logger.info("Daily market value refresh: %d items updated", refreshed)
    return refreshed


async def estimate_market_value(report_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Główna funkcja. Kolejność (celowo NIE równoległa): najpierw eBay. Każda
    oferta (eBay i Gemini) musi przejść twarde bramki kategorii/sezonu/wariantu
    (_filter_listings_by_category, _filter_listings_by_relevance) I mieć
    match_score >= _MATCH_MIN (patrz _match_score), żeby wejść do finalnej
    estymaty (_estimate_from_matched: mediana + 25/75 percentyl + confidence).

    Jeśli dopasowane oferty eBay dają confidence="high" samodzielnie, Gemini
    w ogóle nie jest wołane — oszczędza to płatny/limitowany Google Search
    Grounding i skraca czas odpowiedzi. W przeciwnym razie Gemini jest
    dociągane i oba źródła są łączone przed finalnym wyliczeniem.

    Zwraca dict z kluczami: price, low, high, matched_count, confidence,
    listings, source, query_used (i error/None gdy nic się nie znalazło).
    Nadpisanie już zapisanej wyceny w kolekcji (nie dotyczy tej funkcji wprost,
    ale wywołujących ją endpointów) idzie przez should_update_market_value().
    Spec 2026-09-03.
    """
    verdict_category = ((report_data.get("verdict") or {}).get("verdict_category") or "").strip()
    subject = report_data.get("subject") or {}
    query = build_search_query(report_data)
    ebay_query = build_ebay_search_query(report_data)

    ebay_raw = await estimate_via_ebay_browse(ebay_query)
    ebay_gated = _filter_listings_by_category(ebay_raw, verdict_category)
    ebay_gated = _filter_listings_by_relevance(ebay_gated, subject)
    ebay_matched = [l for l in ebay_gated if _match_score(l, subject) >= _MATCH_MIN]

    estimate = _estimate_from_matched(ebay_matched)
    if estimate["confidence"] == "high":
        estimate["source"] = "ebay"
        estimate["query_used"] = ebay_query
        return estimate

    # eBay nie dał samodzielnie wysokiej pewności — dociągamy Gemini i łączymy
    # oba źródła zamiast tracić dobre dane z eBay.
    gemini_result = await estimate_via_gemini(report_data)
    gemini_gated = _filter_listings_by_category(gemini_result.get("listings") or [], verdict_category)
    gemini_gated = _filter_listings_by_relevance(gemini_gated, subject)
    gemini_matched = [l for l in gemini_gated if _match_score(l, subject) >= _MATCH_MIN]

    combined = ebay_matched + gemini_matched
    estimate = _estimate_from_matched(combined)
    gemini_query_used = gemini_result.get("query_used", query)
    if ebay_matched and gemini_matched:
        estimate["source"] = "ebay+gemini"
        estimate["query_used"] = f"eBay: {ebay_query} | Gemini: {gemini_query_used}"
    elif ebay_matched:
        estimate["source"] = "ebay"
        estimate["query_used"] = ebay_query
    elif gemini_matched:
        estimate["source"] = "gemini"
        estimate["query_used"] = gemini_query_used
    else:
        estimate["source"] = None
        estimate["query_used"] = None
        estimate["error"] = gemini_result.get("error") or "Brak wyników po odfiltrowaniu dopasowania."
    return estimate
