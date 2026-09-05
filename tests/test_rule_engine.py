"""
Testy jednostkowe Rule Engine i pomocniczych funkcji.
Uruchom: pytest tests/test_rule_engine.py -v
"""

import pytest
from app.services.agent_a_gemini import (
    _clean_contradictory_data_after_override,
    _compute_classification,
    _compute_confidence_ceiling,
    _compute_manufacturing_quality,
    _meczowa_label,
    _sync_decision_matrix_d_with_manufacturing_quality,
    run_rule_engine,
)


# ---------------------------------------------------------------------------
# _clean_contradictory_data_after_override
# ---------------------------------------------------------------------------

class TestCleanContradictoryData:
    """Testy czyszczenia sprzecznych danych po hard override."""

    def _base_report(self):
        return {
            "missing_data": [],
            "notes": {},
        }

    def test_removes_sku_phrase(self):
        report = self._base_report()
        report["missing_data"] = ["Brak kodu SKU", "Zdjęcie frontu"]
        _clean_contradictory_data_after_override(report)
        assert report["missing_data"] == ["Zdjęcie frontu"]

    def test_removes_kod_produktu_phrase(self):
        report = self._base_report()
        report["missing_data"] = ["Brak kod produktu na metce"]
        _clean_contradictory_data_after_override(report)
        assert report["missing_data"] == []

    def test_removes_internal_tag_inflections(self):
        """Wszystkie odmiany 'metka wewnętrzna' powinny być usunięte."""
        phrases = [
            "Brak metki wewnętrznej",
            "Nie widać metką wewnętrzną",
            "Brak metek wewnętrznych",
            "Jakość wewnętrznej metki nieznana",
        ]
        for phrase in phrases:
            report = self._base_report()
            report["missing_data"] = [phrase, "Zdjęcie tył"]
            _clean_contradictory_data_after_override(report)
            assert len(report["missing_data"]) == 1, (
                f"Oczekiwano usunięcia frazy: {phrase!r}"
            )
            assert report["missing_data"] == ["Zdjęcie tył"]

    def test_keeps_unrelated_missing_data(self):
        report = self._base_report()
        report["missing_data"] = ["Zdjęcie tył", "Zdjęcie nadruku", "Bliskie zdjęcie naszywki"]
        _clean_contradictory_data_after_override(report)
        assert len(report["missing_data"]) == 3

    def test_clears_contradictory_mode_note(self):
        report = self._base_report()
        report["notes"] = {"mode_note": "Wymagana weryfikacja SKU kodu produktu."}
        _clean_contradictory_data_after_override(report)
        assert report["notes"]["mode_note"] == ""

    def test_keeps_unrelated_mode_note(self):
        report = self._base_report()
        report["notes"] = {"mode_note": "Tryb expert — pełna analiza."}
        _clean_contradictory_data_after_override(report)
        assert report["notes"]["mode_note"] == "Tryb expert — pełna analiza."

    def test_handles_none_missing_data(self):
        report = {"missing_data": None, "notes": {}}
        _clean_contradictory_data_after_override(report)
        assert report["missing_data"] == []

    def test_handles_none_notes(self):
        report = {"missing_data": [], "notes": None}
        _clean_contradictory_data_after_override(report)
        # Nie rzuca wyjątku — notes=None jest obsługiwany gracefully

    def test_handles_missing_keys(self):
        report = {}
        _clean_contradictory_data_after_override(report)
        assert report["missing_data"] == []

    def test_case_insensitive_matching(self):
        report = self._base_report()
        report["missing_data"] = ["BRAK SKU", "Kod SKU nie odczytany"]
        _clean_contradictory_data_after_override(report)
        assert report["missing_data"] == []


# ---------------------------------------------------------------------------
# _compute_manufacturing_quality
# ---------------------------------------------------------------------------

class TestComputeManufacturingQuality:
    """Testy obliczania jakości produkcji z manufacturing_signals."""

    def _ms(self, **kwargs):
        """Buduje manufacturing_signals z domyślnymi wartościami 'unclear'."""
        fields = [
            "seams_quality", "construction_quality", "panel_join_quality",
            "finish_quality", "material_quality", "neck_tag_quality",
            "print_application_quality",
        ]
        result = {f: "unclear" for f in fields}
        result.update(kwargs)
        return result

    def test_empty_signals_returns_fallback(self):
        assert _compute_manufacturing_quality({}) == "fallback"

    def test_none_signals_returns_fallback(self):
        assert _compute_manufacturing_quality(None) == "fallback"

    def test_all_unclear_returns_fallback(self):
        ms = self._ms()
        assert _compute_manufacturing_quality(ms) == "fallback"

    def test_two_poor_returns_poor(self):
        ms = self._ms(seams_quality="poor", construction_quality="poor")
        assert _compute_manufacturing_quality(ms) == "poor"

    def test_three_poor_returns_poor(self):
        ms = self._ms(seams_quality="poor", construction_quality="poor", finish_quality="poor")
        assert _compute_manufacturing_quality(ms) == "poor"

    def test_one_poor_no_good_returns_mixed(self):
        ms = self._ms(seams_quality="poor")
        assert _compute_manufacturing_quality(ms) == "mixed"

    def test_six_good_no_poor_returns_good(self):
        ms = self._ms(
            seams_quality="good", construction_quality="good",
            panel_join_quality="good", finish_quality="good",
            material_quality="good", neck_tag_quality="good",
        )
        assert _compute_manufacturing_quality(ms) == "good"

    def test_all_good_returns_good(self):
        ms = {
            "seams_quality": "good", "construction_quality": "good",
            "panel_join_quality": "good", "finish_quality": "good",
            "material_quality": "good", "neck_tag_quality": "good",
            "print_application_quality": "good",
        }
        assert _compute_manufacturing_quality(ms) == "good"

    def test_mix_good_and_poor_returns_mixed(self):
        ms = self._ms(seams_quality="good", construction_quality="poor")
        assert _compute_manufacturing_quality(ms) == "mixed"


# ---------------------------------------------------------------------------
# _sync_decision_matrix_d_with_manufacturing_quality
# ---------------------------------------------------------------------------

