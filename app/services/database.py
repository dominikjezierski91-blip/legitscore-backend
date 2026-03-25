import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, Column, String, DateTime, Text, JSON, Integer, Boolean, Float, func as _sqla_func
from sqlalchemy.orm import sessionmaker, declarative_base

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DB_PATH = DATA_DIR / "legitscore.db"

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class CaseRecord(Base):
    __tablename__ = "cases"

    case_id = Column(String, primary_key=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Dane kontaktowe (RODO)
    email = Column(String, nullable=True)
    consent_at = Column(DateTime, nullable=True)  # Data wyrażenia zgody

    # Model i prompt
    model = Column(String, nullable=True)
    prompt_version = Column(String, nullable=True)

    # Wynik analizy
    verdict_category = Column(String, nullable=True)  # meczowa, podrobka, etc.
    confidence_percent = Column(String, nullable=True)

    # Pełny raport jako JSON
    report_data = Column(JSON, nullable=True)

    # Dane z formularza
    offer_link = Column(Text, nullable=True)  # Link do oferty / cena
    context = Column(Text, nullable=True)  # Dodatkowy kontekst

    # Feedback użytkownika
    feedback = Column(String, nullable=True)  # correct / incorrect / unsure
    feedback_at = Column(DateTime, nullable=True)
    feedback_comment = Column(Text, nullable=True)

    # Ocena raportu (1-5 piłek)
    rating = Column(Integer, nullable=True)
    rating_at = Column(DateTime, nullable=True)

    # SKU wykryte przez model (jeśli widoczne na zdjęciach)
    sku = Column(String, nullable=True)


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Profil użytkownika (opcjonalne — zbierany po rejestracji)
    user_type = Column(String, nullable=True)                          # kolekcjoner / okazjonalny_kupujacy / sprzedajacy
    collection_size_range = Column(String, nullable=True)              # 0-5 / 6-20 / 21-50 / 50+
    profile_survey_completed_at = Column(DateTime, nullable=True)
    profile_survey_skipped_at = Column(DateTime, nullable=True)


class CollectionItem(Base):
    __tablename__ = "collection_items"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, index=True, nullable=False)
    case_id = Column(String, nullable=False)
    added_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Snapshot z raportu
    report_mode = Column(String, nullable=True)
    club = Column(String, nullable=True)
    season = Column(String, nullable=True)
    model_type = Column(String, nullable=True)
    brand = Column(String, nullable=True)
    player_name = Column(String, nullable=True)
    player_number = Column(String, nullable=True)
    verdict_category = Column(String, nullable=True)
    confidence_percent = Column(Integer, nullable=True)
    confidence_level = Column(String, nullable=True)
    sku = Column(String, nullable=True)
    report_id = Column(String, nullable=True)
    analysis_date = Column(String, nullable=True)

    # Pola dodawane przez usera (opcjonalne)
    purchase_price = Column(String, nullable=True)
    purchase_currency = Column(String, nullable=True)
    purchase_date = Column(String, nullable=True)
    purchase_source = Column(String, nullable=True)
    notes = Column(Text, nullable=True)

    # Szacowana wartość rynkowa (Portfel Koszulek)
    market_value_pln = Column(Float, nullable=True)
    market_value_range_min = Column(Float, nullable=True)
    market_value_range_max = Column(Float, nullable=True)
    market_value_sample_size = Column(Integer, nullable=True)
    market_value_source = Column(String, nullable=True)
    market_value_updated_at = Column(DateTime, nullable=True)

    # Ręczne dodawanie do kolekcji (bez analizy)
    is_manual = Column(Boolean, default=False, nullable=True)
    photo_path = Column(String, nullable=True)  # ścieżka do zdjęcia profilowego (manual lub override)


