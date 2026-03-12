"""
Moduł bezpieczeństwa LegitScore.
Rate limiting, walidacja plików, sanityzacja inputów.
"""

import os
import re
from typing import List, Optional
from fastapi import UploadFile, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

# === KONFIGURACJA ===

# Rate limiting
RATE_LIMIT_DEFAULT = os.getenv("RATE_LIMIT_DEFAULT", "30/minute")
RATE_LIMIT_UPLOAD = os.getenv("RATE_LIMIT_UPLOAD", "10/minute")
RATE_LIMIT_ANALYSIS = os.getenv("RATE_LIMIT_ANALYSIS", "5/minute")

# File upload
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "10"))
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_FILES_PER_UPLOAD = int(os.getenv("MAX_FILES_PER_UPLOAD", "12"))
ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}

# Input validation
MAX_EMAIL_LENGTH = 254
MAX_TEXT_FIELD_LENGTH = 2000
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

# CORS - dozwolone domeny (produkcja)
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")


# === RATE LIMITER ===

def get_client_ip(request: Request) -> str:
    """Pobiera IP klienta, uwzględniając proxy."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=get_client_ip)


# === WALIDACJA PLIKÓW ===

async def validate_upload_file(file: UploadFile) -> None:
    """Waliduje pojedynczy plik - typ MIME, rozszerzenie, rozmiar."""

    # Sprawdź rozszerzenie
    filename = file.filename or ""
    ext = os.path.splitext(filename.lower())[1]
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Niedozwolone rozszerzenie pliku: {ext}. Dozwolone: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # Sprawdź MIME type
    content_type = file.content_type or ""
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Niedozwolony typ pliku: {content_type}. Dozwolone: obrazy (JPEG, PNG, WebP, HEIC)"
        )

    # Sprawdź rozmiar (odczytaj i przewiń)
    content = await file.read()
    await file.seek(0)

    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Plik {filename} jest za duży ({len(content) // 1024 // 1024}MB). Maksymalny rozmiar: {MAX_FILE_SIZE_MB}MB"
        )

    if len(content) == 0:
        raise HTTPException(
            status_code=400,
            detail=f"Plik {filename} jest pusty"
        )


async def validate_upload_files(files: List[UploadFile]) -> None:
    """Waliduje listę plików."""

    if not files:
        raise HTTPException(status_code=400, detail="Nie przesłano żadnych plików")

    if len(files) > MAX_FILES_PER_UPLOAD:
        raise HTTPException(
            status_code=400,
            detail=f"Za dużo plików ({len(files)}). Maksymalnie: {MAX_FILES_PER_UPLOAD}"
        )

    for file in files:
        await validate_upload_file(file)


# === WALIDACJA INPUTÓW ===

def validate_email(email: Optional[str]) -> Optional[str]:
    """Waliduje i sanityzuje email."""
    if not email:
        return None

    email = email.strip().lower()

    if len(email) > MAX_EMAIL_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Email za długi. Maksymalnie {MAX_EMAIL_LENGTH} znaków"
        )

    if not EMAIL_REGEX.match(email):
        raise HTTPException(
            status_code=400,
            detail="Nieprawidłowy format adresu email"
        )

    return email


def validate_text_field(value: Optional[str], field_name: str, max_length: int = MAX_TEXT_FIELD_LENGTH) -> Optional[str]:
    """Waliduje i sanityzuje pole tekstowe."""
    if not value:
        return None

    value = value.strip()

    if len(value) > max_length:
        raise HTTPException(
            status_code=400,
            detail=f"Pole {field_name} za długie. Maksymalnie {max_length} znaków"
        )

    # Usuń potencjalnie niebezpieczne znaki (basic XSS prevention)
    # Nie usuwamy całkowicie, tylko escapujemy w renderingu
    return value


def validate_case_id(case_id: str) -> str:
    """Waliduje format case_id (UUID)."""
    uuid_regex = re.compile(r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$", re.IGNORECASE)

    if not uuid_regex.match(case_id):
        raise HTTPException(
            status_code=400,
            detail="Nieprawidłowy format identyfikatora sprawy"
        )

    return case_id.lower()


# === SECURITY HEADERS ===

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}