class TestSyncDecisionMatrixDWithManufacturingQuality:
    """Regresja na realny incydent 2026-09-05 (case 50f59024, Pedri/FC Barcelona,
    zgłoszone przez Dominika): manufacturing_signals pokazywał seams_quality=
    "poor" i finish_quality="poor", a mimo to decision_matrix wiersz D (waga 6,
    najcięższe kryterium) był GREEN z tekstem "Jakość szwów i konstrukcji na
    zdjęciach wydaje się wysoka" — bezpośrednia sprzeczność w tym samym
    raporcie, mimo że prompt_a.txt (linia ~435-437) już wcześniej instruował
    Agenta A, żeby D nie było GREEN przy tanim/niestarannym wykonaniu. Agent A
    pisze oba pola (manufacturing_signals i decision_matrix[D].observation)
    częściowo niezależnie w jednym JSON-ie i nie zawsze stosuje własną regułę
    — stąd deterministyczna synchronizacja po stronie backendu, ten sam
    wzorzec co _sku_dm_map dla wierszy A/B."""

    def _dm_with_d_green(self):
        return [
            {"code": "A", "status": "GREEN", "observation": ""},
            {"code": "C", "status": "GREEN", "observation": ""},
            {"code": "D", "status": "GREEN", "observation": "Jakość szwów wydaje się wysoka."},
            {"code": "E", "status": "GREEN", "observation": ""},
        ]

    def test_poor_seams_and_finish_downgrades_green_d_to_red(self):
        dm = self._dm_with_d_green()
        ms = {"seams_quality": "poor", "finish_quality": "poor", "construction_quality": "good"}
        _sync_decision_matrix_d_with_manufacturing_quality(dm, ms, "poor")
        d = next(r for r in dm if r["code"] == "D")
        assert d["status"] == "RED"
        assert "szwy" in d["observation"]
        assert "wykończenie" in d["observation"]

    def test_mentions_only_the_actually_poor_fields(self):
        dm = self._dm_with_d_green()
        ms = {"seams_quality": "poor", "finish_quality": "good", "construction_quality": "good"}
        _sync_decision_matrix_d_with_manufacturing_quality(dm, ms, "mixed")
        d = next(r for r in dm if r["code"] == "D")
        assert "szwy" in d["observation"]
        assert "wykończenie" not in d["observation"]

    def test_single_poor_field_with_mixed_aggregate_downgrades_to_yellow(self):
        dm = self._dm_with_d_green()
        ms = {"seams_quality": "poor", "finish_quality": "good", "construction_quality": "good"}
        _sync_decision_matrix_d_with_manufacturing_quality(dm, ms, "mixed")
        d = next(r for r in dm if r["code"] == "D")
        assert d["status"] == "YELLOW"

    def test_good_manufacturing_quality_leaves_green_d_untouched(self):
        dm = self._dm_with_d_green()
        original_observation = dm[2]["observation"]
        ms = {"seams_quality": "good", "finish_quality": "good", "construction_quality": "good"}
        _sync_decision_matrix_d_with_manufacturing_quality(dm, ms, "good")
        d = next(r for r in dm if r["code"] == "D")
        assert d["status"] == "GREEN"
        assert d["observation"] == original_observation

    def test_does_not_touch_d_already_correctly_yellow_or_red(self):
        """Nie nadpisuje, jeśli Agent A już sam poprawnie ustawił YELLOW/RED —
        synchronizacja łata tylko przypadek GREEN-mimo-poor."""
        dm = [{"code": "D", "status": "RED", "observation": "Agent's own correct text."}]
        ms = {"seams_quality": "poor", "finish_quality": "poor"}
        _sync_decision_matrix_d_with_manufacturing_quality(dm, ms, "poor")
        assert dm[0]["observation"] == "Agent's own correct text."

    def test_missing_d_row_does_not_crash(self):
        dm = [{"code": "A", "status": "GREEN", "observation": ""}]
        ms = {"seams_quality": "poor", "finish_quality": "poor"}
        _sync_decision_matrix_d_with_manufacturing_quality(dm, ms, "poor")  # no exception

    def test_poor_aggregate_without_any_d_relevant_poor_field_leaves_untouched(self):
        """mfg_quality może być 'poor' z powodu pól spoza zakresu D (np.
        neck_tag_quality/print_application_quality) — nie zgaduj wtedy na
        podstawie samego agregatu, tylko sprawdzaj konkretne pola D."""
        dm = self._dm_with_d_green()
        ms = {"neck_tag_quality": "poor", "print_application_quality": "poor",
              "seams_quality": "good", "finish_quality": "good", "construction_quality": "good"}
        _sync_decision_matrix_d_with_manufacturing_quality(dm, ms, "poor")
        d = next(r for r in dm if r["code"] == "D")
        assert d["status"] == "GREEN"

    def test_none_manufacturing_signals_does_not_crash(self):
        """Code review: brak defensywnego guard'a wewnątrz funkcji mógłby
        crashować, gdyby kiedyś wywołana bez wzorca `... or {}` u callera."""
        dm = self._dm_with_d_green()
        _sync_decision_matrix_d_with_manufacturing_quality(dm, None, "poor")
        d = next(r for r in dm if r["code"] == "D")
        assert d["status"] == "GREEN"  # brak danych = brak podstaw do obniżenia

    def test_aged_authentic_skips_downgrade_even_with_poor_field(self):
        """Code review (2026-09-05): dla realnie starych/vintage koszulek z
        naturalnym zużyciem Agent A może słusznie zostawić D=GREEN mimo
        jednego 'poor' pola — bez wyjątku ta synchronizacja odtworzyłaby
        dokładnie ten sam błąd w drugą stronę (poprawny werdykt, zła tabela)."""
        dm = self._dm_with_d_green()
        original_observation = dm[2]["observation"]
        ms = {"seams_quality": "poor", "finish_quality": "poor", "construction_quality": "good"}
        _sync_decision_matrix_d_with_manufacturing_quality(dm, ms, "poor", is_aged_authentic=True)
        d = next(r for r in dm if r["code"] == "D")
        assert d["status"] == "GREEN"
        assert d["observation"] == original_observation


# ---------------------------------------------------------------------------
# _compute_confidence_ceiling
# ---------------------------------------------------------------------------

class TestComputeConfidenceCeiling:
    """Testy obliczania ceiling pewności."""

    def _call(self, sku_effect="neutral", dm_statuses=None, missing_data=None,
              verdict_category="oryginalna_sklepowa", coverage_result=None,
              reasoning_limits=None, construction_flagged=False, mfg_quality="good"):
        return _compute_confidence_ceiling(
            sku_effect=sku_effect,
            dm_statuses=dm_statuses or {"C": "GREEN", "D": "GREEN"},
            missing_data=missing_data or [],
            verdict_category=verdict_category,
            coverage_result=coverage_result or {"detected_views": {"identity_tag": True}},
            reasoning_limits=reasoning_limits or [],
            construction_flagged=construction_flagged,
            mfg_quality=mfg_quality,
        )

    def test_sku_hard_conflict_authentic_returns_medium(self):
        level, _ = self._call(sku_effect="hard_conflict", verdict_category="oryginalna_sklepowa")
        assert level == "medium"

    def test_sku_hard_conflict_edycja_limitowana_returns_low(self):
        level, _ = self._call(sku_effect="hard_conflict", verdict_category="edycja_limitowana")
        assert level == "low"

    def test_no_identity_tag_authentic_returns_medium(self):
        coverage = {"detected_views": {"identity_tag": False}}
        level, _ = self._call(coverage_result=coverage, verdict_category="oryginalna_sklepowa")
        assert level == "medium"

    def test_many_reasoning_limits_without_sku_support_returns_medium(self):
        level, _ = self._call(
            reasoning_limits=["a", "b", "c", "d"],
            sku_effect="neutral",
        )
        assert level == "medium"

    def test_many_reasoning_limits_with_sku_support_returns_high(self):
        """Potwierdzone SKU przebija reasoning_limits."""
        level, _ = self._call(
            reasoning_limits=["a", "b", "c", "d"],
            sku_effect="supports_authentic",
        )
        assert level == "high"

    def test_three_unknown_dm_returns_low(self):
        dm = {"C": "UNKNOWN", "D": "UNKNOWN", "A": "UNKNOWN", "E": "GREEN"}
        level, _ = self._call(dm_statuses=dm)
        assert level == "low"

    def test_meczowa_poor_mfg_returns_medium(self):
        level, _ = self._call(verdict_category="meczowa", mfg_quality="poor")
        assert level == "medium"

    def test_meczowa_good_mfg_returns_high(self):
        level, _ = self._call(verdict_category="meczowa", mfg_quality="good")
        assert level == "high"

    def test_meczowa_mixed_mfg_with_sku_support_returns_medium(self):
        """Regresja 2026-09-04 (case b545a7d4, PSG/Dembélé): potwierdzone SKU
        nie odblokowuje już unrestricted high dla mixed mfg — SKU to sam
        tekst/kod, można go przepisać z prawdziwego ogłoszenia, więc nie
        powinien samodzielnie ratować niejednoznacznej jakości fizycznej do
        pełnej pewności (95%). Przed fixem: mixed traktowane identycznie jak
        good, gdy SKU pasuje. Teraz: mixed zawsze capuje na medium, tak jak
        poor — spójna hierarchia poor ≤ mixed ≤ good."""
        level, _ = self._call(
            verdict_category="meczowa",
            mfg_quality="mixed",
            sku_effect="supports_authentic",
        )
        assert level == "medium"

    def test_meczowa_mixed_mfg_ceiling_reduced_returns_medium(self):
        # ceiling_reduced trafia w ogólną regułę is_authentic_like przed blokiem meczowej
        level, _ = self._call(
            verdict_category="meczowa",
            mfg_quality="mixed",
            sku_effect="ceiling_reduced",
        )
        assert level == "medium"

    def test_default_authentic_good_returns_high(self):
        level, _ = self._call()
        assert level == "high"


