"""
Testy integracji eBay Browse API w market_value_agent.py.
Uruchom: pytest tests/test_market_value_agent.py -v

Wszystkie testy mockują httpx — brak realnych wywołań sieciowych.
"""
import asyncio
from unittest.mock import patch

import pytest

from app.services import market_value_agent as mva


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def reset_ebay_token_state():
    """Cache tokena jest module-level — resetujemy przed/po każdym teście, żeby testy się nie zanieczyszczały."""
    mva._ebay_token_cache["token"] = None
    mva._ebay_token_cache["expires_at"] = 0.0
    mva._ebay_token_lock = None
    yield
    mva._ebay_token_cache["token"] = None
    mva._ebay_token_cache["expires_at"] = 0.0
    mva._ebay_token_lock = None


class FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._json


class FakeAsyncClient:
    """Emuluje httpx.AsyncClient jako async context manager z get()/post()."""

    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, **kwargs):
        return self._response

    async def get(self, url, **kwargs):
        return self._response


class TestOAuthToken:
    def test_missing_credentials_returns_none_without_network_call(self, monkeypatch):
        monkeypatch.delenv("EBAY_APP_ID", raising=False)
        monkeypatch.delenv("EBAY_CERT_ID_PRD", raising=False)
        with patch("httpx.AsyncClient") as mock_client:
            token = run(mva._get_ebay_oauth_token())
        assert token is None
        mock_client.assert_not_called()

    def test_fetches_and_caches_token(self, monkeypatch):
        monkeypatch.setenv("EBAY_APP_ID", "app-id")
        monkeypatch.setenv("EBAY_CERT_ID_PRD", "cert-id")
        response = FakeResponse({"access_token": "tok123", "expires_in": 7200})
        with patch("httpx.AsyncClient", side_effect=lambda **kw: FakeAsyncClient(response)) as mock_client:
            token1 = run(mva._get_ebay_oauth_token())
            token2 = run(mva._get_ebay_oauth_token())
        assert token1 == "tok123"
        assert token2 == "tok123"
        # druga wywołanie musi trafić w cache, nie odpalić kolejnego requestu
        assert mock_client.call_count == 1

    def test_refetches_after_cache_expiry(self, monkeypatch):
        monkeypatch.setenv("EBAY_APP_ID", "app-id")
        monkeypatch.setenv("EBAY_CERT_ID_PRD", "cert-id")
        mva._ebay_token_cache["token"] = "stale-token"
        mva._ebay_token_cache["expires_at"] = 0.0  # już wygasł
        response = FakeResponse({"access_token": "fresh-token", "expires_in": 7200})
        with patch("httpx.AsyncClient", side_effect=lambda **kw: FakeAsyncClient(response)):
            token = run(mva._get_ebay_oauth_token())
        assert token == "fresh-token"

    def test_http_error_returns_none(self, monkeypatch):
        monkeypatch.setenv("EBAY_APP_ID", "app-id")
        monkeypatch.setenv("EBAY_CERT_ID_PRD", "cert-id")
        response = FakeResponse({}, status_code=401)
        with patch("httpx.AsyncClient", side_effect=lambda **kw: FakeAsyncClient(response)):
            token = run(mva._get_ebay_oauth_token())
        assert token is None

    def test_missing_access_token_in_response_returns_none(self, monkeypatch):
        monkeypatch.setenv("EBAY_APP_ID", "app-id")
        monkeypatch.setenv("EBAY_CERT_ID_PRD", "cert-id")
        response = FakeResponse({"error": "invalid_client"})
        with patch("httpx.AsyncClient", side_effect=lambda **kw: FakeAsyncClient(response)):
            token = run(mva._get_ebay_oauth_token())
        assert token is None


class TestSearchEbayMarketplace:
    def test_parses_valid_items_and_skips_malformed(self):
        items = {
            "itemSummaries": [
                {"title": "Valid Item", "price": {"value": "25.50", "currency": "GBP"}},
                {"title": "Zero price", "price": {"value": "0", "currency": "GBP"}},
                {"title": "Missing price field"},
                {"title": "Non-numeric value", "price": {"value": "abc", "currency": "GBP"}},
                {"title": "Missing currency defaults to GBP", "price": {"value": "10"}},
            ]
        }
        with patch("httpx.AsyncClient", side_effect=lambda **kw: FakeAsyncClient(FakeResponse(items))):
            listings = run(mva._search_ebay_marketplace("query", "faketoken", "EBAY_GB"))

        titles = {l["title"] for l in listings}
        assert titles == {"Valid Item", "Missing currency defaults to GBP"}

        valid = next(l for l in listings if l["title"] == "Valid Item")
        assert valid["currency_original"] == "GBP"
        assert valid["price_original"] == 25.50
        assert valid["price_pln"] == mva.to_pln(25.50, "GBP")

        no_currency = next(l for l in listings if l["title"] == "Missing currency defaults to GBP")
        assert no_currency["currency_original"] == "GBP"

    def test_no_items_key_returns_empty(self):
        with patch("httpx.AsyncClient", side_effect=lambda **kw: FakeAsyncClient(FakeResponse({}))):
            listings = run(mva._search_ebay_marketplace("query", "faketoken", "EBAY_GB"))
        assert listings == []

    def test_http_error_returns_empty_not_raises(self):
        with patch("httpx.AsyncClient", side_effect=lambda **kw: FakeAsyncClient(FakeResponse({}, status_code=500))):
            listings = run(mva._search_ebay_marketplace("query", "faketoken", "EBAY_GB"))
        assert listings == []


