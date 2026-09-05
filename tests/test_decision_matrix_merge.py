"""
Testy deterministycznego scalania dowodów dla macierzy decyzyjnej
(app/services/decision_matrix_merge.py).

SPEC: Macierz decyzyjna — deterministyczne scalanie dowodów (evidence-merge),
2026-09-05 (case 15364d60, złota koszulka Lewandowskiego, zgłoszone przez
Dominika). Do tego dnia backend bezwarunkowo nadpisywał wiersze A/B
decision_matrix wynikiem zewnętrznego sku_verification — checka bez dostępu do
zdjęć (brak koloru, czasem brak sezonu/modelu), mimo to jego wynik zawsze
wygrywał, nawet gdy przeczył werdyktowi/podsumowaniu w tym samym raporcie
("Podróbka 95%" obok zielonego "Kod SKU potwierdzony u autoryzowanego
sprzedawcy"). Testy poniżej odpowiadają 1:1 kryteriom akceptacji z SPEC
sekcja 9.
"""
from app.services.decision_matrix_merge import (
    Contribution,
    apply_global_invariant,
    build_sku_contributions,
    is_contribution_allowed,
    merge_row,
    merge_sku_rows_into_decision_matrix,
)


# ---------------------------------------------------------------------------
# is_contribution_allowed — capability contract
# ---------------------------------------------------------------------------

class TestCapabilityContract:
    def test_agent_a_visual_allowed_on_every_row_any_claim_scope(self):
        for row in "ABCDEFG":
            assert is_contribution_allowed("agent_a_visual", row, "anything_goes") is True

    def test_sku_verification_allowed_sku_exists_on_row_a(self):
        assert is_contribution_allowed("sku_verification", "A", "sku_exists") is True

    def test_sku_verification_rejected_sku_exists_on_row_b(self):
        """SPEC sekcja 9, kryterium 'Zakres B': sku_verification z pozytywnym
        'sku_exists' próbujący pisać wiersz B → odrzucony (nie tworzy
        twierdzenia o zgodności)."""
        assert is_contribution_allowed("sku_verification", "B", "sku_exists") is False

    def test_sku_verification_allowed_sku_mismatch_on_row_b(self):
        assert is_contribution_allowed("sku_verification", "B", "sku_mismatch") is True

    def test_undeclared_source_row_pair_rejected_by_default(self):
        assert is_contribution_allowed("sku_verification", "D", "anything") is False
        assert is_contribution_allowed("unknown_source", "A", "anything") is False


# ---------------------------------------------------------------------------
# merge_row — monotoniczność
# ---------------------------------------------------------------------------