# ---------------------------------------------------------------------------
# _compute_classification
# ---------------------------------------------------------------------------

class TestComputeClassification:
    """Regresja 2026-09-04 (case b545a7d4, PSG/Dembélé): mixed manufacturing +
    SKU potwierdzone/autoryzowane dawało 'likely_match_issue' zamiast
    'mixed_signals' — ta sama poprawka co w _compute_confidence_ceiling
    (SKU sam w sobie to tekst/kod, można go przepisać z prawdziwego
    ogłoszenia, więc nie powinien samodzielnie zamieniać niejednoznacznej
    jakości fizycznej w etykietę widoczną w UI jako 'prawdopodobnie meczowa').
    `classification` steruje badge'em "mixed signals" we frontendzie
    (case-report-view.tsx: isMixedSignals)."""

    def _call(self, verdict_category="meczowa", dm_statuses=None, pcc=None,
               sku_verification=None, construction_flagged=False, mfg_quality="fallback"):
        return _compute_classification(
            verdict_category=verdict_category,
            dm_statuses=dm_statuses or {"C": "GREEN", "D": "GREEN", "E": "GREEN"},
            pcc=pcc or {},
            sku_verification=sku_verification or {},
            construction_flagged=construction_flagged,
            mfg_quality=mfg_quality,
        )

    def test_meczowa_mixed_mfg_with_found_authorized_sku_returns_mixed_signals(self):
        result = self._call(
            mfg_quality="mixed",
            sku_verification={"status": "found_authorized"},
        )
        assert result == "mixed_signals"

    def test_meczowa_mixed_mfg_with_found_official_sku_returns_mixed_signals(self):
        result = self._call(
            mfg_quality="mixed",
            sku_verification={"status": "found_official"},
        )
        assert result == "mixed_signals"

    def test_meczowa_mixed_mfg_without_sku_returns_mixed_signals(self):
        result = self._call(
            mfg_quality="mixed",
            sku_verification={"status": "not_found"},
        )
        assert result == "mixed_signals"

    def test_meczowa_good_mfg_with_no_conflicts_returns_likely_match_issue(self):
        """Regresja pilnująca, że fix nie zepsuł dobrej ścieżki — good mfg
        nadal daje pewny wynik, tylko mixed został zawężony."""
        result = self._call(mfg_quality="good", sku_verification={"status": "found_authorized"})
        assert result == "likely_match_issue"

    def test_fake_verdict_always_likely_fake_regardless_of_mfg(self):
        result = self._call(verdict_category="podrobka", mfg_quality="good")
        assert result == "likely_fake"

    def test_meczowa_poor_mfg_with_confirmed_sku_returns_likely_match_issue(self):
        """Gałąź 'poor' NIE była zmieniana tym fixem — pilnuje, że pozostała
        nietknięta (osobna, celowo węższa lista statusów SKU niż 'mixed')."""
        result = self._call(
            mfg_quality="poor",
            sku_verification={"status": "confirmed"},
        )
        assert result == "likely_match_issue"

    def test_meczowa_poor_mfg_with_found_authorized_sku_returns_mixed_signals(self):
        """'poor' celowo NIE traktuje found_authorized jak confirmed/found_official
        (inaczej niż 'mixed') — pre-existing, poza zakresem tego fixu, ale
        warte zapisania jako świadomej regresji."""
        result = self._call(
            mfg_quality="poor",
            sku_verification={"status": "found_authorized"},
        )
        assert result == "mixed_signals"

    def test_meczowa_poor_mfg_without_sku_returns_mixed_signals(self):
        result = self._call(
            mfg_quality="poor",
            sku_verification={"status": "not_found"},
        )
        assert result == "mixed_signals"

    def test_meczowa_fallback_with_visual_conflict_returns_mixed_signals(self):
        result = self._call(
            mfg_quality="fallback",
            dm_statuses={"C": "GREEN", "D": "RED", "E": "GREEN"},
        )
        assert result == "mixed_signals"

    def test_meczowa_fallback_clean_returns_likely_match_issue(self):
        result = self._call(mfg_quality="fallback")
        assert result == "likely_match_issue"

    def test_oryginalna_sklepowa_clean_returns_likely_authentic_retail(self):
        result = self._call(verdict_category="oryginalna_sklepowa", mfg_quality="mixed")
        assert result == "likely_authentic_retail"

    def test_oryginalna_sklepowa_with_visual_conflict_returns_mixed_signals(self):
        result = self._call(
            verdict_category="oryginalna_sklepowa",
            dm_statuses={"C": "RED", "D": "GREEN", "E": "GREEN"},
        )
        assert result == "mixed_signals"

    def test_oryginalna_sklepowa_pcc_inconsistent_returns_later_modifications(self):
        result = self._call(
            verdict_category="oryginalna_sklepowa",
            dm_statuses={"C": "GREEN", "D": "GREEN", "E": "YELLOW"},
            pcc={"status": "inconsistent"},
        )
        assert result == "likely_authentic_base_with_later_modifications"

    def test_catch_all_verdict_clean_returns_inconclusive(self):
        result = self._call(verdict_category="oficjalna_replika")
        assert result == "inconclusive"

    def test_catch_all_verdict_with_visual_conflict_returns_mixed_signals(self):
        result = self._call(
            verdict_category="treningowa_custom",
            dm_statuses={"C": "GREEN", "D": "RED", "E": "GREEN"},
        )
        assert result == "mixed_signals"


