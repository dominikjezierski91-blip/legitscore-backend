import mimetypes
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.services.database import get_db, CollectionItem, SessionLocal
from app.routes.auth import get_current_user
from app.services.database import User
from app.services.market_value_agent import estimate_market_value

router = APIRouter()

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
COLLECTION_PHOTOS_DIR = DATA_DIR / "collection_photos"

_EDITABLE_FIELDS = {
    "club", "season", "model_type", "brand", "player_name", "player_number",
    "verdict_category", "purchase_price", "purchase_currency",
    "purchase_date", "purchase_source", "notes",
}


# ── Pydantic models ──────────────────────────────────────────

class CollectionItemCreate(BaseModel):
    case_id: Optional[str] = None  # None dla ręcznych wpisów
    report_mode: Optional[str] = None
    # snapshot z raportu
    club: Optional[str] = None
    season: Optional[str] = None
    model_type: Optional[str] = None
    brand: Optional[str] = None
    player_name: Optional[str] = None
    player_number: Optional[str] = None
    verdict_category: Optional[str] = None
    confidence_percent: Optional[int] = None
    confidence_level: Optional[str] = None
    sku: Optional[str] = None
    report_id: Optional[str] = None
    analysis_date: Optional[str] = None
    # pola usera
    purchase_price: Optional[str] = None
    purchase_currency: Optional[str] = None
    purchase_date: Optional[str] = None
    purchase_source: Optional[str] = None
    notes: Optional[str] = None
    # ręczny wpis
    is_manual: Optional[bool] = False


class CollectionItemUpdate(BaseModel):
    club: Optional[str] = None
    season: Optional[str] = None
    model_type: Optional[str] = None
    brand: Optional[str] = None
    player_name: Optional[str] = None
    player_number: Optional[str] = None
    verdict_category: Optional[str] = None
    purchase_price: Optional[str] = None
    purchase_currency: Optional[str] = None
    purchase_date: Optional[str] = None
    purchase_source: Optional[str] = None
    notes: Optional[str] = None


# ── Helpers ──────────────────────────────────────────────────

async def _auto_estimate_market_value(item_id: str) -> None:
    """Background task: szacuje wartość rynkową tuż po dodaniu do kolekcji."""
    db = SessionLocal()
    try:
        item = db.query(CollectionItem).filter(CollectionItem.id == item_id).first()
        if not item:
            return
        report_data = {
            "subject": {
                "club": item.club, "season": item.season, "brand": item.brand,
                "player_name": item.player_name, "player_number": item.player_number,
                "model": item.model_type,
            },
            "verdict": {"verdict_category": item.verdict_category},
        }
        result = await estimate_market_value(report_data)
        if result.get("sample_size", 0) > 0:
            item.market_value_pln = result.get("median_pln")
            item.market_value_range_min = result.get("range_min_pln")
            item.market_value_range_max = result.get("range_max_pln")
            item.market_value_sample_size = result.get("sample_size")
            item.market_value_source = result.get("source", "gemini")
            item.market_value_updated_at = datetime.now(timezone.utc)
            db.commit()
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Auto market value failed for item %s", item_id)
    finally:
        db.close()


# ── Endpoints ────────────────────────────────────────────────