class TestMergeRowMonotonicity:
    def test_positive_external_does_not_erase_problem_base(self):
        """SPEC sekcja 9, kryterium 1: contrib agent_a_visual(row B, problem) +
        sku_verification(found_authorized, próbujący pisać B) → wiersz B
        pozostaje problem, NIGDY ok. (found_authorized nie generuje w ogóle
        wkładu dla B — patrz capability contract — więc base stoi bez zmian)."""
        base = Contribution(source="agent_a_visual", row="B", claim_scope="visual",
                             status="problem", info_level="high", text="Agent A: niezgodność sezonu.")
        # Symulujemy próbę zapisu B pozytywnym wkładem — capability contract go odrzuci.
        rejected_external = Contribution(source="sku_verification", row="B", claim_scope="sku_exists",
                                          status="ok", info_level="high", text="Kod istnieje.")
        status, text = merge_row("B", base, [rejected_external])
        assert status == "problem"
        assert text == "Agent A: niezgodność sezonu."

    def test_external_can_worsen_ok_base(self):
        base = Contribution(source="agent_a_visual", row="A", claim_scope="visual",
                             status="ok", info_level="high", text="Metka wygląda dobrze.")
        worsening = Contribution(source="sku_verification", row="A", claim_scope="sku_exists",
                                  status="problem", info_level="high", text="Kod niezgodny.")
        status, text = merge_row("A", base, [worsening])
        assert status == "problem"
        assert "Metka wygląda dobrze." in text
        assert "Kod niezgodny." in text

    def test_high_info_external_can_override_low_info_base_even_if_technically_improving(self):
        base = Contribution(source="agent_a_visual", row="A", claim_scope="visual",
                             status="problem", info_level="low", text="Niepewne, słabe zdjęcie.")
        confident_positive = Contribution(source="sku_verification", row="A", claim_scope="sku_exists",
                                           status="ok", info_level="high", text="Kod potwierdzony.")
        status, text = merge_row("A", base, [confident_positive])
        assert status == "ok"

    def test_low_info_external_cannot_override_high_info_base(self):
        base = Contribution(source="agent_a_visual", row="A", claim_scope="visual",
                             status="problem", info_level="high", text="Wyraźnie zła metka.")
        weak_positive = Contribution(source="sku_verification", row="A", claim_scope="sku_exists",
                                      status="ok", info_level="low", text="Może istnieje.")
        status, text = merge_row("A", base, [weak_positive])
        assert status == "problem"

    def test_missing_base_defaults_to_neutral_uwaga(self):
        status, text = merge_row("A", None, [])
        assert status == "uwaga"

    def test_no_external_contributions_returns_base_unchanged(self):
        base = Contribution(source="agent_a_visual", row="C", claim_scope="visual",
                             status="ok", info_level="high", text="Haft wygląda dobrze.")
        status, text = merge_row("C", base, [])
        assert status == "ok"
        assert text == "Haft wygląda dobrze."

    def test_external_for_different_row_ignored(self):
        base = Contribution(source="agent_a_visual", row="A", claim_scope="visual",
                             status="ok", info_level="high", text="OK.")
        other_row = Contribution(source="sku_verification", row="B", claim_scope="sku_mismatch",
                                  status="problem", info_level="high", text="Niezgodność.")
        status, text = merge_row("A", base, [other_row])
        assert status == "ok"
        assert text == "OK."

    def test_malformed_status_does_not_crash_fail_closed(self):
        """QA (2026-09-05): merge_row jest publiczną funkcją modułu — nie
        powinna crashować KeyError-em na nieznanej wartości status, nawet
        jeśli dziś żaden realny caller jej nie produkuje."""
        base = Contribution(source="agent_a_visual", row="A", claim_scope="visual",
                             status="ok", info_level="high", text="OK.")
        bad = Contribution(source="sku_verification", row="A", claim_scope="sku_exists",
                            status="ZZZ_TYPO", info_level="high", text="Coś dziwnego.")
        status, text = merge_row("A", base, [bad])  # nie rzuca

    def test_text_order_independent_for_multiple_applicable_externals(self):
        """QA (2026-09-05): status już był order-independent, tekst — nie był
        (łączył wkłady 'po drodze', które finalny wynik później przebijał).
        Weryfikacja w obu kolejnościach daje IDENTYCZNY tekst, nie tylko status."""
        base = Contribution(source="agent_a_visual", row="A", claim_scope="visual",
                             status="ok", info_level="high", text="Baza OK.")
        mild = Contribution(source="sku_verification", row="A", claim_scope="sku_exists",
                             status="uwaga", info_level="high", text="Łagodne zastrzeżenie.")
        severe = Contribution(source="sku_verification", row="A", claim_scope="sku_exists",
                               status="problem", info_level="high", text="Poważny problem.")
        status_1, text_1 = merge_row("A", base, [mild, severe])
        status_2, text_2 = merge_row("A", base, [severe, mild])
        assert status_1 == status_2 == "problem"
        assert text_1 == text_2
        assert "Poważny problem." in text_1
        assert "Łagodne zastrzeżenie." not in text_1  # przebite, nie powinno zostać


# ---------------------------------------------------------------------------
# build_sku_contributions
# ---------------------------------------------------------------------------

class TestBuildSkuContributionsMismatch:
    """SPEC kryterium 5: mismatch dokłada problem."""

    def test_mismatch_produces_problem_on_both_rows(self):
        contribs = build_sku_contributions(
            {"status": "mismatch", "reason": "Kod z innego modelu."},
            {"club": "FC Barcelona", "season": "2023/24", "model": "domowa"},
        )
        by_row = {c.row: c for c in contribs}
        assert by_row["A"].status == "problem"
        assert by_row["B"].status == "problem"
        assert by_row["B"].claim_scope == "sku_mismatch"


