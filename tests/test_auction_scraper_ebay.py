"""
Testy importu zdjęć z eBay w auction_scraper.py przez Browse API
(get_item_by_legacy_id) — zamiennik dla HTML-scrapingu, który eBay blokuje
na poziomie bot-detection (HTTP 403, potwierdzone w produkcji).

Wszystkie testy mockują httpx — brak realnych wywołań sieciowych.
"""
import asyncio
from unittest.mock import patch

import pytest

from app.services import auction_scraper as scraper
from app.services import market_value_agent as mva


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def reset_ebay_token_state():
    mva._ebay_token_cache["token"] = None
    mva._ebay_token_cache["expires_at"] = 0.0
    mva._ebay_token_lock = None
    yield
    mva._ebay_token_cache["token"] = None
    mva._ebay_token_cache["expires_at"] = 0.0
    mva._ebay_token_lock = None


class FakeResponse:
    def __init__(self, json_data=None, status_code=200, content=b"", headers=None):
        self._json = json_data
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._json


class RoutedFakeAsyncClient:
    """Emuluje httpx.AsyncClient, routing po URL do zadanej odpowiedzi."""

    def __init__(self, responses_by_url, default=None):
        self._responses = responses_by_url
        self._default = default

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, **kwargs):
        return self._responses.get(url, self._default)

    async def get(self, url, **kwargs):
        return self._responses.get(url, self._default)


def _patch_ebay_stack(monkeypatch, item_response, image_responses):
    monkeypatch.setenv("EBAY_APP_ID", "app-id")
    monkeypatch.setenv("EBAY_CERT_ID_PRD", "cert-id")
    token_response = FakeResponse({"access_token": "tok123", "expires_in": 7200})

    responses_by_url = {
        "https://api.ebay.com/identity/v1/oauth2/token": token_response,
        "https://api.ebay.com/buy/browse/v1/item/get_item_by_legacy_id": item_response,
    }
    responses_by_url.update(image_responses)

    return patch(
        "httpx.AsyncClient",
        side_effect=lambda **kw: RoutedFakeAsyncClient(responses_by_url),
    )


class TestEbayLegacyItemId:
    def test_plain_itm_url(self):
        assert scraper._ebay_legacy_item_id("https://www.ebay.com/itm/305716156524") == "305716156524"

    def test_itm_url_with_title_slug(self):
        url = "https://www.ebay.com/itm/Some-Cool-Jersey-Title/305716156524"
        assert scraper._ebay_legacy_item_id(url) == "305716156524"

    def test_no_item_id_returns_none(self):
        assert scraper._ebay_legacy_item_id("https://www.ebay.com/sch/i.html?_nkw=jersey") is None


class TestEbayMarketplaceForUrl:
    def test_ebay_com_maps_to_us(self):
        assert scraper._ebay_marketplace_for_url("https://www.ebay.com/itm/123") == "EBAY_US"

    def test_ebay_co_uk_maps_to_gb(self):
        assert scraper._ebay_marketplace_for_url("https://www.ebay.co.uk/itm/123") == "EBAY_GB"

    def test_unknown_ebay_domain_defaults_to_us(self):
        assert scraper._ebay_marketplace_for_url("https://www.ebay.fr/itm/123") == "EBAY_US"


