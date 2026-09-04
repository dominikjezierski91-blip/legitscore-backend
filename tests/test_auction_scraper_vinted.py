"""
Testy filtra awatara sprzedawcy w auction_scraper.py (_filter_vinted_avatar_outliers).

Regresja na realny incydent (case b545a7d4, ogłoszenie Vinted PSG/Dembélé,
2026-09-04): Vinted preloaduje w <head> nie tylko zdjęcia galerii oferty, ale
też awatar sprzedawcy (ten sam wzorzec CDN images*.vinted.net/t/.../f800/
{timestamp}.webp) — trafił do analizy Agenta A jako rzekome 7. zdjęcie
koszulki (w tym wypadku: zdjęcie Pepa Guardioli z pucharem Ligi Mistrzów,
ustawione jako zdjęcie profilowe sprzedawcy "razvana586"). Zweryfikowane
end-to-end na prawdziwym, pobranym HTML tego ogłoszenia — fix poprawnie
odsiewa dokładnie ten jeden awatar, zostawia wszystkie 6 realnych zdjęć.
"""
from app.services.auction_scraper import _extract_images_from_html, _filter_vinted_avatar_outliers


def _vinted_url(photo_id: str, timestamp: str) -> str:
    return f"https://images1.vinted.net/t/{photo_id}/f800/{timestamp}.webp?s=abc123"


class TestFilterVintedAvatarOutliers:
    def test_drops_singleton_timestamp_when_majority_group_has_at_least_three(self):
        images = [
            _vinted_url("02_00325_AAA", "1788519287"),
            _vinted_url("01_01dd8_BBB", "1788519287"),
            _vinted_url("05_021af_CCC", "1788519287"),
            _vinted_url("02_01f59_SELLER_AVATAR", "1785782475"),  # awatar sprzedawcy
        ]
        candidates = [{"url": u[:200], "source": "link_preload", "status": "used", "drop_reason": None} for u in images]
        result = _filter_vinted_avatar_outliers(images, candidates)
        assert len(result) == 3
        assert all("SELLER_AVATAR" not in u for u in result)

    def test_updates_candidate_status_for_dropped_avatar(self):
        images = [
            _vinted_url("02_00325_AAA", "1788519287"),
            _vinted_url("01_01dd8_BBB", "1788519287"),
            _vinted_url("05_021af_CCC", "1788519287"),
            _vinted_url("02_01f59_SELLER_AVATAR", "1785782475"),
        ]
        candidates = [{"url": u[:200], "source": "link_preload", "status": "used", "drop_reason": None} for u in images]
        _filter_vinted_avatar_outliers(images, candidates)
        avatar_candidate = next(c for c in candidates if "SELLER_AVATAR" in c["url"])
        assert avatar_candidate["status"] == "dropped"
        assert avatar_candidate["drop_reason"] == "vinted_avatar_outlier"
        # pozostałe kandydaty nie zostały tknięte
        untouched = [c for c in candidates if "SELLER_AVATAR" not in c["url"]]
        assert all(c["status"] == "used" for c in untouched)

    def test_single_timestamp_group_is_untouched(self):
        """Normalny listing, wszystkie zdjęcia z jednej tury uploadu — nic do odsiania."""
        images = [
            _vinted_url("02_00325_AAA", "1788519287"),
            _vinted_url("01_01dd8_BBB", "1788519287"),
        ]
        candidates = [{"url": u[:200], "source": "link_preload", "status": "used", "drop_reason": None} for u in images]
        result = _filter_vinted_avatar_outliers(images, candidates)
        assert result == images
        assert all(c["status"] == "used" for c in candidates)

    def test_two_comparable_groups_kept_ambiguous_case(self):
        """Sprzedawca mógł dograć zdjęcia w dwóch turach edycji ogłoszenia —
        obie grupy mają >1 zdjęcie, więc nie ma pewności które są 'prawdziwe',
        nie odsiewamy niczego."""
        images = [
            _vinted_url("02_00325_AAA", "1788519287"),
            _vinted_url("01_01dd8_BBB", "1788519287"),
            _vinted_url("05_021af_CCC", "1700000000"),
            _vinted_url("01_02168_DDD", "1700000000"),
        ]
        candidates = [{"url": u[:200], "source": "link_preload", "status": "used", "drop_reason": None} for u in images]
        result = _filter_vinted_avatar_outliers(images, candidates)
        assert len(result) == 4

    def test_majority_group_smaller_than_three_not_filtered(self):
        """Za mało zdjęć, żeby ufać, że mniejsza grupa to na pewno awatar —
        nie ryzykujemy odrzucenia prawdziwego zdjęcia przy bardzo krótkiej galerii."""
        images = [
            _vinted_url("02_00325_AAA", "1788519287"),
            _vinted_url("01_01dd8_BBB", "1788519287"),
            _vinted_url("02_01f59_MAYBE_AVATAR", "1785782475"),
        ]
        candidates = [{"url": u[:200], "source": "link_preload", "status": "used", "drop_reason": None} for u in images]
        result = _filter_vinted_avatar_outliers(images, candidates)
        assert len(result) == 3

    def test_non_vinted_urls_passthrough_untouched(self):
        images = [
            "https://img.kleinanzeigen.de/api/v1/prod-ads/images/aaa?rule=$_59.AUTO",
            "https://img.kleinanzeigen.de/api/v1/prod-ads/images/bbb?rule=$_59.AUTO",
        ]
        candidates = [{"url": u[:200], "source": "img", "status": "used", "drop_reason": None} for u in images]
        result = _filter_vinted_avatar_outliers(images, candidates)
        assert result == images

    def test_empty_images_list(self):
        assert _filter_vinted_avatar_outliers([], []) == []

    def test_non_webp_extension_still_matches_timestamp(self):
        """Regresja z code review: regex łapał tylko .webp — realne zdjęcie
        z innym rozszerzeniem (np. .jpg fallback) trafiałoby do koszyka
        'unknown' i mogłoby zostać błędnie potraktowane jak odosobniony
        znacznik czasu (fałszywy pozytyw)."""
        images = [
            "https://images1.vinted.net/t/02_00325_AAA/f800/1788519287.jpg?s=abc",
            _vinted_url("01_01dd8_BBB", "1788519287"),
            _vinted_url("05_021af_CCC", "1788519287"),
            _vinted_url("02_01f59_9RAMebPzmyosFB9pjF6dALBx", "1785782475"),
        ]
        candidates = [{"url": u[:200], "source": "link_preload", "status": "used", "drop_reason": None} for u in images]
        result = _filter_vinted_avatar_outliers(images, candidates)
        assert len(result) == 3
        assert "1788519287" in result[0]

    def test_unmatched_timestamp_url_never_dropped_even_as_apparent_singleton(self):
        """Regresja z QA: URL bez dopasowanego /f800/ (np. inny wariant
        rozmiaru CDN) NIE MOŻE zostać odrzucony jako 'osobliwy' — nie mamy
        żadnej podstawy, żeby wiedzieć, czy to prawdziwe zdjęcie czy nie,
        więc zostaje, zamiast ryzykować utratę prawdziwej fotografii."""
        images = [
            _vinted_url("A", "1788519287"),
            _vinted_url("B", "1788519287"),
            _vinted_url("C", "1788519287"),
            "https://images1.vinted.net/t/02_00325_AAA/1200x1600/preview.webp?s=abc",
        ]
        candidates = [{"url": u[:200], "source": "og:image", "status": "used", "drop_reason": None} for u in images]
        result = _filter_vinted_avatar_outliers(images, candidates)
        assert len(result) == 4
        assert all(c["status"] == "used" for c in candidates)

    def test_two_unmatched_urls_never_collide_into_fake_group(self):
        """Regresja z QA: dwa RÓŻNE niepowiązane URL-e bez znacznika czasu
        (np. awatar w innym wariancie rozmiaru + coś jeszcze) nie mogą
        skolidować w jedną wspólną grupę 'unknown' i przez to obie umknąć
        odrzuceniu — teraz są po prostu zawsze pomijane, nigdy nie tworzą grupy."""
        images = [
            _vinted_url("A", "1788519287"),
            _vinted_url("B", "1788519287"),
            _vinted_url("C", "1788519287"),
            "https://images1.vinted.net/t/X/220x220/stray1.webp?s=abc",
            "https://images1.vinted.net/t/Y/220x220/stray2.webp?s=def",
        ]
        candidates = [{"url": u[:200], "source": "img", "status": "used", "drop_reason": None} for u in images]
        result = _filter_vinted_avatar_outliers(images, candidates)
        # Nie odrzucamy niczego, bo oba są nierozpoznawalne — ale nie
        # utraciliśmy przy tym żadnego z 3 prawdziwych zdjęć.
        assert len(result) == 5
        assert sum("1788519287" in u for u in result) == 3

    def test_multiple_singleton_outliers_all_dropped(self):
        """Dwa niezależne odosobnione znaczniki czasu (np. awatar + inny
        przypadkowy trop) — obie grupy powinny odpaść, nie tylko pierwsza."""
        images = [
            _vinted_url("A", "1788519287"),
            _vinted_url("B", "1788519287"),
            _vinted_url("C", "1788519287"),
            _vinted_url("D", "1785782475"),
            _vinted_url("E", "1600000000"),
        ]
        candidates = [{"url": u[:200], "source": "link_preload", "status": "used", "drop_reason": None} for u in images]
        result = _filter_vinted_avatar_outliers(images, candidates)
        assert len(result) == 3
        assert all("1788519287" in u for u in result)