class SupportSubmission(Base):
    __tablename__ = "support_submissions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Status: nowe / w_trakcie / zamkniete
    status = Column(String, default="nowe", nullable=False)

    # Treść zgłoszenia
    type = Column(String, nullable=False)       # pytanie / problem / sugestia / inne
    message = Column(Text, nullable=False)
    email = Column(String, nullable=True)
    wants_reply = Column(Boolean, default=False, nullable=True)

    # Kontekst użytkownika
    user_id = Column(String, nullable=True)
    auth_state = Column(String, nullable=True)  # logged_in / guest

    # Kontekst strony
    source_page = Column(String, nullable=True)
    current_url = Column(String, nullable=True)
    app_section = Column(String, nullable=True)  # report / analysis / collection

    # Powiązane encje
    report_id = Column(String, nullable=True)
    analysis_id = Column(String, nullable=True)
    shirt_id = Column(String, nullable=True)
    collection_item_id = Column(String, nullable=True)

    # Backoffice
    internal_notes = Column(Text, nullable=True)
    resolved_at = Column(DateTime, nullable=True)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    token = Column(String, primary_key=True)
    user_id = Column(String, index=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False, nullable=False)


def init_db():
    """Tworzy tabele jeśli nie istnieją + migruje nowe kolumny."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    _migrate_collection_market_value()
    _migrate_collection_manual_fields()
    _migrate_user_profile_fields()
    _migrate_password_reset_tokens()


def _migrate_password_reset_tokens():
    """Tworzy tabelę password_reset_tokens jeśli nie istnieje (SQLite migration)."""
    with engine.connect() as conn:
        existing_tables = {row[0] for row in conn.execute(
            __import__("sqlalchemy").text("SELECT name FROM sqlite_master WHERE type='table'")
        )}
        if "password_reset_tokens" not in existing_tables:
            conn.execute(__import__("sqlalchemy").text("""
                CREATE TABLE password_reset_tokens (
                    token TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    expires_at DATETIME NOT NULL,
                    used INTEGER NOT NULL DEFAULT 0
                )
            """))
            conn.commit()


def _migrate_collection_market_value():
    """Dodaje kolumny market_value_* do collection_items jeśli nie istnieją (SQLite migration)."""
    new_columns = [
        ("market_value_pln", "REAL"),
        ("market_value_range_min", "REAL"),
        ("market_value_range_max", "REAL"),
        ("market_value_sample_size", "INTEGER"),
        ("market_value_source", "TEXT"),
        ("market_value_updated_at", "TEXT"),
    ]
    with engine.connect() as conn:
        existing = {row[1] for row in conn.execute(
            __import__("sqlalchemy").text("PRAGMA table_info(collection_items)")
        )}
        for col_name, col_type in new_columns:
            if col_name not in existing:
                conn.execute(__import__("sqlalchemy").text(
                    f"ALTER TABLE collection_items ADD COLUMN {col_name} {col_type}"
                ))
        conn.commit()


def _migrate_collection_manual_fields():
    """Dodaje kolumny is_manual i photo_path do collection_items."""
    new_columns = [
        ("is_manual", "INTEGER"),
        ("photo_path", "TEXT"),
    ]
    with engine.connect() as conn:
        existing = {row[1] for row in conn.execute(
            __import__("sqlalchemy").text("PRAGMA table_info(collection_items)")
        )}
        for col_name, col_type in new_columns:
            if col_name not in existing:
                conn.execute(__import__("sqlalchemy").text(
                    f"ALTER TABLE collection_items ADD COLUMN {col_name} {col_type}"
                ))
        conn.commit()


def _migrate_user_profile_fields():
    """Dodaje kolumny profilu użytkownika do tabeli users."""
    new_columns = [
        ("user_type", "TEXT"),
        ("collection_size_range", "TEXT"),
        ("profile_survey_completed_at", "TEXT"),
        ("profile_survey_skipped_at", "TEXT"),
    ]
    with engine.connect() as conn:
        existing = {row[1] for row in conn.execute(
            __import__("sqlalchemy").text("PRAGMA table_info(users)")
        )}
        for col_name, col_type in new_columns:
            if col_name not in existing:
                conn.execute(__import__("sqlalchemy").text(
                    f"ALTER TABLE users ADD COLUMN {col_name} {col_type}"
                ))
        conn.commit()


def get_db():
    """Dependency dla FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def save_case_to_db(
    case_id: str,
    model: Optional[str] = None,
    prompt_version: Optional[str] = None,
    verdict_category: Optional[str] = None,
    confidence_percent: Optional[int] = None,
    report_data: Optional[dict] = None,
    email: Optional[str] = None,
    consent_at: Optional[datetime] = None,
    offer_link: Optional[str] = None,
    context: Optional[str] = None,
    sku: Optional[str] = None,
):
    """Zapisuje lub aktualizuje case w bazie."""
    db = SessionLocal()
    try:
        record = db.query(CaseRecord).filter(CaseRecord.case_id == case_id).first()
        if record is None:
            record = CaseRecord(case_id=case_id)
            db.add(record)

        if model is not None:
            record.model = model
        if prompt_version is not None:
            record.prompt_version = prompt_version
        if verdict_category is not None:
            record.verdict_category = verdict_category
        if confidence_percent is not None:
            record.confidence_percent = str(confidence_percent)
        if report_data is not None:
            record.report_data = report_data
        if email is not None:
            record.email = email
        if consent_at is not None:
            record.consent_at = consent_at
        if offer_link is not None:
            record.offer_link = offer_link
        if context is not None:
            record.context = context
        if sku is not None:
            record.sku = sku

        db.commit()
        return record
    finally:
        db.close()


