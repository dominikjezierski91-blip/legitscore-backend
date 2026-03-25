import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.services.database import get_db, User, CollectionItem, PasswordResetToken
from app.services.auth_service import hash_password, verify_password, create_access_token, decode_access_token
from app.services.email_service import send_welcome_email, send_password_reset_email
from app.services.security import limiter, RATE_LIMIT_DEFAULT

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")

router = APIRouter()


# ── Pydantic models ──────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)
    password_confirm: str = Field(max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# ── Helper: wyciągnij usera z tokena ─────────────────────────

def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Brak autoryzacji.")
    token = auth[7:]
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token wygasł lub jest nieprawidłowy.")
    user = db.query(User).filter(User.id == payload["sub"]).first()
    if not user:
        raise HTTPException(status_code=401, detail="Użytkownik nie istnieje.")
    return user


def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Brak uprawnień administratora.")
    return current_user


# ── Endpoints ────────────────────────────────────────────────

@router.post("/auth/register")
async def register(data: RegisterRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    if len(data.password) < 8:
        raise HTTPException(status_code=400, detail="Hasło musi mieć co najmniej 8 znaków.")
    if data.password != data.password_confirm:
        raise HTTPException(status_code=400, detail="Hasła nie są identyczne.")

    email = data.email.strip().lower()
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Konto z tym adresem email już istnieje.")

    user = User(
        id=str(uuid.uuid4()),
        email=email,
        password_hash=hash_password(data.password),
        is_admin=False,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id, is_admin=user.is_admin)
    # Email powitalny — BackgroundTasks (nie blokuje odpowiedzi)
    background_tasks.add_task(send_welcome_email, email)
    return {"token": token, "user": {"id": user.id, "email": user.email, "is_admin": user.is_admin}}


@router.post("/auth/login")
async def login(data: LoginRequest, db: Session = Depends(get_db)):
    email = data.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Nieprawidłowy email lub hasło.")

    token = create_access_token(user.id, is_admin=user.is_admin)
    return {"token": token, "user": {"id": user.id, "email": user.email, "is_admin": user.is_admin}}


@router.get("/auth/me")
async def me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "is_admin": current_user.is_admin,
        "user_type": getattr(current_user, "user_type", None),
        "collection_size_range": getattr(current_user, "collection_size_range", None),
        "profile_survey_completed_at": (
            getattr(current_user, "profile_survey_completed_at", None).isoformat()
            if getattr(current_user, "profile_survey_completed_at", None) else None
        ),
        "profile_survey_skipped_at": (
            getattr(current_user, "profile_survey_skipped_at", None).isoformat()
            if getattr(current_user, "profile_survey_skipped_at", None) else None
        ),
    }


# ── Admin: lista użytkowników ────────────────────────────────

@router.get("/admin/users")
async def admin_list_users(
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    users = db.query(User).order_by(User.created_at.desc()).all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "is_admin": u.is_admin,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


VALID_USER_TYPES = {"kolekcjoner", "okazjonalny_kupujacy", "sprzedajacy"}
VALID_COLLECTION_SIZES = {"0-5", "6-20", "21-50", "50+"}


class ProfileSurveyRequest(BaseModel):
    user_type: Optional[str] = None
    collection_size_range: Optional[str] = None


@router.post("/auth/profile-survey")
async def submit_profile_survey(
    data: ProfileSurveyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Zapisuje profil użytkownika zebrany po rejestracji."""
    if data.user_type and data.user_type not in VALID_USER_TYPES:
        raise HTTPException(status_code=400, detail="Nieprawidłowy typ użytkownika.")
    if data.collection_size_range and data.collection_size_range not in VALID_COLLECTION_SIZES:
        raise HTTPException(status_code=400, detail="Nieprawidłowy zakres kolekcji.")

    if data.user_type:
        current_user.user_type = data.user_type
    if data.collection_size_range:
        current_user.collection_size_range = data.collection_size_range
    current_user.profile_survey_completed_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


@router.post("/auth/profile-survey/skip")
async def skip_profile_survey(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Zapisuje pominięcie profilu użytkownika."""
    current_user.profile_survey_skipped_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


@router.patch("/auth/profile")
async def update_profile(
    data: ProfileSurveyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Aktualizuje profil użytkownika (edycja z poziomu konta)."""
    if data.user_type is not None:
        if data.user_type and data.user_type not in VALID_USER_TYPES:
            raise HTTPException(status_code=400, detail="Nieprawidłowy typ użytkownika.")
        current_user.user_type = data.user_type or None
    if data.collection_size_range is not None:
        if data.collection_size_range and data.collection_size_range not in VALID_COLLECTION_SIZES:
            raise HTTPException(status_code=400, detail="Nieprawidłowy zakres kolekcji.")
        current_user.collection_size_range = data.collection_size_range or None
    if not current_user.profile_survey_completed_at:
        current_user.profile_survey_completed_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(max_length=128)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(max_length=36)
    new_password: str = Field(max_length=128)


@router.post("/auth/change-password")
async def change_password(
    data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(data.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Nieprawidłowe obecne hasło.")
    if len(data.new_password) < 8:
        raise HTTPException(status_code=400, detail="Nowe hasło musi mieć co najmniej 8 znaków.")
    current_user.password_hash = hash_password(data.new_password)
    # Unieważnij tokeny resetu hasła — zmiana hasła unieważnia wcześniej wysłane linki
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == current_user.id,
        PasswordResetToken.used == False,  # noqa: E712
    ).update({"used": True})
    db.commit()
    return {"ok": True}


@router.delete("/auth/delete-account")
async def delete_account(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.query(CollectionItem).filter(CollectionItem.user_id == current_user.id).delete()
    db.query(PasswordResetToken).filter(PasswordResetToken.user_id == current_user.id).delete()
    db.delete(current_user)
    db.commit()
    return {"ok": True}


@router.get("/auth/export-data")
async def export_data(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items = db.query(CollectionItem).filter(CollectionItem.user_id == current_user.id).all()
    return {
        "user": {
            "email": current_user.email,
            "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
        },
        "collection": [_serialize_for_export(i) for i in items],
    }


def _serialize_for_export(item: CollectionItem) -> dict:
    return {
        "id": item.id,
        "club": item.club,
        "season": item.season,
        "brand": item.brand,
        "model_type": item.model_type,
        "player_name": item.player_name,
        "player_number": item.player_number,
        "verdict_category": item.verdict_category,
        "purchase_price": item.purchase_price,
        "purchase_currency": item.purchase_currency,
        "purchase_date": item.purchase_date,
        "purchase_source": item.purchase_source,
        "notes": item.notes,
        "market_value_pln": item.market_value_pln,
        "added_at": item.added_at.isoformat() if item.added_at else None,
        "is_manual": bool(item.is_manual),
    }


@router.post("/auth/forgot-password")
@limiter.limit("5/minute")
async def forgot_password(request: Request, data: ForgotPasswordRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Generuje token resetu hasła i wysyła email z linkiem. Zawsze zwraca 200 (nie ujawnia czy email istnieje)."""
    email = data.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if user:
        # Unieważnij poprzednie tokeny dla tego użytkownika
        db.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used == False,  # noqa: E712
        ).update({"used": True})
        token = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        db.add(PasswordResetToken(token=token, user_id=user.id, expires_at=expires_at, used=False))
        db.commit()
        reset_link = f"{FRONTEND_URL}/reset-password?token={token}"
        background_tasks.add_task(send_password_reset_email, email, reset_link)
    return {"ok": True}


@router.post("/auth/reset-password")
@limiter.limit(RATE_LIMIT_DEFAULT)
async def reset_password(request: Request, data: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Weryfikuje token i ustawia nowe hasło."""
    record = db.query(PasswordResetToken).filter(PasswordResetToken.token == data.token).first()
    if not record:
        raise HTTPException(status_code=400, detail="Nieprawidłowy lub wygasły link resetu hasła.")
    if record.used:
        raise HTTPException(status_code=400, detail="Link resetu hasła został już użyty.")
    now = datetime.now(timezone.utc)
    expires = record.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if now > expires:
        raise HTTPException(status_code=400, detail="Link resetu hasła wygasł.")
    if len(data.new_password) < 8:
        raise HTTPException(status_code=400, detail="Hasło musi mieć co najmniej 8 znaków.")
    user = db.query(User).filter(User.id == record.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="Nieprawidłowy lub wygasły link resetu hasła.")
    user.password_hash = hash_password(data.new_password)
    # Unieważnij wszystkie tokeny resetu dla tego użytkownika
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used == False,  # noqa: E712
    ).update({"used": True})
    db.commit()
    return {"ok": True}


@router.delete("/admin/users/{user_id}")
async def admin_delete_user(
    user_id: str,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Użytkownik nie istnieje.")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Nie możesz usunąć własnego konta.")
    db.query(CollectionItem).filter(CollectionItem.user_id == user.id).delete()
    db.query(PasswordResetToken).filter(PasswordResetToken.user_id == user.id).delete()
    db.delete(user)
    db.commit()
    return {"ok": True}
