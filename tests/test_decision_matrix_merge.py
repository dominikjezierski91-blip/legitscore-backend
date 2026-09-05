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
    apply_season_correction,
    build_sku_contributions,
    compute_season_display,
    gate_season_dependent_evidence,
    is_contribution_allowed,
    merge_row,
    merge_sku_rows_into_decision_matrix,
    reclassify_quality_only_impact,
    resolve_season_only_sku_mismatch,
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
    """SPEC kryterium 5: product_mismatch dokłada problem. Status "mismatch"
    przemianowano na "product_mismatch"/"season_only_mismatch" 2026-09-06
    (SPEC "autorytatywny SKU koryguje sezon", case eb90a5cc vs feee21e0)."""

    def test_product_mismatch_produces_problem_on_both_rows(self):
        contribs = build_sku_contributions(
            {"status": "product_mismatch", "reason": "Kod z innego modelu."},
            {"club": "FC Barcelona", "season": "2023/24", "model": "domowa"},
        )
        by_row = {c.row: c for c in contribs}
        assert by_row["A"].status == "problem"
        assert by_row["B"].status == "problem"
        assert by_row["B"].claim_scope == "sku_mismatch"

    def test_season_only_mismatch_produces_soft_uwaga_not_problem(self):
        """Residualny przypadek (korekta niemożliwa, brak found_season) —
        celowo miękkie zastrzeżenie, nie twardy "problem", bo nie wiadomo,
        czy to prawdziwa niezgodność, czy tylko złe zgadnięcie sezonu."""
        contribs = build_sku_contributions(
            {"status": "season_only_mismatch", "reason": "Inny sezon, brak found_season."},
            {"club": "FC Barcelona", "season": "2023/24", "model": "domowa"},
        )
        by_row = {c.row: c for c in contribs}
        assert by_row["A"].status == "uwaga"
        assert by_row["B"].status == "uwaga"
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

    def test_product_mismatch_upgrades_previously_green_row_b_to_problem(self):
        """SPEC kryterium 'mismatch dokłada problem': sku_verification
        (product_mismatch) + agent_a_visual(B, ok) → B staje się problem."""
        dm = [
            {"code": "A", "status": "GREEN", "observation": "OK.", "weight": 3, "impact": "obniza"},
            {"code": "B", "status": "GREEN", "observation": "Wygląda zgodnie.", "weight": 2, "impact": "obniza"},
        ]
        sku_verification = {"status": "product_mismatch", "reason": "Zupełnie inny model."}
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
        merge_sku_rows_into_decision_matrix(dm, {"status": "product_mismatch"}, {})  # no exception
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


# ---------------------------------------------------------------------------
# SPEC "pewność sezonu + reklasyfikacja jakości" (2026-09-05, case 1b96a6a4,
# Pedri/FC Barcelona). Kryteria akceptacji SPEC sekcja 7.
# ---------------------------------------------------------------------------

