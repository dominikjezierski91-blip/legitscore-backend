"""
Testy player_club_consistency_check (app/services/consistency_check.py).

Regresja na realny wzorzec buga znaleziony przez reviewera (2026-08-24, ten sam
incydent Manchester United co pdf_report.py): jeśli Agent A zwróci placeholder
("nieustalone" itp.) zamiast prawdziwej wartości player_name/club/season, stary
kod (`if not player_name`) traktował placeholder jak realną wartość — bo string
"nieustalone" jest truthy — i leciał dalej do _call_gemini() z fikcyjnym
zawodnikiem jako wejściem, zamiast poprawnie zwrócić not_applicable/uncertain.
"""
import asyncio
from unittest.mock import AsyncMock, patch

from app.services.consistency_check import (
    PLAYER_CLUB_CONSISTENCY_PROMPT,
    _real_value,
    _uncertain_insufficient,
    run_player_club_consistency_check,
)


def run(coro):
    return asyncio.run(coro)


class TestRealValueNormalizesPlaceholders:
    def test_placeholder_returns_empty_string(self):
        assert _real_value("nieustalone") == ""

    def test_case_insensitive(self):
        assert _real_value("Unknown") == ""
        assert _real_value("UNKNOWN") == ""

    def test_real_value_passes_through_unchanged(self):
        assert _real_value("Lewandowski") == "Lewandowski"

    def test_none_and_empty_return_empty_string(self):
        assert _real_value(None) == ""
        assert _real_value("") == ""

    def test_strips_whitespace(self):
        assert _real_value("  Lewandowski  ") == "Lewandowski"


class TestConsistencyCheckSkipsPlaceholderValues:
    _CALL_GEMINI_TARGET = "app.services.consistency_check._call_gemini"

    def test_placeholder_player_name_returns_not_applicable_without_calling_gemini(self):
        report_data = {
            "subject": {"player_name": "nieustalone", "club": "FC Barcelona", "season": "2023/24"},
            "personalization_assessment": {"status": "zweryfikowana"},
        }
        with patch(self._CALL_GEMINI_TARGET, new=AsyncMock()) as mock_call:
            result = run(run_player_club_consistency_check(report_data))
        assert result["status"] == "not_applicable"
        mock_call.assert_not_called()

    def test_real_player_name_with_placeholder_club_returns_uncertain_not_gemini_call(self):
        report_data = {
            "subject": {"player_name": "Lewandowski", "club": "nieustalone", "season": "2023/24"},
            "personalization_assessment": {"status": "zweryfikowana"},
        }
        with patch(self._CALL_GEMINI_TARGET, new=AsyncMock()) as mock_call:
            result = run(run_player_club_consistency_check(report_data))
        assert result["status"] == "uncertain"
        mock_call.assert_not_called()

    def test_placeholder_season_still_calls_gemini_on_club_and_number_alone(self):
        """SPEC "uczciwe wyświetlanie sezonu" (2026-09-06, case 1e8b405c):
        sezon przestał być wymagany — squad-check orzeka o zakresie sezonów
        na podstawie klubu+numeru, sezon to tylko opcjonalny cross-check.
        Wcześniej brak sezonu blokował cały check, mimo że klub+zawodnik
        wystarczają do sensownej odpowiedzi o zakresie."""
        report_data = {
            "subject": {"player_name": "Lewandowski", "club": "FC Barcelona", "season": "brak"},
            "personalization_assessment": {"status": "zweryfikowana"},
        }
        fake_result = {"status": "consistent", "confidence": "high", "reason": "", "notes": []}
        with patch(self._CALL_GEMINI_TARGET, new=AsyncMock(return_value=fake_result)) as mock_call:
            result = run(run_player_club_consistency_check(report_data))
        mock_call.assert_called_once_with("Lewandowski", "FC Barcelona", None, None)
        assert result == fake_result

    def test_real_values_call_gemini_with_normalized_arguments(self):
        report_data = {
            "subject": {
                "player_name": "Lewandowski", "club": "FC Barcelona",
                "season": "2023/24", "player_number": "9",
            },
            "personalization_assessment": {"status": "zweryfikowana"},
        }
        fake_result = {"status": "consistent", "confidence": "high", "reason": "", "notes": []}
        with patch(self._CALL_GEMINI_TARGET, new=AsyncMock(return_value=fake_result)) as mock_call:
            result = run(run_player_club_consistency_check(report_data))
        mock_call.assert_called_once_with("Lewandowski", "FC Barcelona", "2023/24", "9")
        assert result == fake_result

    def test_placeholder_player_number_normalized_to_none(self):
        report_data = {
            "subject": {
                "player_name": "Lewandowski", "club": "FC Barcelona",
                "season": "2023/24", "player_number": "nieustalone",
            },
            "personalization_assessment": {"status": "zweryfikowana"},
        }
        fake_result = {"status": "consistent", "confidence": "high", "reason": "", "notes": []}
        with patch(self._CALL_GEMINI_TARGET, new=AsyncMock(return_value=fake_result)) as mock_call:
            run(run_player_club_consistency_check(report_data))
        mock_call.assert_called_once_with("Lewandowski", "FC Barcelona", "2023/24", None)


