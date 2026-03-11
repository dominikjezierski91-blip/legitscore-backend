import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse, FileResponse

from app.models.decision import Decision
from app.services.agent_a_gemini import GeminiAgentA, normalize_report_data
from app.services.storage import (
    create_case,
    load_case,
    save_case,
    save_assets,
    save_artifact,
    get_case_dir,
    DATA_DIR,
    CASES_DIR,
)
from app.services.report_text_renderer import render_report_text
from app.services.pdf_report import generate_report_pdf

logger = logging.getLogger(__name__)

_REPORT_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}

router = APIRouter()


@router.post("/cases")
async def create_case_endpoint():
    """Tworzy nowy case i zwraca case_id"""
    case_data = create_case()
    return {"case_id": case_data["case_id"]}


@router.post("/cases/{case_id}/assets")
async def upload_assets(case_id: str, files: List[UploadFile] = File(...)):
    """Przyjmuje multipart/form-data z plikami i zapisuje je do assets"""
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


@router.post("/cases/{case_id}/run-decision")
async def run_decision(case_id: str, mode: str = Query("basic", description="basic | expert")):
    """Uruchamia automatyczną analizę (Gemini), zapisuje decision + report_data.json, generuje report.txt i report.pdf."""
    case_data = load_case(case_id)
    status = case_data.get("status")

    # Idempotentność: analizę uruchamiamy tylko gdy status in ("CREATED", "ASSETS_READY").
    # Drugi request (status IN_PROGRESS/DECIDED/ERROR) nie uruchamia analizy ani nie nadpisuje artefaktów.
    if status not in ("CREATED", "ASSETS_READY"):
        logger.debug("run-decision skipped for case %s, status=%s", case_id, status)
        return {"ok": True, "status": status, "skipped": True}

    assets = case_data.get("assets") or []
    if not assets:
        raise HTTPException(status_code=400, detail="No assets available for decision")

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="Missing GEMINI_API_KEY")

    # Oznacz case jako będący w trakcie analizy.
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

                    report_mode = "expert" if mode == "expert" else "basic"
                    report_text = render_report_text(report_data, mode=report_mode)
                    (artifacts_dir / "report.txt").write_text(report_text, encoding="utf-8")
                    pdf_path = str(artifacts_dir / "report.pdf")
                    generate_report_pdf(case_id, report_data, pdf_path, mode=report_mode)
            except Exception as e:
                logger.exception("Generowanie report.txt / report.pdf nie powiodło się (kontynuujemy): %s", e)

        logger.debug("Final artifacts ready for case %s", case_id)

        # Dopiero po pełnej finalizacji artefaktów oznacz case jako zakończony.
        case_data["status"] = "DECIDED"
        case_data.setdefault("artifacts", {})
        case_data["artifacts"]["decision"] = artifact_path
        save_case(case_id, case_data)
        logger.debug("Case %s status changed to DECIDED", case_id)

        return {"ok": True, "artifact": artifact_path}
    except Exception:
        # W razie błędu oznacz case jako ERROR (minimalny, konserwatywny stan) i ponownie podnieś wyjątek.
        case_data["status"] = "ERROR"
        save_case(case_id, case_data)
        logger.exception("run-decision failed for case %s; status set to ERROR", case_id)
        raise


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
    rid = report_data.get("report_id")
    adate = report_data.get("analysis_date")
    rid_str = (rid or "").strip() if isinstance(rid, str) else ""
    adate_str = (adate or "").strip() if isinstance(adate, str) else ""
    if not rid_str or "2023" in rid_str:
        report_data["report_id"] = f"{id_prefix}-{case_id[:8]}"
    if not adate_str or adate_str.startswith("2023"):
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
    if isinstance(report_data, dict):
        report_id = report_data.get("report_id")
    logger.debug(
        "get_report_data: case_id=%s report_id=%s headers=%s",
        case_id,
        report_id,
        _REPORT_CACHE_HEADERS,
    )
    return JSONResponse(content=wrapper, headers=_REPORT_CACHE_HEADERS)


@router.get("/cases/{case_id}/report-pdf")
async def get_report_pdf(case_id: str):
    """
    Zwraca finalny snapshot report.pdf dla danego case_id.
    Używane przez frontend do pobierania PDF (no-store).
    """
    artifacts_dir = CASES_DIR / case_id / "artifacts"
    path = artifacts_dir / "report.pdf"
    exists = path.exists()
    size = path.stat().st_size if exists else 0
    logger.debug(
        "get_report_pdf: case_id=%s path=%s exists=%s size=%s headers=%s",
        case_id,
        path,
        exists,
        size,
        _REPORT_CACHE_HEADERS,
    )
    if not exists:
        raise HTTPException(status_code=404, detail="report.pdf not found")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"{case_id}_report.pdf",
        headers=_REPORT_CACHE_HEADERS,
    )