def save_feedback_to_db(
    case_id: str,
    feedback: str,
    comment: Optional[str] = None,
):
    """Zapisuje feedback użytkownika."""
    db = SessionLocal()
    try:
        record = db.query(CaseRecord).filter(CaseRecord.case_id == case_id).first()
        if record is None:
            record = CaseRecord(case_id=case_id)
            db.add(record)

        record.feedback = feedback
        record.feedback_at = datetime.now(timezone.utc)
        if comment:
            record.feedback_comment = comment

        db.commit()
        return record
    finally:
        db.close()


def get_case_from_db(case_id: str) -> Optional[CaseRecord]:
    """Pobiera case z bazy."""
    db = SessionLocal()
    try:
        return db.query(CaseRecord).filter(CaseRecord.case_id == case_id).first()
    finally:
        db.close()


def get_all_cases_from_db(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    auth_state_filter: Optional[str] = None,
    verdict_filter: Optional[str] = None,
    email_filter: Optional[str] = None,
    page: int = 1,
    limit: int = 25,
) -> dict:
    """Pobiera case'y z bazy z opcjonalnym filtrowaniem i paginacją."""
    db = SessionLocal()
    try:
        q = db.query(CaseRecord)
        if date_from:
            try:
                q = q.filter(CaseRecord.created_at >= datetime.fromisoformat(date_from))
            except ValueError:
                pass
        if date_to:
            try:
                q = q.filter(CaseRecord.created_at <= datetime.fromisoformat(date_to))
            except ValueError:
                pass
        if auth_state_filter == "logged_in":
            q = q.filter(CaseRecord.email.isnot(None))
        elif auth_state_filter == "guest":
            q = q.filter(CaseRecord.email.is_(None))
        if verdict_filter:
            q = q.filter(CaseRecord.verdict_category == verdict_filter)
        if email_filter:
            q = q.filter(CaseRecord.email.ilike(f"%{email_filter}%"))

        total = q.count()
        offset = (page - 1) * limit
        records = q.order_by(CaseRecord.created_at.desc()).offset(offset).limit(limit).all()
        cases = [
            {
                "case_id": r.case_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "email": r.email,
                "verdict_category": r.verdict_category,
                "confidence_percent": r.confidence_percent,
                "feedback": r.feedback,
                "feedback_comment": r.feedback_comment,
                "rating": r.rating,
                "sku": r.sku,
                "model": r.model,
                "prompt_version": r.prompt_version,
            }
            for r in records
        ]
        return {"cases": cases, "total": total, "page": page, "limit": limit}
    finally:
        db.close()


