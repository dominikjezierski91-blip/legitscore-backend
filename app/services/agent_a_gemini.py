import os
import json
import time
import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from google import genai
from google.genai import types

from app.models.decision import Decision, Reason, Trace, Recommendation

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "models/gemini-2.5-pro"
DEFAULT_PROMPT_VERSION = "a-2.0"

_client: Optional[genai.Client] = None

# ============================================================
# PRECHECK PROMPTS
# ============================================================

COVERAGE_CHECK_PROMPT = """You are an inspection pre-check system for football jersey authentication.

Your task is NOT to authenticate the jersey.

Your task is only to detect which types of views are present in the provided image set.

You must detect the following views:

REQUIRED views (essential for forensic analysis):
- front_full: full front view of the jersey (whole shirt visible)
- back_full: full back view of the jersey (whole shirt visible)
- crest_or_brand_closeup: close-up of the club crest or manufacturer logo (Nike, Adidas, etc.)
- identity_tag: any identity tag — inner neck tag, neck print with washing instructions, product code tag, or wash label

RECOMMENDED views (improve analysis but are NOT required):
- material_closeup: close-up of fabric texture or material structure
- paper_sku_tag: hanging paper tag with barcode or SKU number
- patch_closeup: close-up of sleeve patches (league badge, cup patch, etc.)
- personalization_closeup: close-up of player name or number if personalized
- sleeve_details: sleeve area or armband details

CRITICAL RULES:

1. Photos from marketplace listings (Vinted, eBay, Allegro) often show the SAME jersey from different angles, with different lighting or backgrounds. This is NORMAL.

2. Only flag "multiple items" if you are 100% certain the photos show genuinely DIFFERENT jerseys (different teams, different colors).

3. A general full-body shot counts as front_full or back_full if the full side is visible.

4. crest_or_brand_closeup is true ONLY if there is a dedicated close-up of the crest or logo — a partial logo visible in a general shot does NOT count.

5. identity_tag is true if ANY of the following is visible: inner neck tag, neck label with product info, neck print, hang tag with product code.

6. Do NOT judge authenticity. Only detect which views are present.

7. Set can_continue=false only when at least one REQUIRED view is missing.

Return JSON only:

{
  "can_continue": true,
  "detected_views": {
    "front_full": true,
    "back_full": false,
    "crest_or_brand_closeup": true,
    "identity_tag": false,
    "material_closeup": true,
    "paper_sku_tag": false,
    "patch_closeup": false,
    "personalization_closeup": false,
    "sleeve_details": false
  },
  "missing_required": [],
  "missing_optional": [],
  "message": ""
}

In missing_required list the REQUIRED view keys that are absent.
In missing_optional list the RECOMMENDED view keys that are absent.
If can_continue=false, explain briefly in "message" what specific images are needed.
IMPORTANT: The "message" field MUST be in Polish language, user-friendly, and specific.
Return JSON only. No markdown. No extra text."""

QUALITY_CHECK_PROMPT = """You are a photo quality inspection system for football jersey authentication.

Your task is NOT to authenticate the jersey.

Your task is only to determine whether the provided images are of sufficient quality to perform a reliable inspection.

Evaluate:

- image sharpness
- distance from key elements
- lighting
- visibility of details
- ability to inspect fabric texture
- readability of tags or labels
- clarity of crest or logo
- clarity of personalization if present

Important rules:

1. Do not judge authenticity.
2. Only judge whether inspection is possible.
3. If images are blurry, too far away, too dark, or compressed, mark them as issues.
4. Be conservative. If critical details cannot be inspected, the analysis should not continue.
5. Do not infer authenticity or final verdict.
6. CRITICAL: Only evaluate quality of image categories that are ACTUALLY PRESENT in the photo set.
   Do NOT report "not_visible" for a category that is simply absent from the photos — that is a coverage issue, not a quality issue.
   If you are told a category is absent, ignore it completely. Do not create a quality issue for it.

Return JSON only:

{
  "can_continue": true,
  "issues": [],
  "message": ""
}

or

{
  "can_continue": false,
  "issues": [
    {
      "area": "material_closeup | tag_sku | crest_logo | personalization | general",
      "issue": "blur | too_far | low_light | compression | not_visible"
    }
  ],
  "message": ""
}

If can_continue=false, provide a short user-friendly explanation in "message".
IMPORTANT: The "message" field MUST be in Polish language, user-friendly, and specific.
Return JSON only. No markdown. No extra text."""


def _get_api_key() -> Optional[str]:
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


def _get_client() -> Optional[genai.Client]:
    global _client
    api_key = _get_api_key()
    if not api_key:
        return None
    if _client is None:
        _client = genai.Client(api_key=api_key)
    return _client


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_system_prompt() -> str:
    """
    Load Agent A system prompt in the following order:
    1. A_PROMPT_TEXT env (non-empty),
    2. A_PROMPT_FILE env (absolute or relative to repo root),
    3. default file prompt_a.txt at repo root,
    4. final hardcoded fallback.
    """
    env_text = os.getenv("A_PROMPT_TEXT")
    if env_text and env_text.strip():
        return env_text

    def _read_prompt_file(path: Path) -> Optional[str]:
        try:
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                if text.strip():
                    logger.info("Loaded Agent A prompt from %s", path)
                    return text
        except Exception:
            logger.exception("Failed to read Agent A prompt file: %s", path)
        return None

    # Repo root = two levels above this file: app/services/agent_a_gemini.py -> app -> repo root
    repo_root = Path(__file__).resolve().parents[2]

    file_from_env = os.getenv("A_PROMPT_FILE")
    if file_from_env:
        candidate = Path(file_from_env)
        if not candidate.is_absolute():
            candidate = repo_root / candidate
        text = _read_prompt_file(candidate)
        if text is not None:
            return text

    # Default prompt file at repo root.
    default_file = repo_root / "prompt_a.txt"
    text = _read_prompt_file(default_file)
    if text is not None:
        return text

    # Fallback: minimal forensic prompt with fixed REPORT_DATA schema.
    return (
        "AGENT A — DECISION ENGINE (FORENSICS) — v2.0\n\n"
        "Zwróć WYŁĄCZNIE poprawny JSON (RFC 8259) w formacie:\n"
        "{ \"REPORT_DATA\": { ... } } zgodnie z poniższym schematem.\n\n"
        "REPORT_DATA musi mieć dokładnie następującą strukturę (klucze i typy):\n"
        "{\n"
        "  \"report_id\": \"...\",\n"
        "  \"analysis_date\": \"...\",\n"
        "  \"subject\": {\n"
        "    \"club\": \"...\",\n"
        "    \"season\": \"...\",\n"
        "    \"model\": \"...\",\n"
        "    \"brand\": \"...\",\n"
        "    \"player_name\": \"...\",\n"
        "    \"player_number\": \"...\"\n"
        "  },\n"
        "  \"verdict\": {\n"
        "    \"label\": \"...\",\n"
        "    \"verdict_category\": \"oryginalna_sklepowa|meczowa|oficjalna_replika|podrobka|edycja_limitowana|treningowa_custom\",\n"
        "    \"confidence_level\": \"bardzo_wysoki|wysoki|sredni|ograniczony\",\n"
        "    \"confidence_percent\": 0,\n"
        "    \"summary\": \"...\"\n"
        "  },\n"
        "  \"probabilities\": {\n"
        "    \"oryginalna_sklepowa\": 0,\n"
        "    \"meczowa\": 0,\n"
        "    \"oficjalna_replika\": 0,\n"
        "    \"podrobka\": 0,\n"
        "    \"edycja_limitowana\": 0,\n"
        "    \"treningowa_custom\": 0\n"
        "  },\n"
        "  \"meczowa_detail\": {\n"
        "    \"status\": \"match_worn|match_prepared|player_issue|unknown\",\n"
        "    \"confidence\": \"wysoka|srednia|niska\",\n"
        "    \"notes\": \"...\"\n"
        "  },\n"
        "  \"personalization_assessment\": {\n"
        "    \"status\": \"fabryczna|pozniejsza|niezweryfikowana|brak\",\n"
        "    \"confidence\": \"wysoka|srednia|niska\",\n"
        "    \"notes\": \"...\"\n"
        "  },\n"
        "  \"decision_matrix\": [\n"
        "    {\"criterion\": \"Metki / SKU / data / fabryka\", \"code\": \"A\", \"weight\": 5, \"status\": \"GREEN|YELLOW|RED|UNKNOWN\", \"observation\": \"...\", \"impact\": \"...\"},\n"
        "    {\"criterion\": \"Zgodność SKU z modelem / sezonem\", \"code\": \"B\", \"weight\": 5, \"status\": \"GREEN|YELLOW|RED|UNKNOWN\", \"observation\": \"...\", \"impact\": \"...\"},\n"
        "    {\"criterion\": \"Haft / logo / herb / patche\", \"code\": \"C\", \"weight\": 4, \"status\": \"GREEN|YELLOW|RED|UNKNOWN\", \"observation\": \"...\", \"impact\": \"...\"},\n"
        "    {\"criterion\": \"Materiał / technologia / krój\", \"code\": \"D\", \"weight\": 3, \"status\": \"GREEN|YELLOW|RED|UNKNOWN\", \"observation\": \"...\", \"impact\": \"...\"},\n"
        "    {\"criterion\": \"Personalizacja (font / numer / technika)\", \"code\": \"E\", \"weight\": 3, \"status\": \"GREEN|YELLOW|RED|UNKNOWN\", \"observation\": \"...\", \"impact\": \"...\"},\n"
        "    {\"criterion\": \"Squad check (zawodnik / numer / sezon)\", \"code\": \"F\", \"weight\": 2, \"status\": \"GREEN|YELLOW|RED|UNKNOWN\", \"observation\": \"...\", \"impact\": \"...\"},\n"
        "    {\"criterion\": \"Źródło zakupu / kontekst\", \"code\": \"G\", \"weight\": 1, \"status\": \"GREEN|YELLOW|RED|UNKNOWN\", \"observation\": \"...\", \"impact\": \"...\"}\n"
        "  ],\n"
        "  \"key_evidence\": [],\n"
        "  \"missing_data\": [],\n"
        "  \"recommendations\": [],\n"
        "  \"notes\": {\"mode_note\": \"...\"}\n"
        "}\n\n"
        "Nie dodawaj innych pól ani struktur poza opisanym schematem.\n"
    )


