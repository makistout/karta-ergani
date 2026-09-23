"""Review, generate and archive diagrams; --check is the CI/deployment gate."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import re
from zipfile import ZipFile
import runpy
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('diagram_versions', ROOT / 'app/rule_diagram_versions.py')
versions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(versions)
ARCHIVE = versions.ARCHIVE
OUTPUT = ROOT / 'deliverables/rule_diagrams'
sys.path.insert(0, str(ROOT / 'scripts'))
from render_rule_document import render_document
ARTIFACTS = {'index.html': OUTPUT / 'index.html', 'rules.json': OUTPUT / 'rules.json',
             'flowcharts.md': ROOT / 'docs/RULE_FLOWCHARTS.md'}


def _artifact_hash_matches(content: bytes, expected: str) -> bool:
    """Σύγκριση hash ανεξάρτητα από CRLF/LF. Το CI τρέχει σε Linux, το build σε Windows."""
    raw = sha256(content).hexdigest()
    if raw == expected:
        return True
    normalized = content.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
    if sha256(normalized).hexdigest() == expected:
        return True
    return sha256(normalized.replace(b'\n', b'\r\n')).hexdigest() == expected


def check():
    try:
        data = versions.manifest()
        entry = versions.version_entry(data['current'])
        if not entry or not versions.is_current(entry):
            raise ValueError('Άλλαξαν κανόνες ή η πηγή των διαγραμμάτων χωρίς νέα ελεγμένη έκδοση.')
        for version in data['versions']:
            for name, expected in version['artifacts'].items():
                content = (ARCHIVE / version['id'] / name).read_bytes()
                if not _artifact_hash_matches(content, expected):
                    raise ValueError('Αλλοιώθηκε αρχειοθετημένο διάγραμμα: ' + version['id'] + '/' + name)
        for name, path in ARTIFACTS.items():
            if not _artifact_hash_matches(path.read_bytes(), entry['artifacts'][name]):
                raise ValueError('Το τρέχον παραδοτέο διαφέρει από το αρχείο εκδόσεων: ' + name)
        print('OK: ' + entry['id'] + ' — πηγές και διαγράμματα συμφωνούν.')
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        print('Ελέγξτε και διορθώστε τα διαγράμματα, μετά: python scripts/build_rule_diagrams.py --reviewed', file=sys.stderr)
        return 1


def build():
    digest, files = versions.fingerprint()
    version = 'rules-' + digest[:16]
    target = ARCHIVE / version
    if target.exists():
        return check()  # Immutable revisions cannot be silently overwritten.
    generator = runpy.run_path(str(OUTPUT / 'build_diagrams.py'), run_name='__main__')
    stamp = datetime.now(timezone.utc).isoformat(timespec='seconds')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    snapshot = re.search(r'CALCULATION_VERSION = "([^"]+)"', (ROOT / 'app/apologistic_snapshot.py').read_text(encoding='utf-8')).group(1)
    timekeeping = re.search(r'"calculation_version": "([^"]+)"', (ROOT / 'app/timekeeping.py').read_text(encoding='utf-8')).group(1)
    label = f'Έκδοση διαγραμμάτων {version} · Απολογιστικό {snapshot} · Ωρομέτρηση {timekeeping}'
    # Replace the initial one-off report's hardcoded header with actual source identity.
    page = ARTIFACTS['index.html'].read_text(encoding='utf-8')
    page = page.replace('έκδοση <code>1787f90</code> · 20 Σεπτεμβρίου 2026', label)
    page = page.replace('στο commit 1787f90 (ανάγνωση 20/09/2026)', f'στην έκδοση {version} (έλεγχος {stamp})')
    page = page.replace('<a href="../../docs/RULE_FLOWCHARTS.md">', '<a href="flowcharts.md">')
    page = re.sub(r'<a href="../../(?:app|docs)/[^"]+">([^<]+)</a>', r'<span>\1</span>', page)
    page = page.replace('<p>Επαλήθευση υπολογισμών: 141 σχετικά tests πέρασαν. Τα διαγράμματα δεν αλλάζουν την εφαρμογή και δεν εκτελούν υποβολές.</p>', '<p>Η τεκμηρίωση αντιστοιχεί στα αποτυπώματα πηγών της συγκεκριμένης έκδοσης. Η αποδοχή έκδοσης απαιτεί επιτυχή σχετικά tests και ανθρώπινο έλεγχο.</p>')
    ARTIFACTS['index.html'].write_text(page, encoding='utf-8')
    md = ARTIFACTS['flowcharts.md'].read_text(encoding='utf-8')
    md = md.replace('στο commit 1787f90 (ανάγνωση 20/09/2026)', f'στην έκδοση {version} (έλεγχος {stamp})')
    md = md.replace('# Λογικά διαγράμματα απολογιστικού και ωρομέτρησης', '# Λογικά διαγράμματα απολογιστικού και ωρομέτρησης\n\n' + label, 1)
    md = re.sub(r'Στην έκδοση 1787f90: 141 tests πέρασαν.*?\n', 'Η αποδοχή νέας έκδοσης απαιτεί ανθρώπινο έλεγχο και επιτυχή σχετικά tests. Ο έλεγχος --check επαληθεύει τα αποτυπώματα πηγών και παραδοτέων.\n', md)
    ARTIFACTS['flowcharts.md'].write_text(md, encoding='utf-8')
    # A portable Markdown companion is also available in the offline output folder.
    (OUTPUT / 'flowcharts.md').write_text(md, encoding='utf-8')
    target.mkdir(parents=True)
    files_to_archive = dict(ARTIFACTS)
    historical_warning = ('Ιστορική περιγραφή του έργου, όχι επικαιροποιημένη επιβεβαίωση κανόνων. '
                          'Για τις αποκλίσεις δείτε την ενότητα Αποκλίσεις και τα ελεγμένα διαγράμματα.')
    for output, source, title in (
        ('catalog', 'docs/APOLOGISTIKO_RULES_CATALOG.md', 'Κατάλογος κανόνων'),
        ('logic', 'docs/APOLOGISTIKO_LOGIC.md', 'Εφαρμοσμένη λογική απολογιστικού και ωρομέτρησης'),
    ):
        text = (ROOT / source).read_text(encoding='utf-8')
        (target / (output + '.md')).write_text(text, encoding='utf-8')
        (target / (output + '.html')).write_text(render_document(title, text, version, historical_warning), encoding='utf-8')
        for suffix in ('.md', '.html'):
            files_to_archive[output + suffix] = target / (output + suffix)
    notes = '# Αποκλίσεις τεκμηρίωσης από κώδικα\n\n' + '\n\n'.join(
        '## ' + title + '\n' + detail for title, detail in generator['DISCREPANCIES'])
    (target / 'notes.html').write_text(render_document('Αποκλίσεις', notes, version), encoding='utf-8')
    files_to_archive['notes.html'] = target / 'notes.html'
    # A readable overview links to the exact step sequence in the diagram viewer.
    (target / 'overview.html').write_text(page.replace('<details id="flow">', '<details id="flow" open>'), encoding='utf-8')
    files_to_archive['overview.html'] = target / 'overview.html'
    files_to_archive['legal-review.docx'] = ROOT / 'documentation/Μηχανισμός Απολογιστικού - Προς Έλεγχο Εργατολόγου.docx'
    hashes = {}
    for name, source in files_to_archive.items():
        content = source.read_bytes()
        (target / name).write_bytes(content)
        hashes[name] = sha256(content).hexdigest()
    with ZipFile(target / 'complete.zip', 'w') as package:
        for name in hashes:
            package.write(target / name, name)
        for svg in sorted((OUTPUT / 'svg').glob('*.svg')):
            package.write(svg, 'svg/' + svg.name)
    hashes['complete.zip'] = sha256((target / 'complete.zip').read_bytes()).hexdigest()
    entry = dict(id=version, fingerprint=digest, files=files, artifacts=hashes,
                 reviewed_at=stamp, source_commit=commit,
                 apologistic_version=snapshot, timekeeping_version=timekeeping,
                 count=len(json.loads(ARTIFACTS['rules.json'].read_text(encoding='utf-8'))))
    data = versions.manifest() if (ARCHIVE / 'manifest.json').exists() else {'versions': []}
    data['versions'].append(entry)
    data['current'] = version
    (ARCHIVE / 'manifest.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return check()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--check', action='store_true')
    choice.add_argument('--reviewed', action='store_true', help='Confirm that the diagram decisions were reviewed against the changed source.')
    args = parser.parse_args()
    sys.exit(check() if args.check else build())
