import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Request, Depends
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

from app.models.decision import Decision
from app.services.agent_a_gemini import GeminiAgentA, normalize_report_data, coverage_check, quality_check, red_flag_check
from app.services.consistency_check import run_player_club_consistency_check
from app.services.sku_agent import run_sku_verification
from app.services.storage import (
    create_case,
    load_case,
    save_case,
    save_assets,
    save_assets_from_bytes,
    save_artifact,
    get_case_dir,
    DATA_DIR,
    CASES_DIR,
)
from app.services.auction_scraper import fetch_auction_images, AuctionScraperError
from app.services.report_text_renderer import render_report_text
from app.services.pdf_report import generate_report_pdf
from app.services.database import save_case_to_db, save_feedback_to_db, save_rating_to_db, get_case_from_db, get_all_cases_from_db, get_db_stats, anonymize_case_email, delete_case_from_db
from app.services.security import (
    limiter,
    validate_upload_files,
    validate_email,
    validate_case_id,
    validate_text_field,
    RATE_LIMIT_DEFAULT,
    RATE_LIMIT_UPLOAD,
    RATE_LIMIT_ANALYSIS,
)

logger = logging.getLogger(__name__)

_REPORT_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}

# Twarde reguły coverage — Python decyduje o gatingu, nie model.
_REQUIRED_VIEWS: set = {"front_full", "crest_or_brand_closeup"}
_REQUIRED_VIEW_LABELS: dict = {
    "front_full": "zdjęcie pełnego przodu koszulki",
    "crest_or_brand_closeup": "zbliżenie herbu lub logo producenta",
}
# Quality check blokuje tylko gdy kluczowy widok jest nieużywalny.
# Nieostre zbliżenie herbu / metki nie blokuje — Agent A po prostu ma mniej danych.
_QUALITY_BLOCKING_VIEWS: set = {"front_full"}
# Model może zwrócić alternatywne nazwy dla tych samych widoków.
# Normalizujemy je do kluczy z _REQUIRED_VIEWS przed gatingiem.
_DETECTED_VIEW_ALIASES: dict = {
    "front_full": ["jersey_front", "front_view", "front", "full_front", "shirt_front", "front_side"],
    "back_full": ["jersey_back", "back_view", "back", "full_back", "shirt_back", "back_side"],
    "crest_or_brand_closeup": ["crest", "badge", "logo", "brand_logo", "crest_closeup", "badge_closeup", "logo_closeup"],
}


def _normalize_detected_views(detected_views: dict) -> dict:
    """Mapuje alternatywne nazwy widoków na klucze używane w _REQUIRED_VIEWS."""
    result = dict(detected_views)
    for canonical, aliases in _DETECTED_VIEW_ALIASES.items():
        if not result.get(canonical):
            for alias in aliases:
                if result.get(alias):
                    result[canonical] = True
                    logger.info("Coverage normalization: '%s' mapped to '%s'", alias, canonical)
                    break
    return result


router = APIRouter()


class CreateCaseRequest(BaseModel):
    email: Optional[str] = None
    offer_link: Optional[str] = None
    context: Optional[str] = None


@router.post("/cases")
@limiter.limit(RATE_LIMIT_DEFAULT)
async def create_case_endpoint(request: Request, req: Optional[CreateCaseRequest] = None):
    """Tworzy nowy case i zwraca case_id. Zapisuje email, link do oferty i kontekst."""
    case_data = create_case()
    case_id = case_data["case_id"]

    # Waliduj i zapisz dane do bazy
    if req:
        validated_email = validate_email(req.email) if req.email else None
        offer_link = validate_text_field(req.offer_link, "offer_link", 2000) if req.offer_link else None
        context = validate_text_field(req.context, "context", 5000) if req.context else None

        if validated_email or offer_link or context:
            save_case_to_db(
                case_id=case_id,
                email=validated_email,
                consent_at=datetime.now(timezone.utc) if validated_email else None,
                offer_link=offer_link,
                context=context,
            )

    return {"case_id": case_id}