def get_activation_detail() -> dict:
    """Metryki aktywacji: czas do pierwszej analizy i lista nieaktywowanych użytkowników."""
    db = SessionLocal()
    try:
        users = db.query(User).order_by(User.created_at.desc()).all()
        avg_hours_list = []
        unactivated = []

        for u in users:
            first_case = db.query(CaseRecord.created_at).filter(
                CaseRecord.email == u.email
            ).order_by(CaseRecord.created_at.asc()).first()

            if first_case and first_case[0] and u.created_at:
                reg = u.created_at.replace(tzinfo=None)
                first = first_case[0].replace(tzinfo=None) if hasattr(first_case[0], 'replace') else first_case[0]
                delta_h = max(0, (first - reg).total_seconds() / 3600)
                avg_hours_list.append(delta_h)
            else:
                unactivated.append({
                    "id": u.id,
                    "email": u.email,
                    "created_at": u.created_at.isoformat() if u.created_at else None,
                })

        avg_hours = round(sum(avg_hours_list) / len(avg_hours_list), 1) if avg_hours_list else None
        return {
            "avg_hours_to_first_analysis": avg_hours,
            "unactivated_users": unactivated[:20],
            "unactivated_count": len(unactivated),
        }
    finally:
        db.close()


def get_retention_metrics() -> dict:
    """Metryki retencji: 7-dniowa retencja, engaged users, lista churned."""
    from datetime import timedelta
    from sqlalchemy import func
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)
        churn_cutoff = now.replace(tzinfo=None) - timedelta(days=14)

        total_users = db.query(User).count()

        # Aktywni w ostatnich 7 dniach (via analiza)
        active_emails = {
            row[0] for row in
            db.query(CaseRecord.email)
            .filter(CaseRecord.created_at >= week_ago, CaseRecord.email.isnot(None))
            .distinct().all()
        }
        active_7d = db.query(User).filter(User.email.in_(active_emails)).count() if active_emails else 0
        retention_7d_pct = round(active_7d / total_users * 100, 1) if total_users > 0 else 0

        # Engaged: ≥3 analiz
        engaged_emails = {
            row[0] for row in
            db.query(CaseRecord.email, func.count(CaseRecord.case_id).label("cnt"))
            .filter(CaseRecord.email.isnot(None))
            .group_by(CaseRecord.email)
            .having(func.count(CaseRecord.case_id) >= 3)
            .all()
        }
        engaged_count = db.query(User).filter(User.email.in_(engaged_emails)).count() if engaged_emails else 0
        engaged_pct = round(engaged_count / total_users * 100, 1) if total_users > 0 else 0

        # Churned: miał ≥1 analizę, ale ostatnia >14 dni temu
        users_with_cases = db.query(User).filter(
            User.email.in_(
                db.query(CaseRecord.email).filter(CaseRecord.email.isnot(None)).distinct()
            )
        ).all()

        churned = []
        for u in users_with_cases:
            last = db.query(CaseRecord.created_at).filter(
                CaseRecord.email == u.email
            ).order_by(CaseRecord.created_at.desc()).first()
            if last and last[0]:
                last_dt = last[0].replace(tzinfo=None) if hasattr(last[0], 'replace') else last[0]
                if last_dt < churn_cutoff:
                    churned.append({
                        "id": u.id,
                        "email": u.email,
                        "last_activity_at": last[0].isoformat(),
                        "created_at": u.created_at.isoformat() if u.created_at else None,
                    })

        churned.sort(key=lambda x: x["last_activity_at"], reverse=True)
        return {
            "retention_7d_pct": retention_7d_pct,
            "active_7d_count": active_7d,
            "engaged_pct": engaged_pct,
            "engaged_count": engaged_count,
            "churned_users": churned[:20],
            "churned_count": len(churned),
        }
    finally:
        db.close()


def get_registration_trend(days: int = 30) -> list:
    """Trend rejestracji dzienny — ostatnie N dni."""
    from datetime import timedelta
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        result = []
        for i in range(days - 1, -1, -1):
            day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            count = db.query(User).filter(
                User.created_at >= day_start,
                User.created_at < day_end,
            ).count()
            result.append({"date": day_start.strftime("%Y-%m-%d"), "count": count})
        return result
    finally:
        db.close()


def get_user_detail(user_id: str) -> Optional[dict]:
    """Szczegóły użytkownika z listą jego analiz."""
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.id == user_id).first()
        if not u:
            return None
        cases = db.query(CaseRecord).filter(
            CaseRecord.email == u.email
        ).order_by(CaseRecord.created_at.desc()).all()
        return {
            "id": u.id,
            "email": u.email,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "is_admin": u.is_admin,
            "user_type": u.user_type,
            "cases": [
                {
                    "case_id": c.case_id,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                    "verdict_category": c.verdict_category,
                    "confidence_percent": c.confidence_percent,
                    "feedback": c.feedback,
                    "sku": c.sku,
                }
                for c in cases
            ],
        }
    finally:
        db.close()


