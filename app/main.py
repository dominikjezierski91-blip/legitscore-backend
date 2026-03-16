from dotenv import load_dotenv
load_dotenv(override=True)

import asyncio
import os
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
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


async def _daily_market_value_refresh_loop():
    """Odświeża wyceny kolekcji codziennie o północy."""
    from app.services.market_value_agent import refresh_stale_market_values
    while True:
        try:
            now = datetime.now(timezone.utc)
            # Następna północ UTC
            next_midnight = (now + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            wait_seconds = (next_midnight - now).total_seconds()
            logger.info("Daily market refresh scheduled in %.0f seconds (next midnight UTC)", wait_seconds)
            await asyncio.sleep(wait_seconds)
            logger.info("Daily market value refresh started")
            count = await refresh_stale_market_values()
            logger.info("Daily market value refresh done: %d items updated", count)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Daily market value refresh error — retrying tomorrow")
            await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_daily_market_value_refresh_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="LegitScore API",
    docs_url="/api/docs" if not PRODUCTION else None,  # Ukryj docs w produkcji
    redoc_url="/api/redoc" if not PRODUCTION else None,
    lifespan=lifespan,
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
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
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
