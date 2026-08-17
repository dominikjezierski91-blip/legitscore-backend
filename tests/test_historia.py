"""
Testy Historii (Faza 2 planu kont) — GET /api/me/reports.

Historia = KAŻDA analiza zalogowanego usera (automatycznie), w odróżnieniu od
Kolekcji (tylko świadomie dodane). Czyta wyłącznie CaseRecord z DB, zero
rekalkulacji — zgodne z zasadą snapshot consistency.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.auth_service import create_access_token, hash_password
from app.services.database import SessionLocal, User, CaseRecord

client = TestClient(app)


@pytest.fixture
def user_and_token():
    db = SessionLocal()
    user = User(
        id=str(uuid.uuid4()),
        email=f"qa-historia-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("not-a-real-password"),
        is_admin=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id, is_admin=user.is_admin)
    try:
        yield user, token
    finally:
        db.query(CaseRecord).filter(CaseRecord.user_id == user.id).delete()
        db.delete(db.query(User).filter(User.id == user.id).first())
        db.commit()
        db.close()


class TestListMyReports:
    def test_requires_auth(self):
        response = client.get("/api/me/reports")
        assert response.status_code == 401

    def test_empty_when_no_cases(self, user_and_token):
        _, token = user_and_token
        response = client.get("/api/me/reports", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json() == []

    def test_lists_own_cases_only(self, user_and_token):
        user, token = user_and_token
        headers = {"Authorization": f"Bearer {token}"}

        case_response = client.post(
            "/api/cases", json={"regulamin_accepted": True}, headers=headers
        )
        case_id = case_response.json()["case_id"]

        response = client.get("/api/me/reports", headers=headers)
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["case_id"] == case_id
        assert body[0]["verdict_category"] is None  # jeszcze bez analizy

    def test_does_not_leak_other_users_cases(self, user_and_token):
        owner, owner_token = user_and_token
        client.post(
            "/api/cases",
            json={"regulamin_accepted": True},
            headers={"Authorization": f"Bearer {owner_token}"},
        )

        db = SessionLocal()
        intruder = User(
            id=str(uuid.uuid4()),
            email=f"qa-historia-intruder-{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("not-a-real-password"),
            is_admin=False,
        )
        db.add(intruder)
        db.commit()
        intruder_token = create_access_token(intruder.id, is_admin=False)
        db.close()

        try:
            response = client.get(
                "/api/me/reports", headers={"Authorization": f"Bearer {intruder_token}"}
            )
            assert response.status_code == 200
            assert response.json() == []  # intruz nie widzi cudzych case'ów
        finally:
            cleanup_db = SessionLocal()
            cleanup_db.delete(cleanup_db.query(User).filter(User.id == intruder.id).first())
            cleanup_db.commit()
            cleanup_db.close()

    def test_includes_verdict_fields_when_decided(self, user_and_token):
        user, token = user_and_token
        case_id = str(uuid.uuid4())
        db = SessionLocal()
        db.add(CaseRecord(
            case_id=case_id,
            user_id=user.id,
            verdict_category="oryginalna_sklepowa",
            confidence_percent="90",
            report_data={
                "verdict": {
                    "confidence_percent": 90,
                    "confidence_level": "wysoki",
                    "label": "Oryginalna sklepowa",
                    "summary": "Zgodność z SKU i materiałem.",
                }
            },
        ))
        db.commit()
        db.close()

        try:
            response = client.get(
                "/api/me/reports", headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == 200
            body = response.json()
            assert len(body) == 1
            item = body[0]
            assert item["case_id"] == case_id
            assert item["verdict_category"] == "oryginalna_sklepowa"
            assert item["confidence_percent"] == 90
            assert item["confidence_level"] == "wysoki"
            assert item["label"] == "Oryginalna sklepowa"
            assert item["summary"] == "Zgodność z SKU i materiałem."
        finally:
            db = SessionLocal()
            db.query(CaseRecord).filter(CaseRecord.case_id == case_id).delete()
            db.commit()
            db.close()

    def test_newest_first(self, user_and_token):
        user, token = user_and_token
        from datetime import datetime, timedelta, timezone

        db = SessionLocal()
        older_id, newer_id = str(uuid.uuid4()), str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        db.add(CaseRecord(case_id=older_id, user_id=user.id, created_at=now - timedelta(hours=1)))
        db.add(CaseRecord(case_id=newer_id, user_id=user.id, created_at=now))
        db.commit()
        db.close()

        try:
            response = client.get(
                "/api/me/reports", headers={"Authorization": f"Bearer {token}"}
            )
            case_ids = [item["case_id"] for item in response.json()]
            assert case_ids == [newer_id, older_id]
        finally:
            db = SessionLocal()
            db.query(CaseRecord).filter(CaseRecord.case_id.in_([older_id, newer_id])).delete(
                synchronize_session=False
            )
            db.commit()
            db.close()
