"""Versioned documentation tied to the exact rule sources; no DB or side effects."""
from pathlib import Path
from hashlib import sha256
import json
import re

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'app' / 'private' / 'rule_diagrams'
SOURCE_FILES = (
    'app/apologistic_rules.py', 'app/apologistic.py', 'app/timekeeping.py',
    'app/apologistic_snapshot.py', 'app/repo_apologistic.py',
    'app/routes_apologistic.py', 'app/apologistic_submit.py',
    'app/apologistic_batch_submit.py', 'app/timekeeping_export.py',
)
DOCUMENT_FILES = (
    'docs/APOLOGISTIKO_RULES_CATALOG.md', 'docs/APOLOGISTIKO_LOGIC.md',
    'scripts/render_rule_document.py',
    'documentation/Μηχανισμός Απολογιστικού - Προς Έλεγχο Εργατολόγου.docx',
    'deliverables/rule_diagrams/build_diagrams.py',
    'deliverables/rule_diagrams/viewer.template.html',
    'scripts/build_rule_diagrams.py', 'app/rule_diagram_versions.py',
)


def fingerprint(root=ROOT):
    files = {}
    for name in SOURCE_FILES + DOCUMENT_FILES:
        content = (root / name).read_bytes()
        if not name.endswith('.docx'):
            content = content.replace(b'\r\n', b'\n')
        files[name] = sha256(content).hexdigest()
    digest = sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    return digest, files


def manifest():
    return json.loads((ARCHIVE / 'manifest.json').read_text(encoding='utf-8'))


def version_entry(version):
    if not re.fullmatch(r'rules-[a-f0-9]{16}', version or ''):
        return None
    return next((item for item in manifest()['versions'] if item['id'] == version), None)


def is_current(entry):
    return entry['fingerprint'] == fingerprint()[0]
