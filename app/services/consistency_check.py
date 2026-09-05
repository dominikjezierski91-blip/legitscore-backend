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
Call google_search with query: '[player_name] [club_name] squad number history'
Call google_search with query: '[player_name] [club_name] number [number] since' (if a number is given)
Call google_search with query: '[player_name] career clubs history'
You MUST do these searches before writing any response.
Answering from memory without searching = invalid response.

Your task is NOT to evaluate authenticity of the jersey.
Your task is NOT to determine whether the shirt is fake or original.

Your task is to determine the RANGE of seasons during which the player wore the given number at the given club (e.g. "since 2021/22", or "2018/19 to 2022/23" if it has ended) — NOT to confirm a single assumed season.

CRITICAL — avoid circular reasoning: the input may include a "Season" value, but it comes from an UNCERTAIN visual guess about the jersey, not a confirmed fact. NEVER just restate that season back as if you had independently confirmed it — your job is to find the real range first, then check whether the given season (if any) falls inside it. If no season is given, evaluate club+number consistency on its own, without inventing or assuming a season.

Use web search to look up: which seasons did [player] wear number [N] at [club]? Search reliable sources: official club records, Wikipedia, Transfermarkt, BBC Sport, UEFA.

CRITICAL: You have access to Google Search. You MUST use it to verify player-club-number history.
NEVER say you lack external data or cannot verify — always search first.
NEVER include phrases like "wymagałoby zewnętrznych danych", "nie posiadam danych", "cannot verify without external data" in your response.
Instead: search, find the answer, and report what you found confidently.

Rules:
1. "consistent" means the player did/does wear the given number at the given club, and — if a season was given — that season falls within the player's known range for that club+number. If no season was given, "consistent" means the player+club+number combination itself checks out; do not invent a season to report.
2. "inconsistent" means the player was NEVER at this club in any season, OR never wore the given number at this club (a different number, or a different player, held it instead).
3. "temporal_mismatch" means the player IS or WAS at the club, wearing that number — but a GIVEN season falls clearly outside that range (jersey season predates the player's arrival, or postdates their departure, or a different player held that number then). Use this only when a season WAS given and it conflicts with the range. This indicates a legitimate later (or earlier) personalization, not a fake.
4. "uncertain" means search results are conflicting or inconclusive.
5. Do not evaluate shirt authenticity.
6. Do not infer counterfeit risk.
7. Do not discuss SKU, patches, fabric, or materials.
8. If player_number is provided, you MUST verify it as part of the range — a number the player never wore at this club is "inconsistent".
9. Keep the reason short, factual, in Polish, and phrased as a RANGE — never as confirmation of a single given season.
10. reason field must state what you found, not what you could not find.

Good: 'Zawodnik nosi numer 8 w klubie X od sezonu 2021/22.'
Good: 'Zawodnik nosił numer 10 w klubie X w sezonach 2018/19-2021/22.'
Bad: 'Zawodnik gra w klubie X z numerem 8 w sezonie 2026/27.' (restates the unverified input season as if newly confirmed — circular, forbidden)
Bad: 'Brak danych', 'Nie udało się zweryfikować', 'Wymagałoby zewnętrznych danych'.

Example of temporal_mismatch (given season predates the range): given season is 2023/24, but the player's range at this club+number only starts in 2025/26 → status: "temporal_mismatch", player_actual_season: "2025/26" (report the START of the range — the boundary closest to, but still covering, when the personalization is actually valid).
Example of temporal_mismatch (given season postdates a CLOSED range): the player wore that number at that club only from 2015/16 to 2018/19, then left — given season is 2023/24 → status: "temporal_mismatch", player_actual_season: "2018/19" (report the END of the range — the boundary closest to the given season, since that is the last season the personalization was actually valid; reporting the range's start here would move the correction further away from the truth than necessary).
Rule for choosing which boundary to report: always report whichever end of the player's actual range is CLOSEST to the given (wrong) season — the start if the given season is too early, the end if the given season is too late.
Example of inconsistent: player never played for this club in any season, or never wore this number there → status: "inconsistent", player_actual_season: null.
Example with no season given: player has worn number 8 at this club since 2021/22 → status: "consistent", reason: "Zawodnik nosi numer 8 w klubie X od sezonu 2021/22.", player_actual_season: null (nothing to correct — no season was given to compare against).

When status is temporal_mismatch, you MUST fill player_actual_season with the season the player actually wore that number at that club (format: "YYYY/YY", e.g. "2025/26"). This is used to correct the jersey season in the report.

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

    # uncertain: bez klubu nie da się nawet wyszukać zakresu numerów.
    # SPEC "uczciwe wyświetlanie sezonu" (2026-09-06): sezon NIE jest już
    # wymagany — squad-check orzeka o zakresie sezonów (klub+numer), sezon
    # służy tylko jako opcjonalny cross-check pod temporal_mismatch (patrz
    # PLAYER_CLUB_CONSISTENCY_PROMPT). Wcześniej brak sezonu blokował cały
    # check ("uncertain", bez wywołania Gemini) — mimo że klub+numer same w
    # sobie dawały wystarczającą podstawę do sensownej odpowiedzi.
    if not club_name:
        return _uncertain_insufficient(
            club_name=club_name, missing_club=True, missing_season=not season,
        )

    return await _call_gemini(player_name, club_name, season or None, player_number)


async def _call_gemini(
    player_name: str,
    club_name: str,
    season: Optional[str],
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
    ]
    # SPEC "uczciwe wyświetlanie sezonu" (2026-09-06): sezon opcjonalny —
    # gdy nieznany, mów to wprost zamiast pomijać linię (żeby model nie
    # zgadywał sezonu z kontekstu i nie potwierdzał go jako "dany").
    if season:
        input_lines.append(f"Season (uncertain visual guess — verify against the real range, do not just confirm it): {season}")
    else:
        input_lines.append("Season: unknown — do not assume any season, verify player+club+number history only")
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
