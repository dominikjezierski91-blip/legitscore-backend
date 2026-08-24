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
"""
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

    def test_json_schema_still_lists_all_five_statuses(self):
        """Tani strażnik przed przypadkowym usunięciem wartości ze schematu
        przy przyszłych edycjach promptu."""
        for status in ["found_official", "found_authorized", "found_unofficial", "not_found", "format_invalid"]:
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
