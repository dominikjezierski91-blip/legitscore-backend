"""
SKU Verification Agent — weryfikuje numer SKU koszulki przy użyciu Google Search.

Ten moduł NIE ocenia autentyczności koszulki.
Wynik NIE wpływa na verdict, probabilities, confidence_percent ani confidence_level.
Check jest strictly non-fatal — błąd zwraca bezpieczny fallback.
"""

import json
import logging
import os
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

SKU_VERIFICATION_PROMPT = """You are a football jersey SKU (product code) lookup specialist.

Your ONLY task: search the web for the provided SKU code and report EXACTLY what you find.
Do NOT interpret or judge authenticity. Only report facts.

Search strategy:
1. Search the SKU on official brand sites first:
   nike.com, adidas.com, puma.com, umbro.com, macron.com
2. Search on official club stores:
   store.fcbarcelona.com, store.juventus.com, shop.mancity.com, etc.
3. Search on major authorized retailers and authentication platforms.
4. Search on general marketplaces (eBay, Amazon).
5. Note if SKU appears ONLY on replica/fake sites.

Report what you find using these exact status values:

"found_official" — SKU found on:
   - Official brand website (nike.com, adidas.com, puma.com, umbro.com, macron.com, kappa.com)
   - Official club store (store.fcbarcelona.com, store.juventus.com, shop.mancity.com, etc.)
   Include exact product name found.

"found_authorized" — SKU found on:
   - Major authorized retailers: unisportstore.com, kitbag.com, prodirectsoccer.com,
     footballkit.com, soccerpro.com, intersport.com, jdsports.com
   - Authentication platforms where items are verified before sale:
     KICKS CREW (kickscrew.com), StockX (stockx.com), GOAT (goat.com), Fanatics (fanatics.com)
   - Major general marketplaces (eBay, Amazon) when the listing clearly shows an authentic
     product with matching SKU description.
     NOTE: eBay/Amazon listing of authentic jersey = found_authorized, NOT found_unofficial.
   Include product name.

"found_unofficial" — SKU found ONLY on:
   - Sites explicitly selling replicas/fakes (words like "replica", "fake", "AAA",
     "best quality", "cheap jersey" in URL or title)
   - Chinese wholesale sites (dhgate.com, aliexpress.com, made-in-china.com)
   - Sites with suspicious pricing (jersey for $5–15)
   - Forums/guides about identifying fake jerseys where SKU is listed as
     "commonly found on fakes"
   NOTE: Being on eBay/Amazon does NOT automatically mean found_unofficial.

"not_found" — SKU not found anywhere in search results.

"format_invalid" — SKU format does not match any known brand pattern before even searching:
   * Nike: XXXXXX-XXX (e.g. FN8680-456) — 6 chars + 3 digits
   * Adidas: XXXXXXX (e.g. BI1872S7T1) — alphanumeric mix
   * Puma: XXXXXX-XX — 6 digits + 2 digits
   * ALL digits only (e.g. 123456789) → format_invalid
   * Single letter + 9+ digits (e.g. B118723771) → format_invalid

CRITICAL RULES:
- KICKS CREW, StockX, GOAT → always found_authorized, NEVER found_unofficial.
  These platforms authenticate products before sale.
- eBay listing showing authentic jersey with matching description → found_authorized.
- Only mark found_unofficial when the source is CLEARLY a fake/replica site.
- ALWAYS search before reporting — never guess from format alone unless clearly format_invalid.
- Report the EXACT product name/description you found.
- Report the source URL.
- Write reason in Polish. Be specific about what was found and where.
- Never say "I cannot verify" — always search first.

Return JSON only. No markdown. No extra text:

{
  "status": "found_official | found_authorized | found_unofficial | not_found | format_invalid",
  "confidence": "low | medium | high",
  "found_product_name": "exact product name from source or empty string",
  "reason": "co dokładnie znaleziono i gdzie",
  "source_url": "URL źródła lub pusty string"
}"""

_FALLBACK = {
    "status": "uncertain",
    "confidence": "low",
    "found_product_name": "",
    "reason": "Nie udało się wykonać weryfikacji SKU.",
    "source_url": "",
}


def _fallback() -> Dict[str, Any]:
    return dict(_FALLBACK)


def _not_applicable() -> Dict[str, Any]:
    return {"status": "not_applicable", "confidence": "low", "reason": "", "source_url": ""}


async def run_sku_verification(report_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Uruchamia weryfikację SKU.
    Zawsze zwraca dict — nigdy nie rzuca wyjątku.
    Nie modyfikuje report_data.
    """
    try:
        return await _run(report_data)
    except Exception as e:
        logger.warning("sku_verification nieoczekiwany błąd: %s", e)
        return _fallback()


async def _run(report_data: Dict[str, Any]) -> Dict[str, Any]:
    subject = report_data.get("subject") or {}
    sku = (subject.get("sku") or "").strip()

    if not sku or sku.lower() in {"nieustalone", "unknown", "brak", "n/a", "—"}:
        return _not_applicable()

    club = (subject.get("club") or "").strip()
    season = (subject.get("season") or "").strip()
    brand = (subject.get("brand") or "").strip()
    model = (subject.get("model") or "").strip()

    return await _call_gemini(sku, club, season, brand, model)


async def _call_gemini(
    sku: str,
    club: str,
    season: str,
    brand: str,
    model: str,
) -> Dict[str, Any]:
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        logger.warning("google-genai nie jest dostępne w sku_agent")
        return _fallback()

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return _fallback()

    gemini_model = os.getenv("GEMINI_MODEL", "models/gemini-2.5-flash")

    input_lines = [f"SKU: {sku}"]
    if club:
        input_lines.append(f"Club: {club}")
    if season:
        input_lines.append(f"Season: {season}")
    if brand:
        input_lines.append(f"Brand: {brand}")
    if model:
        input_lines.append(f"Model: {model}")

    try:
        client = genai.Client(api_key=api_key)
        resp = await client.aio.models.generate_content(
            model=gemini_model,
            contents=[types.Content(role="user", parts=[types.Part(text="\n".join(input_lines))])],
            config=types.GenerateContentConfig(
                system_instruction=SKU_VERIFICATION_PROMPT,
                temperature=0.1,
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
    except Exception as e:
        logger.warning("sku_verification błąd API Gemini: %s", e)
        return _fallback()

    text = (resp.text or "").strip()
    if not text:
        return _fallback()

    try:
        result = json.loads(text)
    except Exception:
        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            result = json.loads(text[start:end])
        except Exception:
            logger.warning("sku_verification nieprawidłowy JSON: %r", text[:200])
            return _fallback()

    logger.info(
        "sku_verification: sku=%s club=%s → status=%s confidence=%s",
        sku, club, result.get("status"), result.get("confidence"),
    )
    return result
