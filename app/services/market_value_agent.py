"""
Market Value Agent — szacuje wartość rynkową koszulki piłkarskiej.

Źródła:
  - Gemini 2.5 z Google Search Grounding (Vinted, Allegro, eBay)
  - eBay Finding API (aktywowane gdy EBAY_APP_ID dostępny)
"""
import json
import logging
import os
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


def _get_client() -> Optional[genai.Client]:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None
    return genai.Client(api_key=api_key)


def build_search_query(report_data: Dict[str, Any]) -> str:
    """Buduje query wyszukiwania na podstawie danych z raportu."""
    subject = report_data.get("subject") or {}
    parts: List[str] = []
    for field in ["club", "season", "brand"]:
        val = subject.get(field)
        if val and str(val).lower().strip() not in _SKIP_VALUES:
            parts.append(str(val).strip())
    player = subject.get("player_name")
    if player and str(player).lower().strip() not in _SKIP_VALUES:
        parts.append(str(player).strip())
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

    prompt = f"""Jesteś ekspertem rynku koszulek piłkarskich.

Przeszukaj aktualne aukcje i znajdź ceny sprzedaży koszulki:
"{query}"

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
