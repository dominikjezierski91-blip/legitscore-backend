from dotenv import load_dotenv
load_dotenv(override=True)

import os
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from app.routes import cases
from app.routes import auth as auth_router
from app.routes import collection as collection_router
from app.services.database import init_db
from app.services.security import limiter, ALLOWED_ORIGINS, SECURITY_HEADERS

# Konfiguracja logowania
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Tryb produkcyjny
PRODUCTION = os.getenv("PRODUCTION", "false").lower() == "true"

app = FastAPI(
    title="LegitScore API",
    docs_url="/api/docs" if not PRODUCTION else None,  # Ukryj docs w produkcji
    redoc_url="/api/redoc" if not PRODUCTION else None,
)

# Rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Inicjalizacja bazy danych
init_db()


# Security headers middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers[header] = value
        return response


app.add_middleware(SecurityHeadersMiddleware)

# CORS - konfigurowalny przez zmienną środowiskową
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
    allow_credentials=True,
)


# Global exception handler - ukrywa stack traces w produkcji
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception: {exc}")
    if PRODUCTION:
        return JSONResponse(
            status_code=500,
            content={"detail": "Wystąpił błąd serwera. Spróbuj ponownie później."}
        )
    raise exc


# Health check endpoint
@app.get("/api/health")
async def health():
    return {"ok": True, "production": PRODUCTION}

# Podłącz routery pod prefixem /api
app.include_router(cases.router, prefix="/api")
app.include_router(auth_router.router, prefix="/api")
app.include_router(collection_router.router, prefix="/api")

app.mount("/", StaticFiles(directory="data"), name="data")