class TestEstimateViaEbayBrowse:
    def test_no_token_returns_empty(self, monkeypatch):
        monkeypatch.delenv("EBAY_APP_ID", raising=False)
        monkeypatch.delenv("EBAY_CERT_ID_PRD", raising=False)
        listings = run(mva.estimate_via_ebay_browse("query"))
        assert listings == []

    def test_aggregates_across_marketplaces(self):
        async def fake_get_token():
            return "tok"

        async def fake_search(query, token, marketplace):
            return [{"source": "ebay", "price_pln": 100, "title": marketplace}]

        with patch.object(mva, "_get_ebay_oauth_token", fake_get_token), \
             patch.object(mva, "_search_ebay_marketplace", fake_search):
            listings = run(mva.estimate_via_ebay_browse("query"))

        assert len(listings) == len(mva._EBAY_MARKETPLACES)
        assert {l["title"] for l in listings} == set(mva._EBAY_MARKETPLACES)

    def test_one_marketplace_failing_does_not_break_others(self):
        async def fake_get_token():
            return "tok"

        async def fake_search(query, token, marketplace):
            if marketplace == mva._EBAY_MARKETPLACES[0]:
                raise RuntimeError("simulated network failure")
            return [{"source": "ebay", "price_pln": 50, "title": marketplace}]

        with patch.object(mva, "_get_ebay_oauth_token", fake_get_token), \
             patch.object(mva, "_search_ebay_marketplace", fake_search):
            listings = run(mva.estimate_via_ebay_browse("query"))

        assert len(listings) == len(mva._EBAY_MARKETPLACES) - 1


class TestBuildEbaySearchQuery:
    """Regresja na case 20260903-238a181d (PSG/Messi): pełne, wielojęzyczne
    zapytanie (build_search_query) nie znajdowało realnej, aktywnej oferty
    użytkownika (1500 PLN) na eBay — krótsze, samo-angielskie zapytanie
    (klub/sezon/gracza/numer/marka, bez wariantu, kategorii werdyktu i
    polskiego 'koszulka piłkarska') znajdowało ją od razu."""

    def test_includes_only_club_season_brand_player_number(self):
        report_data = {
            "subject": {
                "club": "Paris Saint-Germain", "season": "2022/23", "brand": "Nike",
                "model": "wyjazdowa", "player_name": "Messi", "player_number": "30",
            },
            "verdict": {"verdict_category": "meczowa"},
        }
        query = mva.build_ebay_search_query(report_data)
        assert query == "Paris Saint-Germain 2022/23 Nike Messi #30"

    def test_excludes_model_variant(self):
        report_data = {"subject": {"club": "Bayern", "model": "domowa"}, "verdict": {}}
        query = mva.build_ebay_search_query(report_data)
        assert "domowa" not in query

    def test_excludes_verdict_category_term(self):
        report_data = {"subject": {"club": "Bayern"}, "verdict": {"verdict_category": "meczowa"}}
        query = mva.build_ebay_search_query(report_data)
        assert "match worn" not in query
        assert "meczowa" not in query

    def test_excludes_polish_suffix(self):
        report_data = {"subject": {"club": "Bayern"}, "verdict": {}}
        query = mva.build_ebay_search_query(report_data)
        assert "koszulka" not in query

    def test_missing_fields_skipped_like_build_search_query(self):
        report_data = {"subject": {"club": "Bayern"}, "verdict": {}}
        assert mva.build_ebay_search_query(report_data) == "Bayern"

    def test_empty_subject_returns_empty_string(self):
        assert mva.build_ebay_search_query({"subject": {}, "verdict": {}}) == ""


class TestEbayMarketplaces:
    def test_includes_poland(self):
        """Regresja: realna aktywna oferta usera (1500 PLN, case 20260903-238a181d)
        była wystawiona na ebay.pl i nigdy nie pojawiała się w wynikach, bo
        EBAY_PL nie był przeszukiwany (tylko GB/DE/US)."""
        assert "EBAY_PL" in mva._EBAY_MARKETPLACES


