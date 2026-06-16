"""Extract EX_BASE_04 field list from PDF guide."""
import json
import re
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "documentation" / "ΕΡΓΑΝΗ ΙΙ - Οδηγός Χρήσης Διαλειτουργικοτήτων.pdf"
OUT = ROOT / "documentation" / "ex_base_04_schema_from_pdf.json"

doc = fitz.open(PDF)
text = ""
for i in range(21, 24):
    text += doc[i].get_text() or ""

fields = sorted(set(re.findall(r'"(f_[^"]+)"', text)))
schema = {
    "service": "EX_BASE_04",
    "root_key": "EX_BASE_04",
    "record_key": "MiniaiaKatastash",
    "note": "Στο PDF το MiniaiaKatastash εμφανίζεται ως ένα αντικείμενο· σε πραγματική κλήση συνήθως είναι λίστα εγγραφών (ένας εργαζόμενος ανά row).",
    "request_parameters": [
        {"ParameterName": "ReportYear", "example": "2024"},
        {"ParameterName": "ReportMonth", "example": "10"},
    ],
    "fields": fields,
}
OUT.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Wrote {len(fields)} fields to {OUT}")
