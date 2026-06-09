"""Τύποι άδειας — κωδικοί Παράρτημα 9 (εγχειρίδιο Ergani)."""

from __future__ import annotations

LEAVE_TYPES: list[dict[str, str]] = [
    {"code": "ADKAN", "label": "Κανονική άδεια"},
    {"code": "ADAS", "label": "Άδεια ασθένειας (ανυπαίτιο κώλυμα)"},
    {"code": "ADAA", "label": "Άδεια άνευ αποδοχών"},
    {"code": "ADAIM", "label": "Αιμοδοτική άδεια"},
    {"code": "ADEX", "label": "Άδεια εξετάσεων"},
    {"code": "ADTHSYG", "label": "Άδεια λόγω θανάτου συγγενούς"},
    {"code": "ADAPSYK", "label": "Απουσία λόγω επικείμενου κινδύνου βίας/παρενόχλησης"},
    {"code": "ADAL", "label": "Άλλη άδεια"},
]

SUBMISSION_CODE_WTO_LEAVE = "WTOLeave"
