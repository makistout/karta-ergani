"""Όλες οι ρυθμίσεις εισόδου — MSSQL (pyodbc) και Ergani API."""

import os
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent
load_dotenv(_ROOT / ".env", override=True)
load_dotenv()


class Config:
    """Προτιμήστε μεταβλητές περιβάλλοντος (.env)."""

    SECRET_KEY = (
        os.environ.get("FLASK_SECRET_KEY")
        or os.environ.get("SECRET_KEY")
        or "karta-ergani-dev-change-me"
    )

    # MSSQL — ίδιος server/χρήστης με D:\\repository_online\\ergani, ξεχωριστή βάση
    DB_SERVER = os.environ.get("DB_SERVER", "95.141.32.37")
    DB_DATABASE = os.environ.get("DB_DATABASE", "ergani-karta")
    DB_USERNAME = os.environ.get("DB_USERNAME", "ergani")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "3rg@n1!!App")
    DB_ODBC_DRIVER = os.environ.get(
        "DB_ODBC_DRIVER", "ODBC Driver 17 for SQL Server"
    )

    ERGANI_API_PRODUCTION_URL = "https://eservices.yeka.gr/WebservicesAPI/Api/"
    ERGANI_API_TRIAL_URL = "https://trialv2eservices.yeka.gr/WebservicesAPI/Api/"
    _ergani_api_default = ERGANI_API_PRODUCTION_URL
    _ergani_api = os.environ.get("ERGANI_API_BASE_URL", _ergani_api_default)
    if "trialeservices.yeka.gr" in _ergani_api and "trialv2eservices" not in _ergani_api:
        _ergani_api = _ergani_api_default
    ERGANI_API_BASE_URL = _ergani_api
    ERGANI_USERNAME = (os.environ.get("ERGANI_USERNAME") or "").strip() or "webuser3"
    ERGANI_PASSWORD = (os.environ.get("ERGANI_PASSWORD") or "").strip() or "w3bu$3R!"
    ERGANI_USERTYPE = (os.environ.get("ERGANI_USERTYPE") or "").strip() or "02"

    WORK_CARD_API_KEY = os.environ.get("WORK_CARD_API_KEY", "").strip()
    WORK_CARD_DEFAULT_EMPLOYER_AFM = os.environ.get(
        "WORK_CARD_DEFAULT_EMPLOYER_AFM", ""
    ).strip()
    WORK_CARD_DEFAULT_BRANCH_AA = (
        os.environ.get("WORK_CARD_DEFAULT_BRANCH_AA", "0").strip() or "0"
    )

    # Κατάλογος Καλλικράτη (ανάγνωση από άλλη βάση στο ίδιο server, π.χ. ergani_ii)
    CATALOG_DATABASE = os.environ.get("CATALOG_DATABASE", "ergani_ii")

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
