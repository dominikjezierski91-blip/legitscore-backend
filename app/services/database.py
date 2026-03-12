import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, Column, String, DateTime, Text, JSON
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

    # Model i prompt
    model = Column(String, nullable=True)
    prompt_version = Column(String, nullable=True)

    # Wynik analizy
    verdict_category = Column(String, nullable=True)  # meczowa, podrobka, etc.
    confidence_percent = Column(String, nullable=True)

    # Pełny raport jako JSON
    report_data = Column(JSON, nullable=True)

    # Feedback użytkownika
    feedback = Column(String, nullable=True)  # correct / incorrect / unsure
    feedback_at = Column(DateTime, nullable=True)
    feedback_comment = Column(Text, nullable=True)


def init_db():
    """Tworzy tabele jeśli nie istnieją."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)


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


def get_all_cases_from_db() -> list:
    """Pobiera wszystkie case'y z bazy."""
    db = SessionLocal()
    try:
        records = db.query(CaseRecord).order_by(CaseRecord.created_at.desc()).all()
        return [
            {
                "case_id": r.case_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "model": r.model,
                "prompt_version": r.prompt_version,
                "verdict_category": r.verdict_category,
                "confidence_percent": r.confidence_percent,
                "feedback": r.feedback,
                "feedback_at": r.feedback_at.isoformat() if r.feedback_at else None,
                "feedback_comment": r.feedback_comment,
            }
            for r in records
        ]
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
