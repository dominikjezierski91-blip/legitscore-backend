#!/usr/bin/env python3
"""
Porównuje starą, WYCOFANĄ z produkcji ścieżkę coverage_check() + quality_check()
(2 wywołania Gemini, te same zdjęcia wysyłane dwa razy) z combined_coverage_quality_check()
(1 wywołanie) — obecnym produkcyjnym kodem w cases.py od commitu
"perf: połącz coverage_check + quality_check w jedno wywołanie Gemini".

Ten skrypt był użyty do walidacji PRZED wdrożeniem (20 realnych case'ów, wynik
w commit message). Stare funkcje zostały w agent_a_gemini.py nieużywane, więc
skrypt wciąż działa jako regression check — ale run_sequential() woła teraz
kod, który produkcja już pomija, nie "obecny flow".

Sprawdza, czy połączony call daje IDENTYCZNĄ decyzję bramkującą co stary,
dwuetapowy flow:
  - detected_views (po normalizacji aliasów, tak jak w cases.py)
  - czy _REQUIRED_VIEWS są kompletne (coverage gate)
  - czy są blokujące issues na _QUALITY_BLOCKING_VIEWS (quality gate)
  - ile tokenów zużywa 2 calle vs 1 call

Osobno śledzi zgodność na 3 polach detected_views, które MAJĄ wpływ poza samą
bramką wejściową — front_full i crest_or_brand_closeup blokują wejście
(_REQUIRED_VIEWS), a identity_tag jest czytane bezpośrednio przez rule engine
(_compute_data_completeness w agent_a_gemini.py) i wpływa na confidence_percent
finalnego werdyktu, mimo że nie blokuje analizy. Rozjazd na pozostałych,
opcjonalnych kluczach (sleeve_details, patch_closeup, material_closeup,
personalization_closeup) jest nieszkodliwym szumem — nic w kodzie ich nie czyta
poza wyświetleniem usera "czego jeszcze możesz dofotografować".

Użycie:
    python scripts/compare_coverage_quality_merge.py --n 10
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(override=True)

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"


def find_candidate_cases(n: int) -> list[dict]:
    """Case'y z >=5 zdjęciami wciąż na dysku (nie wymagamy report_data.json —
    interesuje nas tylko precheck, nie finalny werdykt)."""
    candidates = []
    for cid in sorted(os.listdir(DATA_DIR / "cases")):
        case_json = DATA_DIR / "cases" / cid / "case.json"
        if not case_json.exists():
            continue
        with open(case_json) as f:
            case_data = json.load(f)
        asset_paths = [str(DATA_DIR / a["path"]) for a in case_data.get("assets", [])]
        existing = [p for p in asset_paths if Path(p).exists()]
        if len(existing) >= 5:
            candidates.append({"case_id": cid, "asset_paths": existing})
        if len(candidates) >= n:
            break
    return candidates


def gate_decision(detected_views: dict, quality_issues: list, required_views: set, blocking_views: set) -> tuple[bool, str]:
    """Odtwarza logikę bramkowania z cases.py: czy analiza by przeszła dalej."""
    missing_required = [k for k in required_views if not detected_views.get(k)]
    if missing_required:
        return False, f"coverage: brak {missing_required}"
    blocking = [i for i in quality_issues if i.get("area") in blocking_views]
    if blocking:
        return False, f"quality: blokujące issues na {[i.get('area') for i in blocking]}"
    return True, "PASS"


async def run_sequential(asset_paths: list[str]) -> dict:
    """Obecny produkcyjny flow: coverage_check -> quality_check (2 calle)."""
    from app.services.agent_a_gemini import coverage_check, quality_check
    from app.routes.cases import _normalize_detected_views

    coverage_result = await coverage_check(asset_paths)
    detected_views = _normalize_detected_views(coverage_result.get("detected_views") or {})
    quality_result = await quality_check(asset_paths, detected_views=detected_views)

    return {
        "detected_views": detected_views,
        "missing_required": coverage_result.get("missing_required") or [],
        "issues": quality_result.get("issues") or [],
        "n_calls": 2,
    }


async def run_combined(asset_paths: list[str]) -> dict:
    """Eksperymentalny 1-call merge."""
    from app.services.agent_a_gemini import combined_coverage_quality_check
    from app.routes.cases import _normalize_detected_views

    result = await combined_coverage_quality_check(asset_paths)
    detected_views = _normalize_detected_views(result.get("detected_views") or {})

    return {
        "detected_views": detected_views,
        "missing_required": result.get("missing_required") or [],
        "issues": result.get("issues") or [],
        "usage": result.get("_usage"),
        "n_calls": 1,
    }


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=10, help="liczba case'ów do przetestowania")
    args = parser.parse_args()

    if not os.getenv("GEMINI_API_KEY") and not os.getenv("GOOGLE_API_KEY"):
        print("BRAK GEMINI_API_KEY / GOOGLE_API_KEY w środowisku — sprawdź .env")
        sys.exit(1)

    from app.routes.cases import _REQUIRED_VIEWS, _QUALITY_BLOCKING_VIEWS

    cases = find_candidate_cases(args.n)
    if not cases:
        print("Nie znaleziono case'ów z >=5 zdjęciami na dysku.")
        sys.exit(1)

    print(f"Testuję {len(cases)} case'ów: sekwencyjnie (2 calle) vs połączone (1 call)\n")

    # Klucze, których rozjazd MA realny efekt poza samą bramką (patrz docstring).
    IMPACTFUL_KEYS = {"front_full", "crest_or_brand_closeup", "identity_tag"}

    gate_matches = 0
    view_matches = 0
    impactful_matches = 0
    errors = 0

    for i, c in enumerate(cases, 1):
        cid_short = c["case_id"][:8]
        print(f"[{i}/{len(cases)}] case {cid_short}... ({len(c['asset_paths'])} zdjęć)")
        try:
            seq = await run_sequential(c["asset_paths"])
            comb = await run_combined(c["asset_paths"])
        except Exception as e:
            print(f"    BŁĄD: {type(e).__name__}: {e}")
            errors += 1
            continue

        seq_pass, seq_reason = gate_decision(seq["detected_views"], seq["issues"], _REQUIRED_VIEWS, _QUALITY_BLOCKING_VIEWS)
        comb_pass, comb_reason = gate_decision(comb["detected_views"], comb["issues"], _REQUIRED_VIEWS, _QUALITY_BLOCKING_VIEWS)

        gate_same = seq_pass == comb_pass
        views_same = seq["detected_views"] == comb["detected_views"]
        gate_matches += 1 if gate_same else 0
        view_matches += 1 if views_same else 0

        diff_keys = {k for k in set(seq["detected_views"]) | set(comb["detected_views"])
                     if seq["detected_views"].get(k) != comb["detected_views"].get(k)}
        impactful_diff = diff_keys & IMPACTFUL_KEYS
        impactful_same = not impactful_diff
        impactful_matches += 1 if impactful_same else 0

        mark_gate = "TAK" if gate_same else "NIE <<<"
        mark_views = "TAK" if views_same else "NIE (nieszkodliwe)"
        mark_impactful = "TAK" if impactful_same else "NIE <<< WPŁYW NA WERDYKT/CONFIDENCE"
        print(f"    bramka: seq={seq_pass} ({seq_reason}) | comb={comb_pass} ({comb_reason}) | zgodność={mark_gate}")
        print(f"    kluczowe pola (front_full/crest/identity_tag) zgodne: {mark_impactful}")
        print(f"    detected_views identyczne (wszystkie pola): {mark_views}")
        if diff_keys:
            diff = {k: (seq["detected_views"].get(k), comb["detected_views"].get(k)) for k in diff_keys}
            print(f"    różnice: {diff}")
        if comb.get("usage"):
            u = comb["usage"]
            print(f"    tokeny (combined, 1 call): {u.get('prompt_token_count')}/{u.get('candidates_token_count')}")

    n_compared = len(cases) - errors
    print("\n" + "=" * 70)
    if n_compared:
        print(f"Zgodność decyzji bramkującej (pass/fail): {gate_matches}/{n_compared} ({100*gate_matches/n_compared:.0f}%)")
        print(f"Zgodność kluczowych pól (front_full/crest_or_brand_closeup/identity_tag): "
              f"{impactful_matches}/{n_compared} ({100*impactful_matches/n_compared:.0f}%)")
        print(f"Identyczne detected_views (wszystkie pola, w tym kosmetyczne): {view_matches}/{n_compared} ({100*view_matches/n_compared:.0f}%)")
    if errors:
        print(f"Błędy: {errors}/{len(cases)} case'ów")
    print(
        "\nDwa niezależne kryteria bezpieczeństwa do wdrożenia:\n"
        "1. 100% zgodności decyzji bramkującej (blokuje/przepuszcza case'y — błąd tu psuje UX).\n"
        "2. 100% zgodności na front_full/crest_or_brand_closeup/identity_tag (te 3 pola czyta\n"
        "   rule engine przy liczeniu confidence_percent — błąd tu realnie zmienia werdykt,\n"
        "   nawet gdy case przechodzi bramkę). Rozjazd na pozostałych, kosmetycznych polach\n"
        "   (sleeve_details, patch_closeup, material_closeup, personalization_closeup) jest\n"
        "   nieszkodliwy — nic w kodzie ich nie czyta poza podpowiedzią dla usera."
    )


if __name__ == "__main__":
    asyncio.run(main())