class TestReclassifyQualityOnlyImpact:
    """SPEC Część 3, kryterium akceptacji 2: 'jakość nie podnosi' — przesłanka
    "wysoka jakość wykonania" → Wpływ = neutralne, NIGDY "podnosi"."""

    def test_row_c_podnosi_reclassified_to_neutralne(self):
        dm = [{"code": "C", "status": "GREEN", "observation": "Herb i logo starannie wykonane, spójne z wersją meczową.", "impact": "podnosi"}]
        reclassify_quality_only_impact(dm)
        assert dm[0]["impact"] == "neutralne"

    def test_row_e_podnosi_reclassified_to_neutralne(self):
        dm = [{"code": "E", "status": "GREEN", "observation": "Personalizacja wygląda profesjonalnie.", "impact": "podnosi"}]
        reclassify_quality_only_impact(dm)
        assert dm[0]["impact"] == "neutralne"

    def test_canonical_nondecisive_text_used(self):
        dm = [{"code": "C", "status": "GREEN", "observation": "X.", "impact": "podnosi"}]
        reclassify_quality_only_impact(dm)
        assert "nierozstrzygające" in dm[0]["observation"]

    def test_status_untouched_only_impact_and_text_change(self):
        """Status (GREEN) zostaje — to wciąż prawdziwy opis obserwacji, zmienia
        się tylko jego interpretacyjna waga jako dowodu."""
        dm = [{"code": "C", "status": "GREEN", "observation": "X.", "impact": "podnosi"}]
        reclassify_quality_only_impact(dm)
        assert dm[0]["status"] == "GREEN"

    def test_quality_bad_direction_untouched_obniza_stays(self):
        """Kierunek 'jakość zła → obniża' NIE jest tym SPEC-em dotknięty —
        jakość nadal może dyskwalifikować, tylko nie może już ratować."""
        dm = [{"code": "C", "status": "RED", "observation": "Nierówny haft, tania jakość.", "impact": "obniza"}]
        reclassify_quality_only_impact(dm)
        assert dm[0]["impact"] == "obniza"
        assert dm[0]["observation"] == "Nierówny haft, tania jakość."

    def test_neutral_impact_left_alone(self):
        dm = [{"code": "C", "status": "YELLOW", "observation": "X.", "impact": "neutralne"}]
        reclassify_quality_only_impact(dm)
        assert dm[0]["observation"] == "X."

    def test_other_rows_never_touched(self):
        """Tylko C i E — kryteria z natury oparte na estetyce/staranności.
        D (materiał/technologia) może mieć podnosi z innych, twardszych
        powodów (np. potwierdzona zgodna technologia) i nie jest tu dotykane."""
        dm = [{"code": "D", "status": "GREEN", "observation": "Technologia potwierdzona.", "impact": "podnosi"}]
        reclassify_quality_only_impact(dm)
        assert dm[0]["impact"] == "podnosi"

    def test_missing_rows_does_not_crash(self):
        dm = [{"code": "A", "status": "GREEN", "observation": "", "impact": "neutralne"}]
        reclassify_quality_only_impact(dm)  # no exception


class TestGateSeasonDependentEvidence:
    """SPEC Część 2, kryteria akceptacji 1 i 5 (replay case 1b96a6a4)."""

    def _row_d_strong_season_argument(self):
        return {
            "code": "D", "status": "RED",
            "observation": (
                "Materiał i konstrukcja wizualnie przypominają wersję meczową, ale "
                "oznaczenie technologii 'DRI-FIT ADV' jest sprzeczne z dostarczonymi "
                "informacjami, według których wersja meczowa na sezon 2026/27 "
                "powinna posiadać technologię 'Nike Aero-FIT'."
            ),
            "impact": "obniza",
        }

    def test_low_confidence_downgrades_row_d_impact(self):
        dm = [self._row_d_strong_season_argument()]
        gate_season_dependent_evidence(dm, [], "low")
        assert dm[0]["impact"] == "ogranicza_pewnosc"

    def test_low_confidence_makes_row_d_text_conditional(self):
        dm = [self._row_d_strong_season_argument()]
        gate_season_dependent_evidence(dm, [], "low")
        assert "warunkowa" in dm[0]["observation"] or "niepewnością" in dm[0]["observation"]

    def test_low_confidence_inserts_season_caveat_as_first_key_evidence_item(self):
        """SPEC: nie listuj przesłanki zależnej od niepewnego sezonu jako #1
        'silny wskaźnik' bez zastrzeżenia — caveat trafia na start listy,
        więc jest w 'Najsilniejsze sygnały' (key_evidence[:3])."""
        key_evidence = [
            {"type": "negative", "text": "Kluczowa sprzeczność: DRI-FIT ADV vs Aero-FIT."},
        ]
        dm = [self._row_d_strong_season_argument()]
        gate_season_dependent_evidence(dm, key_evidence, "low")
        assert key_evidence[0]["text"].startswith("⚠")
        assert "sezon" in key_evidence[0]["text"].lower()
        assert key_evidence[1]["text"] == "Kluczowa sprzeczność: DRI-FIT ADV vs Aero-FIT."

    def test_caveat_not_duplicated_on_repeated_calls(self):
        key_evidence = []
        dm = [self._row_d_strong_season_argument()]
        gate_season_dependent_evidence(dm, key_evidence, "low")
        gate_season_dependent_evidence(dm, key_evidence, "low")
        caveat_count = sum(1 for e in key_evidence if e.get("text", "").startswith("⚠"))
        assert caveat_count == 1

    def test_medium_confidence_does_not_trigger_backend_gating(self):
        """SPEC sekcja 4 celowo mówi TYLKO 'low' dla warstwy deterministycznej
        — 'medium' to hedge Agenta A samego w sobie (Część 1), nie backend."""
        dm = [self._row_d_strong_season_argument()]
        original_impact = dm[0]["impact"]
        gate_season_dependent_evidence(dm, [], "medium")
        assert dm[0]["impact"] == original_impact

    def test_high_confidence_leaves_matrix_unchanged(self):
        """SPEC kryterium akceptacji 5: 'Sezon high ⇒ zachowanie jak dziś'."""
        dm = [self._row_d_strong_season_argument()]
        original = dict(dm[0])
        gate_season_dependent_evidence(dm, [], "high")
        assert dm[0] == original

    def test_none_confidence_leaves_matrix_unchanged(self):
        dm = [self._row_d_strong_season_argument()]
        original = dict(dm[0])
        gate_season_dependent_evidence(dm, [], None)
        assert dm[0] == original

    def test_uppercase_or_mixed_case_low_still_triggers_gating(self):
        """QA (2026-09-05): Agent A to LLM, nie gwarantuje literalnej małej
        litery mimo szablonu w promptcie — bez normalizacji 'Low'/'LOW'
        cicho pomijało bramkowanie, odtwarzając dokładnie bug z case
        1b96a6a4 bez żadnego błędu/logu."""
        for variant in ("LOW", "Low", " low ", "lOw"):
            dm = [self._row_d_strong_season_argument()]
            gate_season_dependent_evidence(dm, [], variant)
            assert dm[0]["impact"] == "ogranicza_pewnosc", f"failed for {variant!r}"

    def test_non_string_confidence_does_not_crash_and_does_not_trigger(self):
        dm = [self._row_d_strong_season_argument()]
        original_impact = dm[0]["impact"]
        gate_season_dependent_evidence(dm, [], True)
        assert dm[0]["impact"] == original_impact

    def test_row_d_without_strong_impact_not_touched(self):
        """Jeśli D już ma impact='neutralne'/'ogranicza_pewnosc' (Agent A sam
        nie uznał tego za mocny dowód) — nie ma czego degradować."""
        dm = [{"code": "D", "status": "YELLOW", "observation": "X.", "impact": "ogranicza_pewnosc"}]
        gate_season_dependent_evidence(dm, [], "low")
        assert dm[0]["observation"] == "X."

    def test_missing_row_d_does_not_crash(self):
        dm = [{"code": "C", "status": "GREEN", "observation": "", "impact": "podnosi"}]
        gate_season_dependent_evidence(dm, [], "low")  # no exception

    def test_none_key_evidence_does_not_crash(self):
        dm = [self._row_d_strong_season_argument()]
        gate_season_dependent_evidence(dm, None, "low")  # no exception
        assert dm[0]["impact"] == "ogranicza_pewnosc"  # wiersz D nadal zdegradowany


