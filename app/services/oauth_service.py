"""
Weryfikacja tokenów logowania społecznościowego (Google / Facebook) po stronie serwera.

Front dostaje token bezpośrednio od dostawcy (Google Identity Services / Facebook JS SDK)
i przekazuje go do backendu — backend NIGDY nie ufa danym usera bez weryfikacji tokena
u dostawcy (inaczej ktokolwiek mógłby podać dowolny email i przejąć/założyć cudze konto).
"""
import logging
import os
from dataclasses import dataclass
from typing import Optional

import requests
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

logger = logging.getLogger(__name__)

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
FACEBOOK_APP_ID = os.getenv("FACEBOOK_APP_ID", "")
FACEBOOK_APP_SECRET = os.getenv("FACEBOOK_APP_SECRET", "")


class OAuthVerificationError(Exception):
    """Token nieprawidłowy, wygasły, albo wystawiony dla innej aplikacji."""


@dataclass
class OAuthIdentity:
    provider: str  # "google" | "facebook"
    sub: str       # unikalny ID usera u dostawcy
    email: Optional[str]
    name: Optional[str]


def verify_google_id_token(token: str) -> OAuthIdentity:
    if not GOOGLE_CLIENT_ID:
        raise OAuthVerificationError("Logowanie przez Google nie jest skonfigurowane (brak GOOGLE_CLIENT_ID).")
    try:
        payload = google_id_token.verify_oauth2_token(
            token, google_requests.Request(), audience=GOOGLE_CLIENT_ID
        )
    except ValueError as e:
        logger.warning("Google id_token weryfikacja nieudana: %s", e)
        raise OAuthVerificationError("Nieprawidłowy lub wygasły token Google.") from e

    if payload.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise OAuthVerificationError("Nieprawidłowy wystawca tokena Google.")

    email = payload.get("email") if payload.get("email_verified") else None
    return OAuthIdentity(
        provider="google",
        sub=payload["sub"],
        email=email,
        name=payload.get("name"),
    )


def verify_facebook_access_token(access_token: str) -> OAuthIdentity:
    if not FACEBOOK_APP_ID or not FACEBOOK_APP_SECRET:
        raise OAuthVerificationError("Logowanie przez Facebook nie jest skonfigurowane (brak FACEBOOK_APP_ID/SECRET).")

    try:
        debug = requests.get(
            "https://graph.facebook.com/debug_token",
            params={
                "input_token": access_token,
                "access_token": f"{FACEBOOK_APP_ID}|{FACEBOOK_APP_SECRET}",
            },
            timeout=10,
        ).json()
    except requests.RequestException as e:
        logger.warning("Facebook debug_token request nieudany: %s", e)
        raise OAuthVerificationError("Nie udało się zweryfikować tokena Facebook.") from e

    data = debug.get("data") or {}
    if not data.get("is_valid") or str(data.get("app_id")) != str(FACEBOOK_APP_ID):
        raise OAuthVerificationError("Nieprawidłowy lub wygasły token Facebook.")

    try:
        profile = requests.get(
            "https://graph.facebook.com/me",
            params={"fields": "id,name,email", "access_token": access_token},
            timeout=10,
        ).json()
    except requests.RequestException as e:
        logger.warning("Facebook /me request nieudany: %s", e)
        raise OAuthVerificationError("Nie udało się pobrać profilu Facebook.") from e

    if "id" not in profile:
        raise OAuthVerificationError("Nieprawidłowa odpowiedź Facebook.")

    # Facebook Graph API nie ma pola email_verified (w przeciwieństwie do Google) —
    # /me zwraca email TYLKO gdy jest potwierdzony przez Facebooka, więc ufamy jego obecności
    # jako dowodowi własności. To udokumentowane zachowanie Graph API, nie założenie tego kodu.
    return OAuthIdentity(
        provider="facebook",
        sub=profile["id"],
        email=profile.get("email"),
        name=profile.get("name"),
    )
