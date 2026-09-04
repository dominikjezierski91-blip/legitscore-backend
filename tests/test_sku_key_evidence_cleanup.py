"""
Testy _clean_stale_sku_key_evidence / _is_stale_sku_limitation (app/routes/cases.py)
— regresja na dwa realne incydenty:

1. 2026-09-02, raport 20260902-6d29c75e (Bayern Monachium / Ribéry):
   sku_verification.status="found_authorized" i decision_matrix poprawnie
   mówiły "Kod SKU potwierdzony u autoryzowanego sprzedawcy", ale key_evidence
   nadal zawierał bullet napisany przez Agenta A PRZED weryfikacją SKU:
   "Brak możliwości niezależnej weryfikacji kodu SKU w zewnętrznej bazie
   danych, co jest standardowym ograniczeniem analizy."

2. 2026-09-04, raport 20260904-9c78243b (PSG / Dembélé): ten sam pierwszy fix
   nigdy nie zadziałał, bo wymagał item["type"]=="limitation" — a key_evidence
   Agenta A bywa też w kształcie {text, status} bez pola "type" w ogóle (jak w
   tym raporcie). sku_verification="found_authorized", decision_matrix wiersz A
   mówił "Kod SKU potwierdzony u autoryzowanego sprzedawcy", a key_evidence
   nadal: "Format kodu SKU (II2732-417) jest nietypowy dla standardowych
   produktów Nike, co budzi dodatkowe wątpliwości." Stąd fix: nie wymagamy już
   pola "type", i rozszerzone frazy wątpliwości (nie tylko "weryfikac").
"""
from app.routes.cases import (
    _clean_stale_sku_key_evidence,
    _is_stale_sku_limitation,
    _sku_status_positively_confirmed,
)


class TestIsStaleSkuLimitation:
    def test_matches_real_incident_text_with_type_field(self):
        item = {
            "type": "limitation",
            "text": (
                "Brak możliwości niezależnej weryfikacji kodu SKU w zewnętrznej "
                "bazie danych, co jest standardowym ograniczeniem analizy."
            ),
        }
        assert _is_stale_sku_limitation(item) is True

    def test_matches_same_text_without_type_field(self):
        """Kluczowa regresja: Agent A nie zawsze pisze pole 'type' — funkcja
        nie może na nim polegać, inaczej znowu staje się martwym kodem."""
        item = {
            "text": (
                "Brak możliwości niezależnej weryfikacji kodu SKU w zewnętrznej "
                "bazie danych, co jest standardowym ograniczeniem analizy."
            ),
        }
        assert _is_stale_sku_limitation(item) is True

    def test_matches_dembele_incident_text(self):
        """Raport 20260904-9c78243b — dokładny tekst, kształt {text, status}."""
        item = {
            "text": "Format kodu SKU (II2732-417) jest nietypowy dla standardowych produktów Nike, co budzi dodatkowe wątpliwości.",
            "status": "YELLOW",
        }
        assert _is_stale_sku_limitation(item) is True

    def test_ignores_positive_type_without_doubt_wording(self):
        item = {"type": "positive", "text": "Kod SKU zgodny z autentycznym produktem."}
        assert _is_stale_sku_limitation(item) is False

    def test_ignores_limitation_unrelated_to_sku(self):
        item = {"type": "limitation", "text": "Brak zdjęcia metki wewnętrznej uniemożliwia pełną ocenę."}
        assert _is_stale_sku_limitation(item) is False

    def test_ignores_limitation_mentioning_sku_without_doubt_wording(self):
        item = {"type": "limitation", "text": "Kod SKU jest częściowo zasłonięty na zdjęciu."}
        assert _is_stale_sku_limitation(item) is False

    def test_case_insensitive(self):
        item = {"text": "BRAK MOŻLIWOŚCI NIEZALEŻNEJ WERYFIKACJI KODU SKU."}
        assert _is_stale_sku_limitation(item) is True

    def test_non_dict_item_does_not_crash(self):
        assert _is_stale_sku_limitation("not a dict") is False
        assert _is_stale_sku_limitation(None) is False

    def test_ignores_skutecznosc_substring_false_positive(self):
        """Regresja złapana przez QA: bare `"sku" in text` łapał też
        "skuteczność" — niepowiązany bullet o zabezpieczeniach antypodróbkowych
        znikałby za każdym razem, gdy SKU pozytywnie się zweryfikuje."""
        item = {
            "type": "limitation",
            "text": (
                "Niska skuteczność zabezpieczeń antypodróbkowych budzi poważne "
                "wątpliwości co do autentyczności hologramu."
            ),
        }
        assert _is_stale_sku_limitation(item) is False

    def test_still_matches_sku_next_to_punctuation(self):
        """Word-boundary fix nie może złamać dopasowania realnych fraz typu
        "kodu SKU (II2732-417)" — SKU otoczone nawiasem/spacją, nie literami."""
        item = {"text": "Format kodu SKU (II2732-417) jest nietypowy, co budzi dodatkowe wątpliwości."}
        assert _is_stale_sku_limitation(item) is True


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

    def test_dembele_incident_shape(self):
        """Kształt 1:1 z raportu 20260904-9c78243b — bez pola 'type'."""
        key_evidence = [
            {
                "text": "Nadruk na karku zawiera nazwę 'AERO-FIT', przestarzałą technologię Nike, która nie jest stosowana w autentycznych koszulkach z tego okresu. To rażący anachronizm.",
                "status": "RED",
            },
            {
                "text": "Format kodu SKU (II2732-417) jest nietypowy dla standardowych produktów Nike, co budzi dodatkowe wątpliwości.",
                "status": "YELLOW",
            },
        ]
        result = _clean_stale_sku_key_evidence(key_evidence)
        assert len(result) == 1
        assert "AERO-FIT" in result[0]["text"]

    def test_keeps_unrelated_limitations(self):
        key_evidence = [
            {"type": "limitation", "text": "Brak zdjęcia wnętrza kołnierza uniemożliwia pełną ocenę."},
        ]
        assert _clean_stale_sku_key_evidence(key_evidence) == key_evidence

    def test_none_input_returns_empty_list(self):
        assert _clean_stale_sku_key_evidence(None) == []

    def test_empty_list_returns_empty_list(self):
        assert _clean_stale_sku_key_evidence([]) == []