def get_db_stats() -> dict:
    """Statystyki z bazy."""
    db = SessionLocal()
    try:
        total = db.query(CaseRecord).count()
        with_feedback = db.query(CaseRecord).filter(CaseRecord.feedback.isnot(None)).count()
        correct = db.query(CaseRecord).filter(CaseRecord.feedback == "correct").count()
        incorrect = db.query(CaseRecord).filter(CaseRecord.feedback == "incorrect").count()
        unsure = db.query(CaseRecord).filter(CaseRecord.feedback == "unsure").count()
        return {
            "total": total,
            "with_feedback": with_feedback,
            "correct": correct,
            "incorrect": incorrect,
            "unsure": unsure,
        }
    finally:
        db.close()


def save_rating_to_db(
    case_id: str,
    rating: int,
    comment: Optional[str] = None,
) -> bool:
    """Zapisuje ocenę raportu (1-5 piłek)."""
    if rating < 1 or rating > 5:
        return False

    db = SessionLocal()
    try:
        record = db.query(CaseRecord).filter(CaseRecord.case_id == case_id).first()
        if record is None:
            return False

        record.rating = rating
        record.rating_at = datetime.now(timezone.utc)
        if comment:
            record.feedback_comment = comment

        db.commit()
        return True
    finally:
        db.close()


def get_user_stats() -> dict:
    """Statystyki użytkowników dla dashboardu."""
    from datetime import timedelta
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        day_ago = now - timedelta(days=1)
        week_ago = now - timedelta(days=7)

        total = db.query(User).count()
        new_today = db.query(User).filter(User.created_at >= day_ago).count()
        new_7d = db.query(User).filter(User.created_at >= week_ago).count()
        # Aktywni = unikalni użytkownicy (user.id) z aktywnością w ostatnich 7 dniach
        active_via_analysis = {
            row[0]
            for row in db.query(User.id)
            .join(CaseRecord, CaseRecord.email == User.email)
            .filter(CaseRecord.created_at >= week_ago)
            .all()
        }
        active_via_collection = {
            row[0]
            for row in db.query(CollectionItem.user_id)
            .filter(CollectionItem.added_at >= week_ago)
            .all()
        }
        active_7d = len(active_via_analysis | active_via_collection)

        return {
            "total": total,
            "new_today": new_today,
            "new_7d": new_7d,
            "active_7d": active_7d,
        }
    finally:
        db.close()


def get_user_list() -> list:
    """Lista użytkowników ze statystykami aktywności."""
    db = SessionLocal()
    try:
        users = db.query(User).order_by(User.created_at.desc()).all()
        result = []
        for u in users:
            analysis_count = db.query(CaseRecord).filter(CaseRecord.email == u.email).count()
            collection_count = db.query(CollectionItem).filter(CollectionItem.user_id == u.id).count()

            case_dates = db.query(
                _sqla_func.max(CaseRecord.created_at),
                _sqla_func.min(CaseRecord.created_at),
            ).filter(CaseRecord.email == u.email).first()
            last_case = (case_dates[0],) if case_dates and case_dates[0] else None
            first_case = (case_dates[1],) if case_dates and case_dates[1] else None
            last_col = db.query(CollectionItem.added_at).filter(
                CollectionItem.user_id == u.id
            ).order_by(CollectionItem.added_at.desc()).first()

            candidates = []
            if last_case and last_case[0]:
                candidates.append(last_case[0])
            if last_col and last_col[0]:
                candidates.append(last_col[0])
            last_activity = max(candidates).isoformat() if candidates else None

            result.append({
                "id": u.id,
                "email": u.email,
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "is_admin": u.is_admin,
                "analysis_count": analysis_count,
                "collection_count": collection_count,
                "last_activity_at": last_activity,
                "first_analysis_at": first_case[0].isoformat() if first_case and first_case[0] else None,
                "user_type": getattr(u, "user_type", None),
                "collection_size_range": getattr(u, "collection_size_range", None),
                "profile_survey_completed_at": (
                    getattr(u, "profile_survey_completed_at", None).isoformat()
                    if getattr(u, "profile_survey_completed_at", None) else None
                ),
                "profile_survey_skipped_at": (
                    getattr(u, "profile_survey_skipped_at", None).isoformat()
                    if getattr(u, "profile_survey_skipped_at", None) else None
                ),
            })
        return result
    finally:
        db.close()