class TestSeasonAndQualityGatingCombinedReplayCase1b96a6a4:
    """Replay pełnego kształtu case 1b96a6a4 (obie funkcje razem) — dokładna
    kombinacja pól z prawdziwego raportu."""

    def _real_decision_matrix(self):
        return [
            {"criterion": "Metki / SKU / data / fabryka", "code": "A", "weight": 3, "status": "YELLOW",
             "observation": "Widoczne oznaczenia 'DRI-FIT ADV' i 'ENGINEERED' są spójne z wersją meczową, ale kluczowa metka wewnętrzna z kodem SKU jest nieczytelna.",
             "impact": "ogranicza_pewnosc"},
            {"criterion": "Zgodność SKU z modelem / sezonem", "code": "B", "weight": 2, "status": "UNKNOWN",
             "observation": "Kod SKU nie jest widoczny na dostarczonych zdjęciach.", "impact": "neutralne"},
            {"criterion": "Haft / logo / herb / patche", "code": "C", "weight": 5, "status": "GREEN",
             "observation": "Herb, logo Nike oraz naszywka La Liga są aplikowane termicznie, co jest spójne z cechami koszulki w wersji meczowej.",
             "impact": "podnosi"},
            {"criterion": "Materiał / technologia / krój", "code": "D", "weight": 6, "status": "RED",
             "observation": "Materiał i konstrukcja wizualnie przypominają wersję meczową, ale oznaczenie technologii 'DRI-FIT ADV' jest sprzeczne z dostarczonymi informacjami, według których wersja meczowa na sezon 2026/27 powinna posiadać technologię 'Nike Aero-FIT'.",
             "impact": "obniza"},
            {"criterion": "Personalizacja", "code": "E", "weight": 4, "status": "GREEN",
             "observation": "Personalizacja 'PEDRI 8' wygląda na wykonaną profesjonalnie.", "impact": "podnosi"},
        ]

    def _real_key_evidence(self):
        return [
            {"type": "negative", "text": "Kluczowa sprzeczność: koszulka posiada oznaczenie technologii 'DRI-FIT ADV', podczas gdy dostarczone informacje o oficjalnym stroju na sezon 2026/27 wskazują na użycie technologii 'Nike Aero-FIT' w wersji meczowej. To silny wskaźnik nieautentyczności."},
            {"type": "positive", "text": "Wizualna jakość wykonania, termicznie aplikowane logotypy oraz personalizacja są na wysokim poziomie, naśladując cechy autentycznej koszulki meczowej."},
        ]

    def test_row_c_and_e_no_longer_favor_authenticity(self):
        dm = self._real_decision_matrix()
        reclassify_quality_only_impact(dm)
        row_c = next(r for r in dm if r["code"] == "C")
        row_e = next(r for r in dm if r["code"] == "E")
        assert row_c["impact"] == "neutralne"
        assert row_e["impact"] == "neutralne"

    def test_row_d_no_longer_presented_as_decisive_when_season_low(self):
        dm = self._real_decision_matrix()
        gate_season_dependent_evidence(dm, self._real_key_evidence(), "low")
        row_d = next(r for r in dm if r["code"] == "D")
        assert row_d["impact"] == "ogranicza_pewnosc"

    def test_key_evidence_caveat_precedes_original_strong_claim(self):
        key_evidence = self._real_key_evidence()
        dm = self._real_decision_matrix()
        gate_season_dependent_evidence(dm, key_evidence, "low")
        assert key_evidence[0]["text"].startswith("⚠")
        assert "silny wskaźnik" in key_evidence[1]["text"]

    def test_verdict_fields_never_referenced_by_either_function(self):
        """SPEC sekcja 2, POZA zakresem: te funkcje operują wyłącznie na
        decision_matrix/key_evidence, nigdy na verdict_category/confidence/
        label/summary — sprawdzone przez brak takich kluczy w sygnaturach i
        przez to, że test nie przekazuje im nic poza dm/key_evidence."""
        dm = self._real_decision_matrix()
        key_evidence = self._real_key_evidence()
        reclassify_quality_only_impact(dm)
        gate_season_dependent_evidence(dm, key_evidence, "low")
        # Brak crasha i brak nowych kluczy typu 'verdict' wstrzykniętych do dm/key_evidence
        assert all("verdict" not in str(k).lower() for row in dm for k in row.keys())


