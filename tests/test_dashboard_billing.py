"""
Testy danych billingowych w dashboardzie admina (get_user_list/get_user_detail/
get_dashboard_metrics) — Dominik chciał widzieć w dashboardzie ile użytkowników
kupiło raporty, ile mają kredytów, ile wydali.

Dashboard operuje na całej, prawdziwej bazie deweloperskiej (nie ma per-test
izolacji) — testy agregatów (`get_dashboard_metrics`) sprawdzają więc delty
(przed/po) zamiast wartości bezwzględnych, żeby nie być kruche wobec innych
danych już istniejących w bazie.
"""
import uuid

from app.services.auth_service import hash_password
from app.services.database import (
    SessionLocal,
    User,
    CollectionItem,
    CreditPurchase,
    create_credit_purchase,
    complete_credit_purchase,
    get_user_list,
    get_user_detail,
    get_dashboard_metrics,
)


def _make_user(credits: int = 1) -> User:
    db = SessionLocal()
    try:
        user = User(
            id=str(uuid.uuid4()),
            email=f"qa-dashboard-{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("not-a-real-password"),
            credits=credits,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


def _cleanup(user_id: str):
    db = SessionLocal()
    try:
        db.query(CollectionItem).filter(CollectionItem.user_id == user_id).delete()
        db.query(CreditPurchase).filter(CreditPurchase.user_id == user_id).delete()
        db.query(User).filter(User.id == user_id).delete()
        db.commit()
    finally:
        db.close()


class TestGetUserListBillingFields:
    def test_user_without_purchases_shows_zeroes(self):
        user = _make_user(credits=1)
        try:
            row = next(r for r in get_user_list() if r["id"] == user.id)
            assert row["credits"] == 1
            assert row["purchase_count"] == 0
            assert row["credits_purchased"] == 0
            assert row["amount_spent_pln_grosz"] == 0
        finally:
            _cleanup(user.id)

    def test_completed_purchase_reflected_in_list(self):
        user = _make_user(credits=0)
        session_id = f"cs_test_{uuid.uuid4().hex[:12]}"
        try:
            create_credit_purchase(
                user_id=user.id, stripe_session_id=session_id, package="pack3",
                credits=3, amount_pln_grosz=3900,
            )
            complete_credit_purchase(session_id)

            row = next(r for r in get_user_list() if r["id"] == user.id)
            assert row["credits"] == 3
            assert row["purchase_count"] == 1
            assert row["credits_purchased"] == 3
            assert row["amount_spent_pln_grosz"] == 3900
        finally:
            _cleanup(user.id)

    def test_pending_purchase_not_counted(self):
        user = _make_user(credits=0)
        session_id = f"cs_test_{uuid.uuid4().hex[:12]}"
        try:
            create_credit_purchase(
                user_id=user.id, stripe_session_id=session_id, package="single",
                credits=1, amount_pln_grosz=1500,
            )
            # nie wołamy complete_credit_purchase — sesja zostaje "pending"

            row = next(r for r in get_user_list() if r["id"] == user.id)
            assert row["purchase_count"] == 0
            assert row["amount_spent_pln_grosz"] == 0
        finally:
            _cleanup(user.id)

    def test_multiple_completed_purchases_summed(self):
        user = _make_user(credits=0)
        session_a = f"cs_test_{uuid.uuid4().hex[:12]}"
        session_b = f"cs_test_{uuid.uuid4().hex[:12]}"
        try:
            create_credit_purchase(
                user_id=user.id, stripe_session_id=session_a, package="single",
                credits=1, amount_pln_grosz=1500,
            )
            complete_credit_purchase(session_a)
            create_credit_purchase(
                user_id=user.id, stripe_session_id=session_b, package="pack10",
                credits=10, amount_pln_grosz=11900,
            )
            complete_credit_purchase(session_b)

            row = next(r for r in get_user_list() if r["id"] == user.id)
            assert row["purchase_count"] == 2
            assert row["credits_purchased"] == 11
            assert row["amount_spent_pln_grosz"] == 1500 + 11900
        finally:
            _cleanup(user.id)


class TestGetUserDetailBillingFields:
    def test_includes_credits_collection_count_and_purchases(self):
        user = _make_user(credits=0)
        session_id = f"cs_test_{uuid.uuid4().hex[:12]}"
        db = SessionLocal()
        try:
            db.add(CollectionItem(
                id=str(uuid.uuid4()), user_id=user.id, case_id=f"manual_{uuid.uuid4().hex[:12]}",
                is_manual=True,
            ))
            db.commit()
        finally:
            db.close()
        try:
            create_credit_purchase(
                user_id=user.id, stripe_session_id=session_id, package="pack3",
                credits=3, amount_pln_grosz=3900,
            )
            complete_credit_purchase(session_id)

            detail = get_user_detail(user.id)
            assert detail["credits"] == 3
            assert detail["collection_count"] == 1
            assert len(detail["purchases"]) == 1
            assert detail["purchases"][0]["package"] == "pack3"
            assert detail["purchases"][0]["amount_pln_grosz"] == 3900
        finally:
            _cleanup(user.id)

    def test_unknown_user_returns_none(self):
        assert get_user_detail(str(uuid.uuid4())) is None

    def test_user_without_purchases_has_empty_list_and_zero_collection(self):
        user = _make_user(credits=1)
        try:
            detail = get_user_detail(user.id)
            assert detail["credits"] == 1
            assert detail["collection_count"] == 0
            assert detail["purchases"] == []
        finally:
            _cleanup(user.id)


class TestDashboardMetricsBillingAggregate:
    def test_completed_purchase_increases_revenue_and_purchase_totals(self):
        user = _make_user(credits=0)
        session_id = f"cs_test_{uuid.uuid4().hex[:12]}"
        try:
            before = get_dashboard_metrics()["billing"]

            create_credit_purchase(
                user_id=user.id, stripe_session_id=session_id, package="pack10",
                credits=10, amount_pln_grosz=11900,
            )
            complete_credit_purchase(session_id)

            after = get_dashboard_metrics()["billing"]
            assert after["total_purchases"] == before["total_purchases"] + 1
            assert after["total_revenue_pln_grosz"] == before["total_revenue_pln_grosz"] + 11900
            assert after["total_credits_sold"] == before["total_credits_sold"] + 10
            # completed_at ustawiane na "teraz" — mieści się w oknie 7 dni.
            assert after["revenue_7d_pln_grosz"] == before["revenue_7d_pln_grosz"] + 11900
            # total_users nie zmienia się między before/after (user utworzony
            # przed pomiarem "before") — konwersja nie może spaść.
            assert after["paying_conversion_pct"] >= before["paying_conversion_pct"]
            assert after["users_with_purchase"] == before["users_with_purchase"] + 1
        finally:
            _cleanup(user.id)
