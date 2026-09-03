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


class TestRejectOutliers:
    def test_below_three_priced_listings_returns_unchanged(self):
        """Za mało danych, żeby bezpiecznie odróżnić odstającą cenę od
        normalnej wariancji — nawet ewidentnie dziwna cena zostaje."""
        listings = [
            {"price_pln": 200, "title": "a"},
            {"price_pln": 5000, "title": "b"},
        ]
        assert mva._reject_outliers(listings) == listings

    def test_rejects_price_far_from_median(self):
        listings = [
            {"price_pln": 200, "title": "a"},
            {"price_pln": 210, "title": "b"},
            {"price_pln": 220, "title": "c"},
            {"price_pln": 5000, "title": "d — inny produkt/żart"},
        ]
        result = mva._reject_outliers(listings)
        assert {l["title"] for l in result} == {"a", "b", "c"}

    def test_never_drops_below_two_listings(self):
        """Gdyby filtr zostawił mniej niż 2 oferty (bo cały rozrzut jest duży),
        lepiej pokazać wszystko niż zgadywać, co odrzucić."""
        listings = [
            {"price_pln": 100, "title": "a"},
            {"price_pln": 1000, "title": "b"},
            {"price_pln": 5000, "title": "c"},
        ]
        assert mva._reject_outliers(listings) == listings

    def test_ignores_listings_without_price(self):
        listings = [
            {"price_pln": 200, "title": "a"},
            {"price_pln": 210, "title": "b"},
            {"price_pln": 220, "title": "c"},
            {"title": "no price"},
        ]
        result = mva._reject_outliers(listings)
        assert {l["title"] for l in result} == {"a", "b", "c", "no price"}

    def test_normal_case_nothing_rejected(self):
        """Ceny blisko siebie (bez odstającej wartości) — filtr nie powinien
        niczego ruszyć, nawet mając wystarczająco dużo danych do aktywacji."""
        listings = [
            {"price_pln": 200, "title": "a"},
            {"price_pln": 210, "title": "b"},
            {"price_pln": 190, "title": "c"},
            {"price_pln": 205, "title": "d"},
        ]
        assert mva._reject_outliers(listings) == listings


class TestRecalculateStats:
    def test_empty_listings_returns_zero_sample_with_listings_key(self):
        assert mva._recalculate_stats([]) == {"sample_size": 0, "listings": []}

    def test_listings_without_price_returns_zero_sample(self):
        stats = mva._recalculate_stats([{"title": "no price"}])
        assert stats == {"sample_size": 0, "listings": []}

    def test_listings_key_reflects_outlier_rejection(self):
        """stats['listings'] musi odpowiadać dokładnie cenom użytym do mediany —
        inaczej odrzucony outlier nadal wyświetlałby się userowi na liście ofert."""
        listings = [
            {"price_pln": 200, "title": "a"},
            {"price_pln": 210, "title": "b"},
            {"price_pln": 220, "title": "c"},
            {"price_pln": 9000, "title": "outlier"},
        ]
        stats = mva._recalculate_stats(listings)
        assert stats["sample_size"] == 3
        assert {l["title"] for l in stats["listings"]} == {"a", "b", "c"}
        assert stats["median_pln"] == 210


