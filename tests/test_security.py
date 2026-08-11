"""
Testy bezpieczeństwa LegitScore API.
Uruchom: pytest tests/test_security.py -v
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


class TestSecurityHeaders:
    """Testy security headers."""

    def test_security_headers_present(self):
        """Sprawdza czy security headers są ustawione."""
        response = client.get("/api/health")
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert response.headers.get("X-XSS-Protection") == "1; mode=block"
        assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    def test_report_pdf_exempted_from_x_frame_options(self):
        """
        report-pdf jest celowo osadzany w <iframe> na /przyklad (podgląd PDF) —
        musi NIE mieć X-Frame-Options: DENY, i zamiast tego mieć CSP frame-ancestors,
        żeby embedowanie w ogóle było możliwe. Wynik 404 (case nie istnieje) jest
        tu nieistotny — middleware dokłada nagłówki do KAŻDEJ odpowiedzi na tej ścieżce.
        """
        response = client.get("/api/cases/nonexistent-case-id/report-pdf")
        assert response.headers.get("X-Frame-Options") is None
        assert "frame-ancestors" in response.headers.get("Content-Security-Policy", "")
        # inne trasy nie są dotknięte tym wyjątkiem
        other = client.get("/api/health")
        assert other.headers.get("X-Frame-Options") == "DENY"
        assert "Content-Security-Policy" not in other.headers


class TestInputValidation:
    """Testy walidacji inputów."""

    def test_invalid_email_rejected(self):
        """Nieprawidłowy email jest odrzucany."""
        response = client.post(
            "/api/cases", json={"email": "invalid-email", "regulamin_accepted": True}
        )
        assert response.status_code == 400
        assert "email" in response.json()["detail"].lower()

    def test_valid_email_accepted(self):
        """Prawidłowy email jest akceptowany."""
        response = client.post(
            "/api/cases", json={"email": "test@example.com", "regulamin_accepted": True}
        )
        assert response.status_code == 200
        assert "case_id" in response.json()

    def test_empty_email_accepted(self):
        """Pusty email jest akceptowany (opcjonalne pole)."""
        response = client.post("/api/cases", json={"regulamin_accepted": True})
        assert response.status_code == 200

    def test_missing_regulamin_consent_rejected(self):
        """Brak akceptacji Regulaminu blokuje utworzenie case'a."""
        response = client.post("/api/cases", json={})
        assert response.status_code == 400
        assert "regulamin" in response.json()["detail"].lower()

    def test_invalid_case_id_rejected(self):
        """Nieprawidłowy case_id jest odrzucany."""
        response = client.get("/api/cases/invalid-id/report-data")
        # 400 dla złego formatu lub 404 dla nieistniejącego
        assert response.status_code in (400, 404)

    def test_invalid_mode_rejected(self):
        """Nieprawidłowy mode jest odrzucany."""
        # Najpierw utwórz case
        case_response = client.post("/api/cases", json={"regulamin_accepted": True})
        case_id = case_response.json()["case_id"]

        response = client.post(f"/api/cases/{case_id}/run-decision?mode=invalid")
        assert response.status_code == 400
        assert "tryb" in response.json()["detail"].lower() or "mode" in response.json()["detail"].lower()


class TestFileUploadValidation:
    """Testy walidacji uploadowanych plików."""

    def test_txt_file_rejected(self):
        """Plik .txt jest odrzucany."""
        case_response = client.post("/api/cases", json={"regulamin_accepted": True})
        case_id = case_response.json()["case_id"]

        response = client.post(
            f"/api/cases/{case_id}/assets",
            files={"files": ("test.txt", b"test content", "text/plain")}
        )
        assert response.status_code == 400
        detail = response.json()["detail"].lower()
        assert any(kw in detail for kw in ("rozszerzenie", "extension", "typ pliku", "file type", "niedozwolony"))

    def test_empty_file_rejected(self):
        """Pusty plik jest odrzucany."""
        case_response = client.post("/api/cases", json={"regulamin_accepted": True})
        case_id = case_response.json()["case_id"]

        response = client.post(
            f"/api/cases/{case_id}/assets",
            files={"files": ("test.jpg", b"", "image/jpeg")}
        )
        assert response.status_code == 400
        assert "pusty" in response.json()["detail"].lower() or "empty" in response.json()["detail"].lower()


class TestFeedbackValidation:
    """Testy walidacji feedback."""

    def test_invalid_feedback_rejected(self):
        """Nieprawidłowy feedback jest odrzucany."""
        case_response = client.post("/api/cases", json={"regulamin_accepted": True})
        case_id = case_response.json()["case_id"]

        response = client.post(
            f"/api/cases/{case_id}/feedback",
            json={"feedback": "invalid_value"}
        )
        assert response.status_code == 400


class TestHealthEndpoint:
    """Testy health endpoint."""

    def test_health_returns_ok(self):
        """Health endpoint zwraca ok."""
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["ok"] is True
