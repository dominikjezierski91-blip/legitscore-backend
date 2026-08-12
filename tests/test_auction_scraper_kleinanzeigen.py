"""
Testy obsługi Kleinanzeigen.de w auction_scraper.py.

Kleinanzeigen nie blokuje botów (w przeciwieństwie do Allegro/eBay-HTML) —
zwykły httpx.get() wystarcza, więc te testy sprawdzają tylko ekstrakcję
zdjęć z HTML, nie osobną integrację API jak przy eBay.
"""
from app.services import auction_scraper as scraper


def _fake_uuid(seed: str) -> str:
    """Generuje deterministyczny, unikalny fałszywy UUID-podobny fragment ścieżki CDN."""
    h = f"{hash(seed) & 0xffffffff:08x}"
    return f"{h[:2]}/{h}-0000-4000-8000-{h}0000"


class TestDetectProviderKleinanzeigen:
    def test_detects_kleinanzeigen_domain(self):
        assert scraper.detect_provider("https://www.kleinanzeigen.de/s-anzeige/foo/123") == "kleinanzeigen"


class TestValidateAuctionUrlKleinanzeigen:
    def test_allows_kleinanzeigen_domain(self):
        url = "https://www.kleinanzeigen.de/s-anzeige/vfl-wolfsburg-trikot/3482968149-230-7251"
        assert scraper.validate_auction_url(url) == url


