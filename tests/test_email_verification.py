"""
Testy weryfikacji adresu email (soft launch — nic jej jeszcze nie blokuje,
tylko zapisujemy sygnał pod przyszłą Fazę 4 / anty-abuse na free-tier).
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.auth_service import create_access_token, hash_password
from app.services.database import SessionLocal, User, EmailVerificationToken
from app.services.oauth_service import OAuthIdentity

client = TestClient(app)


def _cleanup_user_by_email(email: str):
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == email).first()
        if u:
            db.query(EmailVerificationToken).filter(EmailVerificationToken.user_id == u.id).delete()
            db.delete(u)
            db.commit()
    finally:
        db.close()


class TestRegisterEmailVerification:
    def test_new_registration_is_unverified_and_gets_token(self):
        email = f"qa-verify-{uuid.uuid4().hex[:8]}@example.com"
        try:
            response = client.post(
                "/api/auth/register",
                json={
                    "email": email,
                    "password": "not-a-real-password",
                    "password_confirm": "not-a-real-password",
                    "regulamin_accepted": True,
                },
            )
            assert response.status_code == 200
            user_id = response.json()["user"]["id"]

            db = SessionLocal()
            user = db.query(User).filter(User.id == user_id).first()
            assert user.email_verified is False
            token_row = db.query(EmailVerificationToken).filter(
                EmailVerificationToken.user_id == user_id
            ).first()
            db.close()
            assert token_row is not None
            assert token_row.used is False
        finally:
            _cleanup_user_by_email(email)

    def test_verify_email_with_valid_token_marks_verified(self):
        email = f"qa-verify-ok-{uuid.uuid4().hex[:8]}@example.com"
        try:
            client.post(
                "/api/auth/register",
                json={
                    "email": email,
                    "password": "not-a-real-password",
                    "password_confirm": "not-a-real-password",
                    "regulamin_accepted": True,
                },
            )
            db = SessionLocal()
            user = db.query(User).filter(User.email == email).first()
            token_row = db.query(EmailVerificationToken).filter(
                EmailVerificationToken.user_id == user.id
            ).first()
            token = token_row.token
            db.close()

            response = client.post("/api/auth/verify-email", json={"token": token})
            assert response.status_code == 200
            assert response.json()["ok"] is True

            db = SessionLocal()
            assert db.query(User).filter(User.id == user.id).first().email_verified is True
            assert db.query(EmailVerificationToken).filter(
                EmailVerificationToken.token == token
            ).first().used is True
            db.close()
        finally:
            _cleanup_user_by_email(email)

    def test_verify_email_rejects_reused_token(self):
        email = f"qa-verify-reuse-{uuid.uuid4().hex[:8]}@example.com"
        try:
            client.post(
                "/api/auth/register",
                json={
                    "email": email,
                    "password": "not-a-real-password",
                    "password_confirm": "not-a-real-password",
                    "regulamin_accepted": True,
                },
            )
            db = SessionLocal()
            user = db.query(User).filter(User.email == email).first()
            token = db.query(EmailVerificationToken).filter(
                EmailVerificationToken.user_id == user.id
            ).first().token
            db.close()

            first = client.post("/api/auth/verify-email", json={"token": token})
            second = client.post("/api/auth/verify-email", json={"token": token})
            assert first.status_code == 200
            assert second.status_code == 400
        finally:
            _cleanup_user_by_email(email)

    def test_verify_email_rejects_expired_token(self):
        email = f"qa-verify-expired-{uuid.uuid4().hex[:8]}@example.com"
        try:
            client.post(
                "/api/auth/register",
                json={
                    "email": email,
                    "password": "not-a-real-password",
                    "password_confirm": "not-a-real-password",
                    "regulamin_accepted": True,
                },
            )
            db = SessionLocal()
            user = db.query(User).filter(User.email == email).first()
            token_row = db.query(EmailVerificationToken).filter(
                EmailVerificationToken.user_id == user.id
            ).first()
            token_row.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
            db.commit()
            token = token_row.token
            db.close()

            response = client.post("/api/auth/verify-email", json={"token": token})
            assert response.status_code == 400
        finally:
            _cleanup_user_by_email(email)

    def test_verify_email_rejects_garbage_token(self):
        response = client.post("/api/auth/verify-email", json={"token": "not-a-real-token"})
        assert response.status_code == 400

    def test_auth_me_reports_email_verified(self):
        email = f"qa-verify-me-{uuid.uuid4().hex[:8]}@example.com"
        try:
            reg = client.post(
                "/api/auth/register",
                json={
                    "email": email,
                    "password": "not-a-real-password",
                    "password_confirm": "not-a-real-password",
                    "regulamin_accepted": True,
                },
            )
            token = reg.json()["token"]
            me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
            assert me.status_code == 200
            assert me.json()["email_verified"] is False
        finally:
            _cleanup_user_by_email(email)


class TestResendVerification:
    def test_resend_sends_new_token_when_unverified(self):
        email = f"qa-resend-{uuid.uuid4().hex[:8]}@example.com"
        try:
            reg = client.post(
                "/api/auth/register",
                json={
                    "email": email,
                    "password": "not-a-real-password",
                    "password_confirm": "not-a-real-password",
                    "regulamin_accepted": True,
                },
            )
            token = reg.json()["token"]
            response = client.post(
                "/api/auth/resend-verification", headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == 200
            assert response.json()["already_verified"] is False
        finally:
            _cleanup_user_by_email(email)

    def test_resend_noop_when_already_verified(self):
        email = f"qa-resend-verified-{uuid.uuid4().hex[:8]}@example.com"
        db = SessionLocal()
        user = User(
            id=str(uuid.uuid4()),
            email=email,
            password_hash=hash_password("not-a-real-password"),
            is_admin=False,
            email_verified=True,
        )
        db.add(user)
        db.commit()
        access_token = create_access_token(user.id, is_admin=False)
        db.close()
        try:
            response = client.post(
                "/api/auth/resend-verification", headers={"Authorization": f"Bearer {access_token}"}
            )
            assert response.status_code == 200
            assert response.json()["already_verified"] is True
        finally:
            _cleanup_user_by_email(email)


class TestOAuthEmailVerified:
    def test_new_google_user_is_verified_immediately(self):
        email = f"qa-oauth-verified-{uuid.uuid4().hex[:8]}@example.com"
        sub = f"g-{uuid.uuid4().hex}"
        identity = OAuthIdentity(provider="google", sub=sub, email=email, name="QA")
        try:
            with patch("app.routes.auth.verify_google_id_token", return_value=identity):
                response = client.post(
                    "/api/auth/google",
                    json={"id_token": "fake", "regulamin_accepted": True},
                )
            assert response.status_code == 200
            db = SessionLocal()
            assert db.query(User).filter(User.email == email).first().email_verified is True
            db.close()
        finally:
            _cleanup_user_by_email(email)
