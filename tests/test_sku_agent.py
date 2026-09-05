"""
Testy promptu weryfikacji SKU (app/services/sku_agent.py).

Regresja na realny incydent (2026-08-24, koszulka Manchester United, case
a7beb95b): kod SKU złożony z samych cyfr (09914738) został odrzucony jako
format_invalid BEZ realnego wyszukania w Google — prompt jawnie pozwalał
pominąć szukanie dla "podejrzanie" wyglądających kodów. Później okazało się,
że to prawdziwa koszulka juniorska (metka: AGE 13/15) — starsze/dziecięce
linie Nike mogą mieć inny, nadal legalny format kodu niż współczesny retail
dorosły (XXXXXX-XXX), więc odrzucanie po samym wyglądzie bez szukania było
błędem metodologicznym, nie tylko pechem w tym jednym przypadku.

Druga grupa testów (2026-09-05) — dwa kolejne realne incydenty tego samego dnia:

1. Case 50f59024 (Pedri, FC Barcelona): subject.sku="nieczytelne" (Agentowi A
   prompt_a.txt jawnie każe wpisać ten placeholder, gdy metka wewnętrzna jest
   widoczna, ale kod nieczytelny — patrz prompt_a.txt linia ~90) nie było w
   UNVERIFIED_SUBJECT_VALUES, więc sku_agent._run() przepuścił dosłowny string
   "nieczytelne" jako szukany kod SKU do Gemini → status="format_invalid" →
   twardy override na podróbkę 90%, mimo że agent_suggestion Agenta A było
   "meczowa" i cała reszta dowodów (DRI-FIT ADV, ENGINEERED, termotransfer,
   personalizacja) było pozytywne. Naprawione dodaniem "nieczytelne"/
   "nieczytelny" do wspólnej stałej UNVERIFIED_SUBJECT_VALUES.

2. Case 58646ec2 (Lewandowski, FC Barcelona, złota koszulka): sku_verification
   znalazło kod CV7891-428 u autoryzowanego sprzedawcy (KICKS CREW/Unisport),
   ale własny `reason` agenta mówił wprost, że znaleziony produkt to zupełnie
   inny model/sezon (domowa 2021/22) niż deklarowany (wyjazdowa 2022/2023) —
   mimo to status wyszedł "found_authorized", nie "mismatch", bo prompt nigdy
   nie instruował porównania znalezionego produktu z podanym Club/Season/Model.
   Skutek: werdykt Agenta A (agent_suggestion="podrobka", summary jawnie mówiący
   "rozstrzygający dowód... podróbką") został PRZEBITY przez PCC-correction
   override w agent_a_gemini.py (podrobka→meczowa, gdy PCC spójne i C/D zielone)
   — bo ten override sprawdza tylko `sku_verification.status not in ("mismatch",
   "found_unofficial", "format_invalid")`, a "found_authorized" nie jest na tej
   liście, mimo że w tym wypadku POWINIEN był być zakwalifikowany jako mismatch.
   Naprawione dodaniem statusu "mismatch" do promptu (agent i tak dostaje
   Club/Season/Brand/Model w wejściu — tylko nie miał instrukcji co z tym
   zrobić) — "mismatch" jest już od dawna poprawnie okablowany w
   agent_a_gemini.py (wyzwala sku_mismatch_hard_reject i jest wykluczony z obu
   PCC-override guardów), po prostu obecny prompt nigdy go nie produkował.
"""
import asyncio
from unittest.mock import AsyncMock, patch

from app.services import sku_agent
from app.services.sku_agent import SKU_VERIFICATION_PROMPT, _not_applicable, _fallback


