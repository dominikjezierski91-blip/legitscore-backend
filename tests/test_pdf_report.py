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


class TestSanitizeReportDataSkuPlaceholder:
    """Regresja na realny incydent (2026-08-24, re-analiza Manchester United,
    case 2f3b8c13): Agent A nie odczytał SKU i zwrócił subject.sku="nieustalone"
    (placeholder, nie realny kod) — ale _sanitize_report_data traktowało ten
    napis jak prawdziwy, "widoczny" kod: generowało fałszywe ostrzeżenie o
    niepoprawnym formacie Nike dla dosłownego słowa "nieustalone" i podmieniało
    missing_data na mylące "Kod produktu widoczny na jock tagu..."."""

    def _report(self, sku: str, missing_data=None):
        return {
            "subject": {"sku": sku, "brand": "Nike"},
            "sku_verification": {"status": "not_applicable"},
            "missing_data": missing_data or ["Brak widocznego kodu SKU na zdjęciu."],
            "probabilities": {},
            "recommendations": [],
            "notes": {},
        }

    def test_placeholder_sku_does_not_generate_format_warning(self):
        sanitized = _sanitize_report_data(self._report("nieustalone"))
        assert sanitized["sku_format_warning"] is None

    def test_placeholder_sku_missing_data_not_rewritten_as_visible(self):
        sanitized = _sanitize_report_data(self._report("nieustalone"))
        assert sanitized["missing_data"] == ["Brak widocznego kodu produktu."]
        assert not any("widoczny na jock tagu" in m for m in sanitized["missing_data"])

    def test_real_invalid_sku_still_triggers_format_warning(self):
        """Nie zepsuj oryginalnej funkcji — prawdziwy, tylko źle sformatowany
        kod nadal powinien generować ostrzeżenie."""
        sanitized = _sanitize_report_data(self._report("09914738"))
        assert sanitized["sku_format_warning"] is not None
        assert "09914738" in sanitized["sku_format_warning"]

    def test_real_sku_still_rewrites_missing_data_as_visible(self):
        sanitized = _sanitize_report_data(self._report("09914738"))
        assert any("widoczny na jock tagu" in m for m in sanitized["missing_data"])


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
