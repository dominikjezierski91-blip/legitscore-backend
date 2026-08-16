"""
Testy powiązania case'a z zalogowanym userem (Faza 0 planu kont/kolekcji/płatności).

Upload/tworzenie case'a ma działać zarówno anonimowo (dziś: bez zmian), jak i —
gdy request niesie ważny token — od razu z ustawionym user_id, żeby analiza
trafiła później do Historii danego konta.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.auth_service import create_access_token, hash_password
from app.services.database import SessionLocal, User, get_case_from_db

client = TestClient(app)


@pytest.fixture
def user_and_token():
    db = SessionLocal()
    user = User(
        id=str(uuid.uuid4()),
        email=f"qa-case-owner-{uuid.uuid4().hex[:8]}@example.com",
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
        db.delete(db.query(User).filter(User.id == user.id).first())
        db.commit()
        db.close()


class TestCaseOwnership:
    def test_anonymous_case_has_no_user_id(self):
        response = client.post("/api/cases", json={"regulamin_accepted": True})
        assert response.status_code == 200
        case_id = response.json()["case_id"]
        record = get_case_from_db(case_id)
        assert record.user_id is None

    def test_authenticated_case_gets_user_id(self, user_and_token):
        user, token = user_and_token
        response = client.post(
            "/api/cases",
            json={"regulamin_accepted": True},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        case_id = response.json()["case_id"]
        record = get_case_from_db(case_id)
        assert record.user_id == user.id

    def test_invalid_token_falls_back_to_anonymous(self):
        response = client.post(
            "/api/cases",
            json={"regulamin_accepted": True},
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        assert response.status_code == 200
        case_id = response.json()["case_id"]
        record = get_case_from_db(case_id)
        assert record.user_id is None


class TestRunDecisionAuthGate:
    """run-decision kosztuje (Gemini) — musi wymagać logowania i uszanować własność case'a."""

    def test_run_decision_without_auth_is_rejected(self):
        case_response = client.post("/api/cases", json={"regulamin_accepted": True})
        case_id = case_response.json()["case_id"]

        response = client.post(f"/api/cases/{case_id}/run-decision?mode=basic")
        assert response.status_code == 401

    def test_run_decision_on_nonexistent_case_does_not_create_db_row(self, user_and_token):
        """Podstawiony, nigdy-nieutworzony UUID musi 404-ować BEZ zapisu do DB — inaczej
        dowolny zalogowany user mógłby zaśmiecać tabelę cases osieroconymi wierszami."""
        _, token = user_and_token
        fake_case_id = str(uuid.uuid4())
        assert get_case_from_db(fake_case_id) is None

        response = client.post(
            f"/api/cases/{fake_case_id}/run-decision?mode=basic",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404
        assert get_case_from_db(fake_case_id) is None

    def test_run_decision_backfills_user_id_on_anonymous_case(self, user_and_token):
        """Case stworzony anonimowo (upload bez logowania), analiza odpalona po zalogowaniu —
        user_id ma się dopisać, mimo że sama analiza i tak zawiedzie (brak zdjęć)."""
        user, token = user_and_token
        case_response = client.post("/api/cases", json={"regulamin_accepted": True})
        case_id = case_response.json()["case_id"]
        assert get_case_from_db(case_id).user_id is None

        response = client.post(
            f"/api/cases/{case_id}/run-decision?mode=basic",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 400  # brak zdjęć — ale to już PO auth gate
        assert get_case_from_db(case_id).user_id == user.id

    def test_run_decision_rejects_other_users_case(self, user_and_token):
        owner, owner_token = user_and_token
        case_response = client.post(
            "/api/cases",
            json={"regulamin_accepted": True},
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        case_id = case_response.json()["case_id"]
        assert get_case_from_db(case_id).user_id == owner.id

        db = SessionLocal()
        intruder = User(
            id=str(uuid.uuid4()),
            email=f"qa-intruder-{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("not-a-real-password"),
            is_admin=False,
        )
        db.add(intruder)
        db.commit()
        db.refresh(intruder)
        intruder_token = create_access_token(intruder.id, is_admin=False)
        db.close()

        try:
            response = client.post(
                f"/api/cases/{case_id}/run-decision?mode=basic",
                headers={"Authorization": f"Bearer {intruder_token}"},
            )
            assert response.status_code == 403
            assert get_case_from_db(case_id).user_id == owner.id  # niezmienione
        finally:
            cleanup_db = SessionLocal()
            cleanup_db.delete(cleanup_db.query(User).filter(User.id == intruder.id).first())
            cleanup_db.commit()
            cleanup_db.close()