class TestEstimateMarketValueBlending:
    def test_prefers_ebay_over_gemini_when_both_have_data(self):
        """eBay to realne, zweryfikowane dane API — ma priorytet nad Gemini,
        który tylko samoraportuje wyniki własnego wyszukiwania. Gdy eBay ma
        cokolwiek, wynik liczy się WYŁĄCZNIE z eBay, Gemini jest ignorowany."""
        async def fake_gemini(report_data):
            return {
                "listings": [{"source": "gemini", "price_pln": 100, "title": "koszulka"}],
                "sample_size": 1,
                "median_pln": 100,
                "source": "gemini",
            }

        async def fake_ebay(query):
            return [
                {"source": "ebay", "price_pln": 200, "title": "jersey"},
                {"source": "ebay", "price_pln": 250, "title": "jersey"},
                {"source": "ebay", "price_pln": 300, "title": "jersey"},
            ]

        with patch.object(mva, "estimate_via_gemini", fake_gemini), \
             patch.object(mva, "estimate_via_ebay_browse", fake_ebay):
            result = run(mva.estimate_market_value({"subject": {}, "verdict": {}}))

        assert result["source"] == "ebay"
        assert result["sample_size"] == 3
        assert len(result["listings"]) == 3
        assert all(l["source"] == "ebay" for l in result["listings"])

    def test_falls_back_to_gemini_only_when_ebay_empty(self):
        async def fake_gemini(report_data):
            return {
                "listings": [{"source": "gemini", "price_pln": 100, "title": "koszulka"}],
                "sample_size": 1,
                "median_pln": 100,
                "source": "gemini",
            }

        async def fake_ebay(query):
            return []

        with patch.object(mva, "estimate_via_gemini", fake_gemini), \
             patch.object(mva, "estimate_via_ebay_browse", fake_ebay):
            result = run(mva.estimate_market_value({"subject": {}, "verdict": {}}))

        assert result["source"] == "gemini"
        assert result["sample_size"] == 1

    def test_falls_back_to_gemini_when_all_ebay_listings_filtered_out_by_category(self):
        """eBay zwraca wyniki, ale wszystkie odfiltrowane jako zły tier
        (np. replica przy koszulce meczowej) — musi spaść na Gemini, nie
        zwrócić pustego wyniku mimo że Gemini ma dobre dane."""
        async def fake_gemini(report_data):
            return {
                "listings": [{"source": "gemini", "price_pln": 500, "title": "match worn jersey"}],
                "sample_size": 1,
                "median_pln": 500,
                "source": "gemini",
            }

        async def fake_ebay(query):
            return [{"source": "ebay", "price_pln": 100, "title": "official replica jersey"}]

        with patch.object(mva, "estimate_via_gemini", fake_gemini), \
             patch.object(mva, "estimate_via_ebay_browse", fake_ebay):
            result = run(mva.estimate_market_value({"subject": {}, "verdict": {"verdict_category": "meczowa"}}))

        assert result["source"] == "gemini"
        assert result["sample_size"] == 1

    def test_category_filter_excludes_wrong_tier_from_ebay_but_keeps_matching(self):
        """Mieszanka pasujących i niepasujących ofert eBay dla koszulki meczowej —
        replica musi odpaść, match-worn zostać."""
        async def fake_gemini(report_data):
            return {"listings": [], "sample_size": 0}

        async def fake_ebay(query):
            return [
                {"source": "ebay", "price_pln": 800, "title": "Match worn player issue jersey"},
                {"source": "ebay", "price_pln": 100, "title": "Official replica fan version"},
            ]

        with patch.object(mva, "estimate_via_gemini", fake_gemini), \
             patch.object(mva, "estimate_via_ebay_browse", fake_ebay):
            result = run(mva.estimate_market_value({"subject": {}, "verdict": {"verdict_category": "meczowa"}}))

        assert result["source"] == "ebay"
        assert result["sample_size"] == 1
        assert result["listings"][0]["price_pln"] == 800

    def test_gemini_not_called_when_ebay_alone_meets_reliability_threshold(self):
        """Gemini Search Grounding kosztuje/ma limit — nie wołamy go wcale, jeśli
        eBay samodzielnie ma wystarczająco dużo ofert (>= _MIN_RELIABLE_SAMPLE_SIZE)."""
        gemini_call_count = 0

        async def fake_gemini(report_data):
            nonlocal gemini_call_count
            gemini_call_count += 1
            return {"listings": [], "sample_size": 0}

        async def fake_ebay(query):
            return [
                {"source": "ebay", "price_pln": 200, "title": "jersey"},
                {"source": "ebay", "price_pln": 250, "title": "jersey"},
                {"source": "ebay", "price_pln": 300, "title": "jersey"},
            ]

        with patch.object(mva, "estimate_via_gemini", fake_gemini), \
             patch.object(mva, "estimate_via_ebay_browse", fake_ebay):
            result = run(mva.estimate_market_value({"subject": {}, "verdict": {}}))

        assert gemini_call_count == 0, "Gemini nie powinno być wołane gdy eBay wystarczył samodzielnie"
        assert result["source"] == "ebay"
        assert result["low_confidence"] is False

    def test_lone_ebay_listing_below_threshold_combines_with_gemini_instead_of_being_used_alone(self):
        """Regresja: jedna samotna oferta eBay (poniżej progu) nie może całkowicie
        przyćmić bogatszych danych z Gemini — muszą się połączyć."""
        async def fake_gemini(report_data):
            return {
                "listings": [
                    {"source": "gemini", "price_pln": 400, "title": "koszulka"},
                    {"source": "gemini", "price_pln": 450, "title": "koszulka"},
                    {"source": "gemini", "price_pln": 420, "title": "koszulka"},
                ],
                "sample_size": 3,
                "median_pln": 420,
            }

        async def fake_ebay(query):
            return [{"source": "ebay", "price_pln": 500, "title": "jersey"}]

        with patch.object(mva, "estimate_via_gemini", fake_gemini), \
             patch.object(mva, "estimate_via_ebay_browse", fake_ebay):
            result = run(mva.estimate_market_value({"subject": {}, "verdict": {}}))

        assert result["source"] == "ebay+gemini"
        assert result["sample_size"] == 4
        assert len(result["listings"]) == 4
        assert result["low_confidence"] is False

    def test_lone_ebay_listing_with_no_gemini_data_is_flagged_low_confidence(self):
        """Kluczowa regresja: eBay ma tylko 1 ofertę (poniżej progu), Gemini nie
        dorzuca nic (błąd/brak wyników/wszystko odfiltrowane) — combined ma wciąż
        tylko 1 element. Wynik musi zostać zwrócony (nie ukrywamy jedynej ceny),
        ale MUSI być jawnie oznaczony jako low_confidence, żeby nie wyglądał
        identycznie jak wycena z solidną próbką."""
        async def fake_gemini(report_data):
            return {"listings": [], "sample_size": 0}

        async def fake_ebay(query):
            return [{"source": "ebay", "price_pln": 500, "title": "jersey"}]

        with patch.object(mva, "estimate_via_gemini", fake_gemini), \
             patch.object(mva, "estimate_via_ebay_browse", fake_ebay):
            result = run(mva.estimate_market_value({"subject": {}, "verdict": {}}))

        assert result["source"] == "ebay"
        assert result["sample_size"] == 1
        assert result["low_confidence"] is True

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
                {"source": "ebay", "price_pln": 200, "title": "jersey"},
                {"source": "ebay", "price_pln": 210, "title": "jersey"},
                {"source": "ebay", "price_pln": 220, "title": "jersey"},
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
                "listings": [{"source": "gemini", "price_pln": 400, "title": "koszulka"}],
                "sample_size": 1,
                "query_used": "pelne zapytanie gemini",
            }

        async def fake_ebay(query):
            return [{"source": "ebay", "price_pln": 500, "title": "jersey"}]

        report_data = {"subject": {"club": "Bayern"}, "verdict": {}}
        with patch.object(mva, "estimate_via_gemini", fake_gemini), \
             patch.object(mva, "estimate_via_ebay_browse", fake_ebay):
            result = run(mva.estimate_market_value(report_data))

        assert result["source"] == "ebay+gemini"
        ebay_query = mva.build_ebay_search_query(report_data)
        assert ebay_query in result["query_used"]
        assert "pelne zapytanie gemini" in result["query_used"]
