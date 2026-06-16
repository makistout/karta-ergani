"""Ανθρώπινα μηνύματα για αποτυχίες Ergani API."""

from __future__ import annotations

from typing import Any

from app.http_helpers import json_or_text

_SERVICE_LABELS = {
    "EX_BASE_04": "Μηνιαία κατάσταση (EX_BASE_04)",
    "EX_BASE_07": "Πραγματική απασχόληση (EX_BASE_07)",
    "EX_BASE_08": "Ψηφιακό ωράριο (EX_BASE_08)",
}


def ergani_failure_detail(resp, service_code: str) -> str:
    """Κείμενο σφάλματος για UI — όχι raw JSON."""
    label = _SERVICE_LABELS.get(service_code, service_code)
    parsed: Any = json_or_text(resp)
    upstream = ""
    if isinstance(parsed, dict):
        upstream = str(parsed.get("message") or parsed.get("Message") or "").strip()
    elif isinstance(parsed, str):
        upstream = parsed.strip()

    if upstream and "not authenticate" in upstream.lower():
        return (
            f"Ergani API — {label}: «{upstream}». "
            "Σύμφωνα με τον οδηγό, αυτό το μήνυμα εμφανίζεται και σε λάθος κλήση· "
            "ελέγξτε ServiceCode/Parameters. "
            "Αν η κλήση είναι σωστή, το service λείπει από το ServicesList του χρήστη API "
            "(αίτημα ενεργοποίησης EX_BASE_04 στο e-ΕΦΚΑ / Εργάνη)."
        )

    if resp.status_code >= 500:
        return (
            f"{label}: προσωρινό σφάλμα Ergani (HTTP {resp.status_code}). "
            "Δοκιμάστε αργότερα ή άλλη ημερομηνία."
        )

    if upstream:
        return f"{label}: {upstream}"
    return f"{label}: HTTP {resp.status_code}"
