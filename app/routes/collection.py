import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.services.database import get_db, CollectionItem
from app.routes.auth import get_current_user
from app.services.database import User
from app.services.market_value_agent import estimate_market_value

router = APIRouter()


# ── Pydantic models ──────────────────────────────────────────

class CollectionItemCreate(BaseModel):
    case_id: str
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


# ── Endpoints ────────────────────────────────────────────────

@router.post("/collection")
async def add_to_collection(
    data: CollectionItemCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Zapobiegaj duplikatom (ten sam user + case_id)
    existing = db.query(CollectionItem).filter(
        CollectionItem.user_id == current_user.id,
        CollectionItem.case_id == data.case_id,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Ta koszulka jest już w Twojej kolekcji.")

    item = CollectionItem(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        case_id=data.case_id,
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
    )
    db.add(item)
    db.commit()
    db.refresh(item)
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
    db.delete(item)
    db.commit()
    return {"ok": True}


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

    # Zbuduj mini report_data z danych snapshotu w kolekcji
    report_data = {
        "subject": {
            "club": item.club,
            "season": item.season,
            "brand": item.brand,
            "player_name": item.player_name,
            "player_number": item.player_number,
            "model": item.model_type,
        },
        "verdict": {
            "verdict_category": item.verdict_category,
        },
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


# ── Admin: wszystkie rekordy kolekcji ────────────────────────

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
        "market_value_pln": item.market_value_pln,
        "market_value_range_min": item.market_value_range_min,
        "market_value_range_max": item.market_value_range_max,
        "market_value_sample_size": item.market_value_sample_size,
        "market_value_source": item.market_value_source,
        "market_value_updated_at": item.market_value_updated_at.isoformat() if item.market_value_updated_at else None,
    }