class TestFilterListingsByCategory:
    def test_no_filter_defined_for_category_returns_unchanged(self):
        listings = [{"title": "replica jersey"}]
        assert mva._filter_listings_by_category(listings, "edycja_limitowana") == listings

    def test_unknown_or_empty_category_returns_unchanged(self):
        listings = [{"title": "replica jersey"}]
        assert mva._filter_listings_by_category(listings, "") == listings

    def test_meczowa_excludes_replica_titles(self):
        listings = [
            {"title": "Match worn player issue jersey", "price_pln": 800},
            {"title": "Official replica jersey", "price_pln": 100},
            {"title": "Fan version shirt", "price_pln": 90},
        ]
        result = mva._filter_listings_by_category(listings, "meczowa")
        assert len(result) == 1
        assert result[0]["price_pln"] == 800

    def test_oryginalna_sklepowa_excludes_match_worn_and_replica(self):
        listings = [
            {"title": "Authentic retail jersey", "price_pln": 250},
            {"title": "Match worn player issue jersey", "price_pln": 800},
            {"title": "Official replica jersey", "price_pln": 100},
        ]
        result = mva._filter_listings_by_category(listings, "oryginalna_sklepowa")
        assert len(result) == 1
        assert result[0]["price_pln"] == 250

    def test_case_insensitive_matching(self):
        listings = [{"title": "MATCH WORN Player Issue Jersey", "price_pln": 800}]
        result = mva._filter_listings_by_category(listings, "oryginalna_sklepowa")
        assert result == []

    def test_missing_title_does_not_crash(self):
        listings = [{"price_pln": 100}]
        result = mva._filter_listings_by_category(listings, "meczowa")
        assert result == listings

    def test_oryginalna_sklepowa_excludes_fan_edition(self):
        """Regresja: 'fan edition' był w liście wykluczeń dla 'meczowa', ale brakowało
        go dla 'oryginalna_sklepowa' — oferta replikowa nazwana 'Fan Edition' zaniżałaby
        medianę oryginalnej koszulki sklepowej bez tego wykluczenia."""
        listings = [{"title": "Fan Edition Jersey 23/24", "price_pln": 90}]
        result = mva._filter_listings_by_category(listings, "oryginalna_sklepowa")
        assert result == []


class TestParseSeasonPair:
    def test_full_year_slash_format(self):
        assert mva._parse_season_pair("Bayern Munich 2015/2016 Home Shirt") == (2015, 2016)

    def test_full_year_dash_format(self):
        assert mva._parse_season_pair("2015-2016 shirt") == (2015, 2016)

    def test_short_year_format(self):
        assert mva._parse_season_pair("15/16 kit") == (2015, 2016)

    def test_no_season_returns_none(self):
        assert mva._parse_season_pair("BAYERN MUNICH ADIDAS SIZE M ADULT RIBERY 7") is None

    def test_reversed_years_returns_none(self):
        """Para w kolejności malejącej to nie sezon (np. przypadkowy zakres numerów)."""
        assert mva._parse_season_pair("2016/2015") is None

    def test_skips_kids_clothing_size_range_and_finds_real_season(self):
        """Regresja złapana przez code review: '104/110' (rozmiarówka dziecięca,
        EU height-based sizing) pasuje do regexu pary liczb, ale nie jest sezonem
        — funkcja musi ją pominąć i znaleźć właściwą parę lat dalej w tytule,
        zamiast fałszywie zwrócić (104, 110) i odrzucić poprawnie dopasowaną ofertę."""
        title = "Kids 104/110 Bayern Munich Home Shirt 2015/2016 Adidas"
        assert mva._parse_season_pair(title) == (2015, 2016)

    def test_pure_clothing_size_range_with_no_real_season_returns_none(self):
        assert mva._parse_season_pair("Kids football shirt size 104/110") is None


class TestFilterListingsByRelevance:
    def test_no_season_no_model_returns_unchanged(self):
        listings = [{"title": "Bayern Munich 2018/2019 Away Shirt", "price_pln": 200}]
        assert mva._filter_listings_by_relevance(listings, {}) == listings

    def test_rejects_wrong_season_case_from_real_incident(self):
        """Regresja na case 20260902-6d29c75e (Bayern/Ribéry 2015/2016): query
        eBay zwracał koszulki z zupełnie innych sezonów tego samego klubu,
        rozmywając medianę w dół (mediana 234 PLN zamiast realnych ~680 PLN)."""
        listings = [
            {"title": "BAYERN MUNICH GERMANY 2015/2016 HOME FOOTBALL SHIRT JERSEY ADIDAS", "price_pln": 585},
            {"title": "Bayern Munich 2018 - 2019 Home football Adidas shirt size XL", "price_pln": 214},
            {"title": "FC Bayern 2014/2015 Home Jersey DFB-Pokal Final Size Large", "price_pln": 254},
            {"title": "BAYERN MUNICH 2008/2009 AWAY FOOTBALL SHIRT ADIDAS #7 RIBERY", "price_pln": 431},
            {"title": "BAYERN MUNICH GERMANY 2015/2016 HOME FOOTBALL SHIRT JERSEY ADIDAS", "price_pln": 780},
        ]
        subject = {"season": "2015/2016", "model": "domowa"}
        result = mva._filter_listings_by_relevance(listings, subject)
        assert {l["price_pln"] for l in result} == {585, 780}

    def test_keeps_listings_without_season_in_title(self):
        """Brak sezonu w tytule to brak informacji, nie sprzeczność — oferta zostaje."""
        listings = [{"title": "Bayern Munich Home Shirt Adidas Ribery 7", "price_pln": 500}]
        result = mva._filter_listings_by_relevance(listings, {"season": "2015/2016"})
        assert result == listings

    def test_rejects_conflicting_kit_type(self):
        listings = [
            {"title": "Bayern Munich Home Shirt", "price_pln": 500},
            {"title": "Bayern Munich Away Shirt", "price_pln": 150},
            {"title": "Bayern Munich Third Kit", "price_pln": 180},
        ]
        result = mva._filter_listings_by_relevance(listings, {"model": "domowa"})
        assert result == [{"title": "Bayern Munich Home Shirt", "price_pln": 500}]

    def test_keeps_listings_without_kit_type_in_title(self):
        listings = [{"title": "Bayern Munich Shirt Adidas Ribery 7", "price_pln": 500}]
        result = mva._filter_listings_by_relevance(listings, {"model": "wyjazdowa"})
        assert result == listings

    def test_unknown_model_value_skips_kit_type_filter(self):
        listings = [{"title": "Bayern Munich Away Shirt", "price_pln": 150}]
        result = mva._filter_listings_by_relevance(listings, {"model": "nieustalone"})
        assert result == listings

    def test_missing_title_does_not_crash(self):
        listings = [{"price_pln": 100}]
        result = mva._filter_listings_by_relevance(listings, {"season": "2015/2016", "model": "domowa"})
        assert result == listings