def _extract_first_json_object(text: str) -> str:
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object start found")
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ValueError("Unbalanced JSON braces")


def _clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, n))


def _looks_like_report_data(obj: Any) -> bool:
    """Czy dict wygląda jak surowy REPORT_DATA (bez wrappera)."""
    if not isinstance(obj, dict):
        return False
    return any(k in obj for k in ("REPORT_DATA", "verdict", "report_id", "subject", "decision_matrix"))


def _map_report_data_to_decision_payload(report_data: Dict[str, Any], case_id: str) -> Dict[str, Any]:
    verdict_obj = report_data.get("verdict") or {}
    label = (verdict_obj.get("label") or "").lower()
    verdict_category = (verdict_obj.get("verdict_category") or "").lower()

    try:
        cp = float(verdict_obj.get("confidence_percent", 0))
    except Exception:
        cp = 0.0

    # verdict mapping
    if "podrobka" in label or verdict_category == "podrobka":
        verdict = "likely_not_authentic"
    elif cp <= 40 or verdict_category in {"oficjalna_replika", "treningowa_custom"}:
        verdict = "inconclusive"
    else:
        verdict = "likely_authentic"

    # risk_score mapping
    base_risk = int(round(100 - cp))
    if verdict_category == "podrobka" or verdict == "likely_not_authentic":
        risk_score = max(80, base_risk)
    else:
        risk_score = base_risk
    risk_score = _clamp(risk_score, 0, 100)

    # risk_tier mapping
    if risk_score <= 33:
        risk_tier = "low"
    elif risk_score <= 66:
        risk_tier = "medium"
    else:
        risk_tier = "high"

    # reasons: summary + 1-3 key observations
    reasons: List[Dict[str, Any]] = []
    summary = verdict_obj.get("summary")
    if summary:
        reasons.append(
            {
                "code": "verdict_summary",
                "severity": 2 if risk_tier == "low" else 3 if risk_tier == "medium" else 4,
                "facts": [summary],
                "evidence_refs": [],
            }
        )

    dm = report_data.get("decision_matrix") or []
    observations: List[str] = []
    for row in dm:
        obs = (row.get("observation") or "").strip()
        if obs:
            observations.append(obs)
        if len(observations) >= 3:
            break
    if observations:
        reasons.append(
            {
                "code": "key_observations",
                "severity": 2,
                "facts": observations,
                "evidence_refs": [],
            }
        )

    # recommendations + flags
    missing = report_data.get("missing_data") or []
    recommendations: List[Dict[str, Any]] = []
    flags: List[str] = []

    if missing:
        flags.append("missing_data")
        recommendations.append({"code": "request_more_photos", "priority": "high"})
    else:
        recommendations.append({"code": "review_manually", "priority": "medium"})

    return {
        "decision_version": "2.0",
        "verdict": verdict,
        "risk_score": risk_score,
        "risk_tier": risk_tier,
        "reasons": reasons,
        "recommendations": recommendations,
        "flags": flags,
    }


def _normalize_verdict_from_probabilities(report_data: Dict[str, Any]) -> None:
    """
    Techniczna normalizacja prawdopodobieństw:
    - skala 0–1 → 0–100,
    - zaokrąglenie do intów,
    - dopilnowanie sumy ~ 100.

    Dodatkowo ujednolica confidence_percent i confidence_level względem probabilities
    dla już ustalonej przez Agenta A kategorii verdict.verdict_category:
    - confidence_percent = probabilities[verdict_category],
    - confidence_level wynika z confidence_percent wg bucketów.

    Nie zmienia verdict.verdict_category ani pól opisowych (label, summary, meczowa_detail, personalization_assessment).
    """
    probs = report_data.get("probabilities") or {}
    if not isinstance(probs, dict) or not probs:
        return

    # Read raw scores
    score_map = {
        "oryginalna_sklepowa": float(probs.get("oryginalna_sklepowa") or 0),
        "meczowa": float(probs.get("meczowa") or 0),
        "oficjalna_replika": float(probs.get("oficjalna_replika") or 0),
        "podrobka": float(probs.get("podrobka") or 0),
        "edycja_limitowana": float(probs.get("edycja_limitowana") or 0),
        "treningowa_custom": float(probs.get("treningowa_custom") or 0),
    }

    # Detect fractional scale (0–1) vs 0–100. Treat as fractional if all values are between 0 and 1
    # and at least one is in (0, 1), or if the sum is close to 1.0.
    values = list(score_map.values())
    total = sum(values)
    all_in_unit_interval = all(0.0 <= v <= 1.0 for v in values)
    any_strict_between = any(0.0 < v < 1.0 for v in values)
    looks_fractional = (all_in_unit_interval and any_strict_between) or (0.99 <= total <= 1.01 and any_strict_between)

    if looks_fractional and total > 0:
        # Scale fractions to percentages.
        for k in score_map.keys():
            score_map[k] = score_map[k] * 100.0

    # Round to integers and enforce sum == 100 where possible, without changing ordering.
    rounded = {k: int(round(v)) for k, v in score_map.items()}
    sum_rounded = sum(rounded.values())
    if sum_rounded > 0 and sum_rounded != 100:
        diff = 100 - sum_rounded
        # Adjust the category with the highest score to absorb rounding diff.
        # This preserves the argmax semantics from Agent A.
        max_key = max(rounded, key=lambda k: rounded[k])
        rounded[max_key] = max(0, rounded[max_key] + diff)
        sum_rounded = sum(rounded.values())

    # Write back normalized probabilities.
    for k, v in rounded.items():
        probs[k] = v
    report_data["probabilities"] = probs

    # Ujednolicenie confidence_* z probabilities dla istniejącej kategorii werdyktu.
    verdict_obj = report_data.get("verdict") or {}
    if isinstance(verdict_obj, dict):
        cat = (verdict_obj.get("verdict_category") or "").strip()
        if cat and cat in rounded:
            pct = int(round(rounded[cat]))
            # confidence_level buckets (zgodne z dotychczasową logiką)
            if pct <= 39:
                level = "ograniczony"
            elif pct <= 69:
                level = "sredni"
            elif pct <= 84:
                level = "wysoki"
            else:
                level = "bardzo_wysoki"

            verdict_obj["confidence_percent"] = pct
            verdict_obj["confidence_level"] = level
            report_data["verdict"] = verdict_obj


def normalize_report_data(report_data: Dict[str, Any]) -> None:
    """
    Minimal technical normalization on top of Agent A output:
    - normalize probabilities to integer percentages summing to 100 (supporting 0–1 input scale),
    - align verdict_category, confidence_percent and confidence_level with probabilities.
    Does NOT change any other semantic fields.
    """
    if not isinstance(report_data, dict):
        return
    try:
        _normalize_verdict_from_probabilities(report_data)
    except Exception:
        # Normalizacja jest technicznym udogodnieniem; w razie problemu nie zatrzymujemy całego flow.
        logger.exception("Failed to normalize REPORT_DATA; leaving Agent A output unchanged.")


# ============================================================
# RULE ENGINE v1
# ============================================================

_AUTHENTIC_LIKE = {"oryginalna_sklepowa", "meczowa", "edycja_limitowana"}
_FAKE = {"podrobka"}
_CEILING_MAP = {"high": 80, "medium": 60, "low": 40}


