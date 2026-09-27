"""
Centralny moduł konfiguracji feature-flagowej.

Jedno źródło prawdy dla flag odczytywanych z env w wielu miejscach backendu —
zamiast os.getenv() rozsypanego po plikach (patrz SPEC "Darmowe analizy w
becie + ukrycie płatności za feature flagą", 2026-09-27, §2).
"""
import os


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# Gdy False: cała warstwa płatności jest ukryta (frontend) i nie bramkuje
# analiz (backend) — SPEC §3/§4. Odwracalne bez zmian w kodzie: przełączenie
# env var na środowisku z powrotem na true przywraca płatności (SPEC §5).
# Domyślnie False — świadoma decyzja na czas bety (SPEC §7: "Nie zmieniać
# domyślnej wartości na produkcji bez świadomej decyzji: beta = false").
PAYMENTS_ENABLED = _env_bool("PAYMENTS_ENABLED", default=False)
