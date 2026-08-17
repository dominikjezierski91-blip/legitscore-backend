"""Serwis emailowy — Resend API."""
import os
import logging

import resend

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
# legitscore.app jest realną domeną produktu (app.legitscore.app itd.) — legitscore.com
# nigdy nie było zweryfikowane w Resend. Env var na wypadek zmiany bez redeployu.
FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "info@legitscore.app")
FROM_NAME = "LegitScore"


def _init():
    if RESEND_API_KEY:
        resend.api_key = RESEND_API_KEY


_init()


def send_welcome_email(to_email: str, name: str = "") -> bool:
    """Wysyła email powitalny po rejestracji. Zwraca True jeśli sukces."""
    if not RESEND_API_KEY:
        logger.warning("RESEND_API_KEY nie ustawiony — pomijam email powitalny")
        return False
    try:
        params: resend.Emails.SendParams = {
            "from": f"{FROM_NAME} <{FROM_EMAIL}>",
            "to": [to_email],
            "subject": "Witaj w LegitScore! 🏆",
            "text": f"""Cześć{f', {name}' if name else ''}!

Dziękujemy za dołączenie do LegitScore — systemu analizy autentyczności koszulek piłkarskich.

Możesz teraz:
- Przesłać zdjęcia koszulki i otrzymać szczegółowy raport
- Budować swoją kolekcję i śledzić wartość rynkową
- Sprawdzać czy koszulka jest oryginalna, meczowa czy podróbka

Zacznij swoją pierwszą analizę → legitscore.app/analyze

Pozdrawiamy,
Zespół LegitScore""",
        }
        resend.Emails.send(params)
        logger.info(f"Email powitalny wysłany do {to_email}")
        return True
    except Exception as e:
        logger.error(f"Błąd wysyłania emaila powitalnego do {to_email}: {e}")
        return False


def send_password_reset_email(to_email: str, reset_link: str) -> bool:
    """Wysyła email z linkiem do resetu hasła. Zwraca True jeśli sukces."""
    if not RESEND_API_KEY:
        logger.warning("RESEND_API_KEY nie ustawiony — pomijam email reset hasła")
        return False
    try:
        params: resend.Emails.SendParams = {
            "from": f"{FROM_NAME} <{FROM_EMAIL}>",
            "to": [to_email],
            "subject": "Reset hasła LegitScore",
            "text": f"""Otrzymaliśmy prośbę o reset hasła.

Kliknij poniższy link aby ustawić nowe hasło (ważny przez 1 godzinę):

{reset_link}

Jeśli to nie Ty — zignoruj tę wiadomość.

Zespół LegitScore""",
        }
        resend.Emails.send(params)
        logger.info(f"Email reset hasła wysłany do {to_email}")
        return True
    except Exception as e:
        logger.error(f"Błąd wysyłania emaila reset hasła do {to_email}: {e}")
        return False


def send_verification_email(to_email: str, verify_link: str) -> bool:
    """Wysyła email z linkiem do potwierdzenia adresu. Zwraca True jeśli sukces."""
    if not RESEND_API_KEY:
        logger.warning("RESEND_API_KEY nie ustawiony — pomijam email weryfikacji adresu")
        return False
    try:
        params: resend.Emails.SendParams = {
            "from": f"{FROM_NAME} <{FROM_EMAIL}>",
            "to": [to_email],
            "subject": "Potwierdź swój adres email — LegitScore",
            "text": f"""Cześć!

Potwierdź, że to Twój adres email, klikając poniższy link (ważny przez 24 godziny):

{verify_link}

Jeśli nie zakładałeś konta w LegitScore — zignoruj tę wiadomość.

Zespół LegitScore""",
        }
        resend.Emails.send(params)
        logger.info(f"Email weryfikacyjny wysłany do {to_email}")
        return True
    except Exception as e:
        logger.error(f"Błąd wysyłania emaila weryfikacyjnego do {to_email}: {e}")
        return False