# ---------------------------------------------------------------------------
# run_rule_engine — hard override paths
# ---------------------------------------------------------------------------

def _minimal_report(verdict_category="oryginalna_sklepowa", confidence=75):
    """Minimalne poprawne report_data dla run_rule_engine."""
    return {
        "verdict": {
            "verdict_category": verdict_category,
            "label": "Oryginalna sklepowa",
            "confidence_percent": confidence,
            "confidence_level": "wysoki",
            "summary": "Test",
        },
        "decision_matrix": [
            {"code": "A", "status": "GREEN", "observation": ""},
            {"code": "B", "status": "GREEN", "observation": ""},
            {"code": "C", "status": "GREEN", "observation": ""},
            {"code": "D", "status": "GREEN", "observation": ""},
            {"code": "E", "status": "GREEN", "observation": ""},
        ],
        "probabilities": {
            "oryginalna_sklepowa": 75,
            "meczowa": 5,
            "oficjalna_replika": 10,
            "edycja_limitowana": 5,
            "treningowa_custom": 3,
            "podrobka": 2,
        },
        "missing_data": [],
        "reasoning_limits": [],
        "sku_verification": {"status": "uncertain"},
        "player_club_consistency": {"status": "consistent", "reason": ""},
        "personalization_assessment": {},
        "manufacturing_signals": {
            "seams_quality": "good",
            "construction_quality": "good",
            "panel_join_quality": "good",
            "finish_quality": "good",
            "material_quality": "good",
            "neck_tag_quality": "good",
            "print_application_quality": "good",
        },
        "key_evidence": ["Dobra jakość szycia"],
    }


class TestRunRuleEngineSKUMismatch:
    """SKU mismatch → natychmiastowy override na podróbkę."""

    def _report_with_sku_status(self, status):
        report = _minimal_report()
        report["sku_verification"] = {"status": status, "reason": "SKU test reason."}
        return report

    def test_found_unofficial_triggers_override(self):
        report = self._report_with_sku_status("found_unofficial")
        result = run_rule_engine(report)
        assert result["classification"] == "likely_fake"
        assert report["verdict"]["verdict_category"] == "podrobka"
        assert report["verdict"]["confidence_percent"] == 90
        assert "sku_mismatch_hard_reject" in result["hard_flags"]

    def test_format_invalid_triggers_override(self):
        report = self._report_with_sku_status("format_invalid")
        result = run_rule_engine(report)
        assert result["classification"] == "likely_fake"
        assert report["verdict"]["verdict_category"] == "podrobka"

    def test_mismatch_triggers_override(self):
        report = self._report_with_sku_status("mismatch")
        result = run_rule_engine(report)
        assert report["verdict"]["verdict_category"] == "podrobka"
        assert report["probabilities"]["podrobka"] == 90
        assert report["probabilities"]["meczowa"] == 0

    def test_found_official_does_not_trigger_override(self):
        report = self._report_with_sku_status("found_official")
        run_rule_engine(report)
        assert report["verdict"]["verdict_category"] == "oryginalna_sklepowa"

    def test_found_authorized_does_not_trigger_override(self):
        """found_authorized NIE może triggerować hard override."""
        report = self._report_with_sku_status("found_authorized")
        run_rule_engine(report)
        assert report["verdict"]["verdict_category"] == "oryginalna_sklepowa"

    def test_sku_mismatch_cleans_contradictory_missing_data(self):
        report = self._report_with_sku_status("found_unofficial")
        report["missing_data"] = ["Brak kodu SKU", "Zdjęcie tył"]
        run_rule_engine(report)
        # "Brak kodu SKU" powinno zostać usunięte
        assert not any("sku" in m.lower() for m in report["missing_data"])

    def test_sku_mismatch_updates_decision_matrix_rows_a_b(self):
        report = self._report_with_sku_status("mismatch")
        run_rule_engine(report)
        dm = {row["code"]: row for row in report["decision_matrix"]}
        assert dm["A"]["status"] == "RED"
        assert dm["B"]["status"] == "RED"

    def test_format_invalid_does_not_claim_assigned_to_another_jersey(self):
        """Regresja na realny bug zgłoszony przez Dominika (koszulka Manchester
        United na produkcji): dla format_invalid confidence_explanation twierdziło
        'Kod SKU przypisany do innej koszulki' — nieprawda, ustalono tylko że
        format jest niepoprawny, nie że kod znaleziono przy innym produkcie."""
        report = self._report_with_sku_status("format_invalid")
        run_rule_engine(report)
        explanation = report["verdict"]["confidence_explanation"].lower()
        assert "przypisany do innej koszulki" not in explanation
        assert "nieprawidłowy format" in explanation

    def test_mismatch_without_found_product_uses_real_reason_not_generic_text(self):
        """'mismatch' (i legacy 'invalid') nie występują w aktualnym schemacie
        sku_agent.py (found_official|found_authorized|found_unofficial|not_found|
        format_invalid) — to defensywna, dziś nieosiągalna gałąź. Ale musi
        zostać obsłużona tak samo jak w _build_override_key_evidence: czytać
        realny sku_verification.reason, nie hardkodowany generyczny tekst,
        żeby nie wprowadzić tej samej klasy niespójności confidence_explanation
        vs key_evidence dla tej ścieżki."""
        report = self._report_with_sku_status("mismatch")
        run_rule_engine(report)
        explanation = report["verdict"]["confidence_explanation"].lower()
        # _report_with_sku_status ustawia reason="SKU test reason."
        assert "sku test reason" in explanation

    def test_confidence_explanation_matches_key_evidence_reason(self):
        """Sekcja 'Poziom pewności' (confidence_explanation) i 'Kluczowe sygnały'
        (key_evidence[0], budowane przez _build_override_key_evidence) muszą
        opisywać ten sam powód override'u — to dokładnie ta klasa buga, która
        wywołała ten fix (dwie sekcje tego samego raportu mówiące co innego)."""
        for status in ["found_unofficial", "format_invalid", "mismatch"]:
            report = self._report_with_sku_status(status)
            run_rule_engine(report)
            explanation = report["verdict"]["confidence_explanation"].lower()
            evidence = report["key_evidence"][0].lower()
            # Oba teksty muszą się zgadzać co do statusu — jeśli jeden mówi
            # "nieprawidłowy format", drugi nie może mówić "przypisany do innej".
            assert ("nieprawidłowy format" in explanation) == ("nieprawidłowy format" in evidence), status
            assert ("nieautoryzowanymi" in explanation) == ("nieautoryzowanymi" in evidence), status

    def test_sku_mismatch_regenerates_contradictory_summary(self):
        """Regresja na realny bug: Agent A pisze summary pod swoją oryginalną
        sugestię (np. 'wysokie prawdopodobieństwo oryginalności'), a hard override
        zmienia verdict_category na podróbkę bez dotykania summary — user widział
        raport sprzeczny sam ze sobą (tekst broniący autentyczności obok werdyktu
        Podróbka 90%)."""
        report = self._report_with_sku_status("format_invalid")
        report["verdict"]["summary"] = (
            "Cechy fizyczne są zgodne z autentyczną wersją sklepową. Całkowita "
            "ocena wskazuje na wysokie prawdopodobieństwo oryginalności."
        )
        run_rule_engine(report)
        summary = report["verdict"]["summary"].lower()
        assert "prawdopodobieństwo oryginalności" not in summary
        assert "podróbk" in summary