@router.post("/cases/{case_id}/assets")
@limiter.limit(RATE_LIMIT_UPLOAD)
async def upload_assets(request: Request, case_id: str, files: List[UploadFile] = File(...)):
    """Przyjmuje multipart/form-data z plikami i zapisuje je do assets"""
    # Waliduj case_id
    case_id = validate_case_id(case_id)

    import logging as _logging
    _rlog = _logging.getLogger(__name__)
    _rlog.info("UPLOAD_REQUEST case_id=%s files_count=%d filenames=%r", case_id, len(files), [f.filename for f in files])

    # Waliduj pliki (rozmiar, typ MIME, rozszerzenie)
    try:
        await validate_upload_files(files)
    except HTTPException as _he:
        _rlog.warning("UPLOAD_FAILED detail=%r status=%s", _he.detail, _he.status_code)
        raise

    # Sprawdź czy case istnieje
    case_data = load_case(case_id)

    # Zapisz pliki
    saved_assets = await save_assets(case_id, files)

    # Aktualizuj case.json
    case_data["assets"].extend(saved_assets)
    if len(case_data["assets"]) >= 1:
        case_data["status"] = "ASSETS_READY"

    save_case(case_id, case_data)

    return {"assets": saved_assets}


class ImportFromUrlRequest(BaseModel):
    url: str


