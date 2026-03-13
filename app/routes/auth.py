import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.services.database import get_db, User
from app.services.auth_service import hash_password, verify_password, create_access_token, decode_access_token
from app.services.security import limiter
from fastapi import Request

router = APIRouter()


# ── Pydantic models ──────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str
    password: str
    password_confirm: str


class LoginRequest(BaseModel):
    email: str
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
async def register(data: RegisterRequest, db: Session = Depends(get_db)):
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
    return {"id": current_user.id, "email": current_user.email, "is_admin": current_user.is_admin}


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
    db.delete(user)
    db.commit()
    return {"ok": True}
