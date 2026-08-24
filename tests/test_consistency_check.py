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

from app.services.consistency_check import run_player_club_consistency_check, _real_value


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

    def test_placeholder_season_returns_uncertain_not_gemini_call(self):
        report_data = {
            "subject": {"player_name": "Lewandowski", "club": "FC Barcelona", "season": "brak"},
            "personalization_assessment": {"status": "zweryfikowana"},
        }
        with patch(self._CALL_GEMINI_TARGET, new=AsyncMock()) as mock_call:
            result = run(run_player_club_consistency_check(report_data))
        assert result["status"] == "uncertain"
        mock_call.assert_not_called()

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