class TestRunRuleEngineSkuMismatchSurvivesPccCorrection:
    """Regresja end-to-end 2026-09-05 (case 58646ec2, Lewandowski/Barcelona,
    złota koszulka): agent_suggestion Agenta A było "podrobka" (własny summary:
    "rozstrzygający dowód... podróbką"), ale sku_verification zwróciło
    "found_authorized" zamiast "mismatch" mimo że własny `reason` mówił wprost
    o innym modelu/sezonie niż deklarowany — co pozwoliło PCC-correction
    override'owi (podrobka→meczowa, gdy PCC spójne i C/D zielone) przebić
    słuszny werdykt Agenta A na "Meczowa 75%". Fix w sku_agent.py (nowy status
    "mismatch") + już istniejący, przetestowany hard-reject sprawiają, że z
    poprawnym statusem "mismatch" ta sytuacja się nie powtarza — replay
    dokładnego kształtu przez cały run_rule_engine()."""

    def _report_lewandowski_shaped(self):
        report = _minimal_report(verdict_category="podrobka", confidence=60)
        report["verdict"]["summary"] = (
            "Ta fundamentalna niezgodność metek jest rozstrzygającym dowodem "
            "na to, że produkt jest podróbką."
        )
        report["verdict"]["agent_suggestion"] = "podrobka"
        report["sku_verification"] = {
            "status": "mismatch",
            "reason": (
                "Kod SKU CV7891-428 znaleziony u autoryzowanego sprzedawcy, ale "
                "identyfikuje domową koszulkę 2021/22, a nie wyjazdową 2022/2023 "
                "jak podano w zapytaniu."
            ),
        }
        # PCC spójne + C/D zielone — dokładnie warunki, które wcześniej
        # pozwalały PCC-correction override'owi przebić werdykt.
        report["player_club_consistency"] = {"status": "consistent", "reason": ""}
        report["probabilities"] = {
            "oryginalna_sklepowa": 15, "meczowa": 75, "oficjalna_replika": 5,
            "podrobka": 5, "edycja_limitowana": 0, "treningowa_custom": 0,
        }
        return report

    def test_verdict_stays_podrobka_not_overridden_to_meczowa(self):
        report = self._report_lewandowski_shaped()
        run_rule_engine(report)
        assert report["verdict"]["verdict_category"] == "podrobka"

    def test_hard_reject_flag_present(self):
        report = self._report_lewandowski_shaped()
        result = run_rule_engine(report)
        assert "sku_mismatch_hard_reject" in result["hard_flags"]

    def test_probabilities_reflect_podrobka_not_meczowa(self):
        report = self._report_lewandowski_shaped()
        run_rule_engine(report)
        assert report["probabilities"]["podrobka"] > report["probabilities"]["meczowa"]


class TestRunRuleEngineNoSKUPoorMfg:
    """Brak SKU + poor manufacturing → override na podróbkę."""

    def _report_poor_mfg_no_sku(self):
        report = _minimal_report()
        report["sku_verification"] = {"status": "not_found"}
        report["manufacturing_signals"] = {
            "seams_quality": "poor",
            "construction_quality": "poor",
            "panel_join_quality": "unclear",
            "finish_quality": "unclear",
            "material_quality": "unclear",
            "neck_tag_quality": "unclear",
            "print_application_quality": "unclear",
        }
        return report

    def test_no_sku_poor_mfg_overrides_authentic(self):
        report = self._report_poor_mfg_no_sku()
        result = run_rule_engine(report)
        assert result["classification"] == "likely_fake"
        assert report["verdict"]["verdict_category"] == "podrobka"
        assert report["verdict"]["confidence_percent"] == 80
        assert "no_sku_plus_poor_manufacturing" in result["hard_flags"]

    def test_no_sku_poor_mfg_does_not_leave_row_b_green(self):
        """QA blocker (2026-09-05): ta ścieżka nadpisuje tylko wiersz A ('Brak
        kodu SKU przy słabej jakości...'), nigdy nie dotykała wiersza B —
        _minimal_report()'s default ma B=GREEN, więc bez apply_global_invariant
        na TEJ ścieżce (osobny wczesny return, nie ten na końcu funkcji) raport
        kończył z "Podróbka" obok zielonego wiersza B — dokładnie ta sama klasa
        buga co case 15364d60, tylko przez inną ścieżkę override'u. Repro 1:1
        ze zgłoszenia QA."""
        report = self._report_poor_mfg_no_sku()
        assert report["decision_matrix"][1]["status"] == "GREEN"  # sanity: B startuje zielone
        run_rule_engine(report)
        row_b = next(r for r in report["decision_matrix"] if r["code"] == "B")
        assert row_b["status"] != "GREEN"

    def test_no_sku_poor_mfg_regenerates_contradictory_summary(self):
        report = self._report_poor_mfg_no_sku()
        report["verdict"]["summary"] = "Wysokie prawdopodobieństwo oryginalności."
        run_rule_engine(report)
        summary = report["verdict"]["summary"].lower()
        assert "prawdopodobieństwo oryginalności" not in summary
        assert "podróbk" in summary

    def test_no_sku_poor_mfg_cleans_missing_data(self):
        report = self._report_poor_mfg_no_sku()
        report["missing_data"] = ["Brak kodu SKU", "Brak metki wewnętrznej", "Zdjęcie tył"]
        run_rule_engine(report)
        assert "Zdjęcie tył" in report["missing_data"]
        assert all("sku" not in m.lower() and "metki" not in m.lower() for m in report["missing_data"])

    def test_fallback_mfg_does_not_override(self):
        """mfg_quality=fallback (wszystkie unclear) NIE może triggerować override."""
        report = _minimal_report()
        report["sku_verification"] = {"status": "not_found"}
        report["manufacturing_signals"] = {f: "unclear" for f in [
            "seams_quality", "construction_quality", "panel_join_quality",
            "finish_quality", "material_quality", "neck_tag_quality",
            "print_application_quality",
        ]}
        run_rule_engine(report)
        assert report["verdict"]["verdict_category"] == "oryginalna_sklepowa"

    def test_found_authorized_prevents_no_sku_poor_mfg_override(self):
        """found_authorized traktowane jak sygnał autentyczności — blokuje override."""
        report = self._report_poor_mfg_no_sku()
        report["sku_verification"] = {"status": "found_authorized"}
        run_rule_engine(report)
        assert report["verdict"]["verdict_category"] == "oryginalna_sklepowa"

    def test_no_override_for_podrobka_verdict(self):
        """Koszulka z verdict=podrobka nie powinna być ponownie overridowana."""
        report = _minimal_report(verdict_category="podrobka")
        report["sku_verification"] = {"status": "not_found"}
        report["manufacturing_signals"] = {
            "seams_quality": "poor",
            "construction_quality": "poor",
            "panel_join_quality": "unclear",
            "finish_quality": "unclear",
            "material_quality": "unclear",
            "neck_tag_quality": "unclear",
            "print_application_quality": "unclear",
        }
        # Nie rzuca — verdict_category już "podrobka", nie jest w _AUTHENTIC_LIKE
        run_rule_engine(report)
        assert report["verdict"]["verdict_category"] == "podrobka"


