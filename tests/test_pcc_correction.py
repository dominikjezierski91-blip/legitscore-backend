"""
Testy _apply_pcc_consistent_corrections (app/routes/cases.py) — regresja na realny
incydent (PSG Kvaratskhelia, 2026-08-19): raport jednocześnie pokazywał "OK" w
decision_matrix (squad check potwierdzony) i "brak możliwości weryfikacji" w
key_evidence/reasoning_limits/missing_data dla tej samej rzeczy, bo korekta po PCC
czyściła tylko część miejsc, gdzie ta niepewność mogła zostać zapisana.

Druga klasa testów (TestConfidenceCeilingInteraction) dokumentuje i sprawdza wprost
to, co reviewer oznaczył jako HIGH w pierwszym review tej poprawki: usunięcie wpisów
z reasoning_limits/missing_data ma realny wpływ na confidence_ceiling/data_completeness
w run_rule_engine (progi liczą długość tych list), nie tylko na tekst raportu.
"""
from app.routes.cases import _apply_pcc_consistent_corrections
from app.services.agent_a_gemini import _compute_confidence_ceiling, _compute_data_completeness


def _sample_report_data() -> dict:
    """Kształt zbliżony do realnego incydentu — decision_matrix row F już OK
    (bo to ustawiane wcześniej w run_decision, przed wywołaniem tej funkcji),
    ale reszta pól wciąż niesie starą niepewność o składzie drużyny."""
    return {
        "subject": {"player_name": "Kvaratskhelia"},
        "decision_matrix": [
            {"code": "E", "status": "YELLOW", "impact": "ogranicza_pewnosc",
             "observation": "Personalizacja niezweryfikowana."},
            {"code": "F", "status": "GREEN", "impact": "neutralne",
             "observation": "Squad check potwierdzony przez PCC."},
        ],
        "key_evidence": [
            {"type": "positive", "code": "A", "text": "Kod SKU zgodny z modelem."},
            {"type": "negative", "code": "F",
             "text": "Brak możliwości weryfikacji, czy zawodnik Kvaratskhelia faktycznie "
                     "grał w PSG w sezonie 2025/26, co pozostawia niewielki margines niepewności."},
        ],
        "reasoning_limits": [
            "Brak informacji o składzie drużyny na sezon 2025/26 — F (Squad check) = UNKNOWN.",
            "Brak zbliżeń na szwy — D oceniane z ogólnych zdjęć.",
        ],
        "missing_data": [
            "Informacje o składzie PSG na sezon 2025/26 w celu weryfikacji personalizacji.",
            "Zdjęcia w wysokiej rozdzielczości pokazujące detale szwów.",
        ],
    }


class TestApplyPccConsistentCorrections:
    def test_removes_stale_squad_uncertainty_key_evidence(self):
        report_data = _sample_report_data()
        result = _apply_pcc_consistent_corrections(report_data, "PCC potwierdza zgodność.")
        codes = [ev["code"] for ev in result["key_evidence"]]
        assert "F" not in codes
        assert "A" in codes  # niepowiązany, pozytywny wpis zostaje

    def test_removes_stale_squad_uncertainty_reasoning_limits(self):
        report_data = _sample_report_data()
        result = _apply_pcc_consistent_corrections(report_data, "PCC potwierdza zgodność.")
        joined = " ".join(result["reasoning_limits"]).lower()
        assert "skład" not in joined
        # niepowiązane ograniczenie (o szwach) zostaje
        assert any("szw" in rl.lower() for rl in result["reasoning_limits"])

    def test_removes_stale_squad_uncertainty_missing_data(self):
        report_data = _sample_report_data()
        result = _apply_pcc_consistent_corrections(report_data, "PCC potwierdza zgodność.")
        joined = " ".join(result["missing_data"]).lower()
        assert "składzie" not in joined
        assert any("szw" in md.lower() for md in result["missing_data"])

    def test_corrects_row_e_to_green(self):
        report_data = _sample_report_data()
        result = _apply_pcc_consistent_corrections(report_data, "PCC potwierdza zgodność.")
        row_e = next(r for r in result["decision_matrix"] if r["code"] == "E")
        assert row_e["status"] == "GREEN"
        assert row_e["impact"] == "neutralne"

    def test_unrelated_negative_evidence_survives(self):
        """Filtr nie powinien być tak szeroki, żeby zjadał niepowiązane, wciąż
        aktualne czerwone flagi (np. o materiale) — tylko squad/personalizacja."""
        report_data = _sample_report_data()
        report_data["key_evidence"].append(
            {"type": "negative", "code": "D", "text": "Nieprawidłowy krój kołnierza względem wersji oficjalnej."}
        )
        result = _apply_pcc_consistent_corrections(report_data, "PCC potwierdza zgodność.")
        codes = [ev["code"] for ev in result["key_evidence"]]
        assert "D" in codes


