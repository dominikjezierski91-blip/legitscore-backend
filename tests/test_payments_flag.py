"""
Testy feature flagi PAYMENTS_ENABLED (SPEC "Darmowe analizy w becie + ukrycie
płatności za feature flagą", 2026-09-27).

Bramka kredytowa w run-decision jest przetestowana w test_credits.py
(TestRunDecisionCreditGate) — tu tylko /api/config i endpoint checkout.
"""
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.auth_service import create_access_token, hash_password
from app.services.database import SessionLocal, User, CreditPurchase

client = TestClient(app)


def _make_user() -> User:
    db = SessionLocal()
    try:
        user = User(
            id=str(uuid.uuid4()),
            email=f"qa-payflag-{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("not-a-real-password"),
            credits=1,
            is_admin=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


def _cleanup(user_id: str) -> None:
    db = SessionLocal()
    try:
        db.query(CreditPurchase).filter(CreditPurchase.user_id == user_id).delete()
        db.query(User).filter(User.id == user_id).delete()
        db.commit()
    finally:
        db.close()


class TestPublicConfigEndpoint:
    def test_reflects_payments_enabled_true(self):
        with patch("app.main.PAYMENTS_ENABLED", True):
            resp = client.get("/api/config")
        assert resp.status_code == 200
        assert resp.json() == {"payments_enabled": True}

    def test_reflects_payments_enabled_false(self):
        with patch("app.main.PAYMENTS_ENABLED", False):
            resp = client.get("/api/config")
        assert resp.status_code == 200
        assert resp.json() == {"payments_enabled": False}

    def test_no_auth_required(self):
        # Musi działać dla anonimowego usera — front pyta o config przed loginem.
        resp = client.get("/api/config")
        assert resp.status_code == 200
        assert "payments_enabled" in resp.json()


class TestCheckoutGatedByFlag:
    def test_checkout_returns_409_and_never_calls_stripe_when_disabled(self):
        user = _make_user()
        token = create_access_token(user.id, is_admin=False)
        headers = {"Authorization": f"Bearer {token}"}
        try:
            with patch("app.routes.billing.PAYMENTS_ENABLED", False), patch(
                "app.routes.billing.create_checkout_session"
            ) as mock_stripe:
                resp = client.post(
                    "/api/billing/checkout",
                    json={"package": "single"},
                    headers=headers,
                )
            assert resp.status_code == 409
            assert resp.json()["detail"]["error"] == "payments_disabled_beta"
            mock_stripe.assert_not_called()
        finally:
            _cleanup(user.id)

    def test_checkout_reaches_stripe_call_when_enabled(self):
        """Nie testujemy realnego Stripe (poza zakresem) — tylko że flaga=true
        NIE blokuje requestu przed dotarciem do create_checkout_session, czyli
        że przełączenie PAYMENTS_ENABLED z powrotem na True faktycznie
        przywraca poprzednią ścieżkę (SPEC §5, wymóg odwracalności)."""
        user = _make_user()
        token = create_access_token(user.id, is_admin=False)
        headers = {"Authorization": f"Bearer {token}"}
        try:
            with patch("app.routes.billing.PAYMENTS_ENABLED", True), patch(
                "app.routes.billing.create_checkout_session"
            ) as mock_stripe:
                mock_stripe.return_value = type(
                    "FakeSession", (), {"id": "sess_fake", "url": "https://example.com/checkout"}
                )()
                resp = client.post(
                    "/api/billing/checkout",
                    json={"package": "single"},
                    headers=headers,
                )
            assert resp.status_code == 200
            mock_stripe.assert_called_once()
        finally:
            _cleanup(user.id)