class TestSourceScore:
    def test_ebay_scores_08(self):
        assert mva._source_score({"source": "ebay"}) == mva._SOURCE_SCORE_EBAY

    def test_vinted_scores_06(self):
        assert mva._source_score({"source": "Vinted.pl oferta"}) == mva._SOURCE_SCORE_VINTED_ALLEGRO

    def test_allegro_scores_06(self):
        assert mva._source_score({"source": "Allegro"}) == mva._SOURCE_SCORE_VINTED_ALLEGRO

    def test_generic_gemini_scores_05(self):
        assert mva._source_score({"source": "gemini"}) == mva._SOURCE_SCORE_GEMINI_GENERIC
        assert mva._source_score({"source": "Autoryzowani sprzedawcy Nike"}) == mva._SOURCE_SCORE_GEMINI_GENERIC

    def test_missing_source_defaults_to_generic(self):
        assert mva._source_score({}) == mva._SOURCE_SCORE_GEMINI_GENERIC


class TestTitleComponents:
    def test_club_found_scores_full(self):
        assert mva._title_club_component("bayern munich home shirt", {"club": "Bayern Monachium"}) == 1.0

    def test_club_missing_from_title_scores_low(self):
        """0.2, nie 0.5 (code review 2026-09-04) — brak klubu w tytule w ogóle
        to mocny sygnał złego dopasowania, nie powinien ledwo obniżać wyniku."""
        assert mva._title_club_component("home shirt size m", {"club": "Bayern Monachium"}) == 0.2

    def test_no_declared_club_scores_full(self):
        assert mva._title_club_component("some shirt", {}) == 1.0
        assert mva._title_club_component("some shirt", {"club": "nieustalone"}) == 1.0

    def test_club_with_diacritics_matches_ascii_title(self):
        """Realny przypadek: subject ma spolszczoną/z diakrytykami nazwę,
        tytuł oferty (angielski) jej nie ma."""
        assert mva._title_club_component("cubarsi barcelona jersey", {"club": "FC Barcelona"}) == 1.0

    def test_polish_l_with_stroke_normalized(self):
        """Regresja z code review 2026-09-04: 'ł'/'Ł' to samodzielna litera w
        Unicode bez dekompozycji NFKD (w przeciwieństwie do ą/ć/ę/ń/ó/ś/ź/ż) —
        _strip_diacritics musi ją jawnie mapować, inaczej "Łukasz"/"Michałowski"
        nie dopasowałyby się do angielskiego tytułu bez ogonka."""
        assert mva._strip_diacritics("łukasz") == "lukasz"
        assert mva._strip_diacritics("michałowski") == "michalowski"
        assert mva._title_player_component("borussia michalowski jersey", {"player_name": "Michałowski"}) == 1.0

    def test_player_name_found_scores_full(self):
        assert mva._title_player_component("psg messi #30 jersey", {"player_name": "Messi"}) == 1.0

    def test_player_name_with_diacritics_matches_ascii_title(self):
        """Ribéry (subject, z akcentem) vs 'RIBERY' (tytuł, bez akcentu) —
        realny przypadek z case'u Bayern/Ribéry. Bez normalizacji diakrytyków
        to dopasowanie zawodziłoby mimo że to oczywiście ta sama osoba."""
        assert mva._title_player_component("bayern munich ribery jersey", {"player_name": "Ribéry"}) == 1.0
        # Caller (_match_score) zawsze przekazuje już zlowercase'owany tytuł.
        assert mva._title_player_component("bayern ribery 7".lower(), {"player_name": "Ribéry"}) == 1.0

    def test_player_number_found_scores_full(self):
        assert mva._title_player_component("psg jersey #30", {"player_name": "Messi", "player_number": "30"}) == 1.0

    def test_player_number_variants_no_dot_and_nr(self):
        assert mva._title_player_component("psg jersey no.30", {"player_name": "Messi", "player_number": "30"}) == 1.0
        assert mva._title_player_component("psg jersey no 30", {"player_name": "Messi", "player_number": "30"}) == 1.0
        assert mva._title_player_component("psg jersey nr 30", {"player_name": "Messi", "player_number": "30"}) == 1.0

    def test_player_number_does_not_false_match_unrelated_digits(self):
        """Rozmiar/cena zawierające tę samą cyfrę bez #/no./nr nie powinny
        fałszywie liczyć się jako dopasowanie numeru zawodnika."""
        assert mva._title_player_component("psg jersey size 30 EUR", {"player_name": "Messi", "player_number": "30"}) == 0.7

    def test_player_number_does_not_match_as_substring_of_longer_word(self):
        """Regresja z code review 2026-09-04: brak lewej granicy przed prefiksem
        '#'/'no'/'nr' pozwalał dopasować "no.7" jako podciąg dłuższego słowa,
        np. "piano.7" ("pia" + "no.7"). Wymaga jawnie znanego numeru, żeby test
        w ogóle dotarł do gałęzi sprawdzającej numer (player_name musi NIE
        występować w tytule, inaczej component=1.0 wcześniej)."""
        subject = {"player_name": "Mbappe", "player_number": "7"}
        assert mva._title_player_component("psg piano.7 jersey", subject) == 0.7

    def test_player_number_does_not_match_as_substring_of_longer_number(self):
        """#17 nie powinno fałszywie dopasować player_number='7' (chroni \\b po
        liczbie — 17 to jeden token cyfrowy, nie '1' + granica + '7')."""
        subject = {"player_name": "Mbappe", "player_number": "7"}
        assert mva._title_player_component("psg jersey #17", subject) == 0.7
        assert mva._title_player_component("psg jersey #7", subject) == 1.0

    def test_player_not_found_scores_penalty(self):
        assert mva._title_player_component("psg home jersey size m", {"player_name": "Messi"}) == 0.7

    def test_no_declared_player_scores_full(self):
        assert mva._title_player_component("some shirt", {}) == 1.0