class TestBuildSkuContributionsDegradedInput:
    """SPEC kryterium 3: zdegradowane wejście (Sezon/Model = 'nieustalone') +
    found_authorized → status uwaga, tekst 'nie zweryfikowano zgodności z tym
    egzemplarzem' (nie zielone, nie 'bardzo prawdopodobna')."""

    def test_degraded_season_downgrades_row_a_to_uwaga(self):
        contribs = build_sku_contributions(
            {"status": "found_authorized", "reason": ""},
            {"club": "FC Barcelona", "season": "nieustalone", "model": "domowa"},
        )
        row_a = next(c for c in contribs if c.row == "A")
        assert row_a.status == "uwaga"
        assert "nie zweryfikowano zgodności" in row_a.text
        assert row_a.info_level == "low"

    def test_degraded_model_also_downgrades(self):
        contribs = build_sku_contributions(
            {"status": "found_authorized", "reason": ""},
            {"club": "FC Barcelona", "season": "2023/24", "model": "nieustalone"},
        )
        row_a = next(c for c in contribs if c.row == "A")
        assert row_a.status == "uwaga"

    def test_no_positive_contribution_for_row_b_even_when_degraded(self):
        """Pozytywny 'istnieje' NIGDY nie tworzy twierdzenia o zgodności dla B,
        niezależnie od degradacji wejścia."""
        contribs = build_sku_contributions(
            {"status": "found_authorized", "reason": ""},
            {"club": "FC Barcelona", "season": "nieustalone", "model": "nieustalone"},
        )
        assert all(c.row != "B" for c in contribs)

    def test_non_degraded_found_authorized_stays_ok_high_info(self):
        contribs = build_sku_contributions(
            {"status": "found_authorized", "reason": ""},
            {"club": "FC Barcelona", "season": "2023/24", "model": "domowa"},
        )
        row_a = next(c for c in contribs if c.row == "A")
        assert row_a.status == "ok"
        assert row_a.info_level == "high"


class TestBuildSkuContributionsOtherStatuses:
    def test_found_unofficial_produces_problem_row_a_only(self):
        contribs = build_sku_contributions({"status": "found_unofficial"}, {})
        assert len(contribs) == 1
        assert contribs[0].row == "A"
        assert contribs[0].status == "problem"

    def test_format_invalid_produces_problem_row_a_only(self):
        contribs = build_sku_contributions({"status": "format_invalid"}, {})
        assert len(contribs) == 1
        assert contribs[0].row == "A"
        assert contribs[0].status == "problem"

    def test_not_found_produces_uwaga_row_a_only(self):
        contribs = build_sku_contributions({"status": "not_found"}, {})
        assert len(contribs) == 1
        assert contribs[0].status == "uwaga"

    def test_not_applicable_produces_no_contributions(self):
        assert build_sku_contributions({"status": "not_applicable"}, {}) == []

    def test_uncertain_produces_no_contributions(self):
        assert build_sku_contributions({"status": "uncertain"}, {}) == []

    def test_none_inputs_do_not_crash(self):
        assert build_sku_contributions(None, None) == []


# ---------------------------------------------------------------------------
# merge_sku_rows_into_decision_matrix — orkiestracja end-to-end
# ---------------------------------------------------------------------------