class TestRunRuleEnginePedriShapedIllegibleSkuPoorMfg:
    """Regresja end-to-end 2026-09-05 (case 50f59024, Pedri/FC Barcelona):
    Dominik zgłosił, że werdykt "Podróbka" jest słuszny (widoczne złe szwy i
    wykończenie), ale tabela decyzyjna w PDF-ie temu przeczyła — kryterium D
    było GREEN z tekstem "jakość szwów... wysoka" mimo seams_quality=poor,
    finish_quality=poor. Ten test replayuje pełny kształt tego przypadku
    (agent_suggestion="meczowa", subject.sku="nieczytelne" już znormalizowane
    do sku_verification.status="not_applicable" przez wcześniejszy fix w
    sku_agent.py) przez cały run_rule_engine() i potwierdza DWIE rzeczy razem:
    1. werdykt poprawnie ląduje na "podrobka" (przez no_sku_plus_poor_manufacturing,
       NIE przez błędny format_invalid — ten fix nie zepsuł słusznego werdyktu),
    2. wiersz D w decision_matrix przestaje przeczyć własnym danym."""

    def _report_pedri_shaped(self):
        report = _minimal_report(verdict_category="meczowa", confidence=90)
        report["verdict"]["agent_suggestion"] = "meczowa"
        report["decision_matrix"] = [
            {"code": "A", "status": "GREEN", "observation": "", "weight": 3},
            {"code": "B", "status": "GREEN", "observation": "", "weight": 2},
            {"code": "C", "status": "GREEN", "observation": "Termotransfer, precyzyjnie wykonane.", "weight": 5},
            {
                "code": "D", "status": "GREEN", "weight": 6,
                "observation": (
                    "Materiał posiada zaawansowaną strukturę dzianiny i oznaczenia "
                    "'DRI-FIT ADV'. Jakość szwów i konstrukcji na zdjęciach wydaje "
                    "się wysoka."
                ),
            },
            {"code": "E", "status": "GREEN", "observation": "", "weight": 4},
        ]
        report["sku_verification"] = {"status": "not_applicable"}
        report["manufacturing_signals"] = {
            "seams_quality": "poor",
            "construction_quality": "good",
            "panel_join_quality": "good",
            "finish_quality": "poor",
            "material_quality": "good",
            "neck_tag_quality": "good",
            "print_application_quality": "good",
        }
        return report

    def test_verdict_correctly_lands_on_podrobka(self):
        report = self._report_pedri_shaped()
        run_rule_engine(report)
        assert report["verdict"]["verdict_category"] == "podrobka"

    def test_via_correct_no_sku_poor_mfg_path_not_sku_format(self):
        report = self._report_pedri_shaped()
        result = run_rule_engine(report)
        assert "no_sku_plus_poor_manufacturing" in result["hard_flags"]

    def test_decision_matrix_d_no_longer_contradicts_manufacturing_signals(self):
        report = self._report_pedri_shaped()
        run_rule_engine(report)
        d = next(r for r in report["decision_matrix"] if r["code"] == "D")
        assert d["status"] != "GREEN"
        assert "wysoka" not in d["observation"].lower() or "słab" in d["observation"].lower()


class TestRunRuleEngineProbabilitiesSync:
    """Synchronizacja probabilities z verdict_category."""

    def test_sku_mismatch_zeroes_non_podrobka_probs(self):
        report = _minimal_report()
        report["sku_verification"] = {"status": "mismatch", "reason": "test"}
        run_rule_engine(report)
        assert report["probabilities"]["meczowa"] == 0
        assert report["probabilities"]["oryginalna_sklepowa"] == 4
        assert report["probabilities"]["podrobka"] == 90

    def test_no_sku_poor_mfg_sets_podrobka_80(self):
        report = _minimal_report()
        report["sku_verification"] = {"status": "not_found"}
        report["manufacturing_signals"] = {
            "seams_quality": "poor",
            "construction_quality": "poor",
            "panel_join_quality": "unclear",
            "finish_quality": "unclear",
            "material_quality": "unclear",
            "neck_tag_quality": "unclear",
            "print_application_quality": "unclear",
        }
        run_rule_engine(report)
        assert report["probabilities"]["podrobka"] == 80
        assert report["probabilities"]["meczowa"] == 0


class TestMeczowaLabel:
    """Regresja na case 20260903-238a181d (PSG/Messi): etykieta "Meczowa /
    Player Issue" była zawsze taka sama niezależnie od meczowa_detail.status,
    więc user nie mógł odróżnić taniej wersji player issue od potwierdzonej,
    dużo cenniejszej match_worn. Etykieta ma teraz odzwierciedlać substatus."""

    def test_player_issue(self):
        report = {"meczowa_detail": {"status": "player_issue"}}
        assert _meczowa_label(report) == "Meczowa — Player Issue"

    def test_match_worn(self):
        report = {"meczowa_detail": {"status": "match_worn"}}
        label = _meczowa_label(report)
        assert label.startswith("Meczowa —")
        assert "potwierdzona" in label

    def test_match_prepared(self):
        report = {"meczowa_detail": {"status": "match_prepared"}}
        label = _meczowa_label(report)
        assert label.startswith("Meczowa —")
        assert "przygotowana" in label

    def test_unknown_status_falls_back_to_generic_label(self):
        report = {"meczowa_detail": {"status": "unknown"}}
        assert _meczowa_label(report) == "Meczowa / Player Issue"

    def test_missing_meczowa_detail_falls_back_to_generic_label(self):
        """Legacy raporty sprzed tego pola / override bez własnego meczowa_detail."""
        assert _meczowa_label({}) == "Meczowa / Player Issue"

    def test_missing_status_key_falls_back_to_generic_label(self):
        assert _meczowa_label({"meczowa_detail": {}}) == "Meczowa / Player Issue"


class TestRunRuleEngineMeczowaLabelIntegration:
    """run_rule_engine musi faktycznie zsynchronizować label z meczowa_detail.status
    po wszystkich overrides, nie tylko _meczowa_label() w izolacji."""

    def test_player_issue_gets_substatus_label(self):
        report = _minimal_report(verdict_category="meczowa", confidence=70)
        report["meczowa_detail"] = {"status": "player_issue"}
        run_rule_engine(report)
        assert report["verdict"]["verdict_category"] == "meczowa"
        assert report["verdict"]["label"] == "Meczowa — Player Issue"

    def test_match_worn_gets_substatus_label(self):
        report = _minimal_report(verdict_category="meczowa", confidence=70)
        report["meczowa_detail"] = {"status": "match_worn"}
        run_rule_engine(report)
        assert report["verdict"]["label"] == "Meczowa — potwierdzona (koszulka noszona na boisku)"

    def test_no_meczowa_detail_keeps_generic_label(self):
        """_minimal_report() nie ustawia meczowa_detail — musi zostać stara,
        generyczna etykieta (backward-compat dla starszych/uboższych raportów)."""
        report = _minimal_report(verdict_category="meczowa", confidence=70)
        run_rule_engine(report)
        assert report["verdict"]["label"] == "Meczowa / Player Issue"

    def test_non_meczowa_category_unaffected(self):
        report = _minimal_report(verdict_category="oryginalna_sklepowa", confidence=80)
        run_rule_engine(report)
        assert report["verdict"]["label"] == "Oryginalna (Sklepowa)"


