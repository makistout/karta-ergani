"""Όλες οι ρυθμίσεις εισόδου — MSSQL (pyodbc) και Ergani API."""

import os
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent
load_dotenv(_ROOT / ".env", override=True)
load_dotenv()

_DEV_SECRET = "karta-ergani-dev-only-not-for-production"


def _env_flag(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


class Config:
    """Προτιμήστε μεταβλητές περιβάλλοντος (.env) — χωρίς hardcoded secrets."""

    FLASK_DEBUG = _env_flag("FLASK_DEBUG")

    SECRET_KEY = (
        os.environ.get("FLASK_SECRET_KEY")
        or os.environ.get("SECRET_KEY")
        or ""
    ).strip()
    if not SECRET_KEY:
        SECRET_KEY = _DEV_SECRET if FLASK_DEBUG else ""

    DB_SERVER = (os.environ.get("DB_SERVER") or "").strip()
    DB_DATABASE = (os.environ.get("DB_DATABASE") or "").strip() or "ergani-karta"
    DB_USERNAME = (os.environ.get("DB_USERNAME") or "").strip()
    DB_PASSWORD = (os.environ.get("DB_PASSWORD") or "").strip()
    DB_ODBC_DRIVER = (
        os.environ.get("DB_ODBC_DRIVER") or "ODBC Driver 17 for SQL Server"
    ).strip()

    ERGANI_API_PRODUCTION_URL = "https://eservices.yeka.gr/WebservicesAPI/Api/"
    ERGANI_API_TRIAL_URL = "https://trialv2eservices.yeka.gr/WebservicesAPI/Api/"
    _ergani_api_default = ERGANI_API_PRODUCTION_URL
    _ergani_api = (os.environ.get("ERGANI_API_BASE_URL") or _ergani_api_default).strip()
    if "trialeservices.yeka.gr" in _ergani_api and "trialv2eservices" not in _ergani_api:
        _ergani_api = _ergani_api_default
    ERGANI_API_BASE_URL = _ergani_api

    ERGANI_USERNAME = (os.environ.get("ERGANI_USERNAME") or "").strip()
    ERGANI_PASSWORD = (os.environ.get("ERGANI_PASSWORD") or "").strip()
    ERGANI_USERTYPE = (os.environ.get("ERGANI_USERTYPE") or "").strip() or "02"

    WORK_CARD_API_KEY = (os.environ.get("WORK_CARD_API_KEY") or "").strip()
    WORK_CARD_DEFAULT_EMPLOYER_AFM = (
        os.environ.get("WORK_CARD_DEFAULT_EMPLOYER_AFM") or ""
    ).strip()
    WORK_CARD_DEFAULT_BRANCH_AA = (
        (os.environ.get("WORK_CARD_DEFAULT_BRANCH_AA") or "0").strip() or "0"
    )

    # Προαιρετικό: αν οριστεί, όλα τα /api/* (εκτός health) απαιτούν X-Office-Token
    OFFICE_API_TOKEN = (os.environ.get("KARTA_OFFICE_TOKEN") or "").strip()

    CATALOG_DATABASE = (os.environ.get("CATALOG_DATABASE") or "").strip() or "ergani_ii"

    @staticmethod
    def pyodbc_connection_string() -> str:
        """Σύνδεση αποκλειστικά για pyodbc (χωρίς SQLAlchemy)."""
        d = Config.DB_ODBC_DRIVER
        db = Config.DB_DATABASE
        return (
            f"Driver={{{d}}};"
            f"Server={Config.DB_SERVER};"
            f"Database={db};"
            f"Uid={Config.DB_USERNAME};"
            f"Pwd={Config.DB_PASSWORD};"
            "TrustServerCertificate=yes;"
        )

    @staticmethod
    def validate_for_startup() -> None:
        """Fail-fast όταν λείπουν κρίσιμα secrets (ιδίως εκτός debug)."""
        missing: list[str] = []
        if not Config.DB_SERVER:
            missing.append("DB_SERVER")
        if not Config.DB_USERNAME:
            missing.append("DB_USERNAME")
        if not Config.DB_PASSWORD:
            missing.append("DB_PASSWORD")
        if not Config.FLASK_DEBUG:
            if not Config.SECRET_KEY or Config.SECRET_KEY == _DEV_SECRET:
                missing.append("FLASK_SECRET_KEY (υποχρεωτικό εκτός FLASK_DEBUG)")
            if not Config.WORK_CARD_API_KEY:
                missing.append("WORK_CARD_API_KEY (υποχρεωτικό εκτός FLASK_DEBUG)")
        if missing:
            raise RuntimeError(
                "Λείπουν ρυθμίσεις περιβάλλοντος (.env):\n- "
                + "\n- ".join(missing)
            )