def _round_to_10(n: int) -> int:
    # round-half-up (nie banker's rounding domyślne w Pythonie)
    return int((n + 5) // 10 * 10)


def _map_percent_to_confidence_level(pct: int) -> str:
    if pct <= 39:
        return "ograniczony"
    elif pct <= 69:
        return "sredni"
    elif pct <= 84:
        return "wysoki"
    else:
        return "bardzo_wysoki"


def _compute_data_completeness(
    dm_statuses: Dict[str, str],
    coverage_result: Optional[Dict[str, Any]],
    missing_data: List[Any],
) -> str:
    identity_tag = (coverage_result or {}).get("detected_views", {}).get("identity_tag", False)
    unknowns = sum(1 for code in ["A", "B", "C", "D", "E"] if dm_statuses.get(code) == "UNKNOWN")
    if unknowns <= 1 and identity_tag and len(missing_data) == 0:
        return "high"
    elif unknowns <= 3:
        return "medium"
    else:
        return "low"


def _compute_evidence_confidence(
    dm_statuses: Dict[str, str],
    missing_data: List[Any],
    coverage_result: Optional[Dict[str, Any]],
    sku_effect: str,
    verdict_category: str,
) -> str:
    c_status = dm_statuses.get("C", "UNKNOWN")
    d_status = dm_statuses.get("D", "UNKNOWN")
    c_red = c_status == "RED"
    d_red = d_status == "RED"
    c_green = c_status == "GREEN"
    d_green = d_status == "GREEN"
    is_fake = verdict_category in _FAKE
    identity_tag = (coverage_result or {}).get("detected_views", {}).get("identity_tag", False)

    # Asymetria: mocne red flags → high evidence dla fake (bez względu na brak danych)
    if is_fake:
        if c_red and d_red:
            return "high"
        elif c_red or d_red:
            return "medium"
        else:
            return "low"

    # Dla authentic-like i innych: kompletność danych ma znaczenie
    unknowns = sum(1 for code in ["C", "D", "A"] if dm_statuses.get(code) == "UNKNOWN")
    if unknowns >= 2 or not identity_tag or len(missing_data) >= 3:
        return "low"
    elif c_green and d_green and dm_statuses.get("A") == "GREEN":
        return "high"
    else:
        return "medium"


def _compute_sku_effect(
    sku_verification: Dict[str, Any],
    verdict_category: str,
    dm_statuses: Dict[str, str],
) -> str:
    sku_status = sku_verification.get("status", "uncertain")
    if sku_status == "confirmed":
        return "supports_authentic"
    elif sku_status == "mismatch":
        return "hard_conflict"
    elif sku_status == "invalid":
        return "hard_conflict"
    elif sku_status in ("not_found", "uncertain") and verdict_category in _AUTHENTIC_LIKE:
        return "ceiling_reduced"
    else:
        return "none"


def _compute_manufacturing_quality(ms: Dict[str, Any]) -> str:
    """
    Zwraca 'good' | 'mixed' | 'poor' | 'fallback'.
    'fallback' = brak manufacturing_signals lub wszystkie pola 'unclear'.
    Pojedynczy 'poor' bez żadnego 'good' → 'mixed' (nie 'poor').
    Dwa lub więcej 'poor' → 'poor'.
    """
    if not ms:
        return "fallback"

    quality_fields = ["seams_quality", "construction_quality",
                      "panel_join_quality", "finish_quality", "material_quality",
                      "neck_tag_quality"]
    values = [ms.get(f, "unclear") for f in quality_fields]

    poor_count  = sum(1 for v in values if v == "poor")
    good_count  = sum(1 for v in values if v == "good")
    unclear_count = sum(1 for v in values if v == "unclear")

    if unclear_count == 6:
        return "fallback"
    # Przynajmniej 2 pola 'poor' → całościowo poor (teraz z 6 pól)
    if poor_count >= 2:
        return "poor"
    # Przynajmniej 5 pól 'good' bez żadnego 'poor' → całościowo good
    if good_count >= 5 and poor_count == 0:
        return "good"
    return "mixed"


def _compute_match_issue_signal_strength(ms: Dict[str, Any]) -> str:
    """Zwraca 'strong' | 'medium' | 'weak'. Oparty na match_issue_surface_cues."""
    cues = (ms or {}).get("match_issue_surface_cues", "absent")
    if cues == "strong":
        return "strong"
    elif cues == "medium":
        return "medium"
    return "weak"


def _compute_confidence_ceiling(
    sku_effect: str,
    dm_statuses: Dict[str, str],
    missing_data: List[Any],
    verdict_category: str,
    coverage_result: Optional[Dict[str, Any]],
    reasoning_limits: List[Any],
    construction_flagged: bool = False,
    mfg_quality: str = "fallback",
) -> tuple:
    """Zwraca (ceiling_level: str, ceiling_reason: str)."""
    is_authentic_like = verdict_category in _AUTHENTIC_LIKE
    c_status = dm_statuses.get("C", "UNKNOWN")
    d_status = dm_statuses.get("D", "UNKNOWN")
    identity_tag = (coverage_result or {}).get("detected_views", {}).get("identity_tag", False)

    # SKU hard conflict: dla authentic → medium
    if sku_effect == "hard_conflict":
        if is_authentic_like:
            return "medium", "Niezgodność SKU ogranicza pewność dla werdyktu oryginalnego"
        else:
            return "medium", "Niezgodność SKU przy braku wyraźnych red flags"

    # Brak identity_tag: obniża ceiling dla authentic-like
    if not identity_tag and is_authentic_like:
        return "medium", "Brak identity_tag ogranicza pewność dla werdyktu oryginalnego"

    # Brak potwierdzonego SKU dla authentic-like
    if is_authentic_like and sku_effect == "ceiling_reduced":
        return "medium", "Brak potwierdzonego SKU — ceiling ograniczony"

    # Dużo reasoning_limits = wiele braków
    if len(reasoning_limits) >= 4:
        return "medium", "Wiele ograniczeń wnioskowania w danych wejściowych"

    # Ogólny niedobór danych
    unknowns = sum(1 for code in ["C", "D", "A", "E"] if dm_statuses.get(code) == "UNKNOWN")
    if unknowns >= 3:
        return "low", "Zbyt wiele nieznanych kryteriów"

    # Meczowa: hard quality gate na podstawie manufacturing_signals (lub fallback D-status)
    if verdict_category == "meczowa":
        if mfg_quality == "poor":
            return "medium", "Słaba jakość wykonania blokuje high confidence meczowej"
        elif mfg_quality == "mixed":
            # brak potwierdzonego SKU + mieszana jakość → niski ceiling
            if sku_effect != "supports_authentic":
                return "low", "Mieszana jakość wykonania + brak potwierdzonego SKU — ceiling niski"
            return "medium", "Mieszana jakość wykonania ogranicza ceiling meczowej"
        elif mfg_quality == "fallback":
            # ścieżka legacy: D status + construction_flagged
            if d_status in ("RED", "YELLOW") or construction_flagged:
                return "medium", f"Kryterium D={d_status} ogranicza ceiling dla werdyktu meczowego"
        # mfg_quality == "good": brak blokady — przechodzi do return "high"

    return "high", ""


def _compute_classification(
    verdict_category: str,
    dm_statuses: Dict[str, str],
    pcc: Dict[str, Any],
    sku_verification: Dict[str, Any],
    construction_flagged: bool = False,
    mfg_quality: str = "fallback",
) -> str:
    c_red = dm_statuses.get("C") == "RED"
    d_red = dm_statuses.get("D") == "RED"
    d_not_clean = dm_statuses.get("D") in ("RED", "YELLOW")
    has_visual_conflict = c_red or d_red
    sku_mismatch = sku_verification.get("status") == "mismatch"
    pcc_inconsistent = pcc.get("status") == "inconsistent"
    e_status = dm_statuses.get("E", "UNKNOWN")

    if verdict_category in _FAKE:
        return "likely_fake"
    elif verdict_category == "meczowa":
        # poor = hard push
        if mfg_quality == "poor":
            return "mixed_signals"
        # mixed alone wystarczy — dedykowany ETAP 6 eliminuje confirmation bias,
        # więc mixed jest już po bezstronnej ocenie jakości fizycznej
        if mfg_quality == "mixed":
            return "mixed_signals"
        # fallback: legacy D-status logic
        fallback_concern = mfg_quality == "fallback" and (d_not_clean or construction_flagged)
        if has_visual_conflict or fallback_concern or sku_mismatch:
            return "mixed_signals"
        return "likely_match_issue"
    elif verdict_category in {"oryginalna_sklepowa", "edycja_limitowana"}:
        if sku_mismatch or has_visual_conflict:
            return "mixed_signals"
        elif pcc_inconsistent and e_status not in ("UNKNOWN", "GREEN"):
            return "likely_authentic_base_with_later_modifications"
        return "likely_authentic_retail"
    else:  # oficjalna_replika, treningowa_custom, niejednoznaczna
        if has_visual_conflict:
            return "mixed_signals"
        return "inconclusive"


def _compute_base_shirt_assessment(
    dm_statuses: Dict[str, str],
    verdict_category: str,
    hard_flags: List[str],
    construction_flagged: bool = False,
) -> Dict[str, Any]:
    c_status = dm_statuses.get("C", "UNKNOWN")
    d_status = dm_statuses.get("D", "UNKNOWN")

    if c_status == "RED" or d_status == "RED" or "material_and_crest_both_red" in hard_flags:
        result = "likely_fake"
    elif c_status == "GREEN" and d_status == "GREEN" and not construction_flagged:
        result = "likely_authentic"
    else:
        result = "uncertain"

    key_criteria = [
        code for code in ["C", "D", "A"]
        if dm_statuses.get(code) not in (None, "UNKNOWN")
    ]
    return {"result": result, "key_criteria": key_criteria, "notes": ""}


def _compute_personalization_assessment_v2(
    pa_legacy: Dict[str, Any],
    pcc: Dict[str, Any],
    e_status: str,
) -> Dict[str, Any]:
    STATUS_MAP = {
        "brak": "absent",
        "fabryczna": "factory",
        "pozniejsza": "aftermarket",
        "niezweryfikowana": "unverified",
    }
    legacy_status = pa_legacy.get("status", "brak")
    result = STATUS_MAP.get(legacy_status, "unverified")

    # Niezgodność z PCC zawsze nadpisuje na inconsistent
    if pcc.get("status") == "inconsistent":
        result = "inconsistent"

    confidence_map = {"niska": "low", "srednia": "medium", "wysoka": "high"}
    confidence = confidence_map.get(pa_legacy.get("confidence", "niska"), "low")

    return {
        "result": result,
        "confidence": confidence,
        "notes": pa_legacy.get("notes", ""),
    }


def _compute_consistency_effect(pcc: Dict[str, Any], verdict_category: str) -> str:
    pcc_status = pcc.get("status", "uncertain")
    if pcc_status == "inconsistent":
        if verdict_category in _AUTHENTIC_LIKE:
            return "personalization_flagged"
        else:
            return "historical_claim_limited"
    return "none"


def _compute_hard_flags(
    dm_statuses: Dict[str, str],
    sku_effect: str,
    pcc_status: str,
    missing_data: List[Any],
    pa_result: Optional[str],
    coverage_result: Optional[Dict[str, Any]],
) -> List[str]:
    flags: List[str] = []
    c_red = dm_statuses.get("C") == "RED"
    d_red = dm_statuses.get("D") == "RED"
    c_yellow_or_red = dm_statuses.get("C") in ("RED", "YELLOW")
    d_yellow_or_red = dm_statuses.get("D") in ("RED", "YELLOW")
    sku_mismatch = sku_effect == "hard_conflict"
    identity_tag = (coverage_result or {}).get("detected_views", {}).get("identity_tag", True)

    if c_red and d_red:
        flags.append("material_and_crest_both_red")
    if sku_mismatch:
        flags.append("sku_mismatch")
    if sku_mismatch and (c_red or d_red):
        flags.append("sku_mismatch_plus_visual_issues")
    if pcc_status == "inconsistent" or pa_result == "inconsistent":
        flags.append("personalization_inconsistent")
    if not identity_tag:
        flags.append("critical_evidence_missing")
    if sku_mismatch and (c_yellow_or_red or d_yellow_or_red):
        flags.append("visual_external_conflict")

    return flags


def _compute_override_verdict_suggestion(
    sku_effect: str,
    dm_statuses: Dict[str, str],
    classification: str,
    verdict_category: str,
    construction_flagged: bool = False,
    mfg_quality: str = "fallback",
) -> str:
    sku_mismatch = sku_effect == "hard_conflict"
    c_red = dm_statuses.get("C") == "RED"
    d_red = dm_statuses.get("D") == "RED"
    d_not_clean = dm_statuses.get("D") in ("RED", "YELLOW")

    if (sku_mismatch and (c_red or d_red)) or (c_red and d_red):
        return "podrobka"
    # Meczowa: sprawdź construction concern przez mfg_quality lub fallback D-status
    if verdict_category == "meczowa":
        construction_concern = (
            mfg_quality == "poor"
            or (mfg_quality == "mixed" and (d_not_clean or c_red or sku_mismatch))
            or (mfg_quality == "fallback" and (d_red or construction_flagged))
        )
        if construction_concern:
            if c_red or sku_mismatch:
                return "podrobka"
            return "manual_review"
    if verdict_category in _AUTHENTIC_LIKE and classification in ("mixed_signals", "inconclusive"):
        return "manual_review"
    return "none"


_CONSTRUCTION_NEGATIVE_KW = [
    "niestarann", "nierówn", "słab", "tani", "tanio", "kiepsk",
    "podejrzan", "niska jakość", "niskiej jakości", "nieprawidłow",
    "poor", "cheap", "suspicious", "uneven", "inconsistent",
]


def _construction_quality_flagged(
    dm_statuses: Dict[str, str],
    dm_observations: Dict[str, str],
    reasoning_limits: List[Any],
) -> bool:
    """
    Zwraca True gdy jakość konstrukcji / szwów / wykończenia budzi zastrzeżenia.
    Heurystyka oparta na statusie D, słowach kluczowych w obserwacji D i reasoning_limits.
    """
    d_status = dm_statuses.get("D", "UNKNOWN")
    # D=YELLOW lub D=RED → zawsze flagged
    if d_status in ("RED", "YELLOW"):
        return True
    # D=GREEN ale observation D zawiera negatywne sygnały konstrukcji
    d_obs = (dm_observations.get("D") or "").lower()
    if any(kw in d_obs for kw in _CONSTRUCTION_NEGATIVE_KW):
        return True
    # reasoning_limits wspominające problemy z konstrukcją / szwami
    rl_text = " ".join(str(x) for x in reasoning_limits).lower()
    if any(kw in rl_text for kw in ["szwy", "konstrukcja", "panel", "wykończ", "seam", "finish"]):
        return True
    return False


def _build_sku_observation_text(
    subject: Dict[str, Any],
    sku_verification: Dict[str, Any],
) -> str:
    """
    Buduje znormalizowany tekst obserwacji SKU dla assessment_v2.
    Nie zawiera odniesień do zewnętrznych baz ani ograniczeń systemu.
    """
    raw_sku = (subject.get("sku") or "").strip()
    sku_lower = raw_sku.lower()
    if not raw_sku or sku_lower in ("nieustalone", "nieczytelne", "unknown", "—", "n/a", "brak"):
        return "Kod SKU nie jest widoczny na dostarczonych zdjęciach."
    sku_status = (sku_verification.get("status") or "uncertain")
    if sku_status == "confirmed":
        return "Kod SKU jest zgodny z tym modelem koszulki."
    elif sku_status == "mismatch":
        return f"Kod SKU ({raw_sku}) nie odpowiada opisowi tej koszulki."
    else:  # not_found, uncertain, not_applicable
        return f"Kod SKU ({raw_sku}) nie został potwierdzony jako odpowiadający tej koszulce."


_MFG_CHECK_PROMPT = """You are a forensic garment quality control inspector.

Your SOLE task: evaluate the PHYSICAL MANUFACTURING QUALITY of the garment in the provided photos.

═══════════════════════════════════════════
CRITICAL RULES — READ BEFORE EVALUATING:
═══════════════════════════════════════════
1. IGNORE ALL branding, logos, technology names (DRI-FIT, HEAT.RDY, ENGINEERED, AUTHENTIC, VAPORKNIT, etc.), player names, numbers, patches, sponsor prints. These carry ZERO information about actual manufacturing quality.
2. You are judging RAW WORKMANSHIP only: seams, stitching, panel assembly, fabric, finish.
3. STRONG BIAS TOWARD POOR: Football jersey counterfeits are extremely common. When in doubt about seam quality, always lean toward "poor" or "mixed". NEVER default to "good" without seeing perfectly clean, factory-precision stitching with zero visible irregularities.
4. "good" requires ALL of the following: perfectly even stitch density, perfectly straight seam lines, zero loose threads, zero puckering or waviness, stitching rows that are precisely parallel throughout. If even ONE of these is missing → "mixed" or "poor".
5. "poor" applies when ANY of the following is visible: uneven stitch spacing anywhere on the garment, wavy seam lines anywhere, ANY loose or frayed thread ends, ANY puckering or pulling of fabric at seams, seam lines that curve or wobble, thick or lumpy seam joins.
6. Evaluate each field INDEPENDENTLY. Do not let overall appearance influence individual seam assessment.
7. ZOOM IN MENTALLY: Treat every visible seam as if you are examining it under magnification. Small irregularities count as defects.

═══════════════════════════════════════════
EVALUATION CRITERIA PER FIELD:
═══════════════════════════════════════════

1. seams_quality — Examine EVERY visible seam line and stitch:
   POOR: uneven stitch density (gaps between stitches), wavy or wobbly seam lines, loose or skipped stitches, seams pulling or puckering away from fabric, visible loose thread ends, stitch rows that aren't parallel, seams that curve when they should be straight
   MIXED: mostly even stitching but with some visible irregularities, slightly wavy in places, minor puckering
   GOOD: perfectly consistent stitch density throughout, seam lines are straight and flat, no loose threads, no puckering, stitching rows are precisely parallel
   UNCLEAR: seams not visible enough to judge

2. construction_quality — Overall garment assembly and structure:
   POOR: visible panel misalignment, asymmetric panels (one side different from the other), collar sitting unevenly or twisted, garment shape distorted, elements clearly not centered or balanced
   MIXED: mostly aligned but with small asymmetries or minor distortions
   GOOD: perfect panel symmetry, all elements precisely centered and balanced, structure is crisp
   UNCLEAR: not enough views to judge overall assembly

3. panel_join_quality — Examine where different fabric panels meet:
   POOR: visible gaps or overlaps between panels, panel edges not meeting cleanly, fabric bunching at joins, misaligned patterns at seam lines, visible glue residue or messy join edges
   MIXED: panels meet but with slight irregularities or minor misalignment
   GOOD: panels join seamlessly, clean flush transitions, patterns align perfectly at seams
   UNCLEAR: panel joins not clearly visible

4. finish_quality — Collar, cuffs, sleeve hem, bottom hem:
   POOR: rough or frayed edges, elastic pulling or bunching unevenly, collar shape uneven or distorted, hemline not straight, iron-on elements applied crookedly or with air bubbles, visible adhesive
   MIXED: edges mostly clean but with some roughness, minor unevenness in elastic or hem
   GOOD: all edges perfectly finished, elastic lies flat and even, collar crisp, hemline straight throughout
   UNCLEAR: edges not clearly visible

5. material_quality — Fabric texture, weave structure, weight:
   POOR: fabric looks thin or flimsy, shiny plasticky surface without depth of texture, visible inconsistencies in weave pattern, cheap-looking mesh with irregular holes or uneven spacing, fabric appears to lack structural integrity
   MIXED: material looks acceptable but not premium — some areas look thin or the weave is slightly uneven
   GOOD: uniform weave pattern throughout, solid fabric construction with consistent weight, premium texture, mesh holes are uniform and structured
   UNCLEAR: fabric texture not clearly visible

6. neck_tag_quality — Inner neck tag / neck label / neck print:
   POOR: tag is printed on cheap material, fonts are blurry or pixelated, washing instructions are hard to read, tag is crooked or poorly attached, material of tag feels/looks thin and cheap, tag design doesn't match premium brand standards
   MIXED: tag looks mostly acceptable but has some quality concerns — slight blurriness, minor misalignment, or fonts that are slightly off
   GOOD: tag is clean, crisp, fonts are sharp and legible, material looks premium, tag sits flat and straight, all information is clearly printed
   UNCLEAR: neck area / inner tag not visible in photos

═══════════════════════════════════════════
OUTPUT FORMAT:
═══════════════════════════════════════════
Return ONLY valid JSON. No markdown. No explanation. No extra text. Just the JSON object:

{
  "seams_quality": "good | mixed | poor | unclear",
  "construction_quality": "good | mixed | poor | unclear",
  "panel_join_quality": "good | mixed | poor | unclear",
  "finish_quality": "good | mixed | poor | unclear",
  "material_quality": "good | mixed | poor | unclear",
  "neck_tag_quality": "good | mixed | poor | unclear"
}"""

_MFG_CHECK_FALLBACK = {
    "seams_quality": "unclear",
    "construction_quality": "unclear",
    "panel_join_quality": "unclear",
    "finish_quality": "unclear",
    "material_quality": "unclear",
    "neck_tag_quality": "unclear",
}


async def run_manufacturing_quality_check(
    asset_paths: List[str],
    report_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Etap 6: Dedykowany pass oceny jakości fizycznej wykonania.
    Wysyła zdjęcia bez kontekstu o typie koszulki — eliminuje confirmation bias.
    Nadpisuje manufacturing_signals.seams/construction/panel/finish_quality.
    Non-fatal — przy błędzie zwraca fallback bez zmiany report_data.
    """
    try:
        return await _run_mfg_check(asset_paths, report_data)
    except Exception as e:
        logger.warning("[MFG_CHECK] Nieoczekiwany błąd (non-fatal): %s", e)
        return _MFG_CHECK_FALLBACK.copy()


async def _run_mfg_check(
    asset_paths: List[str],
    report_data: Dict[str, Any],
) -> Dict[str, Any]:
    client = _get_client()
    if client is None:
        logger.warning("[MFG_CHECK] Brak klienta Gemini")
        return _MFG_CHECK_FALLBACK.copy()

    # ETAP 6 używa zawsze gemini-2.5-pro — lepsze rozpoznawanie szczegółów wizualnych
    model = os.getenv("MFG_CHECK_MODEL", "models/gemini-2.5-pro")

    parts: List[types.Part] = [
        types.Part(text="Evaluate the physical manufacturing quality of this garment. Return JSON only.")
    ]

    valid_images = 0
    for p in asset_paths:
        path = Path(p)
        if not path.exists():
            continue
        suffix = path.suffix.lower()
        mime = "image/jpeg"
        if suffix == ".png":
            mime = "image/png"
        elif suffix == ".webp":
            mime = "image/webp"
        try:
            image_bytes = path.read_bytes()
            parts.append(types.Part(inline_data=types.Blob(mime_type=mime, data=image_bytes)))
            valid_images += 1
        except Exception:
            continue

    if valid_images == 0:
        logger.warning("[MFG_CHECK] Brak czytelnych zdjęć")
        return _MFG_CHECK_FALLBACK.copy()

    try:
        resp = await client.aio.models.generate_content(
            model=model,
            contents=[types.Content(role="user", parts=parts)],
            config=types.GenerateContentConfig(
                system_instruction=_MFG_CHECK_PROMPT,
                temperature=0.1,
            ),
        )
    except Exception as e:
        logger.warning("[MFG_CHECK] Błąd API Gemini: %s", e)
        return _MFG_CHECK_FALLBACK.copy()

    text = (resp.text or "").strip()
    if not text:
        return _MFG_CHECK_FALLBACK.copy()

    try:
        result = json.loads(text)
    except Exception:
        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            result = json.loads(text[start:end])
        except Exception:
            logger.warning("[MFG_CHECK] Nieprawidłowy JSON: %r", text[:200])
            return _MFG_CHECK_FALLBACK.copy()

    # Walidacja — tylko dozwolone wartości
    allowed = {"good", "mixed", "poor", "unclear"}
    quality_fields = ["seams_quality", "construction_quality", "panel_join_quality", "finish_quality"]
    validated = {}
    for field in quality_fields:
        val = result.get(field, "unclear")
        validated[field] = val if val in allowed else "unclear"

    logger.info(
        "[MFG_CHECK] seams=%s construction=%s panel=%s finish=%s",
        validated["seams_quality"], validated["construction_quality"],
        validated["panel_join_quality"], validated["finish_quality"],
    )
    return validated


def run_rule_engine(
    report_data: Dict[str, Any],
    coverage_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Deterministyczny rule engine v1.

    Czyta: verdict, decision_matrix, missing_data, subject, reasoning_limits,
           sku_verification, player_club_consistency, coverage_result.
    Mutuje: report_data["verdict"]["confidence_percent"], ["confidence_level"],
            opcjonalnie ["confidence_explanation"].
    Zwraca: assessment_v2 dict.

    Non-fatal — wywołujący powinien owrapować try/except.
    NIE zmienia verdict_category, label, summary.
    """
    verdict = report_data.get("verdict") or {}
    dm = report_data.get("decision_matrix") or []
    missing_data = report_data.get("missing_data") or []
    reasoning_limits = report_data.get("reasoning_limits") or []
    sku_verification = report_data.get("sku_verification") or {}
    pcc = report_data.get("player_club_consistency") or {}
    pa_legacy = report_data.get("personalization_assessment") or {}
    subject = report_data.get("subject") or {}

    verdict_category = (verdict.get("verdict_category") or "").strip()
    try:
        confidence_percent = int(round(float(verdict.get("confidence_percent") or 0)))
    except (TypeError, ValueError):
        confidence_percent = 0

    dm_statuses: Dict[str, str] = {
        row["code"]: row["status"]
        for row in dm
        if isinstance(row, dict) and "code" in row and "status" in row
    }
    dm_observations: Dict[str, str] = {
        row["code"]: row.get("observation", "")
        for row in dm
        if isinstance(row, dict) and "code" in row
    }
    pcc_status = (pcc.get("status") or "uncertain")
    e_status = dm_statuses.get("E", "UNKNOWN")

    manufacturing_signals = report_data.get("manufacturing_signals") or {}
    reasoning_limits_out = list(reasoning_limits)  # kopia — hard override może dopisać
    sku_effect = _compute_sku_effect(sku_verification, verdict_category, dm_statuses)

    # HARD REJECT: SKU mismatch → natychmiastowy override na podrobkę
    if sku_verification.get("status") == "mismatch":
        if isinstance(report_data.get("verdict"), dict):
            report_data["verdict"]["verdict_category"] = "podrobka"
            report_data["verdict"]["label"] = "Podróbka"
            report_data["verdict"]["confidence_percent"] = 90
            report_data["verdict"]["confidence_level"] = "bardzo_wysoki"
            report_data["verdict"]["confidence_explanation"] = (
                "Kod SKU przypisany do innej koszulki — jednoznaczny sygnał podróbki."
            )
        probs = report_data.get("probabilities") or {}
        for k in probs:
            probs[k] = 0
        probs["podrobka"] = 90
        probs["oryginalna_sklepowa"] = 10
        report_data["probabilities"] = probs
        raw_sku = (report_data.get("subject") or {}).get("sku", "")
        return {
            "engine_version": "1.0",
            "classification": "likely_fake",
            "override_verdict_category_suggestion": "podrobka",
            "evidence_confidence": "high",
            "confidence_ceiling": "high",
            "ceiling_reason": "SKU przypisany do innej koszulki",
            "base_shirt_assessment": {"result": "likely_fake", "key_criteria": ["B"], "notes": ""},
            "personalization_assessment": {"result": "unverified", "confidence": "low", "notes": ""},
            "external_checks_effect": {
                "sku_effect": "hard_conflict",
                "consistency_effect": "none",
                "sku_note": f"Kod SKU ({raw_sku}) nie odpowiada tej koszulce — przypisany do innego modelu.",
            },
            "hard_flags": ["sku_mismatch_hard_reject"],
            "reasoning_limits": ["sku_mismatch_overrides_all"],
            "data_completeness": "high",
            "manufacturing_quality": "unknown",
            "match_issue_signal_strength": "weak",
        }

    construction_flagged = _construction_quality_flagged(dm_statuses, dm_observations, reasoning_limits)
    mfg_quality = _compute_manufacturing_quality(manufacturing_signals)

    # HARD REJECT: brak SKU + poor manufacturing → podrobka 80%
    sku_status = sku_verification.get("status", "uncertain")
    if (
        sku_status in ("not_found", "not_applicable")
        and mfg_quality == "poor"
        and manufacturing_signals  # tylko gdy ETAP 6 dostarczył dane
        and verdict_category in _AUTHENTIC_LIKE
    ):
        if isinstance(report_data.get("verdict"), dict):
            report_data["verdict"]["verdict_category"] = "podrobka"
            report_data["verdict"]["label"] = "Podróbka"
            report_data["verdict"]["confidence_percent"] = 80
            report_data["verdict"]["confidence_level"] = "wysoki"
            report_data["verdict"]["confidence_explanation"] = (
                "Brak kodu SKU oraz słaba jakość fizyczna wykonania — "
                "kombinacja jednoznacznie wskazuje na podróbkę."
            )
        probs = report_data.get("probabilities") or {}
        for k in probs:
            probs[k] = 0
        probs["podrobka"] = 80
        probs["oryginalna_sklepowa"] = 20
        report_data["probabilities"] = probs
        verdict_category = "podrobka"
        return {
            "engine_version": "1.0",
            "classification": "likely_fake",
            "override_verdict_category_suggestion": "podrobka",
            "evidence_confidence": "high",
            "confidence_ceiling": "high",
            "ceiling_reason": "Brak SKU + poor manufacturing",
            "base_shirt_assessment": {"result": "likely_fake", "key_criteria": ["A", "D"], "notes": ""},
            "personalization_assessment": {"result": "unverified", "confidence": "low", "notes": ""},
            "external_checks_effect": {
                "sku_effect": "ceiling_reduced",
                "consistency_effect": "none",
                "sku_note": "Kod SKU nie jest widoczny na dostarczonych zdjęciach.",
            },
            "hard_flags": ["no_sku_plus_poor_manufacturing"],
            "reasoning_limits": ["no_sku_and_poor_mfg_overrides_authentic_verdict"],
            "data_completeness": "medium",
            "manufacturing_quality": "poor",
            "match_issue_signal_strength": "weak",
        }

    match_signal_strength = _compute_match_issue_signal_strength(manufacturing_signals)
    pa_v2 = _compute_personalization_assessment_v2(pa_legacy, pcc, e_status)
    hard_flags = _compute_hard_flags(
        dm_statuses, sku_effect, pcc_status, missing_data, pa_v2.get("result"), coverage_result
    )
    classification = _compute_classification(
        verdict_category, dm_statuses, pcc, sku_verification, construction_flagged, mfg_quality
    )
    override = _compute_override_verdict_suggestion(
        sku_effect, dm_statuses, classification, verdict_category, construction_flagged, mfg_quality
    )
    consistency_effect = _compute_consistency_effect(pcc, verdict_category)
    data_completeness = _compute_data_completeness(dm_statuses, coverage_result, missing_data)
    evidence_confidence = _compute_evidence_confidence(
        dm_statuses, missing_data, coverage_result, sku_effect, verdict_category
    )
    confidence_ceiling, ceiling_reason = _compute_confidence_ceiling(
        sku_effect, dm_statuses, missing_data, verdict_category, coverage_result, reasoning_limits,
        construction_flagged, mfg_quality
    )
    base_assessment = _compute_base_shirt_assessment(
        dm_statuses, verdict_category, hard_flags, construction_flagged
    )

    # Fake ceiling logic — pełna kontrola ceiling dla podróbki
    if verdict_category in _FAKE:
        _c = dm_statuses.get("C", "UNKNOWN")
        _d = dm_statuses.get("D", "UNKNOWN")
        _sku_mismatch = sku_verification.get("status") == "mismatch"

        strong_fake_signal = (
            (_c == "RED" and _d == "RED")
            or (_sku_mismatch and (_c == "RED" or _d == "RED"))
            or "material_and_crest_both_red" in hard_flags
        )

        if strong_fake_signal:
            confidence_ceiling = "high"
            ceiling_reason = "Mocne wizualne sygnały podróbki"
        else:
            # Brak mocnych sygnałów → max medium
            if confidence_ceiling == "high":
                confidence_ceiling = "medium"
                ceiling_reason = "Brak mocnych sygnałów wizualnych — ceiling ograniczony"

        # Krok 4: YELLOW lub UNKNOWN w krytycznych kryteriach blokuje high
        _c_weak = _c == "YELLOW"
        _d_weak = _d in ("YELLOW", "UNKNOWN")
        if (_c_weak or _d_weak) and confidence_ceiling == "high":
            confidence_ceiling = "medium"
            ceiling_reason = "Niejednoznaczne sygnały wizualne — ceiling ograniczony do medium"

    # confidence_percent = prawdopodobieństwo kategorii z rozkładu modelu, ograniczone ceilingiem.
    # Ceiling wyraża jakość dowodów (brak SKU, mieszana jakość) — obniża wynik gdy pewność nieuzasadniona.
    probs = report_data.get("probabilities") or {}
    ceiling_value = _CEILING_MAP.get(confidence_ceiling, 80)
    verdict_prob = int(probs.get(verdict_category) or confidence_percent)
    # Ceiling jest aplikowany zawsze — wyjątek tylko gdy wszystkie sygnały pozytywne
    _sku_confirmed = sku_verification.get("status") == "confirmed"
    _no_ceiling_needed = (
        classification == "likely_match_issue"
        and _sku_confirmed
        and mfg_quality == "good"
    )
    if _no_ceiling_needed:
        new_confidence_percent = _round_to_10(verdict_prob)
    else:
        new_confidence_percent = _round_to_10(min(verdict_prob, ceiling_value))
    new_confidence_level = _map_percent_to_confidence_level(new_confidence_percent)

    # confidence_explanation gdy ceiling znacząco niżej niż probability (do wyświetlenia w UI)
    podrobka_prob = int(probs.get("podrobka") or 0)
    meczowa_prob = int(probs.get("meczowa") or 0)
    confidence_explanation = ""
    if verdict_category in _FAKE and confidence_ceiling in ("low", "medium"):
        confidence_explanation = (
            "Prawdopodobieństwo podróbki na podstawie analizy wizualnej. "
            "Ograniczone dane mogą wpływać na dokładność oceny."
        )
    elif verdict_category == "meczowa" and confidence_ceiling == "low":
        confidence_explanation = (
            "Mieszana jakość wykonania i brak potwierdzenia SKU "
            "ograniczają wiarygodność wyniku meczowego."
        )

    # Jeśli wszystkie sygnały są pozytywne — nie aplikuj ceiling
    _sku_confirmed = sku_verification.get("status") == "confirmed"
    _no_ceiling_needed = (
        classification == "likely_match_issue"
        and _sku_confirmed
        and mfg_quality == "good"
    )
    if _no_ceiling_needed:
        final_confidence_percent = _round_to_10(verdict_prob)
    else:
        final_confidence_percent = new_confidence_percent

    if isinstance(report_data.get("verdict"), dict):
        report_data["verdict"]["confidence_percent"] = final_confidence_percent
        report_data["verdict"]["confidence_level"] = _map_percent_to_confidence_level(final_confidence_percent)
        if confidence_explanation:
            report_data["verdict"]["confidence_explanation"] = confidence_explanation

    # HARD BUSINESS OVERRIDE: meczowa + poor manufacturing → podrobka
    # Tylko gdy manufacturing_signals jawnie dostarczone (nie fallback ze starych raportów)
    if (
        verdict_category == "meczowa"
        and mfg_quality == "poor"
        and manufacturing_signals
    ):
        verdict_category = "podrobka"
        if isinstance(report_data.get("verdict"), dict):
            report_data["verdict"]["verdict_category"] = "podrobka"
            report_data["verdict"]["label"] = "Podróbka"
        classification = "likely_fake"
        override = "podrobka"
        hard_flags = hard_flags + ["match_issue_blocked_by_poor_manufacturing"]
        reasoning_limits_out.append("poor_manufacturing_overrides_match_issue")

    # Problem 1: znormalizowany tekst obserwacji SKU
    sku_note = _build_sku_observation_text(subject, sku_verification)

    return {
        "engine_version": "1.0",
        "classification": classification,
        "override_verdict_category_suggestion": override,
        "evidence_confidence": evidence_confidence,
        "confidence_ceiling": confidence_ceiling,
        "ceiling_reason": ceiling_reason,
        "base_shirt_assessment": base_assessment,
        "personalization_assessment": pa_v2,
        "external_checks_effect": {
            "sku_effect": sku_effect,
            "consistency_effect": consistency_effect,
            "sku_note": sku_note,
        },
        "hard_flags": hard_flags,
        "reasoning_limits": reasoning_limits_out,
        "data_completeness": data_completeness,
        "manufacturing_quality": mfg_quality,
        "match_issue_signal_strength": match_signal_strength,
    }


# ============================================================
# PRECHECK FUNCTIONS
# ============================================================

async def coverage_check(asset_paths: List[str]) -> Dict[str, Any]:
    """
    Etap 1: Sprawdza czy zdjęcia pokrywają wystarczające obszary do analizy.
    Używa tego samego modelu Gemini co Agent A.

    Returns:
        Dict z kluczami: can_continue, case_type, detected_views, missing_required, missing_optional, message
    """
    if not asset_paths:
        return {
            "can_continue": False,
            "case_type": "uncertain",
            "detected_views": {},
            "missing_required": ["any_images"],
            "missing_optional": [],
            "message": "Nie przesłano żadnych zdjęć do analizy."
        }

    client = _get_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Gemini API key missing")

    model = os.getenv("GEMINI_FAST_MODEL", "models/gemini-2.5-flash")

    # Przygotuj części z obrazami
    parts: List[types.Part] = [
        types.Part(text="Analyze the attached images for coverage. Return ONLY the JSON as specified.")
    ]

    valid_images = 0
    for p in asset_paths:
        path = Path(p)
        if not path.exists():
            continue
        suffix = path.suffix.lower()
        mime = "image/jpeg"
        if suffix == ".png":
            mime = "image/png"
        elif suffix == ".webp":
            mime = "image/webp"
        parts.append(types.Part.from_bytes(data=path.read_bytes(), mime_type=mime))
        valid_images += 1

    if valid_images == 0:
        return {
            "can_continue": False,
            "case_type": "uncertain",
            "detected_views": {},
            "missing_required": ["any_images"],
            "missing_optional": [],
            "message": "Nie znaleziono prawidłowych plików zdjęć."
        }

    logger.info("Coverage check: sending %d images to model %s", valid_images, model)

    try:
        resp = await client.aio.models.generate_content(
            model=model,
            contents=[types.Content(role="user", parts=parts)],
            config=types.GenerateContentConfig(
                system_instruction=COVERAGE_CHECK_PROMPT,
                temperature=0.1,  # Niska temperatura dla deterministyczności
                response_mime_type="application/json",
            ),
        )
    except Exception as e:
        logger.exception("Coverage check API error: %s", e)
        # W przypadku błędu API, pozwalamy kontynuować (fail-open) żeby nie blokować usera
        return {
            "can_continue": True,
            "case_type": "uncertain",
            "detected_views": {},
            "missing_required": [],
            "missing_optional": [],
            "message": ""
        }

    text = (resp.text or "").strip()
    if not text:
        logger.warning("Empty response from coverage check")
        return {"can_continue": True, "case_type": "uncertain", "detected_views": {}, "missing_required": [], "missing_optional": [], "message": ""}

    try:
        result = json.loads(text)
    except Exception:
        try:
            extracted = _extract_first_json_object(text)
            result = json.loads(extracted)
        except Exception:
            logger.error("Non-JSON response from coverage check: %r", text[:500])
            return {"can_continue": True, "case_type": "uncertain", "detected_views": {}, "missing_required": [], "missing_optional": [], "message": ""}

    logger.info("Coverage check result: can_continue=%s", result.get("can_continue"))
    return result


async def quality_check(
    asset_paths: List[str],
    detected_views: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Etap 2: Sprawdza jakość zdjęć (ostrość, oświetlenie, odległość).
    Używa tego samego modelu Gemini co Agent A.

    detected_views: wynik z coverage_check — informuje model, które kategorie są obecne,
    żeby nie raportował "not_visible" dla kategorii, których po prostu nie ma w zestawie.

    Returns:
        Dict z kluczami: can_continue, issues, message
    """
    if not asset_paths:
        return {
            "can_continue": False,
            "issues": [{"area": "general", "issue": "not_visible"}],
            "message": "Nie przesłano żadnych zdjęć do analizy."
        }

    client = _get_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Gemini API key missing")

    model = os.getenv("GEMINI_FAST_MODEL", "models/gemini-2.5-flash")

    # Buduj kontekst detected_views żeby model nie mylił "brak zdjęcia" z "złą jakością"
    coverage_context = "Evaluate the quality of the attached images. Return ONLY the JSON as specified."
    if detected_views and isinstance(detected_views, dict):
        present = [k for k, v in detected_views.items() if v]
        absent = [k for k, v in detected_views.items() if not v]
        if present:
            coverage_context += f"\n\nThe following view types are PRESENT in the photos: {', '.join(present)}."
        if absent:
            coverage_context += (
                f"\nThe following view types are ABSENT (no photo was taken of them): {', '.join(absent)}."
                "\nDo NOT report quality issues for absent categories — their absence is a coverage issue, not a quality issue."
            )

    # Przygotuj części z obrazami
    parts: List[types.Part] = [
        types.Part(text=coverage_context)
    ]

    valid_images = 0
    for p in asset_paths:
        path = Path(p)
        if not path.exists():
            continue
        suffix = path.suffix.lower()
        mime = "image/jpeg"
        if suffix == ".png":
            mime = "image/png"
        elif suffix == ".webp":
            mime = "image/webp"
        parts.append(types.Part.from_bytes(data=path.read_bytes(), mime_type=mime))
        valid_images += 1

    if valid_images == 0:
        return {
            "can_continue": False,
            "issues": [{"area": "general", "issue": "not_visible"}],
            "message": "Nie znaleziono prawidłowych plików zdjęć."
        }

    logger.info("Quality check: sending %d images to model %s", valid_images, model)

    try:
        resp = await client.aio.models.generate_content(
            model=model,
            contents=[types.Content(role="user", parts=parts)],
            config=types.GenerateContentConfig(
                system_instruction=QUALITY_CHECK_PROMPT,
                temperature=0.1,  # Niska temperatura dla deterministyczności
                response_mime_type="application/json",
            ),
        )
    except Exception as e:
        logger.exception("Quality check API error: %s", e)
        # W przypadku błędu API, pozwalamy kontynuować (fail-open)
        return {"can_continue": True, "issues": [], "message": ""}

    text = (resp.text or "").strip()
    if not text:
        logger.warning("Empty response from quality check")
        return {"can_continue": True, "issues": [], "message": ""}

    try:
        result = json.loads(text)
    except Exception:
        try:
            extracted = _extract_first_json_object(text)
            result = json.loads(extracted)
        except Exception:
            logger.error("Non-JSON response from quality check: %r", text[:500])
            return {"can_continue": True, "issues": [], "message": ""}

    logger.info("Quality check result: can_continue=%s", result.get("can_continue"))
    return result


RED_FLAG_CHECK_PROMPT = """You are a counterfeit detection expert analyzing football jersey photos.

Your task: determine whether the provided images show STRONG visual indicators of a counterfeit/fake jersey.

Focus ONLY on what is clearly visible. Do NOT speculate about absent photos.

Strong red flags to look for:
- Obvious print quality issues: blurry, pixelated, faded, or misaligned sponsor logos/club badges
- Clearly wrong fonts or letter spacing in names/numbers
- Visibly poor stitching quality (uneven, fraying, excessive thread)
- Wrong badge construction (printed instead of woven/embroidered)
- Incorrect collar design or obvious cheap fabric texture
- Sponsor logos in wrong position or wrong color
- Wrong kit design for the claimed club/season (if identifiable)

Be conservative: only return has_strong_red_flags=true if you see CLEAR, OBVIOUS counterfeit indicators — not minor imperfections or ambiguous details.

Return ONLY a JSON object with this exact schema:
{
  "has_strong_red_flags": boolean,
  "red_flags_found": ["list of specific issues observed, or empty array"],
  "confidence": "low" | "medium" | "high",
  "reason": "brief explanation in Polish"
}"""


async def red_flag_check(asset_paths: List[str]) -> Dict[str, Any]:
    """Sprawdza czy zdjęcia zawierają mocne czerwone flagi podróbki.
    Zawsze zwraca dict, nigdy nie rzuca wyjątku."""
    fallback = {
        "has_strong_red_flags": False,
        "red_flags_found": [],
        "confidence": "low",
        "reason": "Nie udało się wykonać sprawdzenia czerwonych flag.",
    }

    client = _get_client()
    if client is None:
        return fallback

    model = os.getenv("GEMINI_FAST_MODEL", "models/gemini-2.5-flash")

    parts: List[types.Part] = [
        types.Part(text="Analyze the attached jersey images for counterfeit red flags.")
    ]

    valid_images = 0
    for p in asset_paths:
        path = Path(p)
        if not path.exists():
            continue
        suffix = path.suffix.lower()
        mime = "image/jpeg"
        if suffix == ".png":
            mime = "image/png"
        elif suffix == ".webp":
            mime = "image/webp"
        parts.append(types.Part.from_bytes(data=path.read_bytes(), mime_type=mime))
        valid_images += 1

    if valid_images == 0:
        return fallback

    logger.info("Red flag check: sending %d images to model %s", valid_images, model)

    try:
        resp = await client.aio.models.generate_content(
            model=model,
            contents=[types.Content(role="user", parts=parts)],
            config=types.GenerateContentConfig(
                system_instruction=RED_FLAG_CHECK_PROMPT,
                temperature=0.1,
                response_mime_type="application/json",
            ),
        )
    except Exception as e:
        logger.exception("Red flag check API error: %s", e)
        return fallback

    text = (resp.text or "").strip()
    if not text:
        return fallback

    try:
        result = json.loads(text)
    except Exception:
        try:
            extracted = _extract_first_json_object(text)
            result = json.loads(extracted)
        except Exception:
            logger.error("Non-JSON response from red flag check: %r", text[:500])
            return fallback

    logger.info(
        "Red flag check result: has_strong_red_flags=%s confidence=%s",
        result.get("has_strong_red_flags"),
        result.get("confidence"),
    )
    return result


class GeminiAgentA:
    async def analyze(self, case_id: str, asset_paths: List[str]) -> Dict[str, Any]:
        if not asset_paths:
            raise HTTPException(status_code=400, detail="No assets available for decision")

        model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
        prompt_version = os.getenv("A_PROMPT_VERSION", DEFAULT_PROMPT_VERSION)
        system_prompt = _load_system_prompt()

        api_key = _get_api_key()
        if not api_key:
            logger.error("Gemini API key missing; set GEMINI_API_KEY or GOOGLE_API_KEY")
            raise HTTPException(status_code=503, detail="Gemini API key missing")

        client = _get_client()
        if client is None:
            raise HTTPException(status_code=503, detail="Gemini API key missing")

        logger.info(
            "Gemini analyze: model=%s key_present=%s", model, True
        )

        parts: List[types.Part] = [
            types.Part(text="Analyze the attached images. Return ONLY the JSON as specified.")
        ]

        valid_images = 0
        for p in asset_paths:
            path = Path(p)
            if not path.exists():
                logger.warning("Asset does not exist: %s", p)
                continue

            suffix = path.suffix.lower()
            mime = "image/jpeg"
            if suffix == ".png":
                mime = "image/png"

            parts.append(types.Part.from_bytes(data=path.read_bytes(), mime_type=mime))
            valid_images += 1

        if valid_images == 0:
            raise HTTPException(status_code=400, detail="No assets available for decision")

        trace_id = str(uuid.uuid4())
        t0 = time.perf_counter()

        try:
            resp = await client.aio.models.generate_content(
                model=model,
                contents=[types.Content(role="user", parts=parts)],
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.2,
                    response_mime_type="application/json",
                ),
            )
        except Exception as e:
            msg = str(e)
            # Rozszerzone logowanie błędów Gemini: spróbujmy wyciągnąć jak najwięcej informacji.
            status_code = getattr(e, "status_code", None) or getattr(e, "code", None)
            error_type = type(e).__name__
            # Niektóre implementacje mogą mieć atrybut response / details
            response_obj = getattr(e, "response", None)
            details = getattr(e, "details", None) or getattr(e, "args", None)
            try:
                logger.error(
                    "Gemini API error: type=%s status=%s msg=%s details=%r response=%r",
                    error_type,
                    status_code,
                    msg,
                    details,
                    response_obj,
                )
            except Exception:
                # W razie problemów z serializacją nadal logujemy przynajmniej podstawowy komunikat.
                logger.exception("Gemini API error (logging failed) for model=%s: %s", model, msg)

            lowered = msg.lower()

            # Specjalna obsługa limitów / RESOURCE_EXHAUSTED (HTTP 429).
            is_quota_error = (
                status_code == 429
                or "resource_exhausted" in lowered
                or "quota" in lowered
                or "rate limit" in lowered
            )
            if is_quota_error:
                retry_after_seconds: Optional[int] = None
                # Best-effort: spróbujmy odczytać retry delay z wyjątku, jeśli jest.
                raw_retry = getattr(e, "retry_delay", None)
                try:
                    # Google klient może zwrócić timedelta lub liczbę sekund.
                    if raw_retry is not None:
                        if hasattr(raw_retry, "total_seconds"):
                            retry_after_seconds = int(raw_retry.total_seconds())
                        else:
                            retry_after_seconds = int(raw_retry)
                except Exception:
                    retry_after_seconds = None

                # Jeśli nie znamy dokładnego opóźnienia, przyjmijmy konserwatywnie ~60s.
                if retry_after_seconds is None or retry_after_seconds <= 0:
                    retry_after_seconds = 60

                raise HTTPException(
                    status_code=503,
                    detail={
                        "code": "gemini_quota_exhausted",
                        "message": (
                            "Limit analiz AI został chwilowo wyczerpany. "
                            f"Spróbuj ponownie za około {retry_after_seconds // 60 or 1} minutę."
                        ),
                        "retry_after_seconds": retry_after_seconds,
                    },
                )

            if ("404" in msg or "not found" in lowered) and "model" in lowered:
                raise HTTPException(
                    status_code=502,
                    detail={
                        "detail": "Gemini model not available",
                        "model": model,
                        "hint": "Set GEMINI_MODEL to an available model (e.g. models/gemini-2.5-flash)",
                    },
                )
            raise HTTPException(
                status_code=502,
                detail=f"Gemini API error: {type(e).__name__}",
            )

        latency_ms = int((time.perf_counter() - t0) * 1000)

        text = (resp.text or "").strip()
        if not text:
            raise HTTPException(status_code=502, detail="Empty response from Gemini")

        # Parse JSON with fallback extraction
        try:
            parsed = json.loads(text)
        except Exception:
            try:
                extracted = _extract_first_json_object(text)
                parsed = json.loads(extracted)
            except Exception:
                logger.error("Non-JSON response from Gemini (first 500 chars): %r", text[:500])
                raise HTTPException(status_code=502, detail="Gemini returned non-JSON output")

        report_data_obj: Optional[Dict[str, Any]] = None
        if isinstance(parsed, dict) and isinstance(parsed.get("REPORT_DATA"), dict):
            report_data_obj = parsed["REPORT_DATA"]
            payload = _map_report_data_to_decision_payload(report_data_obj, case_id)
        elif isinstance(parsed, dict) and _looks_like_report_data(parsed) and "REPORT_DATA" not in parsed:
            # Model zwrócił czysty obiekt REPORT_DATA bez wrappera — opakowujemy
            report_data_obj = parsed
            payload = _map_report_data_to_decision_payload(report_data_obj, case_id)
        else:
            payload = parsed

        # Build trace
        trace = {
            "trace_id": trace_id,
            "model": model,
            "prompt_version": prompt_version,
            "agent_mode": "gemini",
            "generated_at": _utc_now_iso(),
            "latency_ms": latency_ms,
            "usage": getattr(resp, "usage_metadata", None),
        }

        # --- contract guardrails (MVP) ---
        # Wymuszamy decision_version na 1.0 i normalizujemy trace.usage do dict/None.
        payload["decision_version"] = "1.0"

        trace = payload.get("trace") or trace or {}
        usage_obj = trace.get("usage")

        if usage_obj is not None and not isinstance(usage_obj, dict):
            trace["usage"] = {
                "prompt_token_count": getattr(usage_obj, "prompt_token_count", None),
                "candidates_token_count": getattr(usage_obj, "candidates_token_count", None),
                "total_token_count": getattr(usage_obj, "total_token_count", None),
            }

        payload["trace"] = trace
        # --- end guardrails ---

        # Validate Decision
        decision = Decision.model_validate(payload)

        # Zapisz artifacts/report_data_raw.json (1:1 wrapper) — surowy wynik Agenta A
        if report_data_obj is not None:
            try:
                from app.services.storage import ensure_case_dirs
                ensure_case_dirs(case_id)
                artifacts_dir = Path("data") / "cases" / case_id / "artifacts"
                artifacts_dir.mkdir(parents=True, exist_ok=True)
                wrapper = {"REPORT_DATA": report_data_obj}
                raw_path = artifacts_dir / "report_data_raw.json"
                raw_path.write_text(
                    json.dumps(wrapper, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                logger.debug("Saved raw REPORT_DATA for case %s to %s", case_id, raw_path)
            except Exception:
                logger.exception("Failed to save report_data_raw.json (non-fatal)")

        decision_dict = decision.model_dump()
        decision_dict["trace"] = trace
        return decision_dict