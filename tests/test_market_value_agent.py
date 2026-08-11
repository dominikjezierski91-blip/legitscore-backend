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


class TestEstimateMarketValueBlending:
    def test_blends_gemini_and_ebay_when_both_have_data(self):
        async def fake_gemini(report_data):
            return {
                "listings": [{"source": "gemini", "price_pln": 100}],
                "sample_size": 1,
                "median_pln": 100,
                "source": "gemini",
            }

        async def fake_ebay(query):
            return [{"source": "ebay", "price_pln": 200}, {"source": "ebay", "price_pln": 300}]

        with patch.object(mva, "estimate_via_gemini", fake_gemini), \
             patch.object(mva, "estimate_via_ebay_browse", fake_ebay):
            result = run(mva.estimate_market_value({"subject": {}, "verdict": {}}))

        assert result["source"] == "gemini+ebay"
        assert result["sample_size"] == 3
        assert len(result["listings"]) == 3

    def test_falls_back_to_gemini_only_when_ebay_empty(self):
        async def fake_gemini(report_data):
            return {
                "listings": [{"source": "gemini", "price_pln": 100}],
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
