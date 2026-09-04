#!/usr/bin/env python3
"""
Jednorazowy backfill wycen rynkowych wszystkich pozycji kolekcji nową logiką
(match_score + confidence, spec 2026-09-03) — naprawia rekordy sprzed tych
zmian (znane: Cubarsí, Ribéry — zapisana wartość powstała z bardzo cienkiej,
słabo dopasowanej próbki i dawnej logiki mediana-z-całości/top-3).

Domyślnie DRY-RUN: liczy nowe wyceny i drukuje raport stara→nowa cena per
pozycja, NIC nie zapisuje. Wymaga --apply żeby faktycznie zapisać do bazy
(i dopiero wtedy loguje do MarketValueHistory).

Użycie:
    python scripts/backfill_market_values.py                 # dry-run, raport
    python scripts/backfill_market_values.py --apply          # zapisuje do bazy
"""
import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.database import SessionLocal, CollectionItem, log_market_value_history  # noqa: E402
from app.services.market_value_agent import estimate_market_value, should_update_market_value  # noqa: E402


async def backfill(apply: bool) -> None:
    db = SessionLocal()
    try:
        items = (
            db.query(CollectionItem)
            .filter(CollectionItem.verdict_category != "podrobka")
            .all()
        )
        print(f"{'DRY-RUN' if not apply else 'APPLY'} — {len(items)} pozycji do przeliczenia\n")
        print(f"{'id':<10} {'klub / gracz':<35} {'stara cena':>12} {'nowa cena':>12} {'confidence':>10} {'matched':>8} {'decyzja':>18}")
        print("-" * 112)

        changed = 0
        for item in items:
            report_data = {
                "subject": {
                    "club": item.club,
                    "season": item.season,
                    "brand": item.brand,
                    "player_name": item.player_name,
                    "player_number": item.player_number,
                    "model": item.model_type,
                },
                "verdict": {"verdict_category": item.verdict_category},
            }
            try:
                result = await estimate_market_value(report_data)
            except Exception as e:
                print(f"{item.id[:8]:<10} {'BŁĄD: ' + str(e):<35}")
                continue

            new_price = result.get("price")
            new_confidence = result.get("confidence", "low")
            new_matched = result.get("matched_count", 0)
            applied = should_update_market_value(
                item.market_value_pln, item.market_value_confidence,
                new_price, new_confidence, new_matched,
            )
            label = f"{item.club or ''} / {item.player_name or ''}"[:35]
            old_price_str = f"{item.market_value_pln:.0f}" if item.market_value_pln else "—"
            new_price_str = f"{new_price:.0f}" if new_price else "—"
            decision = "AKTUALIZACJA" if applied else "bez zmian"
            print(f"{item.id[:8]:<10} {label:<35} {old_price_str:>12} {new_price_str:>12} {new_confidence:>10} {new_matched:>8} {decision:>18}")

            if applied:
                changed += 1

            if apply:
                log_market_value_history(
                    db, item.id, new_price, result.get("low"), result.get("high"),
                    new_confidence, new_matched, applied,
                )
                if applied:
                    item.market_value_pln = new_price
                    item.market_value_range_min = result.get("low")
                    item.market_value_range_max = result.get("high")
                    item.market_value_sample_size = new_matched
                    item.market_value_confidence = new_confidence
                    item.market_value_source = result.get("source") or "gemini"
                    item.market_value_updated_at = datetime.now(timezone.utc)
                item.market_value_last_attempt_at = datetime.now(timezone.utc)

        print("-" * 112)
        print(f"\n{changed} / {len(items)} pozycji zmieniłoby/zmieniło wartość.")
        if apply:
            db.commit()
            print("Zapisano do bazy.")
        else:
            print("DRY-RUN — nic nie zapisano. Uruchom z --apply żeby zapisać.")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Zapisz zmiany do bazy (domyślnie dry-run)")
    args = parser.parse_args()
    asyncio.run(backfill(apply=args.apply))
