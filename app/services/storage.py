from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone
from fastapi import UploadFile, HTTPException
from typing import Dict, List


DATA_DIR = Path("data")
CASES_DIR = DATA_DIR / "cases"


def ensure_case_dirs(case_id: str) -> None:
    """Tworzy katalogi dla case: data/cases/{case_id}/assets i data/cases/{case_id}/artifacts"""
    case_dir = CASES_DIR / case_id
    (case_dir / "assets").mkdir(parents=True, exist_ok=True)
    (case_dir / "artifacts").mkdir(parents=True, exist_ok=True)


def case_path(case_id: str) -> Path:
    """Zwraca ścieżkę do case.json"""
    return CASES_DIR / case_id / "case.json"


def get_case_dir(case_id: str) -> Path:
    """Zwraca katalog case: data/cases/{case_id}"""
    return CASES_DIR / case_id


def load_case(case_id: str) -> Dict:
    """Ładuje case.json i zwraca jako dict. Rzuca 404 jeśli brak."""
    path = case_path(case_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    import json

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_case(case_id: str, data: Dict) -> None:
    """Zapisuje case.json"""
    path = case_path(case_id)
    path.parent.mkdir(parents=True, exist_ok=True)

    import json

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def create_case() -> Dict:
    """Tworzy nowy case i zwraca dict z created_at ISO"""
    case_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()

    case_data = {
        "case_id": case_id,
        "created_at": now,
        "status": "CREATED",
        "assets": [],
        "artifacts": {},
    }

    ensure_case_dirs(case_id)
    save_case(case_id, case_data)

    return case_data


async def save_assets(case_id: str, files: List[UploadFile]) -> List[Dict]:
    """Zapisuje pliki do data/cases/{case_id}/assets/ i zwraca listę dict z asset_id, filename, path, uploaded_at"""
    ensure_case_dirs(case_id)
    assets_dir = CASES_DIR / case_id / "assets"

    saved_assets: List[Dict] = []
    now = datetime.now(timezone.utc).isoformat()

    for file in files:
        asset_id = str(uuid4())
        filename = f"{asset_id}_{file.filename}"
        file_path = assets_dir / filename

        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        asset_info = {
            "asset_id": asset_id,
            "filename": file.filename,
            "path": str(file_path.relative_to(DATA_DIR)),
            "uploaded_at": now,
        }
        saved_assets.append(asset_info)

    return saved_assets


def save_assets_from_bytes(case_id: str, images: List[tuple]) -> List[Dict]:
    """
    Zapisuje obrazy z bytes do data/cases/{case_id}/assets/.
    images: lista krotek (bytes, filename)
    Zwraca listę dict z asset_id, filename, path, uploaded_at.
    """
    ensure_case_dirs(case_id)
    assets_dir = CASES_DIR / case_id / "assets"

    saved_assets: List[Dict] = []
    now = datetime.now(timezone.utc).isoformat()

    for content, original_filename in images:
        asset_id = str(uuid4())
        filename = f"{asset_id}_{original_filename}"
        file_path = assets_dir / filename

        with open(file_path, "wb") as f:
            f.write(content)

        asset_info = {
            "asset_id": asset_id,
            "filename": original_filename,
            "path": str(file_path.relative_to(DATA_DIR)),
            "uploaded_at": now,
        }
        saved_assets.append(asset_info)

    return saved_assets


def save_artifact(case_id: str, name: str, data: Dict) -> str:
    """Zapisuje artefakt JSON w data/cases/{case_id}/artifacts/{name}.json i zwraca ścieżkę względną od DATA_DIR."""
    ensure_case_dirs(case_id)
    artifacts_dir = CASES_DIR / case_id / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{name}.json"
    path = artifacts_dir / filename

    import json

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return str(path.relative_to(DATA_DIR))