class TestExtractImagesVintedEndToEnd:
    def _html(self, real_timestamp: str, avatar_timestamp: str, n_real: int = 6) -> str:
        """Minimalny HTML naśladujący realną strukturę strony Vinted: <head> z
        <link rel=preload as=image> dla N zdjęć oferty (wspólny timestamp) plus
        jeden dla awatara sprzedawcy (inny timestamp) — dokładnie jak w realnym
        przypadku (potwierdzone ręcznym curl realnego ogłoszenia)."""
        real_links = "\n".join(
            f'<link rel="preload" as="image" href="{_vinted_url(f"0{i}_photo_{i}", real_timestamp)}"/>'
            for i in range(n_real)
        )
        avatar_link = f'<link rel="preload" as="image" href="{_vinted_url("02_01f59_9RAMebPzmyosFB9pjF6dALBx", avatar_timestamp)}"/>'
        return f"<!DOCTYPE html><html><head>{real_links}\n{avatar_link}</head><body></body></html>"

    def test_seller_avatar_excluded_from_extracted_images(self):
        html = self._html(real_timestamp="1788519287", avatar_timestamp="1785782475", n_real=6)
        images, diag = _extract_images_from_html(html, "https://www.vinted.pl/")
        assert diag["assets_extracted_count"] == 6
        assert all("1785782475" not in u for u in images)

    def test_short_gallery_keeps_ambiguous_extra_image(self):
        """Tylko 2 zdjęcia oferty — za mało pewności, nie odsiewamy 3.
        Dokumentuje świadomy kompromis: krótkie galerie mogą przepuścić
        pojedynczy fałszywy trop, ale nie tracą prawdziwych zdjęć."""
        html = self._html(real_timestamp="1788519287", avatar_timestamp="1785782475", n_real=2)
        images, diag = _extract_images_from_html(html, "https://www.vinted.pl/")
        assert diag["assets_extracted_count"] == 3