class TestMergeSkuRowsIntoDecisionMatrixEndToEnd:
    """Replay dokładnego kształtu case 15364d60 (złota koszulka Lewandowskiego)
    przez pełną orkiestrację, nie tylko pure functions."""

    def _dm(self):
        return [
            {"code": "A", "status": "GREEN", "observation": "Metka wewnętrzna widoczna, kod czytelny.", "weight": 3, "impact": "obniza"},
            {"code": "B", "status": "RED", "observation": "Kod SKU wskazuje na zupełnie inny model (wyjazdowy 21/22) niż widoczny (złoty).", "weight": 2, "impact": "obniza"},
            {"code": "C", "status": "YELLOW", "observation": "", "weight": 5, "impact": "ogranicza_pewnosc"},
        ]

    def test_regression_case_15364d60_row_b_stays_red_despite_found_authorized(self):
        dm = self._dm()
        sku_verification = {
            "status": "found_authorized",
            "reason": "Kod CV7891-428 znaleziony u autoryzowanego sprzedawcy — domowa 21/22.",
        }
        subject = {"club": "FC Barcelona", "season": "nieustalone", "model": "nieustalone"}
        merge_sku_rows_into_decision_matrix(dm, sku_verification, subject)
        row_b = next(r for r in dm if r["code"] == "B")
        assert row_b["status"] == "RED"  # nigdy GREEN/OK, mimo found_authorized

    def test_regression_case_15364d60_row_a_downgraded_not_confirmed(self):
        dm = self._dm()
        sku_verification = {
            "status": "found_authorized",
            "reason": "Kod CV7891-428 znaleziony u autoryzowanego sprzedawcy — domowa 21/22.",
        }
        subject = {"club": "FC Barcelona", "season": "nieustalone", "model": "nieustalone"}
        merge_sku_rows_into_decision_matrix(dm, sku_verification, subject)
        row_a = next(r for r in dm if r["code"] == "A")
        # base Agenta A było GREEN (info_level high) — ale zewn. wkład ma info_level
        # "low" (bo wejście zdegradowane), więc low_info_override nie wchodzi w grę
        # z tej strony; jedyna droga zmiany to "worsens" (uwaga > ok) — więc row A
        # zostaje POGORSZONE do uwagi.
        assert row_a["status"] == "YELLOW"
        assert "nie zweryfikowano zgodności" in row_a["observation"]

    def test_mismatch_upgrades_previously_green_row_b_to_problem(self):
        """SPEC kryterium 'mismatch dokłada problem': sku_verification(mismatch)
        + agent_a_visual(B, ok) → B staje się problem."""
        dm = [
            {"code": "A", "status": "GREEN", "observation": "OK.", "weight": 3, "impact": "obniza"},
            {"code": "B", "status": "GREEN", "observation": "Wygląda zgodnie.", "weight": 2, "impact": "obniza"},
        ]
        sku_verification = {"status": "mismatch", "reason": "Zupełnie inny model."}
        subject = {"club": "FC Barcelona", "season": "2023/24", "model": "domowa"}
        merge_sku_rows_into_decision_matrix(dm, sku_verification, subject)
        row_b = next(r for r in dm if r["code"] == "B")
        assert row_b["status"] == "RED"

    def test_no_op_when_status_not_applicable(self):
        dm = self._dm()
        original = [dict(r) for r in dm]
        merge_sku_rows_into_decision_matrix(dm, {"status": "not_applicable"}, {"club": "X", "season": "2023/24", "model": "domowa"})
        assert dm == original

    def test_missing_rows_a_b_does_not_crash(self):
        dm = [{"code": "C", "status": "GREEN", "observation": "", "weight": 5}]
        merge_sku_rows_into_decision_matrix(dm, {"status": "mismatch"}, {})  # no exception
        assert dm[0]["code"] == "C"  # untouched

    def test_unknown_status_preserved_when_no_contribution_applies(self):
        """Code review BLOCKER (2026-09-05): status_a wewnętrznie mapowany
        UNKNOWN→"uwaga", a _INTERNAL_TO_STATUS nie ma klucza UNKNOWN — bez
        no-op guarda każde UNKNOWN wychodziło jako YELLOW nawet gdy
        sku_verification nic nie wniósł (not_applicable/uncertain to
        NAJCZĘSTSZY kształt "brak widocznego SKU", nie skrajny przypadek)."""
        dm = [{"code": "A", "status": "UNKNOWN", "observation": "Kod SKU nie jest widoczny na zdjęciach.", "impact": "neutralne"}]
        merge_sku_rows_into_decision_matrix(dm, {"status": "not_applicable"}, {})
        assert dm[0]["status"] == "UNKNOWN"
        assert dm[0]["observation"] == "Kod SKU nie jest widoczny na zdjęciach."

    def test_unknown_status_preserved_for_uncertain_sku_status_too(self):
        dm = [{"code": "A", "status": "UNKNOWN", "observation": "Brak danych.", "impact": "neutralne"}]
        merge_sku_rows_into_decision_matrix(dm, {"status": "uncertain"}, {})
        assert dm[0]["status"] == "UNKNOWN"

    def test_non_default_impact_preserved_when_no_contribution_applies(self):
        """Code review BLOCKER (2026-09-05): row["impact"] = "obniza" if
        status != "ok" else ... nadpisywał niedomyślny impact (np.
        "ogranicza_pewnosc") nawet dla niezmienionych wierszy."""
        dm = [{"code": "A", "status": "YELLOW", "observation": "Coś niejasnego.", "impact": "ogranicza_pewnosc"}]
        merge_sku_rows_into_decision_matrix(dm, {"status": "not_applicable"}, {})
        assert dm[0]["impact"] == "ogranicza_pewnosc"

    def test_row_completely_untouched_bit_for_bit_when_no_contribution(self):
        dm = [{"code": "A", "status": "UNKNOWN", "observation": "X.", "impact": "neutralne", "weight": 3, "criterion": "Metki / SKU"}]
        original = dict(dm[0])
        merge_sku_rows_into_decision_matrix(dm, {"status": "not_applicable"}, {})
        assert dm[0] == original

    def test_non_degraded_found_authorized_on_green_base_is_still_a_genuine_no_op(self):
        """found_authorized bez degradacji produkuje status='ok' (rank 0) —
        to NIE 'worsens' względem bazy GREEN/ok (rank 0 nie jest > 0), więc
        wiersz zostaje nietknięty, nie tylko 'przekonwertowany na to samo'."""
        dm = [{"code": "A", "status": "GREEN", "observation": "Oryginalny tekst Agenta A.", "impact": "neutralne"}]
        merge_sku_rows_into_decision_matrix(
            dm, {"status": "found_authorized", "reason": ""},
            {"club": "FC Barcelona", "season": "2023/24", "model": "domowa"},
        )
        assert dm[0]["observation"] == "Oryginalny tekst Agenta A."


