import json
import logging
import os
from pathlib import Path
from typing import List

from fastapi import APIRouter, UploadFile, File, HTTPException, Query

from app.models.decision import Decision
from app.services.agent_a_gemini import GeminiAgentA
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

    assets = case_data.get("assets") or []
    if not assets:
        raise HTTPException(status_code=400, detail="No assets available for decision")

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="Missing GEMINI_API_KEY")

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

    case_data["status"] = "DECIDED"
    case_data.setdefault("artifacts", {})
    case_data["artifacts"]["decision"] = artifact_path
    save_case(case_id, case_data)

    # Generuj report.txt i report.pdf z report_data.json (non-fatal)
    artifacts_dir = CASES_DIR / case_id / "artifacts"
    report_data_path = artifacts_dir / "report_data.json"
    if report_data_path.exists():
        try:
            with open(report_data_path, "r", encoding="utf-8") as f:
                wrapper = json.load(f)
            report_data = wrapper.get("REPORT_DATA") if isinstance(wrapper, dict) else None
            if isinstance(report_data, dict):
                report_mode = "expert" if mode == "expert" else "basic"
                report_text = render_report_text(report_data, mode=report_mode)
                (artifacts_dir / "report.txt").write_text(report_text, encoding="utf-8")
                pdf_path = str(artifacts_dir / "report.pdf")
                generate_report_pdf(case_id, report_text, pdf_path)
        except Exception as e:
            logger.exception("Generowanie report.txt / report.pdf nie powiodło się (kontynuujemy): %s", e)

    return {"ok": True, "artifact": artifact_path}

@router.get("/cases/{case_id}")
async def get_case(case_id: str):
    """Zwraca cały case.json"""
    case_data = load_case(case_id)
    return case_data
