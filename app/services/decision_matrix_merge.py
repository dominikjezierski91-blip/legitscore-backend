"""
Deterministyczne scalanie dowodów dla macierzy decyzyjnej (decision_matrix).

SPEC: Macierz decyzyjna — deterministyczne scalanie dowodów (evidence-merge),
2026-09-05 (case 15364d60, złota koszulka Lewandowskiego, zgłoszone przez
Dominika — 4. wariant tego dnia tej samej klasy błędu). Do tego dnia backend
bezwarunkowo NADPISYWAŁ wiersze A/B decision_matrix wynikiem zewnętrznego
sku_verification — checka, który nie widzi zdjęć (brak koloru, czasem brak
sezonu/modelu) i ma strukturalnie MNIEJ informacji niż Agent A, mimo to jego
wynik zawsze wygrywał, nawet gdy przeczył werdyktowi/podsumowaniu w tym samym
raporcie ("Podróbka 95%" obok zielonego "Kod SKU potwierdzony").

Zasada nadrzędna: sygnał może orzekać tylko o tym, co obejmuje jego wejście
(capability contract). Sygnały scalają się MONOTONICZNIE w stronę ostrożności
— zewnętrzny check może pogorszyć status wiersza, ale nie może go poprawić
ponad to, co ustalił Agent A, chyba że Agent A sam był niepewny (info_level
"low") a zewnętrzny check ma pewne dane (info_level "high") na ten sam temat.
Na końcu globalny niezmiennik (apply_global_invariant) gwarantuje, że żaden
wiersz A/B nie zostanie zielony, gdy finalny werdykt to podróbka.

Warstwa czysto deterministyczna — zero wywołań modeli, w pełni testowalna.
NIE dotyka verdict_category/confidence_percent/label/summary — tylko status/
observation/impact pojedynczych wierszy decision_matrix.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.services.constants import UNVERIFIED_SUBJECT_VALUES

# ---------------------------------------------------------------------------
# Model danych
# ---------------------------------------------------------------------------

_STATUS_RANK = {"ok": 0, "uwaga": 1, "problem": 2}

# Konwersja między słownictwem tej warstwy (ok/uwaga/problem) a rzeczywistymi
# statusami w decision_matrix (GREEN/YELLOW/RED/UNKNOWN). UNKNOWN nie ma
# jednoznacznego odpowiednika w drabince ok<uwaga<problem — traktowany jako
# "uwaga" na czas scalania (neutralny, nie potwierdzony ani zanegowany).
_STATUS_TO_INTERNAL = {"GREEN": "ok", "YELLOW": "uwaga", "RED": "problem", "UNKNOWN": "uwaga"}
_INTERNAL_TO_STATUS = {"ok": "GREEN", "uwaga": "YELLOW", "problem": "RED"}


@dataclass(frozen=True)
class Contribution:
    source: str          # np. "agent_a_visual", "sku_verification"
    row: str              # kod wiersza decision_matrix, np. "A", "B"
    claim_scope: str      # o czym WOLNO temu źródłu orzekać dla tego wiersza
    status: str            # "ok" | "uwaga" | "problem"
    info_level: str        # "low" | "medium" | "high"
    text: str = ""


# ---------------------------------------------------------------------------
# Capability contract — co dozwolone dla (source, row)
# ---------------------------------------------------------------------------

_UNRESTRICTED = object()  # sentinel: dowolny claim_scope dozwolony

_CAPABILITY_CONTRACT: Dict[Tuple[str, str], Any] = {
    # agent_a_visual widzi zdjęcia — może orzekać o wszystkich wierszach A-G,
    # to zawsze baza (base) dla merge_row, nie "wkład zewnętrzny".
    ("agent_a_visual", "A"): _UNRESTRICTED,
    ("agent_a_visual", "B"): _UNRESTRICTED,
    ("agent_a_visual", "C"): _UNRESTRICTED,
    ("agent_a_visual", "D"): _UNRESTRICTED,
    ("agent_a_visual", "E"): _UNRESTRICTED,
    ("agent_a_visual", "F"): _UNRESTRICTED,
    ("agent_a_visual", "G"): _UNRESTRICTED,
    # sku_verification nie widzi zdjęć — wąski zakres:
    # wiersz A (istnienie/legalność kodu): może orzekać "sku_exists".
    # wiersz B (zgodność z TYM modelem/sezonem): może orzekać WYŁĄCZNIE
    # "sku_mismatch" (sygnał negatywny) — pozytywne "istnieje" nie dowodzi
    # zgodności z konkretnym egzemplarzem, więc nie może pisać B w ogóle.
    ("sku_verification", "A"): {"sku_exists"},
    ("sku_verification", "B"): {"sku_mismatch"},
}


def is_contribution_allowed(source: str, row: str, claim_scope: str) -> bool:
    """Sprawdza, czy dane źródło wolno mu orzekać o danym wierszu w danym
    zakresie (claim_scope) — niezadeklarowana para (source, row) jest
    odrzucana domyślnie (fail closed, nie fail open)."""
    allowed = _CAPABILITY_CONTRACT.get((source, row))
    if allowed is None:
        return False
    if allowed is _UNRESTRICTED:
        return True
    return claim_scope in allowed


# ---------------------------------------------------------------------------
# merge_row — scalanie jednego wiersza z bazy + dozwolonych wkładów
# ---------------------------------------------------------------------------

def merge_row(
    row: str,
    base: Optional[Contribution],
    externals: List[Contribution],
) -> Tuple[str, str]:
    """Scala bazowy wkład (Agent A) z dozwolonymi wkładami zewnętrznymi wg
    reguły monotoniczności (SPEC sekcja 6). Zwraca (status, text) w słowniku
    wewnętrznym tej warstwy (ok/uwaga/problem) — konwersja na GREEN/YELLOW/RED
    dzieje się w warstwie wywołującej."""
    if base is not None:
        status = base.status
        info_level = base.info_level
        base_text = base.text or ""
    else:
        status, info_level, base_text = "uwaga", "low", ""

    allowed_externals = [
        c for c in externals
        if c.row == row and is_contribution_allowed(c.source, c.row, c.claim_scope)
    ]

    # Fail-closed: status spoza {ok,uwaga,problem} traktowany jak "uwaga"
    # (rank 1) zamiast KeyError — nie powinno się zdarzyć z realnych wywołań
    # (build_sku_contributions emituje tylko poprawne literały), ale merge_row
    # jest publiczną funkcją tego modułu, więc nie ufamy wejściu ślepo.
    applied: List[Contribution] = []
    for c in allowed_externals:
        worsens = _STATUS_RANK.get(c.status, 1) > _STATUS_RANK.get(status, 1)
        # Wyjątek monotoniczności: baza niepewna (low info) + zewn. pewny
        # (high info) na ten sam temat → zewnętrzny wkład wygrywa, nawet
        # jeśli formalnie "poprawia" status — bazie i tak nie ufamy.
        low_info_override = info_level == "low" and c.info_level == "high"
        if worsens or (low_info_override and c.status != status):
            applied.append(c)
            status = c.status
            info_level = c.info_level

    texts = [base_text] if base_text else []
    # QA (2026-09-05): dołącz tekst TYLKO z wkładów, które faktycznie ustaliły
    # finalny status — status jest już order-independent (fold zbiega do tego
    # samego wyniku niezależnie od kolejności wkładów), ale bez tego filtra
    # tekst by nie był — złączałby też wkłady "po drodze", które finalny
    # wynik później przebił. Dziś nieosiągalne (żaden caller nie produkuje 2+
    # wkładów zewn. dla jednego wiersza), ale zabezpiecza na przyszłość.
    for c in applied:
        if c.status == status and c.text:
            texts.append(c.text)

    return status, " ".join(t for t in texts if t).strip()


# ---------------------------------------------------------------------------
# Budowanie wkładów sku_verification wg capability contract
# ---------------------------------------------------------------------------

def _is_blank_subject_value(value: Any) -> bool:
    v = str(value or "").strip()
    return not v or v.lower() in UNVERIFIED_SUBJECT_VALUES


def _is_degraded_subject(subject: Dict[str, Any]) -> bool:
    """True gdy sezon lub model nie zostały ustalone przez Agenta A — wtedy
    sku_verification nie miał się z czym porównać (patrz case 15364d60:
    subject.season=subject.model="nieustalone", sku_verification dostał tylko
    Klub+Markę, więc 'found_authorized' orzeka jedynie że kod istnieje, nie że
    pasuje do TEGO egzemplarza)."""
    return _is_blank_subject_value(subject.get("season")) or _is_blank_subject_value(subject.get("model"))


def build_sku_contributions(
    sku_verification: Optional[Dict[str, Any]],
    subject: Optional[Dict[str, Any]],
) -> List[Contribution]:
    """Buduje wkłady sku_verification dla wierszy A/B wg capability contract.
    Pozytywne statusy (found_official/found_authorized) NIGDY nie tworzą
    wkładu dla wiersza B — samo istnienie kodu nie dowodzi zgodności z tym
    konkretnym egzemplarzem (SPEC sekcja 3/5)."""
    sku_verification = sku_verification or {}
    subject = subject or {}
    status = sku_verification.get("status", "uncertain")
    reason = (sku_verification.get("reason") or "").strip()
    degraded = _is_degraded_subject(subject)
    contributions: List[Contribution] = []

    if status in ("found_official", "found_authorized"):
        if degraded:
            contributions.append(Contribution(
                source="sku_verification", row="A", claim_scope="sku_exists",
                status="uwaga", info_level="low",
                text=(
                    "Kod SKU istnieje w obrocie u autoryzowanego źródła; nie "
                    "zweryfikowano zgodności z tym konkretnym egzemplarzem "
                    "(brak pełnych danych o sezonie/modelu)."
                ),
            ))
        else:
            contributions.append(Contribution(
                source="sku_verification", row="A", claim_scope="sku_exists",
                status="ok", info_level="high",
                text="Kod SKU potwierdzony u autoryzowanego sprzedawcy.",
            ))
        # Wiersz B: celowo brak wkładu w tej gałęzi — pozytywne "istnieje" nie
        # jest dozwolonym claim_scope dla B (patrz capability contract).
    elif status == "mismatch":
        contributions.append(Contribution(
            source="sku_verification", row="A", claim_scope="sku_exists",
            status="problem", info_level="high",
            text=reason or "Kod SKU zidentyfikowany, ale dla innego produktu niż deklarowany.",
        ))
        contributions.append(Contribution(
            source="sku_verification", row="B", claim_scope="sku_mismatch",
            status="problem", info_level="high",
            text="Kod SKU niezgodny z tym modelem i sezonem.",
        ))
    elif status == "found_unofficial":
        contributions.append(Contribution(
            source="sku_verification", row="A", claim_scope="sku_exists",
            status="problem", info_level="high",
            text="Kod SKU powiązany z nieautoryzowanymi produktami.",
        ))
    elif status == "format_invalid":
        contributions.append(Contribution(
            source="sku_verification", row="A", claim_scope="sku_exists",
            status="problem", info_level="high",
            text="Kod SKU ma nieprawidłowy format, niezgodny ze wzorcami producenta.",
        ))
    elif status == "not_found":
        contributions.append(Contribution(
            source="sku_verification", row="A", claim_scope="sku_exists",
            status="uwaga", info_level="medium",
            text="Kod SKU nie został znaleziony w dostępnych źródłach.",
        ))
    # not_applicable / uncertain / cokolwiek innego: brak wkładu — baza
    # Agenta A stoi bez zmian, tak jak dla każdego innego wiersza C-G.

    return contributions


# ---------------------------------------------------------------------------
# Orkiestracja: scal wiersze A/B decision_matrix in-place
# ---------------------------------------------------------------------------

def merge_sku_rows_into_decision_matrix(
    decision_matrix: List[Dict[str, Any]],
    sku_verification: Optional[Dict[str, Any]],
    subject: Optional[Dict[str, Any]],
) -> None:
    """Zastępuje dawne bezwarunkowe nadpisanie (_sku_dm_map) — scala bazowy
    wkład Agenta A (aktualna treść wierszy A/B, ZANIM cokolwiek je nadpisze)
    z wkładem sku_verification wg merge_row(). Mutuje decision_matrix in-place,
    non-fatal (brak wierszy A/B → no-op)."""
    dm_by_code = {
        r["code"]: r for r in decision_matrix
        if isinstance(r, dict) and "code" in r
    }
    row_a = dm_by_code.get("A")
    row_b = dm_by_code.get("B")
    if row_a is None and row_b is None:
        return

    def _base(row: Optional[Dict[str, Any]], code: str) -> Contribution:
        if row is None:
            return Contribution(
                source="agent_a_visual", row=code, claim_scope="visual",
                status="uwaga", info_level="low", text="",
            )
        return Contribution(
            source="agent_a_visual", row=code, claim_scope="visual",
            status=_STATUS_TO_INTERNAL.get(row.get("status"), "uwaga"),
            info_level="high",
            text=row.get("observation", "") or "",
        )

    externals = build_sku_contributions(sku_verification, subject)

    # Code review (2026-09-05, BLOCKER): pisz do wiersza TYLKO gdy scalanie
    # faktycznie coś zmieniło względem bazy Agenta A — porównanie status_x
    # (wynik merge_row) z base.status (stan PRZED scalaniem), oba w tym samym
    # słowniku wewnętrznym (ok/uwaga/problem), więc porównanie jest bezpieczne.
    # Bez tego: (a) UNKNOWN→"uwaga"→(z powrotem, ale _INTERNAL_TO_STATUS nie ma
    # klucza UNKNOWN)→YELLOW nawet gdy sku_verification nic nie wniósł (status
    # "not_applicable"/"uncertain" — to NAJCZĘSTSZY przypadek "brak widocznego
    # SKU", nie skrajny przypadek); (b) `impact` spłaszczał się do "obniza"
    # nawet dla niezmienionych wierszy, kasując np. "ogranicza_pewnosc"
    # ustawione przez Agenta A. Sam brak zmiany = zostaw wiersz bit-w-bit taki,
    # jaki napisał Agent A — dokładnie duch SPEC (sygnał, który nic nie
    # orzeka, nie powinien nic zmieniać).
    if row_a is not None:
        base_a = _base(row_a, "A")
        status_a, text_a = merge_row("A", base_a, externals)
        if status_a != base_a.status:
            row_a["status"] = _INTERNAL_TO_STATUS[status_a]
            if text_a:
                row_a["observation"] = text_a
            row_a["impact"] = "obniza" if status_a != "ok" else row_a.get("impact", "neutralne")

    if row_b is not None:
        base_b = _base(row_b, "B")
        status_b, text_b = merge_row("B", base_b, externals)
        if status_b != base_b.status:
            row_b["status"] = _INTERNAL_TO_STATUS[status_b]
            if text_b:
                row_b["observation"] = text_b
            row_b["impact"] = "obniza" if status_b != "ok" else row_b.get("impact", "neutralne")


# ---------------------------------------------------------------------------
# Globalny niezmiennik — macierz nie może przeczyć finalnemu werdyktowi
# ---------------------------------------------------------------------------

_SKU_RELATED_ROWS = ("A", "B")


def apply_global_invariant(decision_matrix: List[Dict[str, Any]], verdict_category: str) -> None:
    """SPEC sekcja 7. Wołane na SAMYM KOŃCU run_rule_engine (po wszystkich
    hard-override ścieżkach, gdy verdict_category jest już finalne) — jeśli
    finalny werdykt to podróbka, wiersze A/B nie mogą pozostać zielone/'ok',
    niezależnie od tego, co scalanie wcześniej ustaliło. To ostatnia linia
    obrony przed dokładnie tym bugiem, który zgłosił Dominik (case 15364d60):
    werdykt "Podróbka 95%" obok zielonego "Kod SKU potwierdzony"."""
    if verdict_category != "podrobka":
        return
    for code in _SKU_RELATED_ROWS:
        row = next(
            (r for r in decision_matrix if isinstance(r, dict) and r.get("code") == code),
            None,
        )
        if not row or row.get("status") != "GREEN":
            continue
        row["status"] = "YELLOW"
        row["impact"] = "obniza"
        observation = (row.get("observation") or "").rstrip(". ")
        if observation:
            row["observation"] = observation + " — do interpretacji w kontekście werdyktu podróbki."
