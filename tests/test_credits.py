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
    CaseRecord,
    PromoCode,
    PromoRedemption,
    AllowlistedEmail,
    CreditPurchase,
    LUCKY_CODE,
    get_user_credits,
    consume_credit,
    refund_credit,
    add_credits,
    redeem_promo_code,
    apply_allowlist_if_matched,
    create_credit_purchase,
    complete_credit_purchase,
    get_lucky_code_status,
    _seed_lucky_code,
    get_billing_summary,
)

client = TestClient(app)


def _make_user(credits: int = 1, is_admin: bool = False) -> User:
    db = SessionLocal()
    try:
        user = User(
            id=str(uuid.uuid4()),
            email=f"qa-credits-{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("not-a-real-password"),
            is_admin=is_admin,
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


class TestBillingSummary:
    def test_counts_only_decided_cases_as_analyses(self):
        user = _make_user(credits=1)
        decided_id = str(uuid.uuid4())
        pending_id = str(uuid.uuid4())
        db = SessionLocal()
        try:
            db.add(CaseRecord(case_id=decided_id, user_id=user.id, verdict_category="oryginalna_sklepowa"))
            db.add(CaseRecord(case_id=pending_id, user_id=user.id, verdict_category=None))
            db.commit()
        finally:
            db.close()

        try:
            summary = get_billing_summary(user.id)
            assert summary["credits"] == 1
            assert summary["analyses_completed"] == 1
        finally:
            db2 = SessionLocal()
            try:
                db2.query(CaseRecord).filter(CaseRecord.case_id.in_([decided_id, pending_id])).delete(
                    synchronize_session=False
                )
                db2.commit()
            finally:
                db2.close()
            _cleanup(user.id)

    def test_purchases_only_include_completed_newest_first(self):
        user = _make_user(credits=0)
        old_session = f"cs_test_{uuid.uuid4().hex[:12]}"
        new_session = f"cs_test_{uuid.uuid4().hex[:12]}"
        pending_session = f"cs_test_{uuid.uuid4().hex[:12]}"
        try:
            create_credit_purchase(
                user_id=user.id, stripe_session_id=old_session, package="single",
                credits=1, amount_pln_grosz=1500,
            )
            complete_credit_purchase(old_session)

            create_credit_purchase(
                user_id=user.id, stripe_session_id=new_session, package="pack3",
                credits=3, amount_pln_grosz=3900,
            )
            complete_credit_purchase(new_session)

            # Nieukończona sesja (user porzucił checkout) — nie powinna trafić do historii.
            create_credit_purchase(
                user_id=user.id, stripe_session_id=pending_session, package="pack10",
                credits=10, amount_pln_grosz=11900,
            )

            summary = get_billing_summary(user.id)
            packages = [p["package"] for p in summary["purchases"]]
            assert packages == ["pack3", "single"]
        finally:
            _cleanup(user.id)

    def test_other_users_data_never_leaks_into_summary(self):
        """Pilnuje, żeby filtr user_id nigdy nie został przypadkiem zgubiony —
        analiza i zakup usera A nie mogą pojawić się w podsumowaniu usera B."""
        user_a = _make_user(credits=0)
        user_b = _make_user(credits=5)
        case_id = str(uuid.uuid4())
        session_id = f"cs_test_{uuid.uuid4().hex[:12]}"
        db = SessionLocal()
        try:
            db.add(CaseRecord(case_id=case_id, user_id=user_a.id, verdict_category="oryginalna_sklepowa"))
            db.commit()
        finally:
            db.close()
        try:
            create_credit_purchase(
                user_id=user_a.id, stripe_session_id=session_id, package="single",
                credits=1, amount_pln_grosz=1500,
            )
            complete_credit_purchase(session_id)

            summary_b = get_billing_summary(user_b.id)
            assert summary_b["credits"] == 5
            assert summary_b["analyses_completed"] == 0
            assert summary_b["purchases"] == []
        finally:
            db2 = SessionLocal()
            try:
                db2.query(CaseRecord).filter(CaseRecord.case_id == case_id).delete()
                db2.commit()
            finally:
                db2.close()
            _cleanup(user_a.id)
            _cleanup(user_b.id)

    def test_endpoint_requires_auth(self):
        response = client.get("/api/billing/summary")
        assert response.status_code in (401, 403)

    def test_endpoint_returns_summary_for_authenticated_user(self):
        user = _make_user(credits=2)
        token = create_access_token(user.id, is_admin=False)
        headers = {"Authorization": f"Bearer {token}"}
        try:
            response = client.get("/api/billing/summary", headers=headers)
            assert response.status_code == 200
            data = response.json()
            assert data["credits"] == 2
            assert data["analyses_completed"] == 0
            assert data["purchases"] == []
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

    def test_admin_bypasses_credit_gate_entirely(self):
        """Adminom (np. Dominik weryfikujący koszulki od userów) nie liczymy
        kredytów w ogóle — zero kredytów na koncie nie może skutkować 402, i
        request nie powinien ani konsumować, ani zwracać żadnego kredytu."""
        admin = _make_user(credits=0, is_admin=True)
        token = create_access_token(admin.id, is_admin=True)
        headers = {"Authorization": f"Bearer {token}"}
        try:
            case_response = client.post(
                "/api/cases", json={"regulamin_accepted": True}, headers=headers
            )
            case_id = case_response.json()["case_id"]

            # Bez assetów i tak polegnie (400) — ale kluczowe jest, że NIE 402,
            # mimo credits=0, i że saldo w ogóle się nie rusza (nic nie było
            # "wydane", więc refund_credit nie powinien nic doliczyć).
            response = client.post(f"/api/cases/{case_id}/run-decision", headers=headers)
            assert response.status_code != 402
            assert get_user_credits(admin.id) == 0
        finally:
            _cleanup(admin.id)


class TestLuckyCode:
    """LS7 — ewergrinowy kod promo widoczny w apce dopiero po pierwszej ukończonej
    analizie. Kod sam w sobie jest zasiany raz przy starcie appki (_seed_lucky_code),
    więc tu tylko sprawdzamy widoczność (get_lucky_code_status) i realne odebranie
    przez redeem_promo_code — nie tworzymy własnego PromoCode."""

    def _add_completed_case(self, user_id: str) -> str:
        case_id = str(uuid.uuid4())
        db = SessionLocal()
        try:
            db.add(CaseRecord(case_id=case_id, user_id=user_id, verdict_category="oryginalna_sklepowa"))
            db.commit()
        finally:
            db.close()
        return case_id

    def _delete_case(self, case_id: str):
        db = SessionLocal()
        try:
            db.query(CaseRecord).filter(CaseRecord.case_id == case_id).delete()
            db.commit()
        finally:
            db.close()

    def test_not_available_without_completed_analysis(self):
        user = _make_user(credits=0)
        try:
            status = get_lucky_code_status(user.id)
            assert status["code"] == LUCKY_CODE
            assert status["available"] is False
        finally:
            _cleanup(user.id)

    def test_available_after_one_completed_analysis(self):
        user = _make_user(credits=0)
        case_id = self._add_completed_case(user.id)
        try:
            status = get_lucky_code_status(user.id)
            assert status["available"] is True
        finally:
            self._delete_case(case_id)
            _cleanup(user.id)

    def test_redeeming_grants_credits_and_hides_banner_again(self):
        user = _make_user(credits=0)
        case_id = self._add_completed_case(user.id)
        try:
            ok, _ = redeem_promo_code(user.id, LUCKY_CODE)
            assert ok is True
            assert get_user_credits(user.id) == 2

            status = get_lucky_code_status(user.id)
            assert status["available"] is False
        finally:
            self._delete_case(case_id)
            _cleanup(user.id)

    def test_case_without_verdict_does_not_unlock_banner(self):
        """Case w trakcie/nieudany (verdict_category jeszcze NULL) nie liczy się
        jako 'ukończona analiza' — to najbardziej prawdopodobne miejsce na regres
        w warunku isnot(None)."""
        user = _make_user(credits=0)
        case_id = str(uuid.uuid4())
        db = SessionLocal()
        try:
            db.add(CaseRecord(case_id=case_id, user_id=user.id, verdict_category=None))
            db.commit()
        finally:
            db.close()
        try:
            status = get_lucky_code_status(user.id)
            assert status["available"] is False
        finally:
            self._delete_case(case_id)
            _cleanup(user.id)

    def test_other_users_completed_analysis_does_not_unlock_banner(self):
        """Ukończona analiza usera A nie może odblokować bannera dla usera B —
        pilnuje, żeby filtr user_id nigdy nie został przypadkiem zgubiony."""
        user_a = _make_user(credits=0)
        user_b = _make_user(credits=0)
        case_id = self._add_completed_case(user_a.id)
        try:
            assert get_lucky_code_status(user_a.id)["available"] is True
            assert get_lucky_code_status(user_b.id)["available"] is False
        finally:
            self._delete_case(case_id)
            _cleanup(user_a.id)
            _cleanup(user_b.id)

    def test_seed_is_idempotent_on_repeated_calls(self):
        """_seed_lucky_code() jest wołane przy każdym starcie appki — drugie
        wywołanie nie może rzucić (unique PK) ani zduplikować wiersza."""
        _seed_lucky_code()
        _seed_lucky_code()
        db = SessionLocal()
        try:
            count = db.query(PromoCode).filter(PromoCode.code == LUCKY_CODE).count()
            assert count == 1
        finally:
            db.close()

    def test_endpoint_requires_auth(self):
        response = client.get("/api/billing/lucky-code")
        assert response.status_code in (401, 403)

    def test_endpoint_returns_status_for_authenticated_user(self):
        user = _make_user(credits=0)
        token = create_access_token(user.id, is_admin=False)
        headers = {"Authorization": f"Bearer {token}"}
        try:
            response = client.get("/api/billing/lucky-code", headers=headers)
            assert response.status_code == 200
            data = response.json()
            assert data["code"] == LUCKY_CODE
            assert data["available"] is False
        finally:
            _cleanup(user.id)


class TestRegulaminVersionSync:
    def test_create_case_updates_user_regulamin_version(self):
        """Regresja (2026-08-19): POST /api/cases zapisywał zaakceptowaną wersję
        Regulaminu tylko na CaseRecord, nigdy na User — więc /auth/me zawsze
        zwracał regulamin_version sprzed rejestracji, i checkbox zgody pokazywał
        się w nieskończoność userom, którzy założyli konto przed podniesieniem
        wersji regulaminu, mimo że właśnie ją zaakceptowali przy zgłoszeniu."""
        user = _make_user(credits=1)
        db = SessionLocal()
        try:
            db.query(User).filter(User.id == user.id).update({User.regulamin_version: "1.0"})
            db.commit()
        finally:
            db.close()

        token = create_access_token(user.id, is_admin=False)
        headers = {"Authorization": f"Bearer {token}"}
        try:
            response = client.post(
                "/api/cases",
                json={"regulamin_accepted": True, "regulamin_version": "2.0", "privacy_version": "2.0"},
                headers=headers,
            )
            assert response.status_code == 200

            db2 = SessionLocal()
            try:
                refreshed = db2.query(User).filter(User.id == user.id).first()
                assert refreshed.regulamin_version == "2.0"
                assert refreshed.privacy_version == "2.0"
            finally:
                db2.close()
        finally:
            _cleanup(user.id)

    def test_anonymous_case_creation_does_not_touch_any_user(self):
        """Gość (bez tokena) tworzy case anonimowo — nie ma current_user, więc
        update_user_regulamin_acceptance w ogóle nie powinno się wywołać."""
        response = client.post(
            "/api/cases",
            json={"regulamin_accepted": True, "regulamin_version": "2.0"},
        )
        assert response.status_code == 200