# ---------------------------------------------------------------------------
# apply_global_invariant
# ---------------------------------------------------------------------------

class TestApplyGlobalInvariant:
    """SPEC kryterium 'Niezmiennik globalny (regresja case 15364d60)': gdy
    verdict='podrobka', żaden wiersz A/B nie jest ok/zielony; tekst spójny z
    podsumowaniem."""

    def test_green_row_a_downgraded_when_verdict_is_podrobka(self):
        dm = [{"code": "A", "status": "GREEN", "observation": "Kod potwierdzony.", "impact": "neutralne"}]
        apply_global_invariant(dm, "podrobka")
        assert dm[0]["status"] == "YELLOW"

    def test_green_row_b_downgraded_when_verdict_is_podrobka(self):
        dm = [{"code": "B", "status": "GREEN", "observation": "Zgodność bardzo prawdopodobna.", "impact": "obniza"}]
        apply_global_invariant(dm, "podrobka")
        assert dm[0]["status"] == "YELLOW"

    def test_non_green_rows_untouched(self):
        dm = [
            {"code": "A", "status": "RED", "observation": "Już czerwony.", "impact": "obniza"},
            {"code": "B", "status": "YELLOW", "observation": "Już uwaga.", "impact": "obniza"},
        ]
        original = [dict(r) for r in dm]
        apply_global_invariant(dm, "podrobka")
        assert dm == original

    def test_other_rows_not_touched_even_if_green(self):
        dm = [{"code": "C", "status": "GREEN", "observation": "Haft dobry.", "impact": "podnosi"}]
        apply_global_invariant(dm, "podrobka")
        assert dm[0]["status"] == "GREEN"

    def test_no_op_when_verdict_is_not_podrobka(self):
        dm = [{"code": "A", "status": "GREEN", "observation": "Kod potwierdzony.", "impact": "neutralne"}]
        apply_global_invariant(dm, "meczowa")
        assert dm[0]["status"] == "GREEN"

    def test_missing_row_does_not_crash(self):
        dm = [{"code": "C", "status": "GREEN", "observation": "", "impact": "neutralne"}]
        apply_global_invariant(dm, "podrobka")  # no exception, row C untouched
        assert dm[0]["status"] == "GREEN"
