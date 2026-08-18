import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.routes.auth import get_current_user
from app.services.database import (
    User,
    get_user_credits,
    redeem_promo_code,
    create_credit_purchase,
    complete_credit_purchase,
)
from app.services.security import limiter, RATE_LIMIT_DEFAULT
from app.services.stripe_service import PACKAGES, create_checkout_session, construct_webhook_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])


class PromoRedeemRequest(BaseModel):
    code: str = Field(max_length=64)


class CheckoutRequest(BaseModel):
    package: str


@router.get("/pricing")
def get_pricing():
    """Publiczny cennik — używany przez frontend do wyświetlenia opcji zakupu."""
    return {"packages": PACKAGES}


@router.get("/credits")
def get_credits(current_user: User = Depends(get_current_user)):
    """Aktualne saldo kredytów zalogowanego usera."""
    return {"credits": get_user_credits(current_user.id)}


@router.post("/promo/redeem")
@limiter.limit(RATE_LIMIT_DEFAULT)
def redeem_promo(
    request: Request,
    data: PromoRedeemRequest,
    current_user: User = Depends(get_current_user),
):
    """Wykorzystuje kod zaproszenia — dolicza kredyty do konta, jeśli kod jest ważny
    i user jeszcze go nie użył."""
    ok, message = redeem_promo_code(current_user.id, data.code)
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    return {"ok": True, "message": message, "credits": get_user_credits(current_user.id)}


@router.post("/checkout")
@limiter.limit(RATE_LIMIT_DEFAULT)
def create_checkout(
    request: Request,
    data: CheckoutRequest,
    current_user: User = Depends(get_current_user),
):
    """Tworzy Stripe Checkout Session dla wybranego pakietu i zwraca URL do przekierowania."""
    if data.package not in PACKAGES:
        raise HTTPException(status_code=400, detail="Nieznany pakiet.")
    try:
        session = create_checkout_session(current_user.id, current_user.email, data.package)
    except RuntimeError as e:
        # Brak STRIPE_SECRET_KEY skonfigurowanego na środowisku — jasny błąd zamiast 500 bez kontekstu.
        raise HTTPException(status_code=500, detail=str(e))

    pkg = PACKAGES[data.package]
    create_credit_purchase(
        user_id=current_user.id,
        stripe_session_id=session.id,
        package=data.package,
        credits=pkg["credits"],
        amount_pln_grosz=pkg["price_pln_grosz"],
    )
    return {"checkout_url": session.url}


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Odbiera zdarzenia Stripe. Nasłuchuje checkout.session.completed i dolicza
    kredyty — idempotentnie (complete_credit_purchase ignoruje powtórki po session_id).
    Bez auth (Stripe nie wysyła naszego tokena) — bezpieczeństwo daje weryfikacja
    podpisu (construct_webhook_event), nie nagłówek Authorization."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    try:
        event = construct_webhook_event(payload, sig_header)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.warning("Stripe webhook: nieprawidłowy podpis/payload: %s", e)
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        meta = session.get("metadata") or {}
        # Fallback z metadata sesji Stripe — gdyby create_credit_purchase() (wywoływane
        # przy tworzeniu sesji, w /billing/checkout) nie zdążyło zapisać rekordu do bazy
        # (np. proces padł tuż po utworzeniu sesji), webhook mimo to doliczy kredyty
        # zamiast po cichu nic nie zrobić.
        fallback = None
        if meta.get("user_id") and meta.get("credits"):
            fallback = {
                "user_id": meta["user_id"],
                "package": meta.get("package", "unknown"),
                "credits": meta["credits"],
                "amount_pln_grosz": session.get("amount_total"),
            }
        credited = complete_credit_purchase(session["id"], fallback=fallback)
        logger.info(
            "Stripe webhook: checkout.session.completed session_id=%s credited=%s",
            session["id"], credited,
        )

    return {"received": True}