def get_dashboard_metrics() -> dict:
    """Metryki produktowe dla dashboardu."""
    from datetime import timedelta
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        day_ago = now - timedelta(days=1)
        week_ago = now - timedelta(days=7)

        total_cases = db.query(CaseRecord).count()
        total_users = db.query(User).count()
        cases_today = db.query(CaseRecord).filter(CaseRecord.created_at >= day_ago).count()
        cases_7d = db.query(CaseRecord).filter(CaseRecord.created_at >= week_ago).count()
        logged_in_cases = db.query(CaseRecord).filter(CaseRecord.email.isnot(None)).count()
        guest_cases = db.query(CaseRecord).filter(CaseRecord.email.is_(None)).count()

        users_with_collection = db.query(CollectionItem.user_id).distinct().count()
        collection_adoption = round(users_with_collection / total_users * 100, 1) if total_users > 0 else 0

        # Aktywacja = zarejestrowani użytkownicy z ≥1 analizą (nie distinct emaile z case'ów)
        users_with_analysis = (
            db.query(User)
            .filter(
                User.email.in_(
                    db.query(CaseRecord.email).filter(CaseRecord.email.isnot(None)).distinct()
                )
            )
            .count()
        )
        activation_rate = (
            round(min(users_with_analysis / total_users * 100, 100.0), 1)
            if total_users > 0
            else 0
        )
        # Średnia per aktywny użytkownik, nie per wszystkich zarejestrowanych
        avg_analyses = (
            round(logged_in_cases / users_with_analysis, 1)
            if users_with_analysis > 0
            else 0
        )

        # Segmenty profilu użytkownika
        def count_user_type(ut: str) -> int:
            return db.query(User).filter(User.user_type == ut).count()

        def count_size_range(sr: str) -> int:
            return db.query(User).filter(User.collection_size_range == sr).count()

        survey_completed = db.query(User).filter(
            User.profile_survey_completed_at.isnot(None)
        ).count()
        survey_skipped = db.query(User).filter(
            User.profile_survey_skipped_at.isnot(None)
        ).count()

        return {
            "total_cases": total_cases,
            "cases_today": cases_today,
            "cases_7d": cases_7d,
            "logged_in_cases": logged_in_cases,
            "guest_cases": guest_cases,
            "collection_adoption_pct": collection_adoption,
            "avg_analyses_per_user": avg_analyses,
            "activation_rate_pct": activation_rate,
            "users_with_analysis": users_with_analysis,
            "segments": {
                "user_type": {
                    "kolekcjoner": count_user_type("kolekcjoner"),
                    "okazjonalny_kupujacy": count_user_type("okazjonalny_kupujacy"),
                    "sprzedajacy": count_user_type("sprzedajacy"),
                },
                "collection_size": {
                    "0-5": count_size_range("0-5"),
                    "6-20": count_size_range("6-20"),
                    "21-50": count_size_range("21-50"),
                    "50+": count_size_range("50+"),
                },
                "survey_completed": survey_completed,
                "survey_skipped": survey_skipped,
            },
        }
    finally:
        db.close()


def anonymize_case_email(case_id: str) -> bool:
    """Anonimizuje email w case (RODO - prawo do bycia zapomnianym)."""
    db = SessionLocal()
    try:
        record = db.query(CaseRecord).filter(CaseRecord.case_id == case_id).first()
        if record is None:
            return False
        record.email = None
        record.consent_at = None
        db.commit()
        return True
    finally:
        db.close()


def delete_case_from_db(case_id: str) -> bool:
    """Usuwa case z bazy (RODO - prawo do bycia zapomnianym)."""
    db = SessionLocal()
    try:
        record = db.query(CaseRecord).filter(CaseRecord.case_id == case_id).first()
        if record is None:
            return False
        db.delete(record)
        db.commit()
        return True
    finally:
        db.close()
