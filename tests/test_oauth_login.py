"""
Testy logowania społecznościowego (Google/Facebook) — Zadanie 0.2 planu kont.

Weryfikacja tokena u dostawcy jest mockowana (nie wołamy prawdziwego Google/Facebook
w testach) — testujemy wyłącznie logikę backendu: tworzenie konta, odrzucenie (409) gdy
email trafia na już istniejące konto, i logowanie po oauth_sub przy kolejnych wizytach.
"""
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.auth_service import hash_password
from app.services.database import SessionLocal, User
from app.services.oauth_service import OAuthIdentity, OAuthVerificationError

client = TestClient(app)


def _cleanup_user_by_email(email: str):
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == email).first()
        if u:
            db.delete(u)
            db.commit()
    finally:
        db.close()


class TestGoogleLogin:
    def test_invalid_token_rejected(self):
        with patch(
            "app.routes.auth.verify_google_id_token",
            side_effect=OAuthVerificationError("Nieprawidłowy lub wygasły token Google."),
        ):
            response = client.post("/api/auth/google", json={"id_token": "garbage"})
        assert response.status_code == 401

    def test_new_user_requires_consent(self):
        email = f"qa-google-noconsent-{uuid.uuid4().hex[:8]}@example.com"
        identity = OAuthIdentity(provider="google", sub=f"g-{uuid.uuid4().hex}", email=email, name="QA")
        try:
            with patch("app.routes.auth.verify_google_id_token", return_value=identity):
                response = client.post(
                    "/api/auth/google",
                    json={"id_token": "fake", "regulamin_accepted": False},
                )
            assert response.status_code == 400
        finally:
            _cleanup_user_by_email(email)

    def test_new_user_created_with_consent(self):
        email = f"qa-google-new-{uuid.uuid4().hex[:8]}@example.com"
        sub = f"g-{uuid.uuid4().hex}"
        identity = OAuthIdentity(provider="google", sub=sub, email=email, name="QA")
        try:
            with patch("app.routes.auth.verify_google_id_token", return_value=identity):
                response = client.post(
                    "/api/auth/google",
                    json={
                        "id_token": "fake",
                        "regulamin_accepted": True,
                        "regulamin_version": "1.0",
                        "privacy_version": "1.0",
                    },
                )
            assert response.status_code == 200
            body = response.json()
            assert body["user"]["email"] == email
            assert "token" in body

            db = SessionLocal()
            record = db.query(User).filter(User.email == email).first()
            db.close()
            assert record.oauth_provider == "google"
            assert record.oauth_sub == sub
        finally:
            _cleanup_user_by_email(email)

    def test_second_login_reuses_same_account(self):
        email = f"qa-google-repeat-{uuid.uuid4().hex[:8]}@example.com"
        sub = f"g-{uuid.uuid4().hex}"
        identity = OAuthIdentity(provider="google", sub=sub, email=email, name="QA")
        try:
            with patch("app.routes.auth.verify_google_id_token", return_value=identity):
                first = client.post(
                    "/api/auth/google",
                    json={"id_token": "fake", "regulamin_accepted": True},
                )
                second = client.post("/api/auth/google", json={"id_token": "fake"})
            assert first.status_code == 200 and second.status_code == 200
            assert first.json()["user"]["id"] == second.json()["user"]["id"]

            db = SessionLocal()
            count = db.query(User).filter(User.email == email).count()
            db.close()
            assert count == 1
        finally:
            _cleanup_user_by_email(email)

    def test_does_not_auto_link_existing_password_account_by_email(self):
        """Brak auto-linku po samym dopasowaniu emaila — to byłby trwały backdoor omijający
        reset hasła (zweryfikowany email u dostawcy dowodzi własności TERAZ, nie w momencie
        gdy konto zakładano). Musi wrócić konflikt, zero zmian w kontach."""
        email = f"qa-google-link-{uuid.uuid4().hex[:8]}@example.com"
        db = SessionLocal()
        existing = User(
            id=str(uuid.uuid4()),
            email=email,
            password_hash=hash_password("original-password"),
            is_admin=False,
        )
        db.add(existing)
        db.commit()
        existing_id = existing.id
        db.close()

        sub = f"g-{uuid.uuid4().hex}"
        identity = OAuthIdentity(provider="google", sub=sub, email=email, name="QA")
        try:
            with patch("app.routes.auth.verify_google_id_token", return_value=identity):
                response = client.post("/api/auth/google", json={"id_token": "fake"})
            assert response.status_code == 409

            db = SessionLocal()
            count = db.query(User).filter(User.email == email).count()
            unchanged = db.query(User).filter(User.id == existing_id).first()
            db.close()
            assert count == 1
            assert unchanged.oauth_provider is None
            assert unchanged.oauth_sub is None
        finally:
            _cleanup_user_by_email(email)

    def test_oauth_only_account_cannot_login_with_password(self):
        email = f"qa-google-nopw-{uuid.uuid4().hex[:8]}@example.com"
        identity = OAuthIdentity(provider="google", sub=f"g-{uuid.uuid4().hex}", email=email, name="QA")
        try:
            with patch("app.routes.auth.verify_google_id_token", return_value=identity):
                created = client.post(
                    "/api/auth/google",
                    json={"id_token": "fake", "regulamin_accepted": True},
                )
            assert created.status_code == 200

            # Losowe hasło wygenerowane serwerowo nie jest znane nikomu — próba zalogowania
            # się dowolnym hasłem (w tym pustym stringiem) musi się nie udać.
            response = client.post(
                "/api/auth/login", json={"email": email, "password": "cokolwiek123"}
            )
            assert response.status_code == 401
        finally:
            _cleanup_user_by_email(email)

    def test_unverified_email_cannot_create_account(self):
        # verify_google_id_token samo zwraca email=None gdy email_verified=False —
        # tu symulujemy dokładnie taki wynik weryfikacji.
        identity = OAuthIdentity(provider="google", sub=f"g-{uuid.uuid4().hex}", email=None, name="QA")
        with patch("app.routes.auth.verify_google_id_token", return_value=identity):
            response = client.post(
                "/api/auth/google",
                json={"id_token": "fake", "regulamin_accepted": True},
            )
        assert response.status_code == 400


class TestFacebookLogin:
    def test_invalid_token_rejected(self):
        with patch(
            "app.routes.auth.verify_facebook_access_token",
            side_effect=OAuthVerificationError("Nieprawidłowy lub wygasły token Facebook."),
        ):
            response = client.post("/api/auth/facebook", json={"access_token": "garbage"})
        assert response.status_code == 401

    def test_new_user_created_with_consent(self):
        email = f"qa-fb-new-{uuid.uuid4().hex[:8]}@example.com"
        sub = f"fb-{uuid.uuid4().hex}"
        identity = OAuthIdentity(provider="facebook", sub=sub, email=email, name="QA FB")
        try:
            with patch("app.routes.auth.verify_facebook_access_token", return_value=identity):
                response = client.post(
                    "/api/auth/facebook",
                    json={"access_token": "fake", "regulamin_accepted": True},
                )
            assert response.status_code == 200
            assert response.json()["user"]["email"] == email
        finally:
            _cleanup_user_by_email(email)

    def test_missing_email_permission_rejected(self):
        identity = OAuthIdentity(provider="facebook", sub=f"fb-{uuid.uuid4().hex}", email=None, name="QA FB")
        with patch("app.routes.auth.verify_facebook_access_token", return_value=identity):
            response = client.post(
                "/api/auth/facebook",
                json={"access_token": "fake", "regulamin_accepted": True},
            )
        assert response.status_code == 400
