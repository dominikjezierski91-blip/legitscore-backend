"""
Pomocniczy factual check: spójność personalizacji zawodnika z klubem i sezonem.

Ten moduł NIE ocenia autentyczności koszulki.
Wynik NIE wpływa na verdict, probabilities, confidence_percent ani confidence_level.
Check jest strictly non-fatal — błąd zwraca bezpieczny fallback.
"""

import json
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

PLAYER_CLUB_CONSISTENCY_PROMPT = """You are a factual consistency checker for football jersey personalization.

You have access to Google Search. Use it to verify player-club-number facts before answering.

Your task is NOT to evaluate authenticity of the jersey.
Your task is NOT to determine whether the shirt is fake or original.

Your task is only to check whether the detected player personalization is factually consistent with the given club and season.

Use web search to look up: which squad number did [player] wear at [club] during [season]?
Search for reliable sources: official club records, Wikipedia, transfermarkt, BBC Sport, UEFA.

CRITICAL: You have access to Google Search. You MUST use it to verify player-club-season consistency.
NEVER say you lack external data or cannot verify — always search first.
If search returns no results for a specific season, state what you found and what season the jersey appears to be from based on visual cues.
NEVER include phrases like "wymagałoby zewnętrznych danych", "nie posiadam danych", "cannot verify without external data" in your response.
Instead: search, find the answer, and report what you found confidently.

Rules:
1. "consistent" means the player was at the given club in the given season AND wore the given number (if provided).
2. "inconsistent" means the player was NOT at the club in that season, OR wore a DIFFERENT number.
3. "uncertain" means search results are conflicting or inconclusive.
4. Do not evaluate shirt authenticity.
5. Do not infer counterfeit risk.
6. Do not discuss SKU, patches, fabric, or materials.
7. Keep the reason short, factual, and in Polish.
8. If player_number is provided, you MUST verify it — a wrong number is "inconsistent".

Return JSON only. No markdown. No extra text:

{
  "status": "consistent | inconsistent | uncertain",
  "confidence": "low | medium | high",
  "reason": "",
  "notes": []
}"""

_FALLBACK = {
    "status": "uncertain",
    "confidence": "low",
    "reason": "Nie udało się wykonać dodatkowego sprawdzenia zgodności personalizacji.",
    "notes": [],
}


def _fallback() -> Dict[str, Any]:
    return dict(_FALLBACK)


def _not_applicable() -> Dict[str, Any]:
    return {"status": "not_applicable", "confidence": "low", "reason": "", "notes": []}


def _uncertain_insufficient() -> Dict[str, Any]:
    return {
        "status": "uncertain",
        "confidence": "low",
        "reason": "Niewystarczające dane do sprawdzenia zgodności (brak klubu lub sezonu).",
        "notes": [],
    }


async def run_player_club_consistency_check(report_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Uruchamia pomocniczy check spójności personalizacji.
    Zawsze zwraca dict — nigdy nie rzuca wyjątku.
    Nie modyfikuje report_data.
    """
    try:
        return await _run(report_data)
    except Exception as e:
        logger.warning("player_club_consistency_check nieoczekiwany błąd: %s", e)
        return _fallback()


async def _run(report_data: Dict[str, Any]) -> Dict[str, Any]:
    subject = report_data.get("subject") or {}
    player_name = (subject.get("player_name") or "").strip()
    club_name = (subject.get("club") or "").strip()
    season = (subject.get("season") or "").strip()
    player_number = (subject.get("player_number") or "").strip() or None

    personalization = report_data.get("personalization_assessment") or {}
    personalization_status = (personalization.get("status") or "").lower()

    # not_applicable: brak personalizacji lub brak player_name
    if not player_name or personalization_status == "brak":
        return _not_applicable()

    # uncertain: mamy zawodnika, ale za mało danych do oceny
    if not club_name or not season:
        return _uncertain_insufficient()

    return await _call_gemini(player_name, club_name, season, player_number)


async def _call_gemini(
    player_name: str,
    club_name: str,
    season: str,
    player_number: Optional[str],
) -> Dict[str, Any]:
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        logger.warning("google-genai nie jest dostępne w consistency_check")
        return _fallback()

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return _fallback()

    # Consistency check używa flash — pro zwraca parts=None przy grounding+JSON
    model = os.getenv("CONSISTENCY_MODEL", "models/gemini-2.5-flash")

    input_lines = [
        f"Player name: {player_name}",
        f"Club: {club_name}",
        f"Season: {season}",
    ]
    if player_number:
        input_lines.append(f"Player number: {player_number}")

    try:
        client = genai.Client(api_key=api_key)
        resp = await client.aio.models.generate_content(
            model=model,
            contents=[types.Content(role="user", parts=[types.Part(text="\n".join(input_lines))])],
            config=types.GenerateContentConfig(
                system_instruction=PLAYER_CLUB_CONSISTENCY_PROMPT,
                temperature=0.1,
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
    except Exception as e:
        logger.warning("player_club_consistency_check błąd API Gemini: %s", e)
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
            logger.warning("player_club_consistency_check nieprawidłowy JSON: %r", text[:200])
            return _fallback()

    logger.info(
        "player_club_consistency_check: player=%s club=%s season=%s → status=%s confidence=%s",
        player_name, club_name, season, result.get("status"), result.get("confidence"),
    )
    return result