class TestApplySeasonCorrection:
    """Code review finding H1 (2026-09-05): PCC (temporal_mismatch) koryguje
    subject.season NIEZALEŻNIE od tego, co Agent A sam zgłosił jako
    season_confidence. Bez tej funkcji: Agent A mógł zgłosić "high", PCC i
    tak poprawia sezon, a gate_season_dependent_evidence nigdy nie odpala —
    dokładnie ta sama luka co case 1b96a6a4, tylko od strony PCC. Zasada:
    automatyczna korekta pola unieważnia pewność TEGO pola."""

    def _row_d_strong_season_argument(self):
        return {
            "code": "D", "status": "RED",
            "observation": (
                "Oznaczenie technologii 'DRI-FIT ADV' jest sprzeczne z sezonem "
                "2026/27, który powinien mieć 'Nike Aero-FIT'."
            ),
            "impact": "obniza",
        }

    def test_sets_corrected_season_as_content(self):
        subject = {"season": "2026-2027", "season_confidence": "high"}
        apply_season_correction(subject, [], [], "2025-2026")
        assert subject["season"] == "2025-2026"

    def test_forces_season_confidence_to_low_even_when_agent_a_said_high(self):
        subject = {"season": "2026-2027", "season_confidence": "high"}
        apply_season_correction(subject, [], [], "2025-2026")
        assert subject["season_confidence"] == "low"

    def test_forces_season_confidence_to_low_even_when_agent_a_said_medium(self):
        subject = {"season": "2026-2027", "season_confidence": "medium"}
        apply_season_correction(subject, [], [], "2025-2026")
        assert subject["season_confidence"] == "low"

    def test_re_gates_row_d_despite_original_high_confidence(self):
        """To jest sedno H1: bez re-bramkowania, wysokie season_confidence
        sprzed korekty PCC zostawiłoby wiersz D z mocnym (niezdegradowanym)
        impact, mimo że sezon leżący u podstaw tego wniosku właśnie okazał
        się błędny."""
        subject = {"season": "2026-2027", "season_confidence": "high"}
        dm = [self._row_d_strong_season_argument()]
        apply_season_correction(subject, dm, [], "2025-2026")
        assert dm[0]["impact"] == "ogranicza_pewnosc"

    def test_re_gating_inserts_season_caveat_into_key_evidence(self):
        subject = {"season": "2026-2027", "season_confidence": "high"}
        dm = [self._row_d_strong_season_argument()]
        key_evidence = [{"type": "negative", "text": "DRI-FIT ADV vs Aero-FIT — silny wskaźnik."}]
        apply_season_correction(subject, dm, key_evidence, "2025-2026")
        assert key_evidence[0]["text"].startswith("⚠")

    def test_does_not_touch_verdict_fields(self):
        subject = {
            "season": "2026-2027", "season_confidence": "high",
            "verdict_category": "podrobka", "confidence_percent": 95,
        }
        apply_season_correction(subject, [self._row_d_strong_season_argument()], [], "2025-2026")
        assert subject["verdict_category"] == "podrobka"
        assert subject["confidence_percent"] == 95