class TestExtractImagesKleinanzeigen:
    def _html(self, photo_ids, similar_items_photo_ids=None, photo_padding_chars=0):
        """Buduje HTML naśladujący realną strukturę oferty Kleinanzeigen: kontener
        galerii (class="vip-image-gallery") ze zdjęciami oferty, każde w kilku
        rozmiarach ($_2/$_35/$_59) pod tym samym UUID — dokładnie jak na realnych
        stronach (potwierdzone ręcznie przez curl). `photo_padding_chars` dokleja
        filler po każdym zdjęciu, symulując realną gęstość markupu (na produkcji
        każde zdjęcie to ~2000+ znaków przez osadzony ld+json ImageObject z opisem
        oferty) — bez tego fikstura jest nierealistycznie gęsta i nie wykryłaby
        regresji polegającej na powrocie do sztywnego okna znakowego zamiast
        cięcia po realnym markerze końca galerii. Opcjonalnie dokleja sekcję
        "könnte dich auch interessieren" (podobne ogłoszenia) PO galerii, z
        miniaturkami INNYCH ofert pod tym samym wzorcem URL CDN — symuluje
        realny układ strony, na którym wykryto zanieczyszczenie przed fixem."""
        photo_filler = "<!-- ld+json ImageObject description placeholder -->" * (photo_padding_chars // 50 + 1) if photo_padding_chars else ""
        srcset_tags = "\n".join(
            f'<img srcset="https://img.kleinanzeigen.de/api/v1/prod-ads/images/{pid}?rule=$_2.AUTO 1x, '
            f'https://img.kleinanzeigen.de/api/v1/prod-ads/images/{pid}?rule=$_35.AUTO 2x" />{photo_filler}'
            for pid in photo_ids
        )
        gallery = f'<div class="vip-image-gallery">{srcset_tags}</div>'

        similar_section = ""
        if similar_items_photo_ids:
            similar_items_html = "\n".join(
                f'<img src="https://img.kleinanzeigen.de/api/v1/prod-ads/images/{pid}?rule=$_2.AUTO" />'
                for pid in similar_items_photo_ids
            )
            # Na realnych stronach jest >35000 znaków (opis, cena, dane sprzedawcy)
            # między galerią a sekcją podobnych ofert — filler odtwarza ten odstęp,
            # żeby test faktycznie sprawdzał, że cięcie działa po realnym marker,
            # a nie przechodzi tylko dlatego, że fikstura jest za mała.
            filler = "<!-- viewad-price/description/seller-info placeholder -->" * 500
            similar_section = f'{filler}<h2>könnte dich auch interessieren</h2><div class="ad-list">{similar_items_html}</div>'

        return f"<html><body>{gallery}{similar_section}</body></html>"

    def test_extracts_one_fullsize_url_per_unique_photo(self):
        photo_ids = [
            "76/76a220ef-c740-4782-8629-9dfe9b5f9a58",
            "3e/3ebb73ef-5cb2-4ebf-95ea-305621af695f",
        ]
        html = self._html(photo_ids)
        images, diag = scraper._extract_images_from_html(html, "https://www.kleinanzeigen.de/s-anzeige/x/1")

        assert len(images) == 2
        for url in images:
            assert url.endswith("?rule=$_59.AUTO")

    def test_prefers_fullsize_over_thumbnail_variants(self):
        """Nawet jeśli mniejszy wariant ($_35) pojawia się w HTML, finalny URL musi być $_59."""
        pid = "90/90c72482-ae09-40dc-acca-02897cc2fc20"
        html = self._html([pid])
        images, _ = scraper._extract_images_from_html(html, "https://www.kleinanzeigen.de/s-anzeige/x/1")

        assert len(images) == 1
        assert images[0].endswith("?rule=$_59.AUTO")
        assert "$_35" not in images[0]
        assert "$_2.AUTO" not in images[0]

    def test_no_duplicate_entries_for_same_photo_different_sizes(self):
        pid = "51/514f589d-8fbe-4ba3-9905-e374d144ef7c"
        html = self._html([pid])
        images, diag = scraper._extract_images_from_html(html, "https://www.kleinanzeigen.de/s-anzeige/x/1")

        assert len(images) == 1
        duplicate_drops = [c for c in diag["candidates"] if c["drop_reason"] == "duplicate"]
        assert len(duplicate_drops) >= 2  # $_2 i $_35 (srcset) warianty tego samego zdjęcia

    def test_similar_items_section_photos_are_not_included(self):
        """
        Regresja dla realnego zanieczyszczenia: strona oferty zawiera dalej sekcję
        "könnte dich auch interessieren" (podobne ogłoszenia) z miniaturkami INNYCH
        ofert pod tym samym wzorcem URL CDN. Ekstrakcja musi być ograniczona do
        galerii tej oferty i NIE może wciągać zdjęć z tej sekcji.
        """
        own_photo = "76/76a220ef-c740-4782-8629-9dfe9b5f9a58"
        unrelated_photo_from_other_listing = "90/9080cfe9-97db-418b-9d6b-01d6233790de"

        html = self._html(
            photo_ids=[own_photo],
            similar_items_photo_ids=[unrelated_photo_from_other_listing],
        )
        images, _ = scraper._extract_images_from_html(html, "https://www.kleinanzeigen.de/s-anzeige/x/1")

        assert len(images) == 1
        assert own_photo in images[0]
        assert not any(unrelated_photo_from_other_listing in u for u in images)

    def test_large_gallery_beyond_any_fixed_window_is_not_truncated(self):
        """
        Regresja dla drugiego bugu znalezionego przy review: sztywne okno znakowe
        (np. 20000 znaków od startu galerii) cicho gubiło zdjęcia w realnej ofercie
        z 12 zdjęciami, bo każde zdjęcie w produkcyjnym markupie zajmuje ~2000+
        znaków (osadzony ld+json ImageObject). Ta fikstura odtwarza tę gęstość
        (12 zdjęć × ~2500 znaków paddingu = ~30000 znaków, więcej niż dawne
        sztywne okno) i sekcję podobnych ofert PO całej galerii — wszystkie 12
        własnych zdjęć musi się znaleźć w wyniku, cięcie musi być po realnym
        markerze końca, nie po stałej liczbie znaków.
        """
        photo_ids = [_fake_uuid(f"own-photo-{i}") for i in range(12)]
        unrelated = _fake_uuid("unrelated-similar-item")

        html = self._html(
            photo_ids=photo_ids,
            similar_items_photo_ids=[unrelated],
            photo_padding_chars=2500,
        )
        images, diag = scraper._extract_images_from_html(html, "https://www.kleinanzeigen.de/s-anzeige/x/1")

        assert len(images) == 12, f"oczekiwano 12 własnych zdjęć, dostano {len(images)}"
        for pid in photo_ids:
            assert any(pid in u for u in images), f"zdjęcie {pid} zostało cicho utracone"
        assert not any(unrelated in u for u in images)

    def test_no_end_marker_falls_back_to_wide_window_without_crashing(self):
        """Jeśli strona nie ma sekcji podobnych ofert (marker nieobecny), ekstrakcja
        nie powinna się wysypać — powinna zadziałać na szerokim oknie fallback."""
        photo_ids = [_fake_uuid(f"only-photo-{i}") for i in range(3)]
        html = self._html(photo_ids=photo_ids)  # brak similar_items_photo_ids -> brak markera końca

        images, _ = scraper._extract_images_from_html(html, "https://www.kleinanzeigen.de/s-anzeige/x/1")

        assert len(images) == 3
        for pid in photo_ids:
            assert any(pid in u for u in images)