class TestSkuStatusPositivelyConfirmed:
    """Regresja na bug złapany przez review+QA: pierwsza wersja fixu reużywała
    `status in _sku_dm_map` jako guard w run-decision, ale ta mapa zawiera też
    "not_found" — status, dla którego weryfikacja NIC nie ustaliła, więc bullet
    "brak możliwości weryfikacji SKU" jest wciąż prawdziwy i NIE powinien być
    czyszczony. Usunięcie go dla not_found odtwarzałoby ten sam błąd (sprzeczny/
    mylący raport) w drugą stronę.

    Druga, węższa różnica względem tamtego guarda: found_unofficial i
    format_invalid to NEGATYWNE ustalenia — bullet wyrażający wątpliwość co do
    SKU jest tam nadal PRAWDZIWY (spójny z wynikiem), więc też nie powinien być
    czyszczony. Stąd _sku_status_positively_confirmed jest True tylko dla
    found_official/found_authorized, nie dla całej "coś ustaliła" grupy."""

    def test_not_found_is_not_positively_confirmed(self):
        assert _sku_status_positively_confirmed("not_found") is False

    def test_uncertain_is_not_positively_confirmed(self):
        assert _sku_status_positively_confirmed("uncertain") is False

    def test_not_applicable_is_not_positively_confirmed(self):
        assert _sku_status_positively_confirmed("not_applicable") is False

    def test_found_unofficial_is_not_positively_confirmed(self):
        """Negatywne ustalenie — bullet z wątpliwością wciąż prawdziwy, nie czyścimy."""
        assert _sku_status_positively_confirmed("found_unofficial") is False

    def test_format_invalid_is_not_positively_confirmed(self):
        """Negatywne ustalenie — bullet z wątpliwością wciąż prawdziwy, nie czyścimy."""
        assert _sku_status_positively_confirmed("format_invalid") is False

    def test_found_official_is_positively_confirmed(self):
        assert _sku_status_positively_confirmed("found_official") is True

    def test_found_authorized_is_positively_confirmed(self):
        assert _sku_status_positively_confirmed("found_authorized") is True