class TestUncertainInsufficientReasonText:
    """SPEC evidence-merge sekcja 8 (2026-09-05, case 15364d60, złota koszulka
    Lewandowskiego): generyczny tekst "brak klubu lub sezonu" mylił, gdy klub
    (FC Barcelona) był w rzeczywistości znany i widoczny w tabeli identyfikacji
    produktu dwa akapity wyżej w tym samym raporcie — brakowało tylko sezonu.
    Ten sam tekst zasila zarówno sekcję "Zgodność personalizacji" jak i wiersz F
    (squad check) w decision_matrix (oba czytają player_club_consistency.reason
    bezpośrednio — patrz app/routes/cases.py linia ~1013)."""

    def test_missing_only_season_names_known_club(self):
        result = _uncertain_insufficient(club_name="FC Barcelona", missing_club=False, missing_season=True)
        assert result["reason"] == "Niewystarczające dane do sprawdzenia zgodności — brak sezonu (klub: FC Barcelona)."

    def test_missing_only_club(self):
        result = _uncertain_insufficient(club_name="", missing_club=True, missing_season=False)
        assert "brak klubu" in result["reason"]
        assert "sezonu" not in result["reason"]

    def test_missing_both(self):
        result = _uncertain_insufficient(club_name="", missing_club=True, missing_season=True)
        assert "brak klubu i sezonu" in result["reason"]

    def test_missing_season_without_known_club_falls_back_generically(self):
        """Skrajny przypadek: brakuje sezonu, a klub też jest pusty (np. wywołane
        bezpośrednio z club_name="") — nie ma czego wstawić w nawias."""
        result = _uncertain_insufficient(club_name="", missing_club=False, missing_season=True)
        assert result["reason"] == "Niewystarczające dane do sprawdzenia zgodności — brak sezonu."

    def test_end_to_end_real_case_shape_known_club_missing_season(self):
        """Replay case 15364d60: club='FC Barcelona' znany, season='nieustalone'
        (znormalizowane do pustego stringa przez _real_value).

        UWAGA (2026-09-06, SPEC "uczciwe wyświetlanie sezonu"): to zachowanie
        celowo się ZMIENIŁO. Wcześniej brak sezonu przy znanym klubie kończył
        się "uncertain" bez wywołania Gemini ("brak sezonu (klub: ...)").
        Teraz squad-check i tak orzeka o zakresie sezonów na podstawie
        klubu+numeru — sezon nie jest już blokerem. Test
        TestUncertainInsufficientReasonText pokrywa dalej samą funkcję
        _uncertain_insufficient (wciąż poprawną, tylko już nieużywaną z tą
        kombinacją argumentów przez _run)."""
        report_data = {
            "subject": {"player_name": "LEWANDOWSKI", "club": "FC Barcelona", "season": "nieustalone"},
            "personalization_assessment": {"status": "zweryfikowana"},
        }
        fake_result = {"status": "consistent", "confidence": "medium", "reason": "Zawodnik nosi numer 9 w FC Barcelona od sezonu 2022/23.", "notes": []}
        with patch("app.services.consistency_check._call_gemini", new=AsyncMock(return_value=fake_result)) as mock_call:
            result = run(run_player_club_consistency_check(report_data))
        mock_call.assert_called_once_with("LEWANDOWSKI", "FC Barcelona", None, None)
        assert result == fake_result