class TestMatchScore:
    """Regresja na powtarzający się wzorzec (Bayern/Ribéry, PSG/Messi,
    Barcelona/Cubarsí) — patrz _filter_listings_by_category/_filter_listings_by_relevance
    (wołane PRZED _match_score w estimate_market_value, nie testowane tu ponownie).
    match_score sam w sobie to blend dopasowania tytułu i wiarygodności źródła,
    dla ofert które JUŻ przeszły twarde bramki."""

    def test_ebay_full_match_passes_threshold_comfortably(self):
        score = mva._match_score(
            {"source": "ebay", "title": "Bayern Munich Ribery jersey"},
            {"club": "Bayern Monachium", "player_name": "Ribery"},
        )
        assert score >= mva._MATCH_MIN
        assert score == 0.92  # 0.6*1.0 (title) + 0.4*0.8 (ebay)

    def test_gemini_full_title_match_passes_threshold(self):
        score = mva._match_score(
            {"source": "gemini", "title": "Bayern Munich Ribery jersey"},
            {"club": "Bayern Monachium", "player_name": "Ribery"},
        )
        assert score >= mva._MATCH_MIN
        assert score == 0.8  # 0.6*1.0 + 0.4*0.5

    def test_ebay_completely_unrelated_title_fails_threshold(self):
        """Regresja na HIGH z code review 2026-09-04: przy wagach 50/50 i karze
        0.5 za brak klubu, match_score dla eBay przechodził próg ZAWSZE,
        niezależnie od treści tytułu (matematyczna bezwładność) — sam
        match_score nic nie filtrował dla dominującego źródła. Kompletnie
        niedopasowany tytuł (brak klubu I zawodnika) musi teraz odpaść nawet
        dla eBay."""
        score = mva._match_score(
            {"source": "ebay", "title": "random unrelated football shirt size L"},
            {"club": "Bayern Monachium", "player_name": "Ribery"},
        )
        assert score < mva._MATCH_MIN

    def test_ebay_club_present_personalization_absent_still_passes(self):
        """Legalny, częsty przypadek (personalizacja pominięta w tytule) nadal
        ma komfortowo przechodzić, mimo zaostrzenia progu wyżej."""
        score = mva._match_score(
            {"source": "ebay", "title": "Bayern Munich home shirt 2015/16 size M"},
            {"club": "Bayern Monachium", "player_name": "Ribery"},
        )
        assert score >= mva._MATCH_MIN

    def test_gemini_weak_title_match_fails_threshold(self):
        """Gemini to źródło pomocnicze — słabe dopasowanie tytułu (brak klubu
        i zawodnika w tytule) nie powinno przejść progu, w przeciwieństwie do eBay."""
        score = mva._match_score(
            {"source": "gemini", "title": "football shirt size M"},
            {"club": "Bayern Monachium", "player_name": "Ribery"},
        )
        assert score < mva._MATCH_MIN

    def test_no_subject_constraints_always_passes(self):
        score = mva._match_score({"source": "ebay", "title": "anything"}, {})
        assert score >= mva._MATCH_MIN


class TestComputeConfidence:
    def test_high_needs_3_plus_and_tight_spread(self):
        assert mva._compute_confidence(3, 0.35) == "high"
        assert mva._compute_confidence(5, 0.1) == "high"

    def test_wide_spread_with_3_plus_is_medium(self):
        assert mva._compute_confidence(3, 0.5) == "medium"
        assert mva._compute_confidence(3, 0.36) == "medium"

    def test_exactly_2_is_medium_regardless_of_spread(self):
        assert mva._compute_confidence(2, 0.9) == "medium"
        assert mva._compute_confidence(2, 0.0) == "medium"

    def test_very_wide_spread_with_3_plus_is_low(self):
        assert mva._compute_confidence(3, 0.61) == "low"

    def test_0_or_1_is_always_low(self):
        assert mva._compute_confidence(0, 0.0) == "low"
        assert mva._compute_confidence(1, 0.0) == "low"


