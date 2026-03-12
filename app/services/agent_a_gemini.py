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