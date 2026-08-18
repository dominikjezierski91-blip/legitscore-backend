"""
Testy systemu kredytów / limitu darmowych analiz (Faza 4/5).

Testujemy wyłącznie logikę backendu (baza danych + gate w run-decision) — Stripe
i faktyczne wywołania Gemini są poza zakresem tych testów. Zgodnie z konwencją
reszty projektu (patrz test_security.py/_auth_headers_for_new_user) testy działają
na prawdziwej bazie deweloperskiej, tworząc tymczasowe rekordy z losowym sufiksem
i sprzątając je w bloku finally.
"""
import uuid
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.services.storage import load_case, save_case
from app.services.auth_service import create_access_token, hash_password
from app.services.database import (
    SessionLocal,
    User,
    PromoCode,
    PromoRedemption,
    AllowlistedEmail,
    CreditPurchase,
    get_user_credits,
    consume_credit,
    refund_credit,
    add_credits,
    redeem_promo_code,
    apply_allowlist_if_matched,
    create_credit_purchase,
    complete_credit_purchase,
)

client = TestClient(app)


def _make_user(credits: int = 1) -> User:
    db = SessionLocal()
    try:
        user = User(
            id=str(uuid.uuid4()),
            email=f"qa-credits-{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("not-a-real-password"),
            is_admin=False,
            credits=credits,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


def _cleanup(user_id: str, promo_code: str = None):
    db = SessionLocal()
    try:
        db.query(CreditPurchase).filter(CreditPurchase.user_id == user_id).delete()
        db.query(PromoRedemption).filter(PromoRedemption.user_id == user_id).delete()
        if promo_code:
            db.query(PromoCode).filter(PromoCode.code == promo_code).delete()
        u = db.query(User).filter(User.id == user_id).first()
        if u:
            db.delete(u)
        db.commit()
    finally:
        db.close()


class TestConsumeAndRefundCredit:
    def test_consume_credit_decrements_and_blocks_double_spend(self):
        user = _make_user(credits=1)
        try:
            assert consume_credit(user.id) is True
            assert get_user_credits(user.id) == 0
            # Drugie wywołanie na zerowym saldzie nie może się udać (no double-spend).
            assert consume_credit(user.id) is False
            assert get_user_credits(user.id) == 0
        finally:
            _cleanup(user.id)

    def test_refund_credit_restores_balance(self):
        user = _make_user(credits=1)
        try:
            assert consume_credit(user.id) is True
            refund_credit(user.id)
            assert get_user_credits(user.id) == 1
        finally:
            _cleanup(user.id)

    def test_add_credits_is_additive_not_overwriting(self):
        user = _make_user(credits=2)
        try:
            new_balance = add_credits(user.id, 3)
            assert new_balance == 5
            assert get_user_credits(user.id) == 5
        finally:
            _cleanup(user.id)


class TestPromoCode:
    def test_unknown_code_returns_false_without_raising(self):
        user = _make_user(credits=0)
        try:
            ok, message = redeem_promo_code(user.id, "TO-NIE-ISTNIEJE")
            assert ok is False
            assert get_user_credits(user.id) == 0
        finally:
            _cleanup(user.id)

    def test_valid_code_credits_once_then_rejects_second_redeem(self):
        user = _make_user(credits=0)
        code = f"TEST-{uuid.uuid4().hex[:8]}"
        db = SessionLocal()
        try:
            db.add(PromoCode(code=code, credits=3, max_uses=None))
            db.commit()
        finally:
            db.close()

        try:
            ok, _ = redeem_promo_code(user.id, code)
            assert ok is True
            assert get_user_credits(user.id) == 3

            # Ten sam user, ten sam kod — drugi raz musi się nie udać (bez podwojenia).
            ok2, message2 = redeem_promo_code(user.id, code)
            assert ok2 is False
            assert get_user_credits(user.id) == 3
        finally:
            _cleanup(user.id, promo_code=code)

    def test_max_uses_limit_enforced(self):
        user_a = _make_user(credits=0)
        user_b = _make_user(credits=0)
        code = f"TEST-LIMIT-{uuid.uuid4().hex[:8]}"
        db = SessionLocal()
        try:
            db.add(PromoCode(code=code, credits=1, max_uses=1))
            db.commit()
        finally:
            db.close()

        try:
            ok_a, _ = redeem_promo_code(user_a.id, code)
            assert ok_a is True
            ok_b, message_b = redeem_promo_code(user_b.id, code)
            assert ok_b is False
            assert get_user_credits(user_b.id) == 0
        finally:
            _cleanup(user_a.id)
            _cleanup(user_b.id, promo_code=code)


class TestAllowlist:
    def test_matching_email_credits_once(self):
        user = _make_user(credits=0)
        db = SessionLocal()
        try:
            db.add(AllowlistedEmail(email=user.email.lower(), credits=2))
            db.commit()
        finally:
            db.close()

        try:
            granted = apply_allowlist_if_matched(user.id, user.email)
            assert granted == 2
            assert get_user_credits(user.id) == 2

            # Drugie wywołanie (np. przy kolejnym logowaniu) nic już nie dolicza.
            granted_again = apply_allowlist_if_matched(user.id, user.email)
            assert granted_again == 0
            assert get_user_credits(user.id) == 2
        finally:
            db = SessionLocal()
            try:
                db.query(AllowlistedEmail).filter(AllowlistedEmail.email == user.email.lower()).delete()
                db.commit()
            finally:
                db.close()
            _cleanup(user.id)


class TestStripePurchaseIdempotency:
    def test_completing_same_session_twice_credits_only_once(self):
        user = _make_user(credits=0)
        session_id = f"cs_test_{uuid.uuid4().hex[:12]}"
        try:
            create_credit_purchase(
                user_id=user.id,
                stripe_session_id=session_id,
                package="pack3",
                credits=3,
                amount_pln_grosz=3900,
            )

            first = complete_credit_purchase(session_id)
            assert first is True
            assert get_user_credits(user.id) == 3

            # Symulacja powtórnej dostawy tego samego webhooka Stripe.
            second = complete_credit_purchase(session_id)
            assert second is False
            assert get_user_credits(user.id) == 3
        finally:
            _cleanup(user.id)

    def test_fallback_reconstructs_missing_purchase_record(self):
        """Gdyby create_credit_purchase() nie zdążyło zapisać rekordu, webhook
        i tak dolicza kredyty na podstawie metadata z sesji Stripe."""
        user = _make_user(credits=0)
        session_id = f"cs_test_{uuid.uuid4().hex[:12]}"
        try:
            result = complete_credit_purchase(
                session_id,
                fallback={"user_id": user.id, "package": "single", "credits": 1, "amount_pln_grosz": 1500},
            )
            assert result is True
            assert get_user_credits(user.id) == 1

            # Powtórka (druga dostawa tego samego webhooka) nie dolicza drugi raz.
            result2 = complete_credit_purchase(
                session_id,
                fallback={"user_id": user.id, "package": "single", "credits": 1, "amount_pln_grosz": 1500},
            )
            assert result2 is False
            assert get_user_credits(user.id) == 1
        finally:
            _cleanup(user.id)


class TestRunDecisionCreditGate:
    def test_run_decision_returns_402_when_no_credits(self):
        user = _make_user(credits=0)
        token = create_access_token(user.id, is_admin=False)
        headers = {"Authorization": f"Bearer {token}"}
        try:
            case_response = client.post("/api/cases", json={"regulamin_accepted": True})
            case_id = case_response.json()["case_id"]

            response = client.post(f"/api/cases/{case_id}/run-decision", headers=headers)
            assert response.status_code == 402
            # Bez kredytu nie mogliśmy w ogóle dotrzeć do sprawdzenia assetów/Gemini.
            assert get_user_credits(user.id) == 0
        finally:
            _cleanup(user.id)

    def test_gemini_failure_mid_pipeline_refunds_credit(self):
        """Regresja na realny incydent (2026-08-18): GeminiAgentA().analyze() rzucił
        HTTPException(502, ...) (ServerError od Gemini) w środku pipeline'u — to
        omijało refund_credit, bo tylko precheck/walidacja miały własny refund przed
        swoim raise, a każdy INNY HTTPException z tej ścieżki (w tym właśnie ten z
        analyze()) zjadał kredyt bezpowrotnie. Naprawa: jeden centralny refund w
        `except HTTPException` obejmujący całą ścieżkę. Mockujemy dokładnie tę samą
        funkcję, która zawiodła na produkcji (nie combined_coverage_quality_check —
        ta w realnym kodzie łapie błędy Gemini wewnętrznie i nigdy nie rzuca)."""
        user = _make_user(credits=1)
        token = create_access_token(user.id, is_admin=False)
        headers = {"Authorization": f"Bearer {token}"}
        try:
            case_response = client.post(
                "/api/cases", json={"regulamin_accepted": True}, headers=headers
            )
            case_id = case_response.json()["case_id"]

            # Wstrzykujemy fałszywy asset bezpośrednio do case'a na dysku — omijamy
            # realny upload/walidację obrazu.
            case_data = load_case(case_id)
            case_data["assets"] = [{"path": f"cases/{case_id}/assets/fake.jpg"}]
            save_case(case_id, case_data)

            # Precheck musi przejść (wymagane widoki wykryte), żeby pipeline w ogóle
            # dotarł do GeminiAgentA().analyze() — to tam nastąpił realny incydent.
            fake_coverage_result = {
                "detected_views": {"front_full": True, "crest_or_brand_closeup": True},
                "issues": [],
                "missing_optional": [],
            }

            with patch(
                "app.routes.cases.combined_coverage_quality_check",
                return_value=fake_coverage_result,
            ), patch(
                "app.routes.cases.GeminiAgentA.analyze",
                side_effect=HTTPException(status_code=502, detail="Chwilowy problem z usługą analizy AI."),
            ):
                response = client.post(f"/api/cases/{case_id}/run-decision", headers=headers)

            assert response.status_code == 502
            assert get_user_credits(user.id) == 1  # kredyt wrócił

            case_data_after = load_case(case_id)
            assert case_data_after.get("status") == "ERROR"
        finally:
            _cleanup(user.id)
