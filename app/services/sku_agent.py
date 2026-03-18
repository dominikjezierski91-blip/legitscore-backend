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

SKU_VERIFICATION_PROMPT = """You are a football jersey SKU (product code) verification specialist.

You have access to Google Search. Use it to verify the given SKU against the described jersey.

Your task is ONLY to check whether the provided SKU matches the described jersey (club, season, model, brand).

Search for the SKU on official brand websites and retailers (Adidas, Nike, Puma, etc.).

Rules:
1. "confirmed" — search results clearly show this SKU matches the described jersey.
2. "mismatch" — search results show this SKU belongs to a DIFFERENT jersey (wrong club, season, or model).
3. "not_found" — SKU not found in any reliable source.
4. "uncertain" — conflicting or inconclusive search results.
5. "invalid" — the SKU code was found but has a non-standard format that does not match any known brand format (Nike, Adidas, Puma, etc.), OR the SKU appears in search results only on counterfeit/replica sites, OR the format is clearly fabricated (random letters+numbers without brand pattern). This is a stronger signal than "not_found".
6. Do not evaluate jersey authenticity.
6. Do not discuss fabric, stitching, or physical properties.
7. Keep the reason short, factual, and in Polish. Write only what was found — do not mention
   search limitations, external databases, or inability to verify.
   Examples of good reason text:
   - "Kod odpowiada koszulce FC Barcelona 2023/24 domowa."
   - "Kod wskazuje na inny model (Real Madrid wyjazdowa 2022/23)."
   - "Kod nie został znaleziony w dostępnych wynikach."
   - "Wyniki są niejednoznaczne — kod pojawia się przy różnych modelach."
8. Include the source URL if you find one.

Return JSON only. No markdown. No extra text:

{
  "status": "confirmed | mismatch | not_found | uncertain | invalid",
  "confidence": "low | medium | high",
  "reason": "",
  "source_url": ""
}"""

_FALLBACK = {
    "status": "uncertain",
    "confidence": "low",
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