class TestSkuVerificationPromptRequiresSearchFirst:
    def test_no_longer_permits_skipping_search_for_suspicious_format(self):
        """Stara instrukcja pozwalała nie szukać dla 'clearly format_invalid' —
        to dokładnie ta furtka, która spowodowała błędne odrzucenie prawdziwego
        kodu juniorskiego bez sprawdzenia."""
        assert "never guess from format alone unless clearly format_invalid" not in SKU_VERIFICATION_PROMPT

    def test_requires_search_for_every_sku_regardless_of_format(self):
        prompt = SKU_VERIFICATION_PROMPT.lower()
        assert "always search first, for every sku" in prompt

    def test_format_invalid_requires_having_actually_searched(self):
        prompt = SKU_VERIFICATION_PROMPT.lower()
        assert "use rarely, only for codes that are structurally impossible" in prompt
        assert "you searched for the exact code and found" in prompt

    def test_acknowledges_youth_and_older_products_may_differ(self):
        """Sedno fixu: format 'nietypowy' dla współczesnego retail nie oznacza
        podróbki — starsze/dziecięce linie mogą mieć inny, wciąż legalny format."""
        prompt = SKU_VERIFICATION_PROMPT.lower()
        assert "youth/kids" in prompt or "kids-line" in prompt

    def test_all_digits_no_longer_auto_rejected_without_search(self):
        """Stara reguła: 'ALL digits only ... -> format_invalid' jako
        natychmiastowa decyzja bez szukania. Nowa wersja dopuszcza taki kod,
        ale wymaga najpierw szukania."""
        assert "all digits only (e.g. 123456789) → format_invalid" not in SKU_VERIFICATION_PROMPT

    def test_brand_patterns_framed_as_reference_only(self):
        """Pilnuje, żeby nikt w przyszłości nie 'utwardził' z powrotem listy
        wzorców Nike/Adidas/Puma w regułę auto-reject — mają zostać wyłącznie
        punktem odniesienia, nie twardym warunkiem."""
        assert "reference only" in SKU_VERIFICATION_PROMPT.lower()

    def test_json_schema_still_lists_all_seven_statuses(self):
        """Tani strażnik przed przypadkowym usunięciem wartości ze schematu
        przy przyszłych edycjach promptu."""
        for status in [
            "found_official", "found_authorized", "found_unofficial",
            "product_mismatch", "season_only_mismatch", "not_found", "format_invalid",
        ]:
            assert status in SKU_VERIFICATION_PROMPT

    def test_prefers_not_found_over_format_invalid_when_only_format_is_unusual(self):
        """Follow-up po code review (2026-08-24): sam fix 'zawsze szukaj' nie
        wystarczał — dla starego/niszowego produktu wyszukiwanie i tak może nic
        nie znaleźć, a wtedy bez tie-breakera model nadal miałby pełne prawo
        oznaczyć format_invalid (twardy override na 90% podróbki) zamiast
        znacznie łagodniejszego not_found. Prompt musi jawnie preferować
        not_found, gdy jedynym argumentem jest niepasujący format."""
        prompt = SKU_VERIFICATION_PROMPT.lower()
        assert "when in doubt between not_found and format_invalid, choose not_found" in prompt
        assert "structurally impossible" in prompt
        assert "structurally nonsensical, not just unfamiliar" in prompt


