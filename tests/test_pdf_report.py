"""
Testy grupowania rozkładu prawdopodobieństwa w raporcie PDF (basic/expert).

Regresja na realny feedback (2026-08-24): raport pokazywał fałszywą precyzję —
1%/3%/4% dla kategorii, które i tak nie miały znaczenia obok werdyktu z wysoką
pewnością (podróbka 90%). Kategorie poniżej progu są teraz zbierane w jedną
pozycję "Pozostałe".
"""
from app.services.pdf_report import _group_probabilities_for_display, _sanitize_report_data


class TestGroupProbabilitiesForDisplay:
    def test_keeps_categories_at_or_above_threshold(self):
        probs = {
            "oryginalna_sklepowa": 4,
            "meczowa": 0,
            "oficjalna_replika": 3,
            "podrobka": 90,
            "edycja_limitowana": 1,
            "treningowa_custom": 2,
        }
        result = _group_probabilities_for_display(probs)
        labels = [label for label, _ in result]
        assert "Podróbka" in labels
        assert "Oryginalna (sklepowa)" not in labels
        assert "Oficjalna replika" not in labels

    def test_collects_remainder_into_pozostale(self):
        probs = {
            "oryginalna_sklepowa": 4,
            "meczowa": 0,
            "oficjalna_replika": 3,
            "podrobka": 90,
            "edycja_limitowana": 1,
            "treningowa_custom": 2,
        }
        result = _group_probabilities_for_display(probs)
        assert dict(result)["Pozostałe"] == 10  # 4+0+3+1+2

    def test_no_pozostale_row_when_nothing_below_threshold(self):
        probs = {
            "oryginalna_sklepowa": 60,
            "meczowa": 0,
            "oficjalna_replika": 0,
            "podrobka": 40,
            "edycja_limitowana": 0,
            "treningowa_custom": 0,
        }
        result = _group_probabilities_for_display(probs)
        assert "Pozostałe" not in dict(result)

    def test_empty_probabilities_returns_empty_list(self):
        assert _group_probabilities_for_display({}) == []
        assert _group_probabilities_for_display(None) == []

    def test_percentages_sum_preserved(self):
        probs = {
            "oryginalna_sklepowa": 4,
            "meczowa": 0,
            "oficjalna_replika": 3,
            "podrobka": 90,
            "edycja_limitowana": 1,
            "treningowa_custom": 2,
        }
        result = _group_probabilities_for_display(probs)
        assert sum(pct for _, pct in result) == 100


class TestSanitizeReportDataAddsGroupedProbabilities:
    def test_sanitize_adds_grouped_probabilities_field(self):
        report_data = {
            "subject": {},
            "probabilities": {
                "oryginalna_sklepowa": 4, "meczowa": 0, "oficjalna_replika": 3,
                "podrobka": 90, "edycja_limitowana": 1, "treningowa_custom": 2,
            },
            "missing_data": [],
            "recommendations": [],
            "notes": {},
        }
        sanitized = _sanitize_report_data(report_data)
        assert "grouped_probabilities" in sanitized
        assert dict(sanitized["grouped_probabilities"])["Podróbka"] == 90
