"""
Testy dwóch slotów zdjęć w Kolekcji (Faza "przód/tył bez AI", 2026-08-19):
ręcznie dodawana koszulka może mieć drugie, opcjonalne zdjęcie (photo_path_2),
serwowane pod /collection/{id}/thumbnail?slot=2, żeby widok szczegółowy mógł
pokazać karuzelę ze swipe'em. slot=1 musi zachowywać się dokładnie jak dawniej
(bez parametru w URL, bo istniejący frontend/JerseyThumbnail go nie wysyła).
"""
import io
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.auth_service import create_access_token, hash_password
from app.services.database import SessionLocal, User, CollectionItem

client = TestClient(app)

# POST /api/collection odpala background task estimate_market_value (realne
# wywołanie Gemini) — mockujemy w każdym teście, żeby nie robić sieciowych
# wywołań i nie blokować testu (TestClient wykonuje background tasks
# synchronicznie przed zwróceniem odpowiedzi).
_MARKET_VALUE_PATCH_TARGET = "app.routes.collection.estimate_market_value"


def _make_user() -> User:
    db = SessionLocal()
    try:
        user = User(
            id=str(uuid.uuid4()),
            email=f"qa-photos-{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("not-a-real-password"),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


def _cleanup(user_id: str):
    db = SessionLocal()
    try:
        db.query(CollectionItem).filter(CollectionItem.user_id == user_id).delete()
        db.query(User).filter(User.id == user_id).delete()
        db.commit()
    finally:
        db.close()


def _fake_image_bytes() -> bytes:
    # Minimalny prawidłowy PNG (1x1) — wystarczy, endpoint sprawdza tylko content_type.
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
        "1f15c4890000000a49444154789c6360000002000100ffff03000006"
        "0005570d99c40000000049454e44ae426082"
    )


class TestCollectionTwoPhotoSlots:
    def _headers(self, user: User) -> dict:
        token = create_access_token(user.id, is_admin=False)
        return {"Authorization": f"Bearer {token}"}

    def _create_manual_item(self, headers: dict) -> str:
        with patch(_MARKET_VALUE_PATCH_TARGET, return_value={"sample_size": 0}):
            resp = client.post(
                "/api/collection",
                json={"club": "Testowy Klub", "season": "24/25", "brand": "Nike", "is_manual": True},
                headers=headers,
            )
        assert resp.status_code == 200
        return resp.json()["id"]

    def test_slot1_upload_and_serve_unchanged(self):
        """slot=1 (domyślny, bez parametru w URL) musi działać tak jak przed
        wprowadzeniem drugiego slotu — nic nie może się tu zepsuć."""
        user = _make_user()
        headers = self._headers(user)
        try:
            item_id = self._create_manual_item(headers)

            upload = client.post(
                f"/api/collection/{item_id}/photo",
                files={"file": ("front.png", io.BytesIO(_fake_image_bytes()), "image/png")},
                headers=headers,
            )
            assert upload.status_code == 200
            assert upload.json()["slot"] == 1

            thumb = client.get(f"/api/collection/{item_id}/thumbnail")
            assert thumb.status_code == 200

            listing = client.get("/api/collection", headers=headers)
            item = next(i for i in listing.json() if i["id"] == item_id)
            assert item["has_photo"] is True
            assert item["has_photo_2"] is False
        finally:
            _cleanup(user.id)

    def test_slot2_optional_second_photo(self):
        user = _make_user()
        headers = self._headers(user)
        try:
            item_id = self._create_manual_item(headers)

            client.post(
                f"/api/collection/{item_id}/photo",
                files={"file": ("front.png", io.BytesIO(_fake_image_bytes()), "image/png")},
                headers=headers,
            )
            upload2 = client.post(
                f"/api/collection/{item_id}/photo?slot=2",
                files={"file": ("back.png", io.BytesIO(_fake_image_bytes()), "image/png")},
                headers=headers,
            )
            assert upload2.status_code == 200
            assert upload2.json()["slot"] == 2

            thumb1 = client.get(f"/api/collection/{item_id}/thumbnail?slot=1")
            thumb2 = client.get(f"/api/collection/{item_id}/thumbnail?slot=2")
            assert thumb1.status_code == 200
            assert thumb2.status_code == 200

            listing = client.get("/api/collection", headers=headers)
            item = next(i for i in listing.json() if i["id"] == item_id)
            assert item["has_photo_2"] is True
        finally:
            _cleanup(user.id)

    def test_missing_slot2_returns_404(self):
        """Item bez drugiego zdjęcia — frontend polega na tym 404, żeby
        wykryć brak drugiego zdjęcia i nie pokazywać kropek karuzeli."""
        user = _make_user()
        headers = self._headers(user)
        try:
            item_id = self._create_manual_item(headers)
            client.post(
                f"/api/collection/{item_id}/photo",
                files={"file": ("front.png", io.BytesIO(_fake_image_bytes()), "image/png")},
                headers=headers,
            )
            thumb2 = client.get(f"/api/collection/{item_id}/thumbnail?slot=2")
            assert thumb2.status_code == 404
        finally:
            _cleanup(user.id)

    def test_delete_cleans_up_both_photo_slots(self):
        user = _make_user()
        headers = self._headers(user)
        try:
            item_id = self._create_manual_item(headers)
            client.post(
                f"/api/collection/{item_id}/photo",
                files={"file": ("front.png", io.BytesIO(_fake_image_bytes()), "image/png")},
                headers=headers,
            )
            client.post(
                f"/api/collection/{item_id}/photo?slot=2",
                files={"file": ("back.png", io.BytesIO(_fake_image_bytes()), "image/png")},
                headers=headers,
            )

            db = SessionLocal()
            try:
                item = db.query(CollectionItem).filter(CollectionItem.id == item_id).first()
                from pathlib import Path
                path1, path2 = Path(item.photo_path), Path(item.photo_path_2)
                assert path1.exists() and path2.exists()
            finally:
                db.close()

            delete_resp = client.delete(f"/api/collection/{item_id}", headers=headers)
            assert delete_resp.status_code == 200
            assert not path1.exists()
            assert not path2.exists()
        finally:
            _cleanup(user.id)

    def test_invalid_slot_rejected(self):
        user = _make_user()
        headers = self._headers(user)
        try:
            item_id = self._create_manual_item(headers)
            resp = client.post(
                f"/api/collection/{item_id}/photo?slot=3",
                files={"file": ("front.png", io.BytesIO(_fake_image_bytes()), "image/png")},
                headers=headers,
            )
            assert resp.status_code == 422
        finally:
            _cleanup(user.id)


class TestCaseThumbnailIndex:
    def test_index_out_of_range_returns_404(self):
        """Case bez żadnych zdjęć (case_id losowy/nieistniejący) — index=1 na
        pustej liście assets musi zwrócić 404, nie IndexError/500."""
        resp = client.get(f"/api/cases/{uuid.uuid4()}/thumbnail?index=1")
        assert resp.status_code == 404

    def test_default_index_matches_no_param(self):
        """Domyślne wywołanie bez ?index= (jak dotychczasowy frontend) musi
        zachowywać się identycznie jak ?index=0."""
        case_id = str(uuid.uuid4())
        resp_default = client.get(f"/api/cases/{case_id}/thumbnail")
        resp_index0 = client.get(f"/api/cases/{case_id}/thumbnail?index=0")
        assert resp_default.status_code == resp_index0.status_code == 404
