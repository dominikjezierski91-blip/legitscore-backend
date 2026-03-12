from dotenv import load_dotenv
load_dotenv(override=True)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.routes import cases
from app.services.database import init_db

app = FastAPI()

# Inicjalizacja bazy danych
init_db()

# CORS dla MVP
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check endpoint
@app.get("/api/health")
async def health():
    return {"ok": True}

# Podłącz router cases pod prefixem /api
app.include_router(cases.router, prefix="/api")

app.mount("/", StaticFiles(directory="data"), name="data")