class TestFetchEbayImagesViaBrowseApi:
    def test_no_item_id_in_url_raises_before_any_network_call(self):
        with patch("httpx.AsyncClient") as mock_client:
            with pytest.raises(scraper.AuctionScraperError, match="numeru oferty"):
                run(scraper._fetch_ebay_images_via_browse_api("https://www.ebay.com/sch/i.html"))
        mock_client.assert_not_called()

    def test_missing_credentials_raises_clear_error(self, monkeypatch):
        monkeypatch.delenv("EBAY_APP_ID", raising=False)
        monkeypatch.delenv("EBAY_CERT_ID_PRD", raising=False)
        with pytest.raises(scraper.AuctionScraperError, match="niedostępny"):
            run(scraper._fetch_ebay_images_via_browse_api("https://www.ebay.com/itm/305716156524"))

    def test_fetches_main_and_additional_images(self, monkeypatch):
        item_response = FakeResponse({
            "image": {"imageUrl": "https://i.ebayimg.com/main.jpg"},
            "additionalImages": [
                {"imageUrl": "https://i.ebayimg.com/extra1.jpg"},
                {"imageUrl": "https://i.ebayimg.com/main.jpg"},  # duplikat, ma być odfiltrowany
                {"imageUrl": "https://i.ebayimg.com/extra2.webp"},
            ],
        })
        image_responses = {
            "https://i.ebayimg.com/main.jpg": FakeResponse(content=b"jpgbytes", headers={"content-type": "image/jpeg"}),
            "https://i.ebayimg.com/extra1.jpg": FakeResponse(content=b"jpgbytes2", headers={"content-type": "image/jpeg"}),
            "https://i.ebayimg.com/extra2.webp": FakeResponse(content=b"webpbytes", headers={"content-type": "image/webp"}),
        }
        with _patch_ebay_stack(monkeypatch, item_response, image_responses):
            images, meta = run(scraper._fetch_ebay_images_via_browse_api("https://www.ebay.com/itm/305716156524"))

        assert len(images) == 3
        filenames = [f for _, f in images]
        assert filenames == ["auction_image_1.jpg", "auction_image_2.jpg", "auction_image_3.webp"]
        assert meta["provider"] == "ebay"
        assert meta["assets_extracted_count"] == 3
        assert meta["assets_passed_to_model_count"] == 3
        assert meta["incomplete_image_set"] is False

    def test_no_images_in_item_raises(self, monkeypatch):
        item_response = FakeResponse({"image": None, "additionalImages": []})
        with _patch_ebay_stack(monkeypatch, item_response, {}):
            with pytest.raises(scraper.AuctionScraperError, match="Nie znaleziono zdjęć"):
                run(scraper._fetch_ebay_images_via_browse_api("https://www.ebay.com/itm/305716156524"))

    def test_item_lookup_http_error_raises_auction_scraper_error(self, monkeypatch):
        import httpx as real_httpx
        item_response = FakeResponse(status_code=404)

        # RuntimeError z FakeResponse.raise_for_status nie jest httpx.HTTPStatusError,
        # więc symulujemy to dokładniej przez podmianę raise_for_status.
        class NotFoundResponse(FakeResponse):
            def raise_for_status(self):
                request = real_httpx.Request("GET", "https://api.ebay.com/buy/browse/v1/item/get_item_by_legacy_id")
                response = real_httpx.Response(404, request=request)
                raise real_httpx.HTTPStatusError("not found", request=request, response=response)

        with _patch_ebay_stack(monkeypatch, NotFoundResponse(status_code=404), {}):
            with pytest.raises(scraper.AuctionScraperError, match="HTTP 404"):
                run(scraper._fetch_ebay_images_via_browse_api("https://www.ebay.com/itm/305716156524"))

    def test_item_lookup_connection_error_raises_auction_scraper_error(self, monkeypatch):
        monkeypatch.setenv("EBAY_APP_ID", "app-id")
        monkeypatch.setenv("EBAY_CERT_ID_PRD", "cert-id")
        token_response = FakeResponse({"access_token": "tok123", "expires_in": 7200})

        class BrokenConnectionClient:
            def __init__(self, *a, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def post(self, url, **kwargs):
                return token_response

            async def get(self, url, **kwargs):
                import httpx as real_httpx
                raise real_httpx.ConnectError("connection refused")

        with patch("httpx.AsyncClient", side_effect=lambda **kw: BrokenConnectionClient()):
            with pytest.raises(scraper.AuctionScraperError, match="połączyć"):
                run(scraper._fetch_ebay_images_via_browse_api("https://www.ebay.com/itm/305716156524"))

    def test_malformed_json_response_raises_clear_error(self, monkeypatch):
        class BadJsonResponse(FakeResponse):
            def json(self):
                raise ValueError("Expecting value: line 1 column 1 (char 0)")

        with _patch_ebay_stack(monkeypatch, BadJsonResponse(status_code=200), {}):
            with pytest.raises(scraper.AuctionScraperError, match="nieprawidłową odpowiedź"):
                run(scraper._fetch_ebay_images_via_browse_api("https://www.ebay.com/itm/305716156524"))

    def test_unexpected_item_shape_raises_clear_error(self, monkeypatch):
        # additionalImages zawiera string zamiast dicta — realny "kształt niezgodny z oczekiwanym"
        item_response = FakeResponse({
            "image": {"imageUrl": "https://i.ebayimg.com/main.jpg"},
            "additionalImages": ["not-a-dict"],
        })
        with _patch_ebay_stack(monkeypatch, item_response, {}):
            with pytest.raises(scraper.AuctionScraperError, match="nieoczekiwany format"):
                run(scraper._fetch_ebay_images_via_browse_api("https://www.ebay.com/itm/305716156524"))

    def test_all_image_downloads_failing_raises_clear_error(self, monkeypatch):
        item_response = FakeResponse({
            "image": {"imageUrl": "https://i.ebayimg.com/main.jpg"},
            "additionalImages": [],
        })
        image_responses = {
            "https://i.ebayimg.com/main.jpg": FakeResponse(status_code=500, content=b"", headers={}),
        }
        with _patch_ebay_stack(monkeypatch, item_response, image_responses):
            with pytest.raises(scraper.AuctionScraperError, match="Nie udało się pobrać żadnego zdjęcia"):
                run(scraper._fetch_ebay_images_via_browse_api("https://www.ebay.com/itm/305716156524"))


class TestFetchAuctionImagesRoutesEbayToApi:
    def test_ebay_url_skips_html_scraping(self, monkeypatch):
        """fetch_auction_images() dla eBay musi iść ścieżką API, nie HTML-scrapingu."""
        called = {}

        async def fake_api_fetch(url):
            called["url"] = url
            return [(b"x", "auction_image_1.jpg")], {"provider": "ebay"}

        monkeypatch.setattr(scraper, "_fetch_ebay_images_via_browse_api", fake_api_fetch)
        with patch("httpx.AsyncClient") as mock_client:
            images, meta = run(scraper.fetch_auction_images("https://www.ebay.com/itm/305716156524"))

        assert called["url"] == "https://www.ebay.com/itm/305716156524"
        assert meta["provider"] == "ebay"
        # generyczny scraping HTML (który tworzy httpx.AsyncClient w fetch_auction_images) nie mógł się wykonać
        mock_client.assert_not_called()