@router.post("/collection")
async def add_to_collection(
    data: CollectionItemCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Zapobiegaj duplikatom: ten sam user + case_id (tylko dla analiz, nie manual)
    if data.case_id and not data.is_manual:
        existing = db.query(CollectionItem).filter(
            CollectionItem.user_id == current_user.id,
            CollectionItem.case_id == data.case_id,
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail="Ta koszulka jest już w Twojej kolekcji.")

    item = CollectionItem(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        case_id=data.case_id or f"manual_{uuid.uuid4().hex[:12]}",
        added_at=datetime.now(timezone.utc),
        report_mode=data.report_mode,
        club=data.club,
        season=data.season,
        model_type=data.model_type,
        brand=data.brand,
        player_name=data.player_name,
        player_number=data.player_number,
        verdict_category=data.verdict_category,
        confidence_percent=data.confidence_percent,
        confidence_level=data.confidence_level,
        sku=data.sku,
        report_id=data.report_id,
        analysis_date=data.analysis_date,
        purchase_price=data.purchase_price,
        purchase_currency=data.purchase_currency,
        purchase_date=data.purchase_date,
        purchase_source=data.purchase_source,
        notes=data.notes,
        is_manual=bool(data.is_manual),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    background_tasks.add_task(_auto_estimate_market_value, item.id)
    return _serialize(item)


@router.get("/collection")
async def get_collection(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items = (
        db.query(CollectionItem)
        .filter(CollectionItem.user_id == current_user.id)
        .order_by(CollectionItem.added_at.desc())
        .all()
    )
    return [_serialize(i) for i in items]


FIELD_MAX_LENGTHS = {
    "club": 80, "player_name": 60, "brand": 40,
    "model_type": 40, "season": 20, "purchase_source": 60, "notes": 500,
}


@router.patch("/collection/{item_id}")
async def update_collection_item(
    item_id: str,
    data: CollectionItemUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Aktualizuje edytowalne pola pozycji kolekcji."""
    item = db.query(CollectionItem).filter(
        CollectionItem.id == item_id,
        CollectionItem.user_id == current_user.id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Nie znaleziono pozycji w kolekcji.")

    update_dict = data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        if value and field in FIELD_MAX_LENGTHS and len(str(value)) > FIELD_MAX_LENGTHS[field]:
            raise HTTPException(
                status_code=422,
                detail=f"Pole '{field}' przekracza maksymalną długość {FIELD_MAX_LENGTHS[field]} znaków.",
            )
    for field, value in update_dict.items():
        if field in _EDITABLE_FIELDS:
            setattr(item, field, value)

    db.commit()
    db.refresh(item)
    return _serialize(item)


@router.delete("/collection/{item_id}")
async def delete_from_collection(
    item_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = db.query(CollectionItem).filter(
        CollectionItem.id == item_id,
        CollectionItem.user_id == current_user.id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Nie znaleziono pozycji w kolekcji.")
    # Usuń zdjęcie jeśli istnieje
    if item.photo_path:
        try:
            Path(item.photo_path).unlink(missing_ok=True)
        except Exception:
            pass
    db.delete(item)
    db.commit()
    return {"ok": True}


# ── Photo upload/serve ────────────────────────────────────────

@router.post("/collection/{item_id}/photo")
async def upload_collection_photo(
    item_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Wgrywa zdjęcie profilowe dla pozycji kolekcji."""
    item = db.query(CollectionItem).filter(
        CollectionItem.id == item_id,
        CollectionItem.user_id == current_user.id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Nie znaleziono pozycji w kolekcji.")

    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Dozwolone tylko pliki graficzne.")

    COLLECTION_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "photo.jpg").suffix or ".jpg"
    photo_path = COLLECTION_PHOTOS_DIR / f"{item_id}{ext}"

    with photo_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    # Usuń stare zdjęcie jeśli inne rozszerzenie
    if item.photo_path and item.photo_path != str(photo_path):
        try:
            Path(item.photo_path).unlink(missing_ok=True)
        except Exception:
            pass

    item.photo_path = str(photo_path)
    db.commit()
    return {"ok": True, "photo_path": str(photo_path)}


@router.get("/collection/{item_id}/thumbnail")
async def get_collection_thumbnail(
    item_id: str,
    db: Session = Depends(get_db),
):
    """Serwuje zdjęcie profilowe pozycji kolekcji."""
    item = db.query(CollectionItem).filter(
        CollectionItem.id == item_id,
    ).first()
    if not item or not item.photo_path:
        raise HTTPException(status_code=404, detail="Brak zdjęcia.")

    path = Path(item.photo_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Plik zdjęcia nie istnieje.")

    mime = mimetypes.guess_type(str(path))[0] or "image/jpeg"
    return FileResponse(str(path), media_type=mime, headers={"Cache-Control": "no-store, no-cache"})


# ── Market value ─────────────────────────────────────────────

@router.post("/collection/{item_id}/market-value")
async def refresh_market_value(
    item_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Szacuje wartość rynkową koszulki i zapisuje do bazy."""
    item = db.query(CollectionItem).filter(
        CollectionItem.id == item_id,
        CollectionItem.user_id == current_user.id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Nie znaleziono pozycji w kolekcji.")

    report_data = {
        "subject": {
            "club": item.club,
            "season": item.season,
            "brand": item.brand,
            "player_name": item.player_name,
            "player_number": item.player_number,
            "model": item.model_type,
        },
        "verdict": {"verdict_category": item.verdict_category},
    }

    result = await estimate_market_value(report_data)

    if result.get("sample_size", 0) > 0:
        item.market_value_pln = result.get("median_pln")
        item.market_value_range_min = result.get("range_min_pln")
        item.market_value_range_max = result.get("range_max_pln")
        item.market_value_sample_size = result.get("sample_size")
        item.market_value_source = result.get("source", "gemini")
        item.market_value_updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(item)

    return {**_serialize(item), "market_value_result": result}


# ── Admin ────────────────────────────────────────────────────

@router.get("/admin/collection")
async def admin_list_collection(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Brak uprawnień.")
    items = db.query(CollectionItem).order_by(CollectionItem.added_at.desc()).all()
    return [_serialize(i) for i in items]


def _serialize(item: CollectionItem) -> dict:
    return {
        "id": item.id,
        "user_id": item.user_id,
        "case_id": item.case_id,
        "added_at": item.added_at.isoformat() if item.added_at else None,
        "report_mode": item.report_mode,
        "club": item.club,
        "season": item.season,
        "model_type": item.model_type,
        "brand": item.brand,
        "player_name": item.player_name,
        "player_number": item.player_number,
        "verdict_category": item.verdict_category,
        "confidence_percent": item.confidence_percent,
        "confidence_level": item.confidence_level,
        "sku": item.sku,
        "report_id": item.report_id,
        "analysis_date": item.analysis_date,
        "purchase_price": item.purchase_price,
        "purchase_currency": item.purchase_currency,
        "purchase_date": item.purchase_date,
        "purchase_source": item.purchase_source,
        "notes": item.notes,
        "is_manual": bool(item.is_manual),
        "has_photo": bool(item.photo_path),
        "market_value_pln": item.market_value_pln,
        "market_value_range_min": item.market_value_range_min,
        "market_value_range_max": item.market_value_range_max,
        "market_value_sample_size": item.market_value_sample_size,
        "market_value_source": item.market_value_source,
        "market_value_updated_at": item.market_value_updated_at.isoformat() if item.market_value_updated_at else None,
    }