class TestSkuVerificationMismatchStatus:
    """Regresja na incydent 2026-09-05 (Lewandowski, case 58646ec2) — patrz
    docstring modułu. Prompt musi instruować agenta, że kod real+registrowany
    ALE dla innego produktu niż podany to 'product_mismatch', nie
    'found_authorized'.

    UWAGA (2026-09-06, SPEC "autorytatywny SKU koryguje sezon", case eb90a5cc
    vs feee21e0): status "mismatch" rozdzielono na "product_mismatch"
    (inny produkt — model/kolor/typ kompletu/klub) i "season_only_mismatch"
    (ten sam produkt, tylko inny sezon — bo sezon bywa niepewnym zgadnięciem
    Agenta A, nie twardym faktem). Testy poniżej zaktualizowane pod nową
    nazwę/podział; klasa TestSkuVerificationSeasonOnlyMismatch pokrywa nowy
    status i plumbing season_confidence."""

    def test_product_mismatch_status_documented_in_prompt(self):
        prompt = SKU_VERIFICATION_PROMPT.lower()
        assert '"product_mismatch"' in prompt

    def test_product_mismatch_distinguished_from_found_authorized_by_matching_claimed_item(self):
        prompt = SKU_VERIFICATION_PROMPT.lower()
        assert "different product" in prompt and "than the one described" in prompt

    def test_product_mismatch_not_softened_by_legitimate_source(self):
        """Sedno bugu: sam fakt, że źródło jest autoryzowane, nie może
        automatycznie dawać found_authorized, jeśli produkt nie pasuje do
        tego konkretnego przedmiotu."""
        prompt = " ".join(SKU_VERIFICATION_PROMPT.lower().split())
        assert "never soften product_mismatch into found_authorized" in prompt

    def test_product_mismatch_treated_as_stronger_signal_than_not_found(self):
        prompt = SKU_VERIFICATION_PROMPT.lower()
        assert "stronger red flag" in prompt or "more serious signal" in prompt

    def test_trivial_variation_not_product_mismatch(self):
        """Nie każda różnica to product_mismatch — inny kolor tego samego
        modelu to wciąż found_authorized, nie product_mismatch."""
        prompt = SKU_VERIFICATION_PROMPT.lower()
        assert "do not use product_mismatch for trivial variation" in prompt

    def test_model_version_tier_mismatch_covered(self):
        """Code review (2026-09-05): definicja mismatch pierwotnie wymieniała
        tylko sezon/kit-type/klub, pomijając Model, mimo że Model jest
        przekazywany agentowi jako input — realna luka, bo fan/replica vs
        player/match/authentic to jeden z najczęstszych przypadków 'prawdziwy
        kod, zła wersja' w praktyce."""
        prompt = " ".join(SKU_VERIFICATION_PROMPT.lower().split())
        assert "different model/version" in prompt
        assert "fan/replica" in prompt or "player/match" in prompt

    def test_product_mismatch_has_ambiguous_listing_tie_breaker(self):
        """QA (2026-09-05): mismatch wyzwala ten sam bezwzględny 90% hard-reject
        co format_invalid, więc zasługuje na ten sam rodzaj tie-breakera —
        wolimy found_authorized, gdy sprzeczność opiera się na jednym
        niejednoznacznym ogłoszeniu, nie na kanonicznej tożsamości kodu."""
        prompt = " ".join(SKU_VERIFICATION_PROMPT.lower().split())
        assert "tie-breaker" in prompt and "mismatch" in prompt.split("tie-breaker")[1][:200]
        assert "canonical" in prompt


class TestSkuVerificationSeasonOnlyMismatch:
    """SPEC "autorytatywny SKU koryguje sezon" (2026-09-06, case eb90a5cc vs
    feee21e0, Lewandowski/FC Barcelona): ten sam, w pełni autoryzowany kod
    SKU (FN8792-010) dał "mismatch"→Podróbka 95% w jednym przebiegu i
    "found_authorized"→Meczowa 80% w drugim — jedyna różnica to własne,
    niepewne zgadnięcie sezonu Agenta A (season_confidence=medium).
    sku_agent.py nigdy nie czytał season_confidence, więc rozbieżność
    sezonu ze zgadniętym, niepewnym wejściem dawała ten sam bezwzględny
    90%-hard-reject co realna niezgodność produktu."""

    def test_season_only_mismatch_documented_in_prompt(self):
        prompt = SKU_VERIFICATION_PROMPT.lower()
        assert '"season_only_mismatch"' in prompt

    def test_season_only_mismatch_is_separate_softer_status_from_product_mismatch(self):
        prompt = SKU_VERIFICATION_PROMPT.lower()
        assert "separate" in prompt and "softer" in prompt

    def test_season_only_mismatch_requires_found_season_field(self):
        prompt = SKU_VERIFICATION_PROMPT
        assert "found_season" in prompt
        assert "REQUIRED when status is season_only_mismatch" in prompt

    def test_found_season_field_in_json_schema(self):
        assert '"found_season"' in SKU_VERIFICATION_PROMPT

    def test_season_confidence_instructs_not_to_escalate_to_product_mismatch(self):
        """Sedno regresji: sam fakt niezgodności sezonu, gdy sezon był
        niepewnym zgadnięciem, nie może eskalować do product_mismatch."""
        prompt = " ".join(SKU_VERIFICATION_PROMPT.lower().split())
        assert "never escalate a season-only discrepancy to product_mismatch" in prompt

    def test_season_only_mismatch_not_used_when_other_fields_also_conflict(self):
        prompt = " ".join(SKU_VERIFICATION_PROMPT.lower().split())
        assert "that combination is product_mismatch" in prompt