@router.post("/cases/{case_id}/import-from-url")
@limiter.limit(RATE_LIMIT_UPLOAD)
async def import_from_url(request: Request, case_id: str, req: ImportFromUrlRequest):
    """
    Pobiera zdjęcia z linku do aukcji (Vinted, Allegro, eBay) i zapisuje jako assets.
    Alternatywa dla ręcznego uploadu zdjęć.
    """
    case_id = validate_case_id(case_id)
    case_data = load_case(case_id)

    # Sprawdź czy case nie ma już assets
    if case_data.get("assets"):
        raise HTTPException(
            status_code=400,
            detail="Case ma już dodane zdjęcia. Utwórz nowy case."
        )

    try:
        # Pobierz zdjęcia z aukcji
        images = await fetch_auction_images(req.url)

        # Zapisz jako assets (używamy tej samej funkcji co upload)
        saved_assets = save_assets_from_bytes(case_id, images)

        # Aktualizuj case.json
        case_data["assets"].extend(saved_assets)
        case_data["status"] = "ASSETS_READY"
        case_data["source_url"] = req.url  # Zapisz źródło dla informacji
        save_case(case_id, case_data)

        logger.info(
            "[IMPORT] case_id=%s case_asset_count_saved=%d source_url=%s",
            case_id,
            len(saved_assets),
            req.url[:100]
        )

        return {
            "ok": True,
            "assets": saved_assets,
            "count": len(saved_assets),
        }

    except AuctionScraperError as e:
        logger.warning("Błąd scrapera dla case %s: %s", case_id, str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Nieoczekiwany błąd podczas importu z URL dla case %s", case_id)
        raise HTTPException(
            status_code=500,
            detail="Wystąpił błąd podczas pobierania zdjęć z aukcji."
        )


@router.post("/cases/{case_id}/decision")
async def submit_decision(case_id: str, decision: Decision):
    """Przyjmuje decyzję, zapisuje ją jako artefakt i aktualizuje case."""
    # 404 jeśli case nie istnieje
    case_data = load_case(case_id)

    artifact_data = decision.dict()
    artifact_path = save_artifact(case_id, "decision", artifact_data)

    case_data["status"] = "DECIDED"
    case_data.setdefault("artifacts", {})
    case_data["artifacts"]["decision"] = artifact_path

    save_case(case_id, case_data)

    return {"ok": True, "artifact": artifact_path}


# Test flow: POST /api/cases → POST /api/cases/{id}/assets (zdjęcia) → POST /api/cases/{id}/run-decision?mode=basic
# Sprawdź: /cases/{id}/artifacts/report_data.json, /cases/{id}/artifacts/report.txt, /cases/{id}/artifacts/report.pdf


_LOCK_FILE = "analysis.lock"


@router.post("/cases/{case_id}/run-decision")
@limiter.limit(RATE_LIMIT_ANALYSIS)
async def run_decision(request: Request, case_id: str, mode: str = Query("basic", description="basic | expert")):
    """Uruchamia automatyczną analizę (Gemini), zapisuje decision + report_data.json, generuje report.txt i report.pdf."""
    # Waliduj case_id
    case_id = validate_case_id(case_id)

    # Waliduj mode
    if mode not in ("basic", "expert"):
        raise HTTPException(status_code=400, detail="Nieprawidłowy tryb. Dozwolone: basic, expert")

    case_data = load_case(case_id)
    status = case_data.get("status")

    artifacts_dir = CASES_DIR / case_id / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    lock_path = artifacts_dir / _LOCK_FILE
    decision_path = artifacts_dir / "decision.json"
    report_data_path = artifacts_dir / "report_data.json"

    # Twarda idempotencja: lock lub finalne artefakty -> nie uruchamiaj analizy ponownie.
    if lock_path.exists():
        logger.debug("run-decision skipped for case %s because lock exists", case_id)
        return {"ok": True, "status": status, "skipped": True}
    if decision_path.exists() or report_data_path.exists():
        logger.debug("run-decision skipped for case %s because final artifacts already exist", case_id)
        return {"ok": True, "status": status or "DECIDED", "skipped": True}

    lock_created = False
    lock_path.touch()
    lock_created = True

    assets = case_data.get("assets") or []
    if not assets:
        lock_path.unlink(missing_ok=True)
        lock_created = False
        raise HTTPException(status_code=400, detail="No assets available for decision")

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        lock_path.unlink(missing_ok=True)
        lock_created = False
        raise HTTPException(status_code=500, detail="Missing GEMINI_API_KEY")

    case_data["status"] = "IN_PROGRESS"
    save_case(case_id, case_data)
    logger.info("run-decision started for case %s (mode=%s)", case_id, mode)

    try:
        asset_paths: List[str] = []
        for asset in assets:
            rel_path = asset.get("path")
            if not rel_path:
                continue
            asset_paths.append(str(DATA_DIR / rel_path))

        logger.info(
            "[RUN_DECISION] case_id=%s total_assets=%d asset_paths=%s",
            case_id,
            len(asset_paths),
            [p.split("/")[-1] for p in asset_paths]  # Only filenames for brevity
        )

        # ============================================================
        # ETAP 1: Photo Coverage Check
        # ============================================================
        logger.info("[PRECHECK] case_id=%s stage=coverage coverage_assets_count=%d", case_id, len(asset_paths))
        coverage_result = await coverage_check(asset_paths)

        # Gating na podstawie twardych reguł REQUIRED_VIEWS — nie używamy can_continue z modelu.
        detected_views = _normalize_detected_views(coverage_result.get("detected_views") or {})
        missing_required_keys = [k for k in _REQUIRED_VIEWS if not detected_views.get(k)]

        if missing_required_keys:
            missing_labels = [_REQUIRED_VIEW_LABELS.get(k, k) for k in missing_required_keys]
            lock_path.unlink(missing_ok=True)
            case_data["status"] = "PRECHECK_FAILED"
            case_data["precheck_result"] = {
                "stage": "coverage",
                "message": "Brakuje wymaganych zdjęć do przeprowadzenia analizy.",
                "missing_required": missing_labels,
                "missing_optional": coverage_result.get("missing_optional") or [],
                "detected_views": detected_views,
            }
            save_case(case_id, case_data)

            logger.warning(
                "[PRECHECK] case_id=%s stage=coverage precheck_result=FAILED missing=%s",
                case_id,
                missing_required_keys,
            )
            raise HTTPException(
                status_code=400,
                detail=case_data["precheck_result"]
            )

        logger.info(
            "[PRECHECK] case_id=%s stage=coverage precheck_result=PASSED detected=%s",
            case_id,
            list(detected_views.keys()),
        )

        # ============================================================
        # ETAP 2: Photo Quality Check
        # ============================================================
        logger.info("[PRECHECK] case_id=%s stage=quality quality_assets_count=%d", case_id, len(asset_paths))
        quality_result = await quality_check(asset_paths, detected_views=detected_views)

        # Blokuj tylko gdy problemy dotyczą krytycznych widoków (REQUIRED_VIEWS).
        # Problemy z identity_tag, material_closeup itp. nie blokują analizy.
        quality_issues = quality_result.get("issues") or []
        blocking_quality_issues = [i for i in quality_issues if i.get("area") in _QUALITY_BLOCKING_VIEWS]

        if blocking_quality_issues:
            lock_path.unlink(missing_ok=True)
            case_data["status"] = "PRECHECK_FAILED"
            case_data["precheck_result"] = {
                "stage": "quality",
                "message": quality_result.get("message") or "Jakość kluczowych zdjęć jest niewystarczająca do przeprowadzenia analizy.",
                "issues": blocking_quality_issues,
            }
            save_case(case_id, case_data)

            logger.warning(
                "[PRECHECK] case_id=%s stage=quality precheck_result=FAILED blocking_areas=%s",
                case_id,
                [i.get("area") for i in blocking_quality_issues],
            )
            raise HTTPException(
                status_code=400,
                detail=case_data["precheck_result"]
            )

        logger.info("[PRECHECK] case_id=%s stage=quality precheck_result=PASSED", case_id)

        # ============================================================
        # ETAP 3: Agent A Forensic Analysis (bez zmian)
        # ============================================================
        logger.info("[AGENT_A] case_id=%s agent_a_started=true assets_count=%d", case_id, len(asset_paths))
        decision_dict = await GeminiAgentA().analyze(case_id, asset_paths)

        try:
            decision_model = Decision.model_validate(decision_dict)
        except Exception:
            case_dir = get_case_dir(case_id)
            artifacts_dir = case_dir / "artifacts"
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            raw_path = artifacts_dir / "decision_raw.txt"
            with open(raw_path, "w", encoding="utf-8") as f:
                f.write(json.dumps(decision_dict, indent=2, ensure_ascii=False))
            raise HTTPException(status_code=422, detail="Decision validation failed")

        artifact_path = save_artifact(case_id, "decision", decision_model.model_dump())

        # Generuj report.txt i report.pdf z report_data.json (non-fatal)
        artifacts_dir = CASES_DIR / case_id / "artifacts"
        raw_report_path = artifacts_dir / "report_data_raw.json"
        report_data_path = artifacts_dir / "report_data.json"
        source_path: Path | None = None
        if raw_report_path.exists():
            source_path = raw_report_path
            logger.debug("Loading raw REPORT_DATA for case %s from %s", case_id, raw_report_path)
        elif report_data_path.exists():
            # Defensywnie: obsłuż starsze przypadki, gdzie mamy tylko finalny report_data.json
            source_path = report_data_path
            logger.debug(
                "Loading REPORT_DATA for case %s from existing %s (no raw file found)",
                case_id,
                report_data_path,
            )

        if source_path is not None:
            try:
                with open(source_path, "r", encoding="utf-8") as f:
                    wrapper = json.load(f)
                report_data = wrapper.get("REPORT_DATA") if isinstance(wrapper, dict) else None
                if isinstance(report_data, dict):
                    # Minimal technical fix: ensure report_id and analysis_date when missing.
                    # Renderer uses saved REPORT_DATA; never invent static dates in templates.
                    _ensure_report_metadata(report_data, case_id)
                    # Debug: pokaż surowe REPORT_DATA z Agenta A przed normalizacją techniczną.
                    try:
                        logger.debug(
                            "REPORT_DATA raw (Agent A) for case %s: %s",
                            case_id,
                            json.dumps(report_data, ensure_ascii=False),
                        )
                    except Exception:
                        logger.exception("Failed to log raw REPORT_DATA for case %s", case_id)

                    # Minimalna normalizacja techniczna (skala prawdopodobieństw + spójność verdictu).
                    normalize_report_data(report_data)

                    # Debug: pokaż REPORT_DATA po normalizacji (ta wersja jest zapisywana i renderowana).
                    try:
                        logger.debug(
                            "REPORT_DATA normalized for case %s: %s",
                            case_id,
                            json.dumps(report_data, ensure_ascii=False),
                        )
                    except Exception:
                        logger.exception("Failed to log normalized REPORT_DATA for case %s", case_id)

                    # ============================================================
                    # ETAP 4: Pomocniczy factual check spójności personalizacji.
                    # Strictly non-fatal — nigdy nie przerywa flow, nie zmienia werdyktu.
                    # ============================================================
                    try:
                        pcc_result = await run_player_club_consistency_check(report_data)
                        report_data["player_club_consistency"] = pcc_result
                        logger.info(
                            "[CONSISTENCY_CHECK] case_id=%s status=%s confidence=%s",
                            case_id, pcc_result.get("status"), pcc_result.get("confidence"),
                        )
                    except Exception:
                        logger.exception("[CONSISTENCY_CHECK] Nieoczekiwany błąd (non-fatal), case_id=%s", case_id)
                        report_data["player_club_consistency"] = {
                            "status": "uncertain",
                            "confidence": "low",
                            "reason": "Nie udało się wykonać dodatkowego sprawdzenia zgodności personalizacji.",
                            "notes": [],
                        }

                    # ============================================================
                    # ETAP 5: Pomocnicza weryfikacja SKU.
                    # Strictly non-fatal — nigdy nie przerywa flow, nie zmienia werdyktu.
                    # ============================================================
                    try:
                        sku_result = await run_sku_verification(report_data)
                        report_data["sku_verification"] = sku_result
                        logger.info(
                            "[SKU_VERIFICATION] case_id=%s status=%s confidence=%s",
                            case_id, sku_result.get("status"), sku_result.get("confidence"),
                        )
                    except Exception:
                        logger.exception("[SKU_VERIFICATION] Nieoczekiwany błąd (non-fatal), case_id=%s", case_id)
                        report_data["sku_verification"] = {
                            "status": "uncertain",
                            "confidence": "low",
                            "reason": "Nie udało się wykonać weryfikacji SKU.",
                            "source_url": "",
                        }

                    # Nadpisz artefakt report_data.json z już znormalizowanym REPORT_DATA.
                    try:
                        report_data_path.write_text(
                            json.dumps({"REPORT_DATA": report_data}, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                        logger.debug(
                            "Final REPORT_DATA written for case %s to %s",
                            case_id,
                            report_data_path,
                        )
                    except Exception:
                        logger.exception("Failed to overwrite report_data.json for case %s", case_id)

                    # Jedno źródło prawdy: PDF i report.txt z report_data.json (nie z raw ani decision).
                    report_mode = "expert" if mode == "expert" else "basic"
                    with open(report_data_path, "r", encoding="utf-8") as f:
                        wrapper_from_file = json.load(f)
                    report_data_for_render = wrapper_from_file.get("REPORT_DATA") if isinstance(wrapper_from_file, dict) else report_data
                    if not isinstance(report_data_for_render, dict):
                        report_data_for_render = report_data
                    report_text = render_report_text(report_data_for_render, mode=report_mode)
                    (artifacts_dir / "report.txt").write_text(report_text, encoding="utf-8")
                    pdf_path = str(artifacts_dir / "report.pdf")
                    generate_report_pdf(case_id, report_data_for_render, pdf_path, mode=report_mode)
            except Exception as e:
                logger.exception("Generowanie report.txt / report.pdf nie powiodło się (kontynuujemy): %s", e)

        logger.debug("Final artifacts ready for case %s", case_id)

        # Zapisz do bazy danych dla przyszłego ML
        try:
            verdict_cat = None
            conf_pct = None
            extracted_sku = None
            if isinstance(report_data, dict):
                verdict_obj = report_data.get("verdict") or {}
                if isinstance(verdict_obj, dict):
                    verdict_cat = verdict_obj.get("verdict_category")
                    conf_pct = verdict_obj.get("confidence_percent")
                # Wyciągnij SKU jeśli model go wykrył
                extracted_sku = _extract_sku_from_report(report_data)
                if extracted_sku:
                    logger.info("Extracted SKU for case %s: %s", case_id, extracted_sku)

            save_case_to_db(
                case_id=case_id,
                model=os.getenv("GEMINI_MODEL", "unknown"),
                prompt_version=os.getenv("A_PROMPT_VERSION", "unknown"),
                verdict_category=verdict_cat,
                confidence_percent=conf_pct,
                report_data=report_data,
                sku=extracted_sku,
            )
            logger.info("Case %s saved to database", case_id)
        except Exception:
            logger.exception("Failed to save case %s to database (non-fatal)", case_id)

        # Dopiero po pełnej finalizacji artefaktów oznacz case jako zakończony.
        case_data["status"] = "DECIDED"
        case_data.setdefault("artifacts", {})
        case_data["artifacts"]["decision"] = artifact_path
        save_case(case_id, case_data)
        logger.debug("Case %s status changed to DECIDED", case_id)

        logger.debug("run-decision finished for case %s", case_id)
        return {"ok": True, "artifact": artifact_path}
    except HTTPException:
        # HTTPException z prechecków - nie nadpisuj statusu ERROR, propaguj dalej
        raise
    except Exception:
        case_data["status"] = "ERROR"
        save_case(case_id, case_data)
        logger.exception("run-decision failed for case %s; status set to ERROR", case_id)
        raise
    finally:
        if lock_created and lock_path.exists():
            try:
                lock_path.unlink()
            except OSError:
                logger.warning("Failed to remove analysis.lock for case %s", case_id)


def _extract_sku_from_report(report_data: Dict[str, Any]) -> Optional[str]:
    """
    Wyciąga SKU z raportu AI jeśli zostało wykryte.
    Szuka w key_evidence, decision_matrix i summary.
    """
    if not isinstance(report_data, dict):
        return None

    # Konwertuj cały raport do tekstu
    text = json.dumps(report_data, ensure_ascii=False)

    # Wzorce SKU dla różnych producentów
    patterns = [
        r'\b([A-Z]{2}\d{4}-\d{3})\b',  # Nike: DM1840-452
        r'\b([A-Z]{2}\d{2}-\d{1,3}[A-Z]{0,2}(?:-[A-Z0-9]+)?)\b',  # Inne: NS22-1GA-PS-200
        r'\b([A-Z]{2}\d{5})\b',  # Adidas: GL3746
        r'SKU[:\s]+([A-Z0-9\-]+)',  # Generyczny z prefiksem SKU
    ]

    found_skus = []
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            # Filtruj fałszywe trafienia (za krótkie, tylko litery/cyfry)
            if len(match) >= 5 and re.search(r'\d', match) and re.search(r'[A-Z]', match, re.IGNORECASE):
                found_skus.append(match.upper())

    # Usuń duplikaty i zwróć pierwszy znaleziony
    unique_skus = list(dict.fromkeys(found_skus))
    if unique_skus:
        return unique_skus[0]

    return None


def _ensure_report_metadata(report_data: Dict[str, Any], case_id: str) -> None:
    """
    Minimal technical fix: ensure report_id and analysis_date are current.
    Fills when missing; overwrites when values look like stale samples (e.g. 2023).
    Renderer must not show old placeholder metadata.
    """
    if not isinstance(report_data, dict):
        return
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    id_prefix = now.strftime("%Y%m%d")
    # Backend jest jedynym źródłem prawdy dla metadanych raportu
    report_data["report_id"] = f"{id_prefix}-{case_id[:8]}"
    report_data["analysis_date"] = date_str


@router.get("/cases/{case_id}")
async def get_case(case_id: str):
    """Zwraca cały case.json"""
    case_data = load_case(case_id)
    return case_data


@router.get("/cases/{case_id}/report-data")
async def get_report_data(case_id: str):
    """
    Zwraca finalny snapshot REPORT_DATA dla danego case_id.
    Używane przez frontend do wyświetlania wyniku (no-store).
    """
    artifacts_dir = CASES_DIR / case_id / "artifacts"
    path = artifacts_dir / "report_data.json"
    exists = path.exists()
    size = path.stat().st_size if exists else 0
    logger.debug(
        "get_report_data: case_id=%s path=%s exists=%s size=%s",
        case_id,
        path,
        exists,
        size,
    )
    if not exists:
        raise HTTPException(status_code=404, detail="report_data.json not found")
    try:
        with open(path, "r", encoding="utf-8") as f:
            wrapper = json.load(f)
    except Exception:
        logger.exception("Failed to read report_data.json for case %s", case_id)
        raise HTTPException(status_code=500, detail="Failed to read report_data.json")
    report_data = wrapper.get("REPORT_DATA") if isinstance(wrapper, dict) else None
    report_id = None
    confidence_percent = None
    if isinstance(report_data, dict):
        report_id = report_data.get("report_id")
        verdict_obj = report_data.get("verdict") or {}
        if isinstance(verdict_obj, dict):
            confidence_percent = verdict_obj.get("confidence_percent")
    logger.debug(
        "report-data loaded: case_id=%s report_id=%s confidence_percent=%s",
        case_id,
        report_id,
        confidence_percent,
    )
    return JSONResponse(content=wrapper, headers=_REPORT_CACHE_HEADERS)


@router.get("/cases/{case_id}/thumbnail")
async def get_case_thumbnail(case_id: str):
    """Zwraca pierwsze zdjęcie z assets jako miniaturę do panelu kolekcji."""
    from fastapi.responses import FileResponse as _FileResponse
    import mimetypes as _mimetypes
    case_data = load_case(case_id)
    assets = case_data.get("assets") or []
    for asset in assets:
        rel_path = (asset.get("path") or "").lstrip("/")
        if not rel_path:
            continue
        full_path = Path("data") / rel_path
        if full_path.exists() and full_path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
            mime = _mimetypes.guess_type(str(full_path))[0] or "image/jpeg"
            return _FileResponse(str(full_path), media_type=mime, headers={"Cache-Control": "no-store, no-cache"})
    raise HTTPException(status_code=404, detail="No image assets found")


@router.get("/cases/{case_id}/report-pdf")
async def get_report_pdf(case_id: str):
    """
    Zwraca finalny snapshot report.pdf dla danego case_id.
    Content-Disposition: inline umożliwia preview w Safari/Chrome mobile.
    """
    artifacts_dir = CASES_DIR / case_id / "artifacts"
    path = artifacts_dir / "report.pdf"
    exists = path.exists()
    size = path.stat().st_size if exists else 0

    headers = dict(_REPORT_CACHE_HEADERS)
    headers["Content-Disposition"] = f'inline; filename="{case_id}_report.pdf"'

    logger.debug(
        "report-pdf: case_id=%s size=%s content_disposition=inline",
        case_id,
        size,
    )
    if not exists:
        raise HTTPException(status_code=404, detail="report.pdf not found")
    return FileResponse(
        path,
        media_type="application/pdf",
        headers=headers,
    )


class FeedbackRequest(BaseModel):
    feedback: str  # "correct" | "incorrect" | "unsure"
    comment: Optional[str] = None


@router.post("/cases/{case_id}/feedback")
@limiter.limit(RATE_LIMIT_DEFAULT)
async def submit_feedback(request: Request, case_id: str, req: FeedbackRequest):
    """
    Zapisuje feedback użytkownika o poprawności analizy.
    feedback: correct | incorrect | unsure
    """
    case_id = validate_case_id(case_id)

    if req.feedback not in ("correct", "incorrect", "unsure"):
        raise HTTPException(status_code=400, detail="Invalid feedback value")

    try:
        save_feedback_to_db(case_id, req.feedback, req.comment)
        logger.info("Feedback saved for case %s: %s", case_id, req.feedback)
        return {"ok": True, "feedback": req.feedback}
    except Exception:
        logger.exception("Failed to save feedback for case %s", case_id)
        raise HTTPException(status_code=500, detail="Failed to save feedback")


@router.get("/cases/{case_id}/feedback")
async def get_feedback(case_id: str):
    """Pobiera zapisany feedback dla case."""
    record = get_case_from_db(case_id)
    if record is None:
        return {"feedback": None}
    return {
        "feedback": record.feedback,
        "feedback_at": record.feedback_at.isoformat() if record.feedback_at else None,
        "comment": record.feedback_comment,
    }


class RatingRequest(BaseModel):
    rating: int  # 1-5 (piłki nożne)
    comment: Optional[str] = None


@router.post("/cases/{case_id}/rating")
@limiter.limit(RATE_LIMIT_DEFAULT)
async def submit_rating(request: Request, case_id: str, req: RatingRequest):
    """Zapisuje ocenę raportu (1-5 piłek nożnych)."""
    case_id = validate_case_id(case_id)

    if req.rating < 1 or req.rating > 5:
        raise HTTPException(status_code=400, detail="Ocena musi być w zakresie 1-5")

    comment = validate_text_field(req.comment, "comment", 1000) if req.comment else None

    success = save_rating_to_db(case_id, req.rating, comment)
    if not success:
        raise HTTPException(status_code=404, detail="Case not found")

    logger.info("Rating saved for case %s: %d", case_id, req.rating)
    return {"ok": True, "rating": req.rating}


@router.get("/cases/{case_id}/rating")
async def get_rating(case_id: str):
    """Pobiera ocenę raportu."""
    record = get_case_from_db(case_id)
    if record is None:
        return {"rating": None}
    return {
        "rating": record.rating,
        "rating_at": record.rating_at.isoformat() if record.rating_at else None,
    }


@router.get("/dashboard/cases")
@limiter.limit(RATE_LIMIT_DEFAULT)
async def list_all_cases(request: Request):
    """Lista wszystkich case'ów z bazy (dla dashboardu)."""
    return get_all_cases_from_db()


@router.get("/dashboard/stats")
@limiter.limit(RATE_LIMIT_DEFAULT)
async def get_stats(request: Request):
    """Statystyki z bazy (dla dashboardu)."""
    return get_db_stats()


@router.delete("/cases/{case_id}/email")
async def anonymize_email(case_id: str):
    """Anonimizuje email w case (RODO - prawo do bycia zapomnianym)."""
    success = anonymize_case_email(case_id)
    if not success:
        raise HTTPException(status_code=404, detail="Case not found in database")
    return {"ok": True, "message": "Email został usunięty"}


@router.delete("/cases/{case_id}")
async def delete_case(case_id: str):
    """Usuwa case z bazy danych (RODO - prawo do bycia zapomnianym)."""
    success = delete_case_from_db(case_id)
    if not success:
        raise HTTPException(status_code=404, detail="Case not found in database")
    return {"ok": True, "message": "Dane zostały usunięte z bazy"}
