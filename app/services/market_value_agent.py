"""
Market Value Agent — szacuje wartość rynkową koszulki piłkarskiej.

Źródła:
  - Gemini 2.5 z Google Search Grounding (Vinted, Allegro, eBay)
  - eBay Finding API (findCompletedItems) gdy EBAY_APP_ID dostępny
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


async def estimate_via_ebay(query: str) -> List[Dict]:
    """
    eBay Finding API — findCompletedItems.
    Uwaga: EBAY_APP_ID=...SBX... to klucz sandbox (dane testowe).
    Dla realnych danych potrzebny klucz produkcyjny (PRD).
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
        "categoryId": "32849",  # Soccer-International Clubs
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
    gemini_result = await estimate_via_gemini(report_data)

    ebay_listings = await estimate_via_ebay(build_search_query(report_data))
    if ebay_listings:
        all_listings = (gemini_result.get("listings") or []) + ebay_listings
        stats = _recalculate_stats(all_listings)
        if stats.get("sample_size", 0) > 0:
            gemini_result.update(stats)
            gemini_result["listings"] = all_listings
            gemini_result["source"] = "gemini+ebay"

    return gemini_result
