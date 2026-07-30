#!/usr/bin/env python3
"""
Porównuje jakość werdyktu Agent A między GEMINI_MODEL (domyślnie gemini-2.5-pro,
drogi) a tańszym modelem (domyślnie gemini-2.5-flash) na próbce realnych,
już zanalizowanych case'ów.

Testuje WYŁĄCZNIE surowe wywołanie GeminiAgentA().analyze() — bez rule engine,
PCC/SKU/mfg post-processingu z run-decision. To izoluje najdroższy i
najważniejszy call w pipeline'ie (ten na modelu z GEMINI_MODEL).

Bezpieczne dla danych produkcyjnych: czyta prawdziwe zdjęcia (read-only),
ale zapisuje wynik pod tymczasowym case_id (`modeltest-<model>-<oryginalny_id>`)
w osobnym katalogu — nigdy nie nadpisuje oryginalnych artifacts. Katalogi
testowe są usuwane na koniec (chyba że --keep).

Użycie:
    python scripts/compare_gemini_models.py --n 5
    python scripts/compare_gemini_models.py --n 10 --candidate models/gemini-2.5-flash
"""
import argparse
import asyncio
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(override=True)

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
DB_PATH = DATA_DIR / "legitscore.db"


def find_candidate_cases(n: int) -> list[dict]:
    """Case'y z pełnym report_data.json i >=5 zdjęciami wciąż na dysku."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    candidates = []

    for cid in sorted(os.listdir(DATA_DIR / "cases")):
        case_json = DATA_DIR / "cases" / cid / "case.json"
        report_json = DATA_DIR / "cases" / cid / "artifacts" / "report_data.json"
        if not (case_json.exists() and report_json.exists()):
            continue

        with open(case_json) as f:
            case_data = json.load(f)
        asset_paths = [str(DATA_DIR / a["path"]) for a in case_data.get("assets", [])]
        existing = [p for p in asset_paths if Path(p).exists()]
        if len(existing) < 5:
            continue

        with open(report_json) as f:
            wrapper = json.load(f)
        report_data = wrapper.get("REPORT_DATA") if isinstance(wrapper, dict) else None
        verdict = (report_data or {}).get("verdict") or {}
        if not verdict.get("verdict_category"):
            continue

        row = conn.execute(
            "select model, feedback from cases where case_id=?", (cid,)
        ).fetchone()

        candidates.append({
            "case_id": cid,
            "asset_paths": existing,
            "original_model": (dict(row) if row else {}).get("model"),
            "original_feedback": (dict(row) if row else {}).get("feedback"),
            "original_verdict_category": verdict.get("verdict_category"),
            "original_confidence_percent": verdict.get("confidence_percent"),
            "original_confidence_level": verdict.get("confidence_level"),
        })
        if len(candidates) >= n:
            break

    conn.close()
    return candidates


async def run_candidate_model(case_id: str, asset_paths: list[str], model: str) -> dict:
    """Uruchamia surowy Agent A na podanym modelu, zapisuje pod tymczasowym case_id.

    UWAGA: analyze() zwraca dict zmapowany do starszego, uproszczonego schematu
    Decision (verdict jako string enum likely_authentic/inconclusive/...) — to
    NIE jest ten sam kształt co REPORT_DATA.verdict (verdict_category,
    confidence_percent). Bogaty werdykt trzeba doczytać z pliku
    report_data_raw.json, który analyze() zapisuje jako efekt uboczny.
    """
    from app.services.agent_a_gemini import GeminiAgentA

    os.environ["GEMINI_MODEL"] = model
    temp_case_id = f"modeltest-{model.split('/')[-1]}-{case_id}"

    try:
        decision = await GeminiAgentA().analyze(temp_case_id, asset_paths)
        trace = decision.get("trace") or {}
        usage = trace.get("usage") or {}

        raw_path = DATA_DIR / "cases" / temp_case_id / "artifacts" / "report_data_raw.json"
        if not raw_path.exists():
            return {"ok": False, "error": "brak report_data_raw.json (model nie zwrócił REPORT_DATA)"}

        with open(raw_path) as f:
            wrapper = json.load(f)
        report_data = wrapper.get("REPORT_DATA") or {}
        verdict = report_data.get("verdict") or {}
        if not verdict.get("verdict_category"):
            return {"ok": False, "error": "REPORT_DATA bez verdict_category"}

        return {
            "ok": True,
            "verdict_category": verdict.get("verdict_category"),
            "confidence_percent": verdict.get("confidence_percent"),
            "confidence_level": verdict.get("confidence_level"),
            "summary": (verdict.get("summary") or "")[:160],
            "prompt_tokens": usage.get("prompt_token_count"),
            "output_tokens": usage.get("candidates_token_count"),
            "total_tokens": usage.get("total_token_count"),
        }
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    finally:
        temp_dir = DATA_DIR / "cases" / temp_case_id
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=5, help="liczba case'ów do przetestowania")
    parser.add_argument(
        "--candidate", default="models/gemini-2.5-flash",
        help="model do porównania z oryginałem (domyślnie flash)",
    )
    args = parser.parse_args()

    if not os.getenv("GEMINI_API_KEY") and not os.getenv("GOOGLE_API_KEY"):
        print("BRAK GEMINI_API_KEY / GOOGLE_API_KEY w środowisku — sprawdź .env")
        sys.exit(1)

    cases = find_candidate_cases(args.n)
    if not cases:
        print("Nie znaleziono żadnych case'ów z pełnym report_data.json i zdjęciami na dysku.")
        sys.exit(1)

    print(f"Testuję {len(cases)} case'ów: oryginał vs {args.candidate}\n")

    results = []
    for i, c in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] case {c['case_id'][:8]}... ({len(c['asset_paths'])} zdjęć) — wołam {args.candidate}...")
        candidate_result = await run_candidate_model(c["case_id"], c["asset_paths"], args.candidate)
        results.append({**c, "candidate": candidate_result})

    # --- raport ---
    print("\n" + "=" * 100)
    print(f"{'case_id':<10} {'oryg. werdykt/conf':<28} {'nowy werdykt/conf':<28} {'zgodność':<10} {'tokeny (in/out)'}")
    print("-" * 100)

    matches = 0
    conf_deltas = []
    total_prompt_tokens = 0
    total_output_tokens = 0
    errors = 0

    for r in results:
        cid_short = r["case_id"][:8]
        orig = f"{r['original_verdict_category']} / {r['original_confidence_percent']}%"
        cand = r["candidate"]

        if not cand["ok"]:
            print(f"{cid_short:<10} {orig:<28} {'BŁĄD':<28} {'-':<10} {cand['error'][:40]}")
            errors += 1
            continue

        cand_str = f"{cand['verdict_category']} / {cand['confidence_percent']}%"
        same_verdict = cand["verdict_category"] == r["original_verdict_category"]
        matches += 1 if same_verdict else 0

        try:
            conf_deltas.append(int(cand["confidence_percent"]) - int(r["original_confidence_percent"]))
        except (TypeError, ValueError):
            pass

        tokens_str = f"{cand.get('prompt_tokens', '?')}/{cand.get('output_tokens', '?')}"
        if cand.get("prompt_tokens"):
            total_prompt_tokens += cand["prompt_tokens"]
        if cand.get("output_tokens"):
            total_output_tokens += cand["output_tokens"]

        mark = "TAK" if same_verdict else "NIE"
        print(f"{cid_short:<10} {orig:<28} {cand_str:<28} {mark:<10} {tokens_str}")

    n_compared = len(results) - errors
    print("-" * 100)
    if n_compared:
        print(f"Zgodność kategorii werdyktu: {matches}/{n_compared} ({100*matches/n_compared:.0f}%)")
        if conf_deltas:
            avg_delta = sum(conf_deltas) / len(conf_deltas)
            print(f"Średnia różnica confidence (nowy - oryginał): {avg_delta:+.1f} pkt proc.")
        print(f"Łącznie tokenów ({args.candidate}): {total_prompt_tokens} input / {total_output_tokens} output")
    if errors:
        print(f"Błędy: {errors}/{len(results)} case'ów")

    print(
        "\nUwaga: to porównanie surowego wyniku Agent A (przed rule-engine/PCC/SKU/mfg "
        "post-processingiem), bez niezależnego 'ground truth' (feedback userów na tych "
        "case'ach był pusty w bazie) — traktuj to jako sygnał zgodności modeli, nie "
        "ostateczny wyrok o jakości. Aktualny cennik Gemini sprawdź na ai.google.dev/pricing "
        "— ten skrypt świadomie nie zgaduje kwot w USD/PLN."
    )


if __name__ == "__main__":
    asyncio.run(main())