class TestEstimateFromMatched:
    def test_empty_returns_zero_matched(self):
        assert mva._estimate_from_matched([]) == {
            "price": None, "low": None, "high": None,
            "matched_count": 0, "confidence": "low", "listings": [],
        }

    def test_listings_without_price_treated_as_empty(self):
        result = mva._estimate_from_matched([{"title": "no price"}])
        assert result["matched_count"] == 0
        assert result["confidence"] == "low"

    def test_single_listing_low_confidence_price_equals_range(self):
        result = mva._estimate_from_matched([{"price_pln": 250, "title": "jedyna"}])
        assert result == {
            "price": 250, "low": 250, "high": 250,
            "matched_count": 1, "confidence": "low",
            "listings": [{"price_pln": 250, "title": "jedyna"}],
        }

    def test_tight_cluster_of_3_is_high_confidence(self):
        listings = [{"price_pln": p, "title": str(p)} for p in [460, 470, 480]]
        result = mva._estimate_from_matched(listings)
        assert result["matched_count"] == 3
        assert result["confidence"] == "high"
        assert result["price"] == 470

    def test_wide_spread_cluster_is_medium_or_low_not_high(self):
        listings = [{"price_pln": p, "title": str(p)} for p in [100, 500, 900]]
        result = mva._estimate_from_matched(listings)
        assert result["confidence"] != "high"

    def test_listings_key_reflects_all_matched_not_a_subset(self):
        """Inaczej niż stara _top_offers_stats (tylko top-3) — teraz WSZYSTKIE
        dopasowane oferty wchodzą do estymaty, jakość jest wymuszona wcześniej
        przez match_score, nie przez branie kilku najdrożej wycenionych."""
        listings = [{"price_pln": p, "title": str(p)} for p in [100, 200, 300, 400, 500]]
        result = mva._estimate_from_matched(listings)
        assert result["matched_count"] == 5
        assert len(result["listings"]) == 5


class TestShouldUpdateMarketValue:
    """Regresja na case Barcelona/Cubarsí i Bayern/Ribéry (2026-09-03/04):
    stara reguła ('nie aktualizuj gdy odchylenie > próg') blokowała też
    KOREKTĘ starej błędnej wartości silną, nową próbką — nie było jak
    odróżnić 'nowa wartość to szum' od 'stara wartość była błędem'. Nowa
    reguła: decyzja zależy od JAKOŚCI nowej próbki (confidence), nie samego
    odchylenia. Spec 2026-09-03 §7."""

    def test_blocks_when_no_matched_listings(self):
        assert mva.should_update_market_value(470, "high", None, "low", 0) is False

    def test_high_confidence_updates_unconditionally_even_with_huge_deviation(self):
        """Ribéry: stored 185 (stare, błędne); nowe 365 z solidnej (high) próbki
        — MUSI się zaktualizować mimo ~97% odchylenia."""
        assert mva.should_update_market_value(185, "low", 365, "high", 3) is True

    def test_high_confidence_corrects_bad_stored_value(self):
        """Cubarsí: stored 168 (low, błędne); nowe 608 (high) — aktualizacja."""
        assert mva.should_update_market_value(168, "low", 608, "high", 3) is True

    def test_high_confidence_updates_with_no_prior_value(self):
        assert mva.should_update_market_value(None, None, 470, "high", 3) is True

    def test_medium_confidence_updates_within_deviation_tolerance(self):
        assert mva.should_update_market_value(470, "high", 420, "medium", 3) is True

    def test_medium_confidence_blocked_by_large_deviation_from_stronger_stored(self):
        assert mva.should_update_market_value(470, "high", 168, "medium", 2) is False

    def test_medium_confidence_updates_large_deviation_when_stored_not_stronger(self):
        assert mva.should_update_market_value(470, "medium", 168, "medium", 2) is True
        assert mva.should_update_market_value(470, "low", 168, "medium", 2) is True
        assert mva.should_update_market_value(None, None, 168, "medium", 2) is True

    def test_low_confidence_single_offer_does_not_override_stronger_stored(self):
        """Skok z 1 losowej oferty przy solidnej stored (high/medium) — NIE nadpisuje."""
        assert mva.should_update_market_value(470, "high", 100, "low", 1) is False
        assert mva.should_update_market_value(470, "medium", 100, "low", 1) is False

    def test_low_confidence_updates_when_stored_also_low_or_empty(self):
        assert mva.should_update_market_value(168, "low", 200, "low", 1) is True
        assert mva.should_update_market_value(None, None, 200, "low", 1) is True

    def test_unknown_stored_confidence_with_existing_price_not_treated_as_low(self):
        """Regresja na HIGH z code review 2026-09-04: zaraz po migracji
        (market_value_confidence dopiero dodane) WSZYSTKIE istniejące pozycje
        mają stored_price ustawione ale stored_confidence=None — domyślne
        traktowanie None jako 'low' pozwalało pojedynczej słabej ofercie
        nadpisać realną, wcześniej ustaloną cenę (dokładnie wzorzec Cubarsí,
        odtworzony przez lukę w kolejności wdrożenia zamiast przez dane).
        None ma być traktowane jak 'medium' — low NIE powinno nadpisać."""
        assert mva.should_update_market_value(470, None, 120, "low", 1) is False

    def test_unknown_stored_confidence_still_updatable_by_medium_within_tolerance(self):
        assert mva.should_update_market_value(470, None, 450, "medium", 2) is True

    def test_blocks_when_new_price_is_none(self):
        assert mva.should_update_market_value(470, "low", None, "low", 3) is False