class TestRunRuleEngineMeczowaPoorMfgOverride:
    """meczowa + słaba jakość fizyczna wykonania → override na podróbkę."""

    def _report_meczowa_poor_mfg(self):
        report = _minimal_report(verdict_category="meczowa", confidence=70)
        report["sku_verification"] = {"status": "not_found"}
        report["manufacturing_signals"] = {
            "seams_quality": "poor", "construction_quality": "poor",
            "panel_join_quality": "unclear", "finish_quality": "unclear",
            "material_quality": "unclear", "neck_tag_quality": "unclear",
            "print_application_quality": "unclear",
        }
        return report

    def test_triggers_override_to_podrobka(self):
        report = self._report_meczowa_poor_mfg()
        run_rule_engine(report)
        assert report["verdict"]["verdict_category"] == "podrobka"

    def test_regenerates_contradictory_summary(self):
        report = self._report_meczowa_poor_mfg()
        report["verdict"]["summary"] = "Baza koszulki autentyczna, to egzemplarz meczowy."
        run_rule_engine(report)
        summary = report["verdict"]["summary"].lower()
        assert "egzemplarz meczowy" not in summary
        assert "podróbk" in summary


class TestRunRuleEngineMixedMfgConfidenceCap:
    """Regresja end-to-end 2026-09-04 (case b545a7d4, PSG/Dembélé): mixed mfg
    + SKU found_authorized nie może już dawać 95% pewności dla meczowej —
    replay dokładnego kształtu tego realnego przypadku przez cały
    run_rule_engine(), nie tylko przez pure functions (_compute_confidence_ceiling
    zwraca właściwy ceiling, ale to run_rule_engine faktycznie zapisuje
    final confidence_percent do report_data, przez _CEILING_MAP + _round_to_10
    + resync prawdopodobieństw — to właśnie ten pełny łańcuch tu weryfikujemy)."""

    def _report_dembele_shaped(self):
        report = _minimal_report(verdict_category="meczowa", confidence=95)
        report["verdict"]["confidence_level"] = "bardzo_wysoki"
        report["sku_verification"] = {"status": "found_authorized"}
        report["manufacturing_signals"] = {
            "seams_quality": "mixed", "construction_quality": "good",
            "panel_join_quality": "mixed", "finish_quality": "mixed",
            "material_quality": "good", "neck_tag_quality": "good",
            "print_application_quality": "good",
        }
        report["probabilities"] = {
            "meczowa": 95, "oryginalna_sklepowa": 3, "oficjalna_replika": 1,
            "edycja_limitowana": 1, "treningowa_custom": 0, "podrobka": 0,
        }
        return report

    def test_confidence_percent_capped_at_60(self):
        report = self._report_dembele_shaped()
        run_rule_engine(report)
        assert report["verdict"]["confidence_percent"] == 60

    def test_confidence_level_downgraded_to_sredni(self):
        report = self._report_dembele_shaped()
        run_rule_engine(report)
        assert report["verdict"]["confidence_level"] == "sredni"

    def test_verdict_category_stays_meczowa_not_flipped(self):
        """Cap na confidence NIE jest tym samym co override werdyktu — to
        wciąż 'meczowa', tylko z niższą pewnością, nie 'podrobka'."""
        report = self._report_dembele_shaped()
        run_rule_engine(report)
        assert report["verdict"]["verdict_category"] == "meczowa"

    def test_classification_is_mixed_signals(self):
        report = self._report_dembele_shaped()
        result = run_rule_engine(report)
        assert result["classification"] == "mixed_signals"


class TestRunRuleEngineNeckTagPoorOverride:
    """Słaba jakość wewnętrznej metki (neck tag) + brak SKU → override na podróbkę."""

    def _report_neck_tag_poor(self):
        report = _minimal_report(verdict_category="oryginalna_sklepowa", confidence=70)
        report["sku_verification"] = {"status": "not_found"}
        report["manufacturing_signals"] = {
            "seams_quality": "good", "construction_quality": "good",
            "panel_join_quality": "good", "finish_quality": "good",
            "material_quality": "good", "neck_tag_quality": "poor",
            "print_application_quality": "good",
        }
        return report

    def test_triggers_override_to_podrobka(self):
        report = self._report_neck_tag_poor()
        run_rule_engine(report)
        assert report["verdict"]["verdict_category"] == "podrobka"

    def test_regenerates_contradictory_summary(self):
        report = self._report_neck_tag_poor()
        report["verdict"]["summary"] = "Wysokie prawdopodobieństwo oryginalności."
        run_rule_engine(report)
        summary = report["verdict"]["summary"].lower()
        assert "prawdopodobieństwo oryginalności" not in summary
        assert "podróbk" in summary


class TestRunRuleEnginePrintApplicationPoorOverride:
    """Słaba jakość aplikacji nadruków + brak SKU → override na podróbkę."""

    def _report_print_app_poor(self):
        report = _minimal_report(verdict_category="oryginalna_sklepowa", confidence=70)
        report["sku_verification"] = {"status": "not_found"}
        report["manufacturing_signals"] = {
            "seams_quality": "good", "construction_quality": "good",
            "panel_join_quality": "good", "finish_quality": "good",
            "material_quality": "good", "neck_tag_quality": "good",
            "print_application_quality": "poor",
        }
        return report

    def test_triggers_override_to_podrobka(self):
        report = self._report_print_app_poor()
        run_rule_engine(report)
        assert report["verdict"]["verdict_category"] == "podrobka"

    def test_regenerates_contradictory_summary(self):
        report = self._report_print_app_poor()
        report["verdict"]["summary"] = "Wysokie prawdopodobieństwo oryginalności."
        run_rule_engine(report)
        summary = report["verdict"]["summary"].lower()
        assert "prawdopodobieństwo oryginalności" not in summary
        assert "podróbk" in summary