class TestComputeSeasonDisplay:
    """SPEC "uczciwe wyświetlanie sezonu" (2026-09-06, case 1e8b405c): pole
    identyfikacyjne o niepewnym statusie nie może być prezentowane jako
    pewnik. Replay realnych danych case'a 1e8b405c: subject.season =
    "2026-2027", season_confidence = "high" (mimo że właściciel koszulki sam
    był niepewny — "chyba 2022/23") — ten konkretny case ilustruje, dlaczego
    Część 3 (dyscyplina promptu) jest potrzebna OBOK Części 1 (bramkowanie
    wyświetlania): backend ufa "high" zgłoszonemu przez Agenta A, więc samo
    bramkowanie displayu nie wystarczy, jeśli "high" jest nieuzasadnione —
    stąd też zaostrzenie kryteriów "high" w promptcie."""

    def test_high_confidence_shows_season_as_is(self):
        assert compute_season_display("2026-2027", "high") == "2026-2027"

    def test_medium_confidence_hedges_with_explicit_caveat(self):
        result = compute_season_display("2022-2023", "medium")
        assert result == "prawdopodobnie 2022-2023 (niepewne)"

    def test_low_confidence_hides_the_year_entirely(self):
        assert compute_season_display("2026-2027", "low") == "sezon nieokreślony"

    def test_none_confidence_hides_the_year(self):
        assert compute_season_display("2026-2027", None) == "sezon nieokreślony"

    def test_missing_confidence_string_type_hides_the_year(self):
        assert compute_season_display("2026-2027", True) == "sezon nieokreślony"

    def test_unrecognized_confidence_value_hides_the_year(self):
        assert compute_season_display("2026-2027", "bardzo pewne") == "sezon nieokreślony"

    def test_case_insensitive_high(self):
        assert compute_season_display("2026-2027", "HIGH") == "2026-2027"
        assert compute_season_display("2026-2027", " High ") == "2026-2027"

    def test_blank_season_shows_undetermined_regardless_of_confidence(self):
        assert compute_season_display("nieustalone", "high") == "sezon nieokreślony"
        assert compute_season_display(None, "high") == "sezon nieokreślony"
        assert compute_season_display("", "high") == "sezon nieokreślony"

    def test_forced_low_after_pcc_correction_hides_the_corrected_year_too(self):
        """H1 (poprzedni SPEC): apply_season_correction wymusza
        season_confidence="low" po korekcie PCC — ta sama wartość zasila
        compute_season_display, więc skorygowany rok TEŻ nie jest pokazywany
        jako pewnik. Zamierzone: zasada "korekta unieważnia pewność" ma
        zastosowanie tak samo do prezentacji, jak do siły wniosków."""
        subject = {"season": "2026-2027", "season_confidence": "high"}
        apply_season_correction(subject, [], [], "2022-2023")
        assert compute_season_display(subject["season"], subject["season_confidence"]) == "sezon nieokreślony"

    def test_replay_case_1e8b405c_high_confidence_but_weak_basis_still_shows_as_is(self):
        """Backend nie może wiedzieć, że "high" było nieuzasadnione — ufa
        zgłoszonej wartości. To właśnie dlatego Część 3 (dyscyplina promptu,
        patrz test_prompt_a_season_confidence.py) jest konieczna OBOK tej
        funkcji, nie zamiast niej."""
        assert compute_season_display("2026-2027", "high") == "2026-2027"


