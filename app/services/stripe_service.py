"""Integracja Stripe — Checkout Session + weryfikacja webhooka.

Klucze (STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, STRIPE_PUBLISHABLE_KEY) czytane
leniwie z env przy każdym wywołaniu, nie przy imporcie modułu — pozwala appce
wystartować bez skonfigurowanego Stripe (np. lokalnie, zanim Dominik założy konto)
i dopiero zwrócić czytelny błąd 500 przy próbie użycia billingu, tak jak GEMINI_API_KEY
w app/routes/cases.py.
"""
import os
from typing import Optional

import stripe

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")

# Cennik (Faza 4/5, ustalony 2026-08-18, obniżony 2026-08-28): pierwsza analiza
# zawsze darmowa (patrz User.credits default=1 w database.py) — to są ceny za
# KOLEJNE analizy. Obniżka z 15/39/119 do 10/26/79 zł — realny koszt Gemini per
# analiza to grosze (~0.30-0.50 zł), więc margines na cenie nie był ograniczeniem;
# 15 zł okazało się za wysokie względem wartości tańszych koszulek. Proporcje
# (rabat pakietowy ~13%/~21%) zachowane 1:1 względem poprzedniego cennika.
PACKAGES = {
    "single": {"credits": 1, "price_pln_grosz": 1000, "label": "1 analiza", "name": "Debiut"},
    "pack3": {"credits": 3, "price_pln_grosz": 2600, "label": "Pakiet 3 analizy", "name": "I Liga"},
    "pack10": {"credits": 10, "price_pln_grosz": 7900, "label": "Pakiet 10 analiz", "name": "Ekstraklasa"},
}


def _get_secret_key() -> str:
    key = os.getenv("STRIPE_SECRET_KEY")
    if not key:
        raise RuntimeError("Missing STRIPE_SECRET_KEY")
    return key


def create_checkout_session(user_id: str, user_email: str, package: str) -> "stripe.checkout.Session":
    """Tworzy Stripe Checkout Session dla wybranego pakietu kredytów."""
    if package not in PACKAGES:
        raise ValueError(f"Nieznany pakiet: {package}")

    stripe.api_key = _get_secret_key()
    pkg = PACKAGES[package]

    return stripe.checkout.Session.create(
        mode="payment",
        payment_method_types=["card", "blik"],
        customer_email=user_email,
        line_items=[{
            "price_data": {
                "currency": "pln",
                "unit_amount": pkg["price_pln_grosz"],
                "product_data": {"name": f"LegitScore — {pkg['label']}"},
            },
            "quantity": 1,
        }],
        success_url=f"{FRONTEND_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{FRONTEND_URL}/billing/anulowano",
        metadata={"user_id": user_id, "package": package, "credits": str(pkg["credits"])},
    )


def construct_webhook_event(payload: bytes, sig_header: Optional[str]) -> "stripe.Event":
    """Weryfikuje podpis webhooka Stripe. Rzuca stripe.error.SignatureVerificationError
    (albo ValueError) jeśli payload/podpis są nieprawidłowe — endpoint w billing.py
    łapie to i zwraca 400, żeby nikt nie mógł sfałszować zdarzenia 'opłacono'."""
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if not webhook_secret:
        raise RuntimeError("Missing STRIPE_WEBHOOK_SECRET")
    return stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
