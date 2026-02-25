"""
AGENT B — REPORT WRITER v2.0 (deterministyczny renderer).
Ten sam JSON → ten sam tekst. Brak pola => "nieustalone" / reguły jak w prompt B.
"""

from typing import Any, Dict, List


def _str(v: Any, default: str = "nieustalone") -> str:
    if v is None or (isinstance(v, str) and not v.strip()):
        return default
    return str(v).strip()


def _section(title: str, lines: List[str]) -> str:
    return f"\n=== {title} ===\n" + "\n".join(lines) + "\n"


def render_report_text(report_data: Dict[str, Any], mode: str = "basic") -> str:
    """
    Renderuje tekst raportu w strukturze Agenta B v2.0.
    mode: "basic" | "expert" — BASIC = skrócony, EXPERT = z decision_matrix i szczegółami.
    Deterministic: ten sam report_data → ten sam wynik.
    """
    out: List[str] = []
    out.append("LEGITSCORE — RAPORT ANALIZY AUTENTYCZNOŚCI")
    out.append("(Źródło: Agent A — Decision Engine)")
    out.append("")

    # --- Meta ---
    report_id = _str(report_data.get("report_id"))
    analysis_date = _str(report_data.get("analysis_date"))
    out.append(_section("METADANE", [
        f"Report ID: {report_id}",
        f"Data analizy: {analysis_date}",
    ]))

    # --- Subject ---
    subject = report_data.get("subject") or {}
    if not isinstance(subject, dict):
        subject = {}
    out.append(_section("PRZEDMIOT ANALIZY", [
        f"Klub: {_str(subject.get('club'))}",
        f"Sezon: {_str(subject.get('season'))}",
        f"Model: {_str(subject.get('model'))}",
        f"Marka: {_str(subject.get('brand'))}",
        f"Zawodnik: {_str(subject.get('player_name'))}",
        f"Numer: {_str(subject.get('player_number'))}",
    ]))

    # --- Verdict ---
    verdict = report_data.get("verdict") or {}
    if not isinstance(verdict, dict):
        verdict = {}
    out.append(_section("WERDYKT", [
        f"Kategoria: {_str(verdict.get('verdict_category'))}",
        f"Label: {_str(verdict.get('label'))}",
        f"Poziom pewności: {_str(verdict.get('confidence_level'))}",
        f"Pewność (%): {verdict.get('confidence_percent', '—')}",
        f"Podsumowanie: {_str(verdict.get('summary'), '—')}",
    ]))

    # --- Prawdopodobieństwa ---
    probs = report_data.get("probabilities") or {}
    if isinstance(probs, dict):
        probs_lines = [f"  {k}: {v}%" for k, v in probs.items() if v is not None]
        out.append(_section("PRAWDOPODOBIEŃSTWA", probs_lines if probs_lines else ["—"]))

    if mode == "expert":
        # --- Meczowa / personalizacja ---
        meczowa = report_data.get("meczowa_detail") or {}
        if isinstance(meczowa, dict):
            out.append(_section("SZCZEGÓŁ MECZOWA", [
                f"Status: {_str(meczowa.get('status'))}",
                f"Pewność: {_str(meczowa.get('confidence'))}",
                f"Uwagi: {_str(meczowa.get('notes'), '—')}",
            ]))
        pers = report_data.get("personalization_assessment") or {}
        if isinstance(pers, dict):
            out.append(_section("OCENA PERSONALIZACJI", [
                f"Status: {_str(pers.get('status'))}",
                f"Pewność: {_str(pers.get('confidence'))}",
                f"Uwagi: {_str(pers.get('notes'), '—')}",
            ]))

        # --- Decision matrix ---
        dm = report_data.get("decision_matrix") or []
        if isinstance(dm, list) and dm:
            dm_lines = []
            for row in dm:
                if not isinstance(row, dict):
                    continue
                cid = row.get("criterion_id") or row.get("code") or "—"
                cname = row.get("criterion_name") or row.get("criterion") or "—"
                status = row.get("status", "—")
                obs = _str(row.get("observation"), "—")
                impact = row.get("impact", "—")
                dm_lines.append(f"  [{cid}] {cname} | {status} | {impact}")
                dm_lines.append(f"      Obserwacja: {obs}")
            out.append(_section("MACIERZ DECYZYJNA", dm_lines if dm_lines else ["—"]))
        else:
            out.append(_section("MACIERZ DECYZYJNA", ["Brak danych."]))

    # --- Braki / rekomendacje (wspólne) ---
    missing = report_data.get("missing_data") or []
    if isinstance(missing, list) and missing:
        out.append(_section("BRAKUJĄCE DANE", [_str(x) for x in missing]))
    recs = report_data.get("recommendations") or []
    if isinstance(recs, list) and recs:
        rec_lines = []
        for r in recs:
            if isinstance(r, dict):
                rec_lines.append(_str(r.get("code") or r.get("text") or str(r)))
            else:
                rec_lines.append(str(r))
        out.append(_section("REKOMENDACJE", rec_lines if rec_lines else ["—"]))
    else:
        out.append(_section("REKOMENDACJE", ["Brak dodatkowych rekomendacji."]))

    notes = report_data.get("notes") or {}
    if isinstance(notes, dict) and notes.get("mode_note"):
        out.append(_section("UWAGI", [_str(notes.get("mode_note"))]))

    return "\n".join(out)