class TestPlayerClubConsistencyPromptRangeBased:
    """SPEC "uczciwe wyświetlanie sezonu + squad-check na zakres" (2026-09-06,
    case 1e8b405c). Regresja: prompt pytał o zgodność z JEDNYM, założonym
    sezonem ("Season: {season}"), więc odpowiedź Gemini ("Pedri gra w FC
    Barcelona z numerem 8 w sezonie 2026/27") była kołowa — potwierdzała
    dokładnie ten sezon, który sam był niepewnym ZAŁOŻENIEM. Nie da się
    odpalić prawdziwego Gemini w testach jednostkowych — testujemy więc
    treść promptu (ten sam wzorzec co test_prompt_a_season_confidence.py),
    nie zachowanie modelu."""

    def test_instructs_range_not_single_season(self):
        assert "RANGE" in PLAYER_CLUB_CONSISTENCY_PROMPT

    def test_forbids_circular_confirmation_of_input_season(self):
        prompt = PLAYER_CLUB_CONSISTENCY_PROMPT.lower()
        assert "circular" in prompt

    def test_never_restate_input_season_instruction_present(self):
        assert "NEVER just restate that season back" in PLAYER_CLUB_CONSISTENCY_PROMPT

    def test_no_season_given_still_evaluates_club_and_number(self):
        prompt = PLAYER_CLUB_CONSISTENCY_PROMPT.lower()
        assert "if no season was given" in prompt or "without inventing or assuming a season" in prompt

    def test_bad_example_matches_the_real_regression_text_shape(self):
        """Dokładny kształt złej odpowiedzi z case'a 1e8b405c — sprawdzamy, że
        prompt wprost pokazuje go jako zakazany przykład, nie tylko ogólnikowo
        zakazuje "kołowości"."""
        assert "Zawodnik gra w klubie X z numerem 8 w sezonie 2026/27" in PLAYER_CLUB_CONSISTENCY_PROMPT

    def test_good_examples_are_range_phrased(self):
        assert "od sezonu 2021/22" in PLAYER_CLUB_CONSISTENCY_PROMPT

    def test_consistent_definition_does_not_require_a_season(self):
        prompt = PLAYER_CLUB_CONSISTENCY_PROMPT
        idx = prompt.find('"consistent" means')
        assert idx != -1
        rule_text = prompt[idx:idx + 400]
        assert "do not invent a season" in rule_text

    def test_boundary_choice_covers_both_directions_of_a_closed_range(self):
        """Code review MEDIUM (2026-09-06): oryginalny worked example pokrywał
        tylko przypadek "podany sezon PRZED zakresem" (start range → correction).
        Brak przykładu dla "podany sezon PO zamkniętym zakresie" (zawodnik
        odszedł) zostawiał niejednoznaczność, która sama karmi
        apply_season_correction — zły wybór granicy odtworzyłby zły sezon,
        tylko inną ścieżką (korekta PCC) niż ta naprawiona w tym SPEC-u."""
        prompt = PLAYER_CLUB_CONSISTENCY_PROMPT
        assert "CLOSED range" in prompt
        assert "closest to the given" in prompt.lower()
