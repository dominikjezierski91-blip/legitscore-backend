"""
Testy jednostkowe Rule Engine i pomocniczych funkcji.
Uruchom: pytest tests/test_rule_engine.py -v
"""

import pytest
from app.services.agent_a_gemini import (
    _clean_contradictory_data_after_override,
    _compute_confidence_ceiling,
    _compute_manufacturing_quality,
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

    def test_meczowa_mixed_mfg_with_sku_support_returns_high(self):
        level, _ = self._call(
            verdict_category="meczowa",
            mfg_quality="mixed",
            sku_effect="supports_authentic",
        )
        assert level == "high"

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
        assert "Zdjęcie tył" in report["missing_data"]

    def test_sku_mismatch_updates_decision_matrix_rows_a_b(self):
        report = self._report_with_sku_status("mismatch")
        run_rule_engine(report)
        dm = {row["code"]: row for row in report["decision_matrix"]}
        assert dm["A"]["status"] == "RED"
        assert dm["B"]["status"] == "RED"


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
