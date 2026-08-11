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
_EBAY_MARKETPLACES = ["EBAY_GB", "EBAY_DE", "EBAY_US"]


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


def _recalculate_stats(listings: List[Dict]) -> Dict[str, Any]:
    """Przelicza median/min/max/sample_size z listy ogłoszeń."""
    prices = sorted(l["price_pln"] for l in listings if l.get("price_pln"))
    if not prices:
        return {"sample_size": 0}
    n = len(prices)
    median = prices[n // 2] if n % 2 else (prices[n // 2 - 1] + prices[n // 2]) / 2
    return {
        "median_pln": round(median),
        "range_min_pln": round(min(prices)),
        "range_max_pln": round(max(prices)),
        "sample_size": n,
    }


async def refresh_stale_market_values(max_items: int = 50) -> int:
    """
    Odświeża wyceny dla pozycji kolekcji starszych niż 23h.
    Wywoływana przez daily task o północy.
    """
    from datetime import timedelta
    from app.services.database import SessionLocal, CollectionItem

    cutoff = datetime.now(timezone.utc) - timedelta(hours=23)
    db = SessionLocal()
    refreshed = 0
    try:
        items = (
            db.query(CollectionItem)
            .filter(
                (CollectionItem.market_value_updated_at == None) |  # noqa: E711
                (CollectionItem.market_value_updated_at < cutoff)
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
                if result.get("sample_size", 0) > 0:
                    item.market_value_pln = result.get("median_pln")
                    item.market_value_range_min = result.get("range_min_pln")
                    item.market_value_range_max = result.get("range_max_pln")
                    item.market_value_sample_size = result.get("sample_size")
                    item.market_value_source = result.get("source", "gemini")
                    item.market_value_updated_at = datetime.now(timezone.utc)
                    refreshed += 1
            except Exception:
                logger.exception("Daily refresh failed for item %s", item.id)
        db.commit()
    finally:
        db.close()
    logger.info("Daily market value refresh: %d items updated", refreshed)
    return refreshed


async def estimate_market_value(report_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Główna funkcja — łączy Gemini + eBay (gdy dostępny).
    """
    import asyncio

    gemini_result, ebay_listings = await asyncio.gather(
        estimate_via_gemini(report_data),
        estimate_via_ebay_browse(build_search_query(report_data)),
    )
    if ebay_listings:
        all_listings = (gemini_result.get("listings") or []) + ebay_listings
        stats = _recalculate_stats(all_listings)
        if stats.get("sample_size", 0) > 0:
            gemini_result.update(stats)
            gemini_result["listings"] = all_listings
            gemini_result["source"] = "gemini+ebay"

    return gemini_result
