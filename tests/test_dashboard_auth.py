"""
Testy autoryzacji backoffice'u (dashboard, support, monitoring).

Przed tą zmianą wszystkie te endpointy były w pełni publiczne — każdy znający
URL widział emaile userów, historię analiz i zgłoszenia support. Testuje,
że każdy z nich odrzuca żądania bez ważnego tokena admina.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.auth_service import create_access_token, hash_password
from app.services.database import SessionLocal, User

client = TestClient(app)


@pytest.fixture
def non_admin_token():
    """Tworzy tymczasowego, NIE-adminowego usera i zwraca jego ważny token. Sprząta po sobie."""
    db = SessionLocal()
    user = User(
        id=str(uuid.uuid4()),
        email=f"qa-non-admin-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("not-a-real-password"),
        is_admin=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id, is_admin=user.is_admin)
    try:
        yield token
    finally:
        db.delete(db.query(User).filter(User.id == user.id).first())
        db.commit()
        db.close()


DASHBOARD_ENDPOINTS = [
    ("GET", "/api/dashboard/cases"),
    ("GET", "/api/dashboard/stats"),
    ("GET", "/api/dashboard/user-stats"),
    ("GET", "/api/dashboard/users"),
    ("GET", "/api/dashboard/metrics"),
    ("GET", "/api/dashboard/activation"),
    ("GET", "/api/dashboard/retention"),
    ("GET", "/api/dashboard/registrations"),
    ("GET", "/api/dashboard/users/someone@example.com"),
]

SUPPORT_ADMIN_ENDPOINTS = [
    ("GET", "/api/support"),
    ("GET", "/api/support/nonexistent-id"),
    ("PATCH", "/api/support/nonexistent-id"),
]

MONITORING_ADMIN_ENDPOINTS = [
    ("GET", "/api/monitoring/tickets"),
    ("POST", "/api/monitoring/tickets/T-1/status"),
    ("POST", "/api/monitoring/tickets/T-1/resolve"),
]


def _call(method: str, path: str):
    if method == "GET":
        return client.get(path)
    if method == "POST":
        return client.post(path, json={"status": "Nowy"})
    if method == "PATCH":
        return client.patch(path, json={"status": "nowe"})
    raise ValueError(method)


class TestDashboardRequiresAdmin:
    @pytest.mark.parametrize("method,path", DASHBOARD_ENDPOINTS)
    def test_no_token_rejected(self, method, path):
        response = _call(method, path)
        assert response.status_code == 401

    @pytest.mark.parametrize("method,path", DASHBOARD_ENDPOINTS)
    def test_bogus_token_rejected(self, method, path):
        response = client.request(
            method,
            path,
            headers={"Authorization": "Bearer not-a-real-token"},
            json={"status": "Nowy"} if method != "GET" else None,
        )
        assert response.status_code == 401

    def test_logged_in_non_admin_gets_403(self, non_admin_token):
        """
        get_current_admin musi odróżniać 'brak tokena' (401) od 'ważny token,
        ale is_admin=False' (403) — inaczej dowolny zarejestrowany user
        (nie tylko anonimowy gość) mógłby zobaczyć backoffice.
        """
        response = client.get(
            "/api/dashboard/stats",
            headers={"Authorization": f"Bearer {non_admin_token}"},
        )
        assert response.status_code == 403


class TestSupportBackofficeRequiresAdmin:
    @pytest.mark.parametrize("method,path", SUPPORT_ADMIN_ENDPOINTS)
    def test_no_token_rejected(self, method, path):
        response = _call(method, path)
        assert response.status_code == 401

    def test_public_submit_endpoint_still_open(self):
        """POST /api/support (zgłoszenie od usera) musi zostać publiczne — to nie backoffice."""
        response = client.post(
            "/api/support",
            json={"type": "pytanie", "message": "test", "email": "test@example.com"},
        )
        assert response.status_code != 401


class TestMonitoringRequiresAdmin:
    @pytest.mark.parametrize("method,path", MONITORING_ADMIN_ENDPOINTS)
    def test_no_token_rejected(self, method, path):
        response = _call(method, path)
        assert response.status_code == 401
