"""
Testy _clean_stale_sku_key_evidence / _is_stale_sku_limitation (app/routes/cases.py)
— regresja na realny incydent (Bayern Monachium / Ribéry, 2026-09-02, raport
20260902-6d29c75e): sku_verification.status="found_authorized" i decision_matrix
poprawnie mówiły "Kod SKU potwierdzony u autoryzowanego sprzedawcy", ale
key_evidence nadal zawierał bullet napisany przez Agenta A PRZED weryfikacją SKU:
"Brak możliwości niezależnej weryfikacji kodu SKU w zewnętrznej bazie danych,
co jest standardowym ograniczeniem analizy." — sprzeczność widoczna w tym samym
raporcie, w dwóch różnych sekcjach.
"""
from app.routes.cases import (
    _clean_stale_sku_key_evidence,
    _is_stale_sku_limitation,
    _sku_status_confirms_verification,
)


class TestIsStaleSkuLimitation:
    def test_matches_real_incident_text(self):
        item = {
            "type": "limitation",
            "text": (
                "Brak możliwości niezależnej weryfikacji kodu SKU w zewnętrznej "
                "bazie danych, co jest standardowym ograniczeniem analizy."
            ),
        }
        assert _is_stale_sku_limitation(item) is True

    def test_ignores_non_limitation_type(self):
        item = {"type": "positive", "text": "Brak możliwości niezależnej weryfikacji kodu SKU."}
        assert _is_stale_sku_limitation(item) is False

    def test_ignores_limitation_unrelated_to_sku(self):
        item = {"type": "limitation", "text": "Brak zdjęcia metki wewnętrznej uniemożliwia pełną ocenę."}
        assert _is_stale_sku_limitation(item) is False

    def test_ignores_limitation_mentioning_sku_without_verification_wording(self):
        item = {"type": "limitation", "text": "Kod SKU jest częściowo zasłonięty na zdjęciu."}
        assert _is_stale_sku_limitation(item) is False

    def test_case_insensitive(self):
        item = {"type": "limitation", "text": "BRAK MOŻLIWOŚCI NIEZALEŻNEJ WERYFIKACJI KODU SKU."}
        assert _is_stale_sku_limitation(item) is True

    def test_non_dict_item_does_not_crash(self):
        assert _is_stale_sku_limitation("not a dict") is False
        assert _is_stale_sku_limitation(None) is False


class TestCleanStaleSkuKeyEvidence:
    def test_real_incident_shape(self):
        """Kształt 1:1 z raportu 20260902-6d29c75e."""
        key_evidence = [
            {"type": "positive", "text": "Starannie wykonany, gęsty haft herbu klubu i logo producenta."},
            {"type": "positive", "text": "Obecność wewnętrznej metki z kodem produktu (S14294)."},
            {"type": "positive", "text": "Wysoka jakość materiału z technologią Climacool."},
            {
                "type": "limitation",
                "text": (
                    "Brak możliwości niezależnej weryfikacji kodu SKU w zewnętrznej "
                    "bazie danych, co jest standardowym ograniczeniem analizy."
                ),
            },
        ]
        result = _clean_stale_sku_key_evidence(key_evidence)
        assert len(result) == 3
        assert all(item["type"] == "positive" for item in result)

    def test_keeps_unrelated_limitations(self):
        key_evidence = [
            {"type": "limitation", "text": "Brak zdjęcia wnętrza kołnierza uniemożliwia pełną ocenę."},
        ]
        assert _clean_stale_sku_key_evidence(key_evidence) == key_evidence

    def test_none_input_returns_empty_list(self):
        assert _clean_stale_sku_key_evidence(None) == []

    def test_empty_list_returns_empty_list(self):
        assert _clean_stale_sku_key_evidence([]) == []


class TestSkuStatusConfirmsVerification:
    """Regresja na bug złapany przez review+QA: pierwsza wersja fixu reużywała
    `status in _sku_dm_map` jako guard w run-decision, ale ta mapa zawiera też
    "not_found" — status, dla którego weryfikacja NIC nie ustaliła, więc bullet
    "brak możliwości weryfikacji SKU" jest wciąż prawdziwy i NIE powinien być
    czyszczony. Usunięcie go dla not_found odtwarzałoby ten sam błąd (sprzeczny/
    mylący raport) w drugą stronę."""

    def test_not_found_does_not_confirm_verification(self):
        assert _sku_status_confirms_verification("not_found") is False

    def test_uncertain_does_not_confirm_verification(self):
        assert _sku_status_confirms_verification("uncertain") is False

    def test_not_applicable_does_not_confirm_verification(self):
        assert _sku_status_confirms_verification("not_applicable") is False

    def test_found_official_confirms_verification(self):
        assert _sku_status_confirms_verification("found_official") is True

    def test_found_authorized_confirms_verification(self):
        assert _sku_status_confirms_verification("found_authorized") is True

    def test_found_unofficial_confirms_verification(self):
        assert _sku_status_confirms_verification("found_unofficial") is True

    def test_format_invalid_confirms_verification(self):
        assert _sku_status_confirms_verification("format_invalid") is True