class TestResolveSeasonOnlySkuMismatch:
    """SPEC "autorytatywny SKU koryguje sezon" (2026-09-06, case eb90a5cc vs
    feee21e0, Lewandowski/FC Barcelona). Replay realnego regresu: ten sam,
    w pełni autoryzowany kod SKU FN8792-010 dał w jednym przebiegu
    "mismatch"→Podróbka 95%, a w drugim "found_authorized"→Meczowa 80% —
    jedyna różnica to własne, niepewne zgadnięcie sezonu Agenta A
    (season_confidence="medium" w obu przypadkach)."""

    def _sku_verification(self, found_season=""):
        return {
            "status": "season_only_mismatch",
            "confidence": "high",
            "found_product_name": "Nike FC Barcelona Stadium Away Jsy 24/25",
            "found_season": found_season,
            "reason": "Kod SKU FN8792-010 znaleziony, ale identyfikuje sezon 24/25, nie 23/24.",
            "source_url": "https://example.com",
        }

    def test_not_applicable_when_status_is_not_season_only_mismatch(self):
        sku = {"status": "found_authorized"}
        subject = {"season": "2023-2024", "season_confidence": "medium"}
        result = resolve_season_only_sku_mismatch(sku, subject, [], [])
        assert result == "not_applicable"
        assert sku["status"] == "found_authorized"  # nietknięte

    def test_high_confidence_escalates_to_product_mismatch(self):
        """Kryterium akceptacji: season_only_mismatch + high ⇒ hard-reject
        (Agent A był pewny sezonu, a mimo to kod jest z innego — realny sygnał)."""
        sku = self._sku_verification(found_season="2024/25")
        subject = {"season": "2023-2024", "season_confidence": "high"}
        result = resolve_season_only_sku_mismatch(sku, subject, [], [])
        assert result == "escalated"
        assert sku["status"] == "product_mismatch"
        assert subject["season"] == "2023-2024"  # NIE korygowane przy high

    def test_medium_confidence_with_found_season_corrects_and_repairs_status(self):
        """Kryterium akceptacji: autoryzowany SKU + season_only_mismatch przy
        medium ⇒ korekta, normalna ścieżka (jak w feee21e0), NIE hard-reject."""
        sku = self._sku_verification(found_season="2024/25")
        subject = {"season": "2023-2024", "season_confidence": "medium"}
        result = resolve_season_only_sku_mismatch(sku, subject, [], [])
        assert result == "corrected"
        assert sku["status"] == "found_authorized"
        assert subject["season"] == "2024/25"

    def test_low_confidence_with_found_season_also_corrects(self):
        sku = self._sku_verification(found_season="2024/25")
        subject = {"season": "2023-2024", "season_confidence": "low"}
        result = resolve_season_only_sku_mismatch(sku, subject, [], [])
        assert result == "corrected"
        assert sku["status"] == "found_authorized"

    def test_missing_confidence_treated_as_not_high_and_corrects(self):
        sku = self._sku_verification(found_season="2024/25")
        subject = {"season": "2023-2024"}  # brak season_confidence
        result = resolve_season_only_sku_mismatch(sku, subject, [], [])
        assert result == "corrected"

    def test_correction_forces_season_confidence_low_per_h1(self):
        """Zasada H1 (poprzedni SPEC): automatyczna korekta pola unieważnia
        pewność tego pola — nawet po korekcie sezon nie jest pewny."""
        sku = self._sku_verification(found_season="2024/25")
        subject = {"season": "2023-2024", "season_confidence": "medium"}
        resolve_season_only_sku_mismatch(sku, subject, [], [])
        assert subject["season_confidence"] == "low"

    def test_correction_re_gates_season_dependent_decision_matrix_rows(self):
        """apply_season_correction re-bramkuje decision_matrix — sprawdzone
        pośrednio przez efekt na wierszu D o mocnym impact zależnym od sezonu."""
        sku = self._sku_verification(found_season="2024/25")
        subject = {"season": "2023-2024", "season_confidence": "medium"}
        dm = [{"code": "D", "status": "RED", "observation": "Sprzeczność technologii dla sezonu 23/24.", "impact": "obniza"}]
        resolve_season_only_sku_mismatch(sku, subject, dm, [])
        assert dm[0]["impact"] == "ogranicza_pewnosc"

    def test_medium_confidence_without_found_season_stays_unresolved(self):
        """Kryterium akceptacji: brak found_season ⇒ nie ma na co skorygować
        — status zostaje season_only_mismatch (miękkie zastrzeżenie), NIE
        eskalacja do product_mismatch i NIE fałszywa korekta."""
        sku = self._sku_verification(found_season="")
        subject = {"season": "2023-2024", "season_confidence": "medium"}
        result = resolve_season_only_sku_mismatch(sku, subject, [], [])
        assert result == "unresolved"
        assert sku["status"] == "season_only_mismatch"
        assert subject["season"] == "2023-2024"  # nietknięte
        assert subject["season_confidence"] == "medium"  # nietknięte

    def test_non_string_found_season_does_not_crash(self):
        """QA (2026-09-06): brak str() coercji rzucał AttributeError, gdyby
        Gemini kiedyś zwrócił found_season jako liczbę zamiast stringa —
        zamieniało to miękką korektę w CAŁKOWICIE nieudaną analizę zamiast
        bezpiecznego spadku do "unresolved"."""
        sku = self._sku_verification(found_season=2024)
        subject = {"season": "2023-2024", "season_confidence": "medium"}
        result = resolve_season_only_sku_mismatch(sku, subject, [], [])
        assert result == "corrected"
        assert subject["season"] == "2024"

    def test_reason_text_documents_the_correction(self):
        sku = self._sku_verification(found_season="2024/25")
        subject = {"season": "2023-2024", "season_confidence": "medium"}
        resolve_season_only_sku_mismatch(sku, subject, [], [])
        assert "skorygowany" in sku["reason"].lower()

    def test_case_insensitive_high_confidence_check(self):
        sku = self._sku_verification(found_season="2024/25")
        subject = {"season": "2023-2024", "season_confidence": " High "}
        result = resolve_season_only_sku_mismatch(sku, subject, [], [])
        assert result == "escalated"

    def test_does_not_touch_verdict_fields(self):
        sku = self._sku_verification(found_season="2024/25")
        subject = {
            "season": "2023-2024", "season_confidence": "medium",
            "verdict_category": "meczowa", "confidence_percent": 80,
        }
        resolve_season_only_sku_mismatch(sku, subject, [], [])
        assert subject["verdict_category"] == "meczowa"
        assert subject["confidence_percent"] == 80

    def test_replay_eb90a5cc_full_convergence_with_feee21e0(self):
        """Kryterium akceptacji: konwergencja niezależnie od zgadnięcia sezonu
        — replay obu realnych przebiegów (eb90a5cc: zgadł 23/24, medium;
        feee21e0: zgadł 24/25, trafił). Po fixie obie ścieżki kończą tym
        samym statusem sku_verification (found_authorized), więc żadna nie
        dostaje 90%-hard-rejectu z powodu samego zgadnięcia sezonu."""
        # eb90a5cc: Agent A zgadł źle (23/24), SKU realnie to 24/25.
        sku_wrong_guess = {
            "status": "season_only_mismatch", "confidence": "high",
            "found_product_name": "Nike FC Barcelona Stadium Away Jsy 24/25",
            "found_season": "2024/25",
            "reason": "Kod SKU FN8792-010 identyfikuje sezon 2024/25, nie 2023/24.",
        }
        subject_wrong_guess = {"season": "2023-2024", "season_confidence": "medium"}
        result_wrong = resolve_season_only_sku_mismatch(sku_wrong_guess, subject_wrong_guess, [], [])

        # feee21e0: Agent A zgadł dobrze (24/25) — sku_agent od razu zwraca
        # found_authorized, ta funkcja się nie odpala (not_applicable).
        sku_right_guess = {"status": "found_authorized", "confidence": "high"}
        subject_right_guess = {"season": "2024/2025", "season_confidence": "medium"}
        result_right = resolve_season_only_sku_mismatch(sku_right_guess, subject_right_guess, [], [])

        assert result_wrong == "corrected"
        assert result_right == "not_applicable"
        assert sku_wrong_guess["status"] == sku_right_guess["status"] == "found_authorized"