class TestRunRuleEngineGlobalInvariantEndToEnd:
    """Regresja end-to-end 2026-09-05 (case 15364d60, złota koszulka
    Lewandowskiego): Agent A's OWN werdykt było już "podrobka" (nie przez
    żaden hard-override w run_rule_engine — sku_verification.status=
    "found_authorized" nie wyzwala SKU hard-reject), więc żadna z istniejących
    ścieżek override'u w run_rule_engine nie dotykała wierszy A/B. Bez
    globalnego niezmiennika (apply_global_invariant, wołanego na samym końcu
    run_rule_engine) wiersz A/B mógłby zostać zielony obok werdyktu "Podróbka",
    dokładnie jak w prawdziwym raporcie."""

    def _report_verdict_already_podrobka_green_sku_rows(self):
        report = _minimal_report(verdict_category="podrobka", confidence=95)
        report["verdict"]["agent_suggestion"] = "podrobka"
        # Symuluje sytuację, w której wcześniejszy etap (merge w cases.py) z
        # jakiegoś powodu nie odpalił / nie dotknął wierszy A/B — pozostają
        # zielone, tak jak w realnym case 15364d60 przed fixem.
        report["decision_matrix"][0]["status"] = "GREEN"  # A
        report["decision_matrix"][1]["status"] = "GREEN"  # B
        # D=RED, tak jak w prawdziwym case 15364d60 ("produkt 'fantasy'") — to
        # WAŻNE dla tego testu: musi blokować niepowiązany PCC-correction
        # override (podrobka→meczowa, wymaga D=GREEN), żeby test faktycznie
        # sprawdzał NOWY globalny niezmiennik, a nie przypadkiem trafiał w
        # zupełnie inną, już istniejącą ścieżkę.
        report["decision_matrix"][3]["status"] = "RED"  # D
        report["sku_verification"] = {"status": "found_authorized", "reason": ""}
        return report

    def test_green_row_a_downgraded_when_final_verdict_is_podrobka(self):
        report = self._report_verdict_already_podrobka_green_sku_rows()
        run_rule_engine(report)
        row_a = next(r for r in report["decision_matrix"] if r["code"] == "A")
        assert row_a["status"] != "GREEN"

    def test_green_row_b_downgraded_when_final_verdict_is_podrobka(self):
        report = self._report_verdict_already_podrobka_green_sku_rows()
        run_rule_engine(report)
        row_b = next(r for r in report["decision_matrix"] if r["code"] == "B")
        assert row_b["status"] != "GREEN"

    def test_verdict_category_itself_unaffected_by_invariant(self):
        """Niezmiennik dotyka tylko wierszy macierzy, nigdy werdyktu."""
        report = self._report_verdict_already_podrobka_green_sku_rows()
        run_rule_engine(report)
        assert report["verdict"]["verdict_category"] == "podrobka"

    def test_authentic_verdict_keeps_green_sku_rows(self):
        """Kontrola negatywna: dla poprawnie autentycznego werdyktu zielone
        wiersze A/B zostają zielone — niezmiennik nie jest nadgorliwy."""
        report = _minimal_report(verdict_category="oryginalna_sklepowa", confidence=90)
        report["decision_matrix"][0]["status"] = "GREEN"
        report["decision_matrix"][1]["status"] = "GREEN"
        report["sku_verification"] = {"status": "found_authorized", "reason": ""}
        run_rule_engine(report)
        row_a = next(r for r in report["decision_matrix"] if r["code"] == "A")
        row_b = next(r for r in report["decision_matrix"] if r["code"] == "B")
        assert row_a["status"] == "GREEN"
        assert row_b["status"] == "GREEN"


# ---------------------------------------------------------------------------
# Testy _compress_to_phrase i _shorten_signal (IG fake-case endpoint)
# ---------------------------------------------------------------------------

class TestCompressToPhrase:
    """Testy funkcji _compress_to_phrase — kompresja do maks. 6 słów."""

    def _f(self, text, max_words=6):
        from app.routes.cases import _compress_to_phrase
        return _compress_to_phrase(text, max_words)

    def test_short_phrase_unchanged(self):
        assert self._f("Kod SKU nieprawidłowy") == "Kod SKU nieprawidłowy"

    def test_already_six_words_unchanged(self):
        text = "Nadruk sponsora jest mocno spękany dziś"
        assert self._f(text) == text

    def test_removes_co_do_tail(self):
        result = self._f("Jego wykonanie budzi wątpliwości co do jakości")
        assert "co do" not in result
        assert len(result.split()) <= 6

    def test_removes_co_sugeruje_tail(self):
        result = self._f("Naszywka z herbem ma grube krawędzie, co sugeruje niską jakość")
        assert "co sugeruje" not in result
        assert len(result.split()) <= 6

    def test_removes_dla_tego_tail(self):
        result = self._f("Kod SKU na metce jest nieprawidłowy dla tego modelu koszulki")
        assert len(result.split()) <= 6

    def test_removes_copula_when_needed(self):
        result = self._f("Nadruk na koszulce jest nierówny i wyblakły dla produktu")
        assert len(result.split()) <= 6

    def test_hard_limit_fallback(self):
        result = self._f("jeden dwa trzy cztery pięć sześć siedem osiem dziewięć dziesięć")
        assert len(result.split()) <= 6

    def test_result_not_empty(self):
        assert self._f("Kod SKU jest nieprawidłowy dla modelu koszulki sezonowej") != ""


class TestShortenSignalIG:
    """Testy _shorten_signal — pełny pipeline dla IG fake-case."""

    def _s(self, text):
        from app.routes.cases import _shorten_signal
        return _shorten_signal(text)

    def test_one_word_fragment_filtered(self):
        assert self._s("Logotypy") == ""

    def test_two_word_fragment_filtered(self):
        assert self._s("Nierówne szwy") == ""

    def test_meta_uniemozliwia_odczytanie_filtered(self):
        assert self._s("Jej stan uniemożliwia odczytanie kodu produktu") == ""

    def test_meta_uniemozliwia_weryfikacje_filtered(self):
        assert self._s("Metka uniemożliwia weryfikację kodu SKU") == ""

    def test_meta_brak_kluczowych_zdj_filtered(self):
        assert self._s("Brak kluczowych zdjęć wewnętrznych metek") == ""

    def test_meta_brak_zblizen_filtered(self):
        assert self._s("Brak zbliżeń na szwy i wykończenia krawędzi") == ""

    def test_pro_auth_filtered(self):
        assert self._s("Jakość wykonania wydaje się być na wysokim poziomie") == ""

    def test_sku_nieprawidlowy_passes(self):
        result = self._s("Kod SKU na metce papierowej jest nieprawidłowy dla tego modelu koszulki")
        assert result
        assert len(result.split()) <= 6

    def test_ale_takes_negative_conclusion(self):
        result = self._s("Metka jest widoczna, ale jej treść jest nieczytelna")
        assert result
        assert "nieczytelna" in result.lower()
        assert len(result.split()) <= 6

    def test_jednak_takes_negative_conclusion(self):
        result = self._s("Herb jest haftowany, jednak wykonanie budzi wątpliwości")
        assert result
        assert "wątpliwości" in result.lower()

    def test_max_6_words(self):
        result = self._s("Naszywka z herbem ma grube, niedokładne krawędzie, co sugeruje niską jakość wykonania w porównaniu do produktów autentycznych")
        assert result
        assert len(result.split()) <= 6

    def test_no_trailing_period(self):
        result = self._s("Kod SKU na metce jest nieprawidłowy dla modelu.")
        assert result
        assert not result.endswith('.')

    def test_capitalized(self):
        result = self._s("kod sku na metce jest nieprawidłowy dla modelu")
        if result:
            assert result[0].isupper()
