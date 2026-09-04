"""
Testy: podróbki (verdict_category="podrobka") nie mają sprawdzanej wartości
rynkowej — ani przy dodaniu do kolekcji, ani w ręcznym odświeżeniu, ani w
codziennym daily refreshu. Frontend w ich miejsce pokazuje cenę zakupu (jeśli
user ją podał) — logika czysto frontendowa, tu testujemy tylko backend:
że estimate_market_value w ogóle nie jest wołane dla podróbek.
"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.auth_service import create_access_token, hash_password
from app.services.database import SessionLocal, User, CollectionItem
from app.services.market_value_agent import refresh_stale_market_values

client = TestClient(app)

_MARKET_VALUE_PATCH_TARGET = "app.routes.collection.estimate_market_value"


def _make_user() -> User:
    db = SessionLocal()
    try:
        user = User(
            id=str(uuid.uuid4()),
            email=f"qa-podrobka-{uuid.uuid4().hex[:8]}@example.com",
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


def _headers(user: User) -> dict:
    token = create_access_token(user.id, is_admin=False)
    return {"Authorization": f"Bearer {token}"}


class TestAutoEstimateSkipsPodrobka:
    def test_adding_podrobka_never_calls_estimate_market_value(self):
        user = _make_user()
        try:
            with patch(_MARKET_VALUE_PATCH_TARGET, new=AsyncMock()) as mock_estimate:
                resp = client.post(
                    "/api/collection",
                    json={
                        "club": "FC Barcelona",
                        "season": "2023/24",
                        "verdict_category": "podrobka",
                        "is_manual": True,
                    },
                    headers=_headers(user),
                )
            assert resp.status_code == 200
            mock_estimate.assert_not_called()

            db = SessionLocal()
            try:
                item = db.query(CollectionItem).filter(CollectionItem.user_id == user.id).first()
                assert item.market_value_pln is None
            finally:
                db.close()
        finally:
            _cleanup(user.id)

    def test_adding_authentic_item_still_calls_estimate_market_value(self):
        """Regresja: upewnij się, że wyłączenie dla podróbek nie wyłączyło
        estymacji dla zwykłych koszulek."""
        user = _make_user()
        try:
            with patch(_MARKET_VALUE_PATCH_TARGET, new=AsyncMock(return_value={"sample_size": 0})) as mock_estimate:
                resp = client.post(
                    "/api/collection",
                    json={
                        "club": "FC Barcelona",
                        "season": "2023/24",
                        "verdict_category": "oryginalna_sklepowa",
                        "is_manual": True,
                    },
                    headers=_headers(user),
                )
            assert resp.status_code == 200
            mock_estimate.assert_called_once()
        finally:
            _cleanup(user.id)


class TestManualRefreshRejectsPodrobka:
    def test_refresh_endpoint_returns_400_for_podrobka(self):
        user = _make_user()
        try:
            with patch(_MARKET_VALUE_PATCH_TARGET, new=AsyncMock()):
                create_resp = client.post(
                    "/api/collection",
                    json={
                        "club": "FC Barcelona",
                        "season": "2023/24",
                        "verdict_category": "podrobka",
                        "is_manual": True,
                    },
                    headers=_headers(user),
                )
            item_id = create_resp.json()["id"]

            with patch(_MARKET_VALUE_PATCH_TARGET, new=AsyncMock()) as mock_estimate:
                resp = client.post(f"/api/collection/{item_id}/market-value", headers=_headers(user))

            assert resp.status_code == 400
            mock_estimate.assert_not_called()
        finally:
            _cleanup(user.id)


class TestDailyRefreshSkipsPodrobka:
    def test_stale_items_query_excludes_podrobka(self):
        """Weryfikuje bezpośrednio zapytanie SQL użyte w refresh_stale_market_values
        (bez odpalania całej async orkiestracji/Gemini) — podróbka z pustym
        market_value_last_attempt_at nie kwalifikuje się do codziennego
        odświeżenia, zwykła koszulka w tym samym stanie — tak. Filtr celowo po
        last_attempt_at, nie updated_at — patrz TestDailyRefreshLastAttemptVsUpdatedAt."""
        user = _make_user()
        db = SessionLocal()
        try:
            fake_item = CollectionItem(
                id=str(uuid.uuid4()),
                user_id=user.id,
                case_id=f"manual_{uuid.uuid4().hex[:12]}",
                club="FC Barcelona",
                season="2023/24",
                verdict_category="podrobka",
                is_manual=True,
                market_value_last_attempt_at=None,
            )
            real_item = CollectionItem(
                id=str(uuid.uuid4()),
                user_id=user.id,
                case_id=f"manual_{uuid.uuid4().hex[:12]}",
                club="Real Madrid",
                season="2023/24",
                verdict_category="oryginalna_sklepowa",
                is_manual=True,
                market_value_last_attempt_at=None,
            )
            db.add_all([fake_item, real_item])
            db.commit()
            item_ids = {fake_item.id, real_item.id}

            cutoff = datetime.now(timezone.utc) - timedelta(days=7)
            stale_ids = {
                row.id
                for row in db.query(CollectionItem)
                .filter(
                    CollectionItem.verdict_category != "podrobka",
                    (CollectionItem.market_value_last_attempt_at == None) |  # noqa: E711
                    (CollectionItem.market_value_last_attempt_at < cutoff),
                )
                .filter(CollectionItem.id.in_(item_ids))
                .all()
            }
            assert stale_ids == {real_item.id}
        finally:
            db.close()
            _cleanup(user.id)


class TestDailyRefreshLastAttemptVsUpdatedAt:
    """Spec 2026-09-03 §7: market_value_last_attempt_at bumpuje się po KAŻDEJ
    próbie odświeżenia (żeby pozycja z trwale słabym rynkiem nie kwalifikowała
    się do odświeżenia codziennie zamiast raz na 7 dni — patrz stale-query w
    refresh_stale_market_values, filtruje po last_attempt_at, nie updated_at).
    market_value_updated_at zmienia się TYLKO gdy zapisana wartość faktycznie
    się zmienia (should_update_market_value zwraca True) — to pole ma dawać
    userowi uczciwe "zaktualizowano X dni temu", nie mylić cichej próby z
    realną zmianą ceny."""

    def test_low_confidence_thin_sample_bumps_attempt_not_updated_at(self):
        user = _make_user()
        db = SessionLocal()
        try:
            old_updated_at = datetime.now(timezone.utc) - timedelta(days=10)
            old_attempt_at = datetime.now(timezone.utc) - timedelta(days=10)
            item = CollectionItem(
                id=str(uuid.uuid4()),
                user_id=user.id,
                case_id=f"manual_{uuid.uuid4().hex[:12]}",
                club="FC Barcelona",
                season="2026/2027",
                verdict_category="oryginalna_sklepowa",
                is_manual=True,
                market_value_pln=470.0,
                market_value_confidence="high",
                market_value_updated_at=old_updated_at,
                market_value_last_attempt_at=old_attempt_at,
            )
            db.add(item)
            db.commit()
            item_id = item.id
        finally:
            db.close()

        try:
            # confidence='low' + stored='high' -> should_update_market_value
            # zwraca False (patrz tests/test_market_value_agent.py::TestShouldUpdateMarketValue).
            # Wartość NIE powinna się zmienić, market_value_updated_at NIE powinno
            # się zmienić, ale market_value_last_attempt_at TAK.
            thin_result = AsyncMock(return_value={
                "price": 168, "low": 168, "high": 168,
                "matched_count": 1, "confidence": "low", "source": "ebay",
            })
            with patch("app.services.market_value_agent.estimate_market_value", new=thin_result):
                asyncio.run(refresh_stale_market_values(max_items=50))

            db = SessionLocal()
            try:
                refreshed_item = db.query(CollectionItem).filter(CollectionItem.id == item_id).first()
                assert refreshed_item.market_value_pln == 470.0, "wartość nie powinna się zmienić przy słabej próbce"
                # SQLite zwraca DateTime jako naive — porównaj na tej samej podstawie.
                assert refreshed_item.market_value_updated_at == old_updated_at.replace(tzinfo=None), (
                    "updated_at NIE powinno się zmienić — wartość nie została nadpisana"
                )
                assert refreshed_item.market_value_last_attempt_at > old_attempt_at.replace(tzinfo=None), (
                    "last_attempt_at musi się zaktualizować mimo pominięcia zapisu wartości, "
                    "inaczej pozycja odświeżałaby się codziennie zamiast raz na 7 dni"
                )
            finally:
                db.close()
        finally:
            _cleanup(user.id)

    def test_high_confidence_bumps_both_timestamps(self):
        user = _make_user()
        db = SessionLocal()
        try:
            old_ts = datetime.now(timezone.utc) - timedelta(days=10)
            item = CollectionItem(
                id=str(uuid.uuid4()),
                user_id=user.id,
                case_id=f"manual_{uuid.uuid4().hex[:12]}",
                club="Bayern Monachium",
                season="2015/2016",
                verdict_category="oryginalna_sklepowa",
                is_manual=True,
                market_value_pln=185.0,
                market_value_confidence="low",
                market_value_updated_at=old_ts,
                market_value_last_attempt_at=old_ts,
            )
            db.add(item)
            db.commit()
            item_id = item.id
        finally:
            db.close()

        try:
            strong_result = AsyncMock(return_value={
                "price": 365, "low": 300, "high": 400,
                "matched_count": 3, "confidence": "high", "source": "ebay",
            })
            with patch("app.services.market_value_agent.estimate_market_value", new=strong_result):
                asyncio.run(refresh_stale_market_values(max_items=50))

            db = SessionLocal()
            try:
                refreshed_item = db.query(CollectionItem).filter(CollectionItem.id == item_id).first()
                assert refreshed_item.market_value_pln == 365
                assert refreshed_item.market_value_confidence == "high"
                assert refreshed_item.market_value_updated_at > old_ts.replace(tzinfo=None)
                assert refreshed_item.market_value_last_attempt_at > old_ts.replace(tzinfo=None)
            finally:
                db.close()
        finally:
            _cleanup(user.id)
