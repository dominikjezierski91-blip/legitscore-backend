from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any, Dict

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"  # app/templates

_DEV_NOTE_PATTERNS = ["Agenta A", "Agent B", "BASIC/EXPERT", "prezentacja BASIC", "prezentacja EXPERT"]


def _sanitize_report_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Sanityzacja danych raportu przed renderowaniem PDF.
    Nie zmienia logiki analizy, wyłącznie normalizuje prezentację."""
    d = copy.deepcopy(data)

    # 7. Usuń informacje developerskie z notes.mode_note
    notes = d.get("notes") or {}
    if isinstance(notes, dict):
        note_text = notes.get("mode_note") or ""
        if any(p in note_text for p in _DEV_NOTE_PATTERNS):
            notes["mode_note"] = ""
            d["notes"] = notes

    subject = d.get("subject") or {}
    sku = (subject.get("sku") or "").strip()
    brand = (subject.get("brand") or "").lower()
    missing = list(d.get("missing_data") or [])

    # 3. SKU sprzeczność: SKU rozpoznany, ale missing_data wspomina o brakach SKU
    for i, item in enumerate(missing):
        s = item if isinstance(item, str) else ""
        if "sku" in s.lower() or "kod produktu" in s.lower() or "metk" in s.lower() and "sku" in s.lower():
            if sku:
                missing[i] = (
                    "Kod produktu widoczny na jock tagu, jednak brak pełnych metek "
                    "wewnętrznych utrudnia weryfikację."
                )
            else:
                missing[i] = "Brak widocznego kodu produktu."

    # 6. Zmiękczenie opisu braku zdjęcia materiału
    for i, item in enumerate(missing):
        s = item if isinstance(item, str) else ""
        if "brak szczeg" in s.lower() and "materiał" in s.lower():
            missing[i] = (
                "Ocena struktury materiału jest ograniczona z powodu braku "
                "bardzo bliskiego zdjęcia faktury tkaniny."
            )

    d["missing_data"] = missing

    # 4. SKU format — heurystyka dla Nike
    d["sku_format_warning"] = None
    if sku and "nike" in brand:
        if not re.match(r"^\d{6}-\d{3}$", sku):
            d["sku_format_warning"] = (
                f"Kod produktu ({sku}) nie odpowiada standardowemu formatowi kodów Nike (XXXXXX-XXX)."
            )

    # 8. Filtruj rekomendacje: usuń "porównanie z egzemplarzem ze zweryfikowanego źródła"
    recs = d.get("recommendations") or []
    if isinstance(recs, list):
        def _rec_text(r: Any) -> str:
            if isinstance(r, dict):
                return (r.get("code") or r.get("text") or "").lower()
            return str(r).lower()

        d["recommendations"] = [
            r for r in recs
            if not ("weryfikowan" in _rec_text(r) and "porównan" in _rec_text(r))
        ]

    return d


def generate_report_pdf(case_id: str, report_data: Dict[str, Any], output_path: str, mode: str = "basic") -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    mode = (mode or "basic").lower()
    template_name = "report_basic.html" if mode == "basic" else "report_expert.html"
    template = env.get_template(template_name)

    html = template.render(case_id=case_id, data=_sanitize_report_data(report_data))

    HTML(string=html, base_url=str(TEMPLATES_DIR)).write_pdf(str(out))