class TestSkuVerificationSeasonConfidencePlumbing:
    """Plumbing season_confidence do promptu — bez tego był karmiony
    niepewnym zgadnięciem Agenta A jak twardym faktem."""

    def test_run_reads_season_confidence_from_subject(self):
        report_data = {
            "subject": {
                "sku": "FN8792-010", "club": "FC Barcelona", "season": "2023-2024",
                "brand": "Nike", "model": "wyjazdowa", "season_confidence": "medium",
            },
        }
        fake_result = {"status": "found_authorized", "confidence": "high"}
        with patch("app.services.sku_agent._call_gemini", new=AsyncMock(return_value=fake_result)) as mock_call:
            asyncio.run(sku_agent._run(report_data))
        mock_call.assert_called_once_with(
            "FN8792-010", "FC Barcelona", "2023-2024", "Nike", "wyjazdowa", "medium",
        )

    def test_call_gemini_marks_season_as_uncertain_guess_when_confidence_not_high(self):
        prompt_input = sku_agent._build_input_lines(
            "FN8792-010", "FC Barcelona", "2023-2024", "Nike", "wyjazdowa", "medium",
        )
        joined = "\n".join(prompt_input)
        assert "uncertain guess" in joined
        assert "2023-2024" in joined

    def test_call_gemini_does_not_mark_season_uncertain_when_confidence_high(self):
        prompt_input = sku_agent._build_input_lines(
            "FN8792-010", "FC Barcelona", "2023-2024", "Nike", "wyjazdowa", "high",
        )
        joined = "\n".join(prompt_input)
        assert "uncertain guess" not in joined
        assert "Season: 2023-2024" in joined

    def test_call_gemini_does_not_mark_season_uncertain_when_confidence_missing(self):
        """Brak season_confidence (starsze raporty sprzed tego pola) — nie
        blokuje ani nie oznacza niepewności domyślnie; zachowuje się jak
        przed tym fixem."""
        prompt_input = sku_agent._build_input_lines(
            "FN8792-010", "FC Barcelona", "2023-2024", "Nike", "wyjazdowa", None,
        )
        joined = "\n".join(prompt_input)
        assert "uncertain guess" not in joined
        assert "Season: 2023-2024" in joined


class TestSkuVerificationHelpers:
    def test_not_applicable_returns_safe_shape(self):
        result = _not_applicable()
        assert result["status"] == "not_applicable"
        assert "confidence" in result

    def test_fallback_returns_safe_shape(self):
        result = _fallback()
        assert result["status"] == "uncertain"
        assert result["confidence"] == "low"

    def test_fallback_returns_a_copy_not_shared_mutable_dict(self):
        """_FALLBACK jest modułowym stałym dict-em — _fallback() musi zwracać
        kopię, inaczej mutacja jednego wyniku wyciekłaby do kolejnych wywołań."""
        a = _fallback()
        a["status"] = "mutated"
        b = _fallback()
        assert b["status"] == "uncertain"


class TestRunSkipsIllegiblePlaceholder:
    """Regresja na incydent 2026-09-05 (Pedri, case 50f59024) — patrz docstring
    modułu. subject.sku="nieczytelne" (dosłowny placeholder z prompt_a.txt, nie
    prawdziwy kod) musi być rozpoznany PRZED odpaleniem realnego wyszukiwania,
    inaczej Gemini dostaje bezsensowny string jako "kod SKU do sprawdzenia" i
    zwraca format_invalid (twardy override na podróbkę) zamiast poprawnego
    "nie mamy danych do weryfikacji"."""

    def test_nieczytelne_sku_returns_not_applicable_without_calling_gemini(self):
        result = asyncio.run(sku_agent._run({"subject": {"sku": "nieczytelne"}}))
        assert result["status"] == "not_applicable"

    def test_nieczytelny_masculine_variant_also_returns_not_applicable(self):
        result = asyncio.run(sku_agent._run({"subject": {"sku": "nieczytelny"}}))
        assert result["status"] == "not_applicable"

    def test_case_insensitive(self):
        result = asyncio.run(sku_agent._run({"subject": {"sku": "NIECZYTELNE"}}))
        assert result["status"] == "not_applicable"

    def test_nieustalone_still_works_no_regression(self):
        result = asyncio.run(sku_agent._run({"subject": {"sku": "nieustalone"}}))
        assert result["status"] == "not_applicable"

    def test_missing_sku_key_returns_not_applicable(self):
        result = asyncio.run(sku_agent._run({"subject": {}}))
        assert result["status"] == "not_applicable"