class TestEstimateMarketValueBlending:
    def test_prefers_ebay_over_gemini_when_ebay_alone_reaches_high_confidence(self):
        """eBay to realne, zweryfikowane dane API — jeśli sama daje confidence
        'high' (n>=3, wąski rozrzut), Gemini w ogóle nie jest wołane i nie
        wpływa na wynik."""
        async def fake_gemini(report_data):
            return {"listings": [{"source": "gemini", "price_pln": 100, "title": "koszulka"}]}

        async def fake_ebay(query):
            return [
                {"source": "ebay", "price_pln": 460, "title": "jersey"},
                {"source": "ebay", "price_pln": 470, "title": "jersey"},
                {"source": "ebay", "price_pln": 480, "title": "jersey"},
            ]

        with patch.object(mva, "estimate_via_gemini", fake_gemini), \
             patch.object(mva, "estimate_via_ebay_browse", fake_ebay):
            result = run(mva.estimate_market_value({"subject": {}, "verdict": {}}))

        assert result["source"] == "ebay"
        assert result["confidence"] == "high"
        assert result["matched_count"] == 3
        assert all(l["source"] == "ebay" for l in result["listings"])

    def test_falls_back_to_gemini_only_when_ebay_empty(self):
        async def fake_gemini(report_data):
            return {"listings": [{"source": "gemini", "price_pln": 100, "title": "koszulka"}]}

        async def fake_ebay(query):
            return []

        with patch.object(mva, "estimate_via_gemini", fake_gemini), \
             patch.object(mva, "estimate_via_ebay_browse", fake_ebay):
            result = run(mva.estimate_market_value({"subject": {}, "verdict": {}}))

        assert result["source"] == "gemini"
        assert result["matched_count"] == 1

    def test_falls_back_to_gemini_when_all_ebay_listings_filtered_out_by_category(self):
        """eBay zwraca wyniki, ale wszystkie odfiltrowane jako zły tier
        (replica przy koszulce meczowej) — musi spaść na Gemini, nie zwrócić
        pustego wyniku mimo że Gemini ma dobre dane."""
        async def fake_gemini(report_data):
            return {"listings": [{"source": "gemini", "price_pln": 500, "title": "match worn jersey"}]}

        async def fake_ebay(query):
            return [{"source": "ebay", "price_pln": 100, "title": "official replica jersey"}]

        with patch.object(mva, "estimate_via_gemini", fake_gemini), \
             patch.object(mva, "estimate_via_ebay_browse", fake_ebay):
            result = run(mva.estimate_market_value({"subject": {}, "verdict": {"verdict_category": "meczowa"}}))

        assert result["source"] == "gemini"
        assert result["matched_count"] == 1

    def test_category_filter_excludes_wrong_tier_from_ebay_but_keeps_matching(self):
        """Mieszanka pasujących i niepasujących ofert eBay dla koszulki meczowej —
        replica musi odpaść, match-worn zostać."""
        async def fake_gemini(report_data):
            return {"listings": []}

        async def fake_ebay(query):
            return [
                {"source": "ebay", "price_pln": 800, "title": "Match worn player issue jersey"},
                {"source": "ebay", "price_pln": 100, "title": "Official replica fan version"},
            ]

        with patch.object(mva, "estimate_via_gemini", fake_gemini), \
             patch.object(mva, "estimate_via_ebay_browse", fake_ebay):
            result = run(mva.estimate_market_value({"subject": {}, "verdict": {"verdict_category": "meczowa"}}))

        assert result["source"] == "ebay"
        assert result["matched_count"] == 1
        assert result["listings"][0]["price_pln"] == 800

    def test_gemini_not_called_when_ebay_alone_reaches_high_confidence(self):
        """Gemini Search Grounding kosztuje/ma limit — nie wołamy go wcale, jeśli
        eBay samodzielnie daje confidence='high'."""
        gemini_call_count = 0

        async def fake_gemini(report_data):
            nonlocal gemini_call_count
            gemini_call_count += 1
            return {"listings": []}

        async def fake_ebay(query):
            return [
                {"source": "ebay", "price_pln": 460, "title": "jersey"},
                {"source": "ebay", "price_pln": 470, "title": "jersey"},
                {"source": "ebay", "price_pln": 480, "title": "jersey"},
            ]

        with patch.object(mva, "estimate_via_gemini", fake_gemini), \
             patch.object(mva, "estimate_via_ebay_browse", fake_ebay):
            result = run(mva.estimate_market_value({"subject": {}, "verdict": {}}))

        assert gemini_call_count == 0, "Gemini nie powinno być wołane gdy eBay wystarczył samodzielnie"
        assert result["source"] == "ebay"
        assert result["confidence"] == "high"

    def test_lone_ebay_listing_below_high_confidence_combines_with_gemini(self):
        """Pojedyncza oferta eBay (matched_count=1, więc na pewno nie 'high')
        łączy się z danymi z Gemini zamiast być użyta samodzielnie."""
        async def fake_gemini(report_data):
            return {
                "listings": [
                    {"source": "gemini", "price_pln": 400, "title": "koszulka"},
                    {"source": "gemini", "price_pln": 450, "title": "koszulka"},
                    {"source": "gemini", "price_pln": 420, "title": "koszulka"},
                ],
            }

        async def fake_ebay(query):
            return [{"source": "ebay", "price_pln": 500, "title": "jersey"}]

        with patch.object(mva, "estimate_via_gemini", fake_gemini), \
             patch.object(mva, "estimate_via_ebay_browse", fake_ebay):
            result = run(mva.estimate_market_value({"subject": {}, "verdict": {}}))

        assert result["source"] == "ebay+gemini"
        assert result["matched_count"] == 4
        assert len(result["listings"]) == 4

    def test_lone_ebay_listing_with_no_gemini_data_is_low_confidence(self):
        """eBay ma tylko 1 ofertę, Gemini nie dorzuca nic (błąd/brak wyników/
        wszystko odfiltrowane) — combined ma wciąż tylko 1 element. Wynik musi
        zostać zwrócony (nie ukrywamy jedynej ceny), ale confidence MUSI być
        'low', żeby nie wyglądał identycznie jak wycena z solidną próbką."""
        async def fake_gemini(report_data):
            return {"listings": []}

        async def fake_ebay(query):
            return [{"source": "ebay", "price_pln": 500, "title": "jersey"}]

        with patch.object(mva, "estimate_via_gemini", fake_gemini), \
             patch.object(mva, "estimate_via_ebay_browse", fake_ebay):
            result = run(mva.estimate_market_value({"subject": {}, "verdict": {}}))

        assert result["source"] == "ebay"
        assert result["matched_count"] == 1
        assert result["confidence"] == "low"

    def test_ebay_called_with_short_query_not_full_gemini_query(self):
        """Regresja złapana przez review: rdzeń fixu #238a181d jest w tym, że do
        eBay leci build_ebay_search_query() (krótkie), nie build_search_query()
        (pełne, wielojęzyczne) — dotąd sprawdzone tylko jednostkowo dla samego
        build_ebay_search_query(), nie na poziomie integracji z estimate_market_value()."""
        captured_query = {}

        async def fake_gemini(report_data):
            return {"listings": [], "sample_size": 0}

        async def fake_ebay(query):
            captured_query["value"] = query
            return [
                {"source": "ebay", "price_pln": 200, "title": "Paris Saint-Germain Messi #30 jersey"},
                {"source": "ebay", "price_pln": 210, "title": "Paris Saint-Germain Messi #30 jersey"},
                {"source": "ebay", "price_pln": 220, "title": "Paris Saint-Germain Messi #30 jersey"},
            ]

        report_data = {
            "subject": {
                "club": "Paris Saint-Germain", "season": "2022/23", "brand": "Nike",
                "model": "wyjazdowa", "player_name": "Messi", "player_number": "30",
            },
            "verdict": {"verdict_category": "meczowa"},
        }
        with patch.object(mva, "estimate_via_gemini", fake_gemini), \
             patch.object(mva, "estimate_via_ebay_browse", fake_ebay):
            result = run(mva.estimate_market_value(report_data))

        assert captured_query["value"] == mva.build_ebay_search_query(report_data)
        assert captured_query["value"] == "Paris Saint-Germain 2022/23 Nike Messi #30"
        for forbidden in ("wyjazdowa", "meczowa", "koszulka", "match worn", "player issue"):
            assert forbidden not in captured_query["value"]
        assert result["query_used"] == captured_query["value"]

    def test_query_used_reflects_ebay_query_in_combined_path(self):
        """Regresja złapana przez review: w ścieżce eBay+Gemini, query_used
        pokazywał pełne zapytanie zbudowane dla Gemini nawet gdy source=="ebay"
        albo "ebay+gemini" — czyli nie odzwierciedlał tego co faktycznie
        wysłano do eBay. To samo pole posłużyło do zdiagnozowania oryginalnego
        buga (#238a181d), więc jego niespójność myliłaby przy przyszłym debugu."""
        async def fake_gemini(report_data):
            return {
                "listings": [{"source": "gemini", "price_pln": 400, "title": "Bayern koszulka"}],
                "sample_size": 1,
                "query_used": "pelne zapytanie gemini",
            }

        async def fake_ebay(query):
            return [{"source": "ebay", "price_pln": 500, "title": "Bayern jersey"}]

        report_data = {"subject": {"club": "Bayern"}, "verdict": {}}
        with patch.object(mva, "estimate_via_gemini", fake_gemini), \
             patch.object(mva, "estimate_via_ebay_browse", fake_ebay):
            result = run(mva.estimate_market_value(report_data))

        assert result["source"] == "ebay+gemini"
        ebay_query = mva.build_ebay_search_query(report_data)
        assert ebay_query in result["query_used"]
        assert "pelne zapytanie gemini" in result["query_used"]
