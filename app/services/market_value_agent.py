"""
Market Value Agent — szacuje wartość rynkową koszulki piłkarskiej.

Źródła:
  - Gemini 2.5 z Google Search Grounding (Vinted, Allegro, eBay)
  - eBay Finding API (aktywowane gdy EBAY_APP_ID dostępny)
"""
import json
import logging
import os
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
    "podrobka": "oryginalna",  # dla podróbek szukamy ceny oryginału jako punktu odniesienia
}


def _get_client() -> Optional[genai.Client]:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None
    return genai.Client(api_key=api_key)


def build_search_query(report_data: Dict[str, Any]) -> str:
    """
    Buduje query wyszukiwania na podstawie wszystkich dostępnych parametrów raportu.
    Uwzględnia: klub, sezon, markę, zawodnika, numer, model, typ koszulki (verdict).
    """
    subject = report_data.get("subject") or {}
    verdict = report_data.get("verdict") or {}
    parts: List[str] = []

    # Podstawowe dane koszulki
    for field in ["club", "season", "brand"]:
        val = subject.get(field)
        if val and str(val).lower().strip() not in _SKIP_VALUES:
            parts.append(str(val).strip())

    # Model (np. Vapor Match, Stadium, Authentic)
    model = subject.get("model")
    if model and str(model).lower().strip() not in _SKIP_VALUES:
        parts.append(str(model).strip())

    # Zawodnik + numer
    player = subject.get("player_name")
    if player and str(player).lower().strip() not in _SKIP_VALUES:
        parts.append(str(player).strip())
    number = subject.get("player_number")
    if number and str(number).lower().strip() not in _SKIP_VALUES:
        parts.append(f"#{str(number).strip()}")

    # Typ koszulki z werdyktu — kluczowe dla wyceny
    verdict_cat = (verdict.get("verdict_category") or "").strip()
    if verdict_cat and verdict_cat in _VERDICT_SEARCH_TERMS:
        parts.append(_VERDICT_SEARCH_TERMS[verdict_cat])

    parts.append("koszulka piłkarska")
    return " ".join(parts)


def to_pln(price: float, currency: str) -> float:
    rate = _FX_TO_PLN.get((currency or "PLN").upper().strip(), 1.0)
    return round(price * rate, 2)


async def estimate_via_gemini(report_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Szacuje wartość rynkową używając Gemini z Google Search Grounding.
    Zwraca dict z: median_pln, range_min_pln, range_max_pln, sample_size, listings, source.
    """
    client = _get_client()
    if client is None:
        return {"error": "Brak klucza Gemini API", "sample_size": 0, "listings": []}

    query = build_search_query(report_data)
    if not query.replace("koszulka piłkarska", "").strip():
        return {"error": "Za mało danych do wyceny (brak klubu/sezonu/gracza).", "sample_size": 0, "listings": []}

    model = os.getenv("GEMINI_MODEL", "models/gemini-2.5-flash")

    verdict_cat = ((report_data.get("verdict") or {}).get("verdict_category") or "").strip()
    verdict_context = {
        "oryginalna_sklepowa": "Szukaj oryginalnych koszulek sklepowych (authentic retail). NIE szukaj replik ani podróbek.",
        "meczowa": "Szukaj koszulek meczowych (match worn, match issued, player issue). To są najdroższe egzemplarze.",
        "oficjalna_replika": "Szukaj oficjalnych replik (replica, fan version). NIE szukaj wersji player/authentic.",
        "edycja_limitowana": "Szukaj edycji limitowanych (limited edition, special edition).",
        "treningowa_custom": "Szukaj koszulek treningowych lub customowych.",
        "podrobka": "Koszulka to prawdopodobnie podróbka. Szukaj cen ORYGINALNYCH koszulek jako punkt odniesienia dla wartości rynkowej autentycznego egzemplarza.",
    }.get(verdict_cat, "Szukaj tej koszulki piłkarskiej.")

    prompt = f"""Jesteś ekspertem rynku koszulek piłkarskich.

Przeszukaj aktualne aukcje i znajdź ceny sprzedaży koszulki:
"{query}"

Kontekst: {verdict_context}

Szukaj na: Vinted.pl, Allegro.pl, eBay (cały świat).
Preferuj zakończone transakcje (sold/sprzedane) nad aktywnymi ogłoszeniami.
Szukaj podobnych egzemplarzy jeśli dokładnego modelu nie ma.

Zwróć WYŁĄCZNIE poprawny JSON (bez markdown, bez komentarzy):
{{
  "listings": [
    {{"source": "vinted", "price_original": 350, "currency_original": "PLN", "price_pln": 350, "title": "krótki tytuł"}},
    {{"source": "allegro", "price_original": 399, "currency_original": "PLN", "price_pln": 399, "title": "krótki tytuł"}},
    {{"source": "ebay", "price_original": 45, "currency_original": "EUR", "price_pln": 191, "title": "krótki tytuł"}}
  ],
  "median_pln": 370,
  "range_min_pln": 290,
  "range_max_pln": 490,
  "sample_size": 5,
  "query_used": "{query}",
  "confidence": "wysoka"
}}

Kursy walut: EUR=4.25, GBP=5.0, USD=3.9.
Jeśli masz mniej niż 2 aukcje, zwróć sample_size: 0 i listings: [].
Nie wymyślaj cen — tylko realne dane z wyszukiwania."""

    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.1,
            ),
        )
        text = (response.text or "").strip()
        # Usuń markdown jeśli obecny
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()
        result = json.loads(text)
        result["source"] = "gemini"
        return result
    except json.JSONDecodeError:
        logger.warning("Market value: Gemini returned non-JSON for query: %s", query)
        return {"error": "Nieprawidłowa odpowiedź modelu.", "sample_size": 0, "listings": []}
    except Exception:
        logger.exception("Market value Gemini call failed for query: %s", query)
        return {"error": "Nie udało się oszacować wartości rynkowej.", "sample_size": 0, "listings": []}


async def estimate_via_ebay(query: str) -> List[Dict]:
    """
    eBay Finding API — aktywowane gdy EBAY_APP_ID dostępny.
    Podpinane gdy AppID przyjdzie — placeholder zwraca [].
    """
    app_id = os.getenv("EBAY_APP_ID")
    if not app_id:
        return []
    # TODO: implement eBay Finding API findCompletedItems
    return []


async def refresh_stale_market_values(max_items: int = 50) -> int:
    """
    Odświeża wyceny dla pozycji kolekcji starszych niż 23h.
    Wywoływana przez daily task o północy.
    Zwraca liczbę odświeżonych pozycji.
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
    Zwraca ujednolicony wynik z median_pln, range, sample_size, listings.
    """
    gemini_result = await estimate_via_gemini(report_data)

    # eBay placeholder (wchodzi po podpięciu AppID)
    # ebay_listings = await estimate_via_ebay(build_search_query(report_data))
    # if ebay_listings:
    #     gemini_result["listings"] = (gemini_result.get("listings") or []) + ebay_listings
    #     ... recalculate median

    return gemini_result
