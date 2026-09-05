"""
Testy kontraktu wyjścia Agenta A dla pola subject.season_confidence
(prompt_a.txt) — SPEC "pewność sezonu + reklasyfikacja jakości wykonania",
2026-09-05 (case 1b96a6a4, koszulka Pedri).

Regresja: werdykt "Podróbka 95%" opierał się głównie na "DRI-FIT ADV sprzeczne
z Nike Aero-FIT, bo wersja meczowa 26/27 powinna mieć Aero-FIT" — prawdziwe
TYLKO jeśli sezon rzeczywiście to 26/27, a Agent A sam ustalił sezon bez
twardego potwierdzenia (brak czytelnej metki z datą). Niepewne założenie
(sezon) użyte jako twarda podstawa mocnego wniosku.

Część 1 SPEC-a: Agent A ma zwracać subject.season_confidence i formułować
wnioski zależne od sezonu warunkowo, gdy ta pewność nie jest "high". Nie da
się odpalić prawdziwego Gemini w testach jednostkowych — testujemy więc treść
promptu (podobnie jak SKU_VERIFICATION_PROMPT w test_sku_agent.py), nie
zachowanie modelu.
"""
from pathlib import Path

_PROMPT_A_PATH = Path(__file__).resolve().parents[1] / "prompt_a.txt"
_PROMPT_A_TEXT = _PROMPT_A_PATH.read_text(encoding="utf-8")


class TestSeasonConfidenceFieldDeclared:
    def test_season_confidence_field_present_in_schema(self):
        assert "season_confidence" in _PROMPT_A_TEXT

    def test_season_confidence_allows_high_medium_low(self):
        assert "high | medium | low" in _PROMPT_A_TEXT or (
            "high" in _PROMPT_A_TEXT and "medium" in _PROMPT_A_TEXT and "low" in _PROMPT_A_TEXT
        )

    def test_season_basis_field_present(self):
        """season_basis (na czym oparto ustalenie sezonu) — pomocnicze pole,
        SPEC sekcja 3: 'oraz, jeśli możliwe, season_basis'."""
        assert "season_basis" in _PROMPT_A_TEXT


class TestSeasonConfidenceInstructions:
    def test_instructs_not_to_overstate_confidence(self):
        prompt = _PROMPT_A_TEXT.lower()
        assert "nie zawyżaj" in prompt

    def test_defines_low_confidence_as_guessing(self):
        prompt = _PROMPT_A_TEXT.lower()
        assert "zgadywanie" in prompt

    def test_defines_high_confidence_requires_hard_evidence(self):
        prompt = _PROMPT_A_TEXT.lower()
        # "high" wymaga metki/daty lub jednoznacznego wzoru — nie samego
        # "najlepszego zgadywania" jak w "medium".
        assert "metki" in prompt or "metka" in prompt


class TestConditionalReasoningSection8e:
    def test_section_8e_exists(self):
        assert "8e." in _PROMPT_A_TEXT or "WNIOSKI ZALEŻNE OD SEZONU" in _PROMPT_A_TEXT

    def test_instructs_conditional_phrasing_when_not_high(self):
        prompt = _PROMPT_A_TEXT.lower()
        assert "warunkowo" in prompt

    def test_explicitly_forbids_strong_indicator_wording_when_uncertain(self):
        """Sedno regresji: Agent A pisał 'silny wskaźnik nieautentyczności'
        dla przesłanki opartej na niepewnym sezonie — prompt musi wprost tego
        zakazywać."""
        prompt = _PROMPT_A_TEXT.lower()
        assert "silny wskaźnik" in prompt or "silny wskaznik" in prompt

    def test_references_criterion_d_as_typically_season_dependent(self):
        section_start = _PROMPT_A_TEXT.find("8e.")
        section_end = _PROMPT_A_TEXT.find("9. REGUŁY DECYZYJNE")
        section = _PROMPT_A_TEXT[section_start:section_end] if section_start != -1 else ""
        assert "kryterium D" in section or "kryterium d" in section.lower()

    def test_instructs_honest_summary_when_only_strong_argument(self):
        section_start = _PROMPT_A_TEXT.find("8e.")
        section_end = _PROMPT_A_TEXT.find("9. REGUŁY DECYZYJNE")
        section = _PROMPT_A_TEXT[section_start:section_end].lower() if section_start != -1 else ""
        assert "jedyny" in section and "summary" in section
