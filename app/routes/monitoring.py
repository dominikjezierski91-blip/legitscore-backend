"""
Monitoring dashboard — endpoints do zarządzania ticketami wewnętrznymi.
Dostępne tylko lokalnie (brak auth — tylko do użytku wewnętrznego).
"""
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/monitoring", tags=["monitoring"])

TICKETS_FILE = Path("data/monitoring/tickets.md")

PRIORITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _parse_tickets(content: str) -> List[dict]:
    """Parsuje tickets.md do listy słowników."""
    tickets = []
    # Każdy ticket zaczyna się od "## TICKET-{id}"
    blocks = re.split(r"(?=^## TICKET-)", content, flags=re.MULTILINE)
    for block in blocks:
        block = block.strip()
        if not block.startswith("## TICKET-"):
            continue
        ticket_id_match = re.match(r"## (TICKET-\d+)", block)
        if not ticket_id_match:
            continue
        ticket_id = ticket_id_match.group(1)

        def _field(name: str) -> str:
            # Używamy [ \t]* zamiast \s* — żeby nie przekraczać granicy linii
            m = re.search(rf"^- {name}:[ \t]*(.+)$", block, re.MULTILINE | re.IGNORECASE)
            return m.group(1).strip() if m else ""

        priorytet = _field("Priorytet").upper()
        status = _field("Status")
        case_id = _field("Case ID")

        tickets.append({
            "id": ticket_id,
            "priorytet": priorytet,
            "typ": _field("Typ"),
            "opis": _field("Opis"),
            "data": _field("Data"),
            "status": status,
            "case_id": case_id if case_id else None,
            "sugerowane_rozwiazanie": _field("Sugerowane rozwiązanie"),
        })

    # Sortuj: priorytet → data (najnowsze pierwsze)
    tickets.sort(key=lambda t: (
        PRIORITY_ORDER.get(t["priorytet"], 99),
        t["data"],
    ))
    return tickets


def _read_raw() -> str:
    if not TICKETS_FILE.exists():
        return ""
    return TICKETS_FILE.read_text(encoding="utf-8")


def _write_raw(content: str) -> None:
    TICKETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TICKETS_FILE.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/tickets")
async def get_tickets():
    """Zwraca listę ticketów z tickets.md jako JSON."""
    raw = _read_raw()
    tickets = _parse_tickets(raw)
    open_count = sum(1 for t in tickets if t["status"] != "Rozwiązany")
    critical_count = sum(
        1 for t in tickets
        if t["priorytet"] == "CRITICAL" and t["status"] != "Rozwiązany"
    )
    return {
        "tickets": tickets,
        "open_count": open_count,
        "critical_count": critical_count,
    }


class StatusUpdate(BaseModel):
    status: str  # "Nowy" | "W trakcie" | "Rozwiązany"


@router.post("/tickets/{ticket_id}/status")
async def update_ticket_status(ticket_id: str, body: StatusUpdate):
    """Aktualizuje status ticketu w tickets.md."""
    allowed = {"Nowy", "W trakcie", "Rozwiązany"}
    if body.status not in allowed:
        raise HTTPException(400, f"Nieprawidłowy status. Dozwolone: {allowed}")

    raw = _read_raw()
    if not raw:
        raise HTTPException(404, "Brak pliku tickets.md")

    ticket_id_upper = ticket_id.upper()
    if ticket_id_upper not in raw:
        raise HTTPException(404, f"Ticket {ticket_id} nie istnieje")

    # Zamień linię "- Status: ..." w bloku danego ticketu
    # Blok kończy się przed następnym ## TICKET lub końcem pliku
    pattern = rf"(## {re.escape(ticket_id_upper)}.*?)(- Status:\s*)([^\n]+)"
    new_raw = re.sub(pattern, rf"\g<1>\g<2>{body.status}", raw, flags=re.DOTALL | re.IGNORECASE)

    if new_raw == raw:
        raise HTTPException(500, "Nie udało się zaktualizować statusu")

    _write_raw(new_raw)
    logger.info("Monitoring: ticket %s → status=%s", ticket_id_upper, body.status)
    return {"ok": True, "ticket_id": ticket_id_upper, "status": body.status}


@router.post("/tickets/{ticket_id}/resolve")
async def resolve_ticket_with_ai(ticket_id: str):
    """Wywołuje Claude API z treścią ticketu — zwraca propozycję fixa."""
    try:
        from anthropic import Anthropic
    except ImportError:
        raise HTTPException(500, "Biblioteka anthropic nie jest zainstalowana. Uruchom: pip install anthropic")

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(500, "Brak ANTHROPIC_API_KEY w zmiennych środowiskowych")

    raw = _read_raw()
    if not raw:
        raise HTTPException(404, "Brak pliku tickets.md")

    ticket_id_upper = ticket_id.upper()
    # Wyodrębnij blok danego ticketu
    pattern = rf"(## {re.escape(ticket_id_upper)}\n.*?)(?=\n## TICKET-|\Z)"
    match = re.search(pattern, raw, re.DOTALL)
    if not match:
        raise HTTPException(404, f"Ticket {ticket_id_upper} nie istnieje")

    ticket_content = match.group(1).strip()

    system_prompt = (
        "Jesteś seniorem backendu LegitScore — systemu AI do analizy autentyczności "
        "koszulek piłkarskich.\n\n"
        "Stack: FastAPI (Python 3.13), Next.js 14, Google Gemini Vision, WeasyPrint.\n\n"
        "Kluczowe pliki:\n"
        "- app/services/agent_a_gemini.py — Gemini + rule engine\n"
        "- app/routes/cases.py — główna logika API\n"
        "- tests/test_rule_engine.py — testy jednostkowe\n"
        "- frontend/components/collection/add-to-collection-modal.tsx — modal kolekcji\n\n"
        "Reguły kodu:\n"
        "- Małe izolowane zmiany, minimalne diffs\n"
        "- Komentarze i logi po polsku\n"
        "- Nigdy nie nadpisuj pól werdyktu (verdict_category, confidence_percent, label, summary)\n"
        "- Backend może tylko normalizować probabilities"
    )

    user_message = (
        f"Przeanalizuj ten ticket i zaproponuj konkretny fix "
        f"z dokładnymi liniami kodu do zmiany:\n\n{ticket_content}"
    )

    try:
        client = Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        fix_proposal = message.content[0].text
        logger.info("Monitoring: AI resolve dla %s — %d znaków", ticket_id_upper, len(fix_proposal))
        return {"ticket_id": ticket_id_upper, "fix_proposal": fix_proposal}
    except Exception as e:
        logger.exception("Monitoring: błąd Claude API dla %s", ticket_id_upper)
        raise HTTPException(500, f"Błąd Claude API: {str(e)}")
