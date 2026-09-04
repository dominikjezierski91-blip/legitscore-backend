"""
Testy nowej gałęzi kit_context_search.py: żywa weryfikacja aktualnych nazw
technologii materiału producenta (Nike/Adidas/...), ten sam wzorzec co istniejące
RECENT CONFIRMED TITLES (trofea) — patrz komentarz w _fetch_current_technology_names.

Regresja na realny incydent: raport 20260904-9c78243b (PSG/Dembélé, Podróbka 95%)
— Agent A uznał nazwę technologii "AERO-FIT" za "przestarzałą technologię Nike"
i użył tego jako kluczowego dowodu werdyktu, mimo że to literalnie aktualna,
oficjalna nazwa Nike dla tej dokładnie autentycznej koszulki (potwierdzone na
nike.com pod tym samym SKU II2732-417). Agent A ma datę odcięcia treningu
wcześniejszą niż nazwa "Aero-FIT" weszła w użycie — ten sam typ błędu co
incydent PSG Kvaratskhelia z 2026-08-19 (nierozpoznane trofea "z przyszłości"),
tylko dla nazw technologii zamiast wydarzeń sportowych.

Konwencja: brak pytest-asyncio w tym repo (patrz test_market_value_podrobka.py) —
async funkcje wołane przez asyncio.run() wewnątrz zwykłych sync testów.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.services.kit_context_search import (
    _MAX_CONTEXT_BLOCK_CHARS,
    _build_tech_name_search_prompt,
    _current_season_start_years,
    _fetch_current_technology_names,
    _season_label,
)


class TestBuildTechNameSearchPrompt:
    def test_contains_marker(self):
        assert "CONFIRMED CURRENT TECHNOLOGY NAMES:" in _build_tech_name_search_prompt()

    def test_contains_current_season_label(self):
        label = _season_label(_current_season_start_years(1)[0])
        assert label in _build_tech_name_search_prompt()

    def test_warns_about_training_cutoff(self):
        prompt = _build_tech_name_search_prompt()
        assert "training" in prompt.lower()
        assert "cutoff" in prompt.lower()

    def test_mentions_authentic_and_replica_tiers(self):
        prompt = _build_tech_name_search_prompt()
        assert "authentic" in prompt.lower()
        assert "replica" in prompt.lower()


class TestFetchCurrentTechnologyNames:
    def test_unknown_manufacturer_skips_call_entirely(self):
        client = MagicMock()
        client.aio.models.generate_content = AsyncMock()
        result = asyncio.run(_fetch_current_technology_names(client, "fast-model", MagicMock(), "unknown", "PSG"))
        assert result == ""
        client.aio.models.generate_content.assert_not_called()

    def test_empty_manufacturer_skips_call(self):
        client = MagicMock()
        client.aio.models.generate_content = AsyncMock()
        result = asyncio.run(_fetch_current_technology_names(client, "fast-model", MagicMock(), "", "PSG"))
        assert result == ""
        client.aio.models.generate_content.assert_not_called()

    def test_none_manufacturer_skips_call(self):
        client = MagicMock()
        client.aio.models.generate_content = AsyncMock()
        result = asyncio.run(_fetch_current_technology_names(client, "fast-model", MagicMock(), None, "PSG"))
        assert result == ""
        client.aio.models.generate_content.assert_not_called()

    def test_other_manufacturer_skips_call(self):
        """Regresja z code review: _IDENTIFICATION_PROMPT dopuszcza 'other' jako
        poprawną wartość manufacturer — musi być tak samo pomijane jak 'unknown',
        inaczej odpala się bezsensowne zapytanie 'Manufacturer: other'."""
        client = MagicMock()
        client.aio.models.generate_content = AsyncMock()
        result = asyncio.run(_fetch_current_technology_names(client, "fast-model", MagicMock(), "other", "PSG"))
        assert result == ""
        client.aio.models.generate_content.assert_not_called()

    def test_whitespace_only_manufacturer_skips_call(self):
        """Regresja z QA: manufacturer='   ' nie jest złapane przez 'not manufacturer'
        (niepusty string) ani przez .lower()=='unknown' — wymaga .strip() najpierw."""
        client = MagicMock()
        client.aio.models.generate_content = AsyncMock()
        result = asyncio.run(_fetch_current_technology_names(client, "fast-model", MagicMock(), "   ", "PSG"))
        assert result == ""
        client.aio.models.generate_content.assert_not_called()

    def test_padded_unknown_manufacturer_skips_call(self):
        client = MagicMock()
        client.aio.models.generate_content = AsyncMock()
        result = asyncio.run(_fetch_current_technology_names(client, "fast-model", MagicMock(), " Unknown ", "PSG"))
        assert result == ""
        client.aio.models.generate_content.assert_not_called()

    def test_returns_text_when_marker_present(self):
        client = MagicMock()
        fake_resp = MagicMock()
        fake_resp.text = "CONFIRMED CURRENT TECHNOLOGY NAMES:\nauthentic/match — Aero-FIT — current for 2026/27, replaces Dri-FIT ADV"
        client.aio.models.generate_content = AsyncMock(return_value=fake_resp)
        result = asyncio.run(_fetch_current_technology_names(client, "fast-model", MagicMock(), "Nike", "Paris Saint-Germain"))
        assert "CONFIRMED CURRENT TECHNOLOGY NAMES:" in result
        assert "Aero-FIT" in result

    def test_returns_empty_when_marker_missing(self):
        client = MagicMock()
        fake_resp = MagicMock()
        fake_resp.text = "I couldn't find anything relevant."
        client.aio.models.generate_content = AsyncMock(return_value=fake_resp)
        result = asyncio.run(_fetch_current_technology_names(client, "fast-model", MagicMock(), "Nike", "Paris Saint-Germain"))
        assert result == ""

    def test_returns_empty_on_exception_non_fatal(self):
        client = MagicMock()
        client.aio.models.generate_content = AsyncMock(side_effect=RuntimeError("boom"))
        result = asyncio.run(_fetch_current_technology_names(client, "fast-model", MagicMock(), "Nike", "Paris Saint-Germain"))
        assert result == ""

    def test_max_context_block_chars_is_sane_positive_bound(self):
        """Sanity check na _MAX_CONTEXT_BLOCK_CHARS (code review: bez tego capu
        trophy_context + tech_name_context razem mogłyby przekroczyć extra_context[:4000]
        w agent_a_gemini.py i uciąć marker w połowie)."""
        assert 0 < _MAX_CONTEXT_BLOCK_CHARS < 4000

    def test_none_found_response_still_returned_since_marker_present(self):
        """'none found' jest poprawną, jednoznaczną odpowiedzią (patrz analogiczny
        wzorzec w RECENT CONFIRMED TITLES) — nie powinna być traktowana jak brak wyniku."""
        client = MagicMock()
        fake_resp = MagicMock()
        fake_resp.text = "CONFIRMED CURRENT TECHNOLOGY NAMES: none found"
        client.aio.models.generate_content = AsyncMock(return_value=fake_resp)
        result = asyncio.run(_fetch_current_technology_names(client, "fast-model", MagicMock(), "Nike", "Paris Saint-Germain"))
        assert result == "CONFIRMED CURRENT TECHNOLOGY NAMES: none found"
