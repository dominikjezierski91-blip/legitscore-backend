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
