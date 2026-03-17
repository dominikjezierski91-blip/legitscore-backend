import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.services.database import get_db, SupportSubmission
from app.routes.auth import get_current_user, get_current_admin
from app.services.database import User

router = APIRouter()


# ── Pydantic models ───────────────────────────────────────────

class SupportSubmissionCreate(BaseModel):
    type: str
    message: str
    email: Optional[str] = None
    wants_reply: Optional[bool] = False
    user_id: Optional[str] = None
    auth_state: Optional[str] = None
    source_page: Optional[str] = None
    current_url: Optional[str] = None
    app_section: Optional[str] = None
    report_id: Optional[str] = None
    analysis_id: Optional[str] = None
    shirt_id: Optional[str] = None
    collection_item_id: Optional[str] = None


class SupportSubmissionUpdate(BaseModel):
    status: Optional[str] = None
    internal_notes: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────

VALID_TYPES = {"pytanie", "problem", "sugestia", "inne"}
VALID_STATUSES = {"nowe", "w_trakcie", "zamkniete"}


def _serialize(s: SupportSubmission) -> dict:
    return {
        "id": s.id,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "status": s.status,
        "type": s.type,
        "message": s.message,
        "email": s.email,
        "wants_reply": bool(s.wants_reply),
        "user_id": s.user_id,
        "auth_state": s.auth_state,
        "source_page": s.source_page,
        "current_url": s.current_url,
        "app_section": s.app_section,
        "report_id": s.report_id,
        "analysis_id": s.analysis_id,
        "shirt_id": s.shirt_id,
        "collection_item_id": s.collection_item_id,
        "internal_notes": s.internal_notes,
        "resolved_at": s.resolved_at.isoformat() if s.resolved_at else None,
    }


# ── Endpoints ─────────────────────────────────────────────────

@router.post("/support")
async def create_submission(
    data: SupportSubmissionCreate,
    db: Session = Depends(get_db),
):
    """Tworzy nowe zgłoszenie support (publiczny endpoint)."""
    if data.type not in VALID_TYPES:
        raise HTTPException(status_code=422, detail=f"Nieprawidłowy typ zgłoszenia: {data.type}")
    if not data.message or not data.message.strip():
        raise HTTPException(status_code=422, detail="Wiadomość nie może być pusta.")
    if len(data.message) > 1000:
        raise HTTPException(status_code=422, detail="Wiadomość przekracza 1000 znaków.")
    if not data.email or not data.email.strip():
        raise HTTPException(status_code=422, detail="Email jest wymagany.")

    submission = SupportSubmission(
        id=str(uuid.uuid4()),
        status="nowe",
        type=data.type,
        message=data.message.strip(),
        email=data.email.strip() if data.email else None,
        wants_reply=bool(data.wants_reply),
        user_id=data.user_id,
        auth_state=data.auth_state,
        source_page=data.source_page,
        current_url=data.current_url,
        app_section=data.app_section,
        report_id=data.report_id,
        analysis_id=data.analysis_id,
        shirt_id=data.shirt_id,
        collection_item_id=data.collection_item_id,
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)
    return {"ok": True, "id": submission.id}


@router.get("/support")
async def list_submissions(
    db: Session = Depends(get_db),
):
    """Lista wszystkich zgłoszeń (backoffice — publiczny dashboard)."""
    items = (
        db.query(SupportSubmission)
        .order_by(SupportSubmission.created_at.desc())
        .all()
    )
    return [_serialize(i) for i in items]


@router.get("/support/{submission_id}")
async def get_submission(
    submission_id: str,
    db: Session = Depends(get_db),
):
    """Szczegóły zgłoszenia (backoffice)."""
    item = db.query(SupportSubmission).filter(SupportSubmission.id == submission_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Zgłoszenie nie istnieje.")
    return _serialize(item)


@router.patch("/support/{submission_id}")
async def update_submission(
    submission_id: str,
    data: SupportSubmissionUpdate,
    db: Session = Depends(get_db),
):
    """Aktualizuje status / notatki zgłoszenia (backoffice)."""
    item = db.query(SupportSubmission).filter(SupportSubmission.id == submission_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Zgłoszenie nie istnieje.")

    if data.status is not None:
        if data.status not in VALID_STATUSES:
            raise HTTPException(status_code=422, detail=f"Nieprawidłowy status: {data.status}")
        item.status = data.status
        if data.status == "zamkniete" and item.resolved_at is None:
            item.resolved_at = datetime.now(timezone.utc)
        elif data.status != "zamkniete":
            item.resolved_at = None

    if data.internal_notes is not None:
        item.internal_notes = data.internal_notes

    db.commit()
    db.refresh(item)
    return _serialize(item)
