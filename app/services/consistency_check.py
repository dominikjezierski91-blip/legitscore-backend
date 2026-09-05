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

from app.services.constants import UNVERIFIED_SUBJECT_VALUES

logger = logging.getLogger(__name__)

PLAYER_CLUB_CONSISTENCY_PROMPT = """You are a factual consistency checker for football jersey personalization.

You have access to Google Search. Use it to verify player-club-number facts before answering.

STEP 1 — MANDATORY BEFORE ANYTHING ELSE:
Call google_search with query: '[player_name] [club_name] squad number [season]'
Then call google_search with query: '[player_name] career clubs history'
You MUST do both searches before writing any response.
Answering from memory without searching = invalid response.

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
2. "inconsistent" means the player was NEVER at this club in any season, OR wore a DIFFERENT number.
3. "temporal_mismatch" means the player IS or WAS at the club — but in a DIFFERENT season than the jersey. Use this when the player joined the club after the jersey season ended, or left before the jersey season. This indicates a legitimate later personalization, not a fake.
4. "uncertain" means search results are conflicting or inconclusive.
5. Do not evaluate shirt authenticity.
6. Do not infer counterfeit risk.
7. Do not discuss SKU, patches, fabric, or materials.
8. Keep the reason short, factual, and in Polish.
9. If player_number is provided, you MUST verify it — a wrong number is "inconsistent" (not temporal_mismatch).
10. reason field must state what you found, not what you could not find.
Good: 'Zawodnik grał w klubie X z numerem Y w sezonie Z.'
Bad: 'Brak danych', 'Nie udało się zweryfikować', 'Wymagałoby zewnętrznych danych'.

Example of temporal_mismatch: jersey season is 2023/24, player joined the club in 2025 → status: "temporal_mismatch", player_actual_season: "2025/26".
Example of inconsistent: player never played for this club in any season → status: "inconsistent", player_actual_season: null.

When status is temporal_mismatch, you MUST fill player_actual_season with the season the player actually played at this club (format: "YYYY/YY", e.g. "2025/26"). This is used to correct the jersey season in the report.

Return JSON only. No markdown. No extra text:

{
  "status": "consistent | inconsistent | temporal_mismatch | uncertain",
  "confidence": "low | medium | high",
  "reason": "",
  "player_actual_season": null,
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


def _uncertain_insufficient(club_name: str = "", missing_club: bool = True, missing_season: bool = True) -> Dict[str, Any]:
    """SPEC evidence-merge sekcja 8 (2026-09-05, case 15364d60): generyczny
    "brak klubu lub sezonu" mylił, gdy klub był w rzeczywistości znany (np.
    "FC Barcelona" widoczne wyżej w raporcie) i brakowało tylko sezonu —
    czytelnik zakładał, że oba pola są nieznane. Teraz komunikat wskazuje
    dokładnie, czego brakuje, i podaje znany klub, jeśli jest dostępny."""
    if missing_club and missing_season:
        detail = "brak klubu i sezonu"
    elif missing_club:
        detail = "brak klubu"
    elif club_name:
        detail = f"brak sezonu (klub: {club_name})"
    else:
        detail = "brak sezonu"
    return {
        "status": "uncertain",
        "confidence": "low",
        "reason": f"Niewystarczające dane do sprawdzenia zgodności — {detail}.",
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


def _real_value(raw: Optional[str]) -> str:
    """Zwraca "" dla placeholderów Agenta A (np. "nieustalone") — bez tego
    truthiness-check niżej traktuje placeholder jak realną wartość i woła
    Gemini z fikcyjnym zawodnikiem/klubem jako wejściem (patrz incydent
    2026-08-24, ten sam wzorzec co w sku_agent.py/pdf_report.py)."""
    value = (raw or "").strip()
    return "" if value.lower() in UNVERIFIED_SUBJECT_VALUES else value


async def _run(report_data: Dict[str, Any]) -> Dict[str, Any]:
    subject = report_data.get("subject") or {}
    player_name = _real_value(subject.get("player_name"))
    club_name = _real_value(subject.get("club"))
    season = _real_value(subject.get("season"))
    player_number = _real_value(subject.get("player_number")) or None

    personalization = report_data.get("personalization_assessment") or {}
    personalization_status = (personalization.get("status") or "").lower()

    # not_applicable: brak personalizacji lub brak player_name
    if not player_name or personalization_status == "brak":
        return _not_applicable()

    # uncertain: mamy zawodnika, ale za mało danych do oceny
    if not club_name or not season:
        return _uncertain_insufficient(
            club_name=club_name, missing_club=not club_name, missing_season=not season,
        )

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