class TestConfidenceCeilingInteraction:
    """Dokumentuje realny, zamierzony efekt uboczny: usunięcie rozstrzygniętej
    niepewności z reasoning_limits/missing_data może podnieść confidence_ceiling —
    to intencjonalne (patrz komentarz w _apply_pcc_consistent_corrections), nie
    przypadkowa regresja. Test pokazuje granicę progu z run_rule_engine wprost."""

    def test_four_reasoning_limits_caps_ceiling_when_sku_not_confirmed(self):
        # Próg len(reasoning_limits) >= 4 obniża ceiling TYLKO gdy SKU nie jest
        # "supports_authentic" (agent_a_gemini.py: _compute_confidence_ceiling).
        ceiling, reason = _compute_confidence_ceiling(
            sku_effect="none",
            dm_statuses={"C": "GREEN", "D": "GREEN"},
            missing_data=[],
            verdict_category="oryginalna_sklepowa",
            coverage_result={"detected_views": {"identity_tag": True}},
            reasoning_limits=["a", "b", "c", "d"],
            mfg_quality="good",
        )
        assert ceiling == "medium"
        assert "ograniczeń" in reason

    def test_three_reasoning_limits_does_not_cap_ceiling(self):
        # Ten sam scenariusz, ale po usunięciu JEDNEGO rozstrzygniętego wpisu
        # (dokładnie to, co robi _apply_pcc_consistent_corrections) — próg
        # przestaje działać, ceiling nie jest już sztucznie ograniczony.
        ceiling, reason = _compute_confidence_ceiling(
            sku_effect="none",
            dm_statuses={"C": "GREEN", "D": "GREEN"},
            missing_data=[],
            verdict_category="oryginalna_sklepowa",
            coverage_result={"detected_views": {"identity_tag": True}},
            reasoning_limits=["a", "b", "c"],
            mfg_quality="good",
        )
        assert ceiling != "medium" or "ograniczeń" not in reason

    def test_confirmed_sku_bypasses_reasoning_limits_threshold_entirely(self):
        # Realny incydent: sku_effect="supports_authentic" (found_official) —
        # próg z reasoning_limits w ogóle się nie liczy, więc dla TEGO konkretnego
        # case'a usunięcie wpisu nie zmieniało ceiling przez tę gałąź (inne gałęzie
        # mogą nadal zależeć od missing_data — patrz test niżej).
        ceiling, reason = _compute_confidence_ceiling(
            sku_effect="supports_authentic",
            dm_statuses={"C": "GREEN", "D": "GREEN"},
            missing_data=[],
            verdict_category="oryginalna_sklepowa",
            coverage_result={"detected_views": {"identity_tag": True}},
            reasoning_limits=["a", "b", "c", "d", "e"],
            mfg_quality="good",
        )
        assert "ograniczeń" not in reason

    def test_missing_data_below_three_changes_data_completeness(self):
        # _compute_data_completeness: len(missing_data) == 0 wymagane dla "high";
        # usunięcie jednego z dwóch wpisów (2→1) samo w sobie nie odblokuje "high"
        # (bo próg to == 0, nie < 3), ale demonstruje że funkcja faktycznie liczy
        # długość tej listy — dokumentuje interakcję, którą flagował review.
        completeness_two = _compute_data_completeness(
            dm_statuses={"A": "GREEN", "B": "GREEN", "C": "GREEN", "D": "GREEN", "E": "GREEN"},
            coverage_result={"detected_views": {"identity_tag": True}},
            missing_data=["a", "b"],
        )
        completeness_zero = _compute_data_completeness(
            dm_statuses={"A": "GREEN", "B": "GREEN", "C": "GREEN", "D": "GREEN", "E": "GREEN"},
            coverage_result={"detected_views": {"identity_tag": True}},
            missing_data=[],
        )
        assert completeness_two == "medium"
        assert completeness_zero == "high"
