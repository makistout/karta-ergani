"""Isolated PWA authentication and store-scoped card scanner endpoints."""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import requests
import pyodbc
from flask import Blueprint, current_app, g, jsonify, render_template, request
from werkzeug.security import check_password_hash, generate_password_hash

from app.ergani_client import ErganiClient
from app.ergani_env import store_api_context
from app.ergani_parse import parse_employer_afm
from app.http_helpers import json_or_text
from app.repo_store import get_store_config, list_store_configs
from app.repo_entities import list_active_employees_for_store
from app.work_card_payload import tz_athens
from config import Config
from app.repo_scanner import store_menu_details

scanner_bp = Blueprint("scanner", __name__, url_prefix="/scanner")
COOKIE = "erganios_scanner"


def binding_matches(cfg, binding):
    if isinstance(binding, str):
        return str(cfg.get("web_username") or "").strip() == binding
    return str(cfg.get(binding["field"]) or "").strip() == binding["username"]


@scanner_bp.errorhandler(pyodbc.Error)
def database_error(error):
    current_app.logger.exception("Scanner database unavailable")
    return jsonify(error="Δεν είναι διαθέσιμη η σύνδεση με τη βάση erganiOS. Δοκιμάστε ξανά σε λίγο."), 503


@contextmanager
def database():
    path = Path(current_app.config.get("SCANNER_DB_PATH") or Path(current_app.instance_path) / "scanner.sqlite3")
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=15)
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
          id TEXT PRIMARY KEY, stores TEXT NOT NULL, store_id INTEGER,
          expires REAL NOT NULL, pin TEXT, unlocked REAL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS attempts (key TEXT PRIMARY KEY, count INTEGER, until REAL);
        CREATE TABLE IF NOT EXISTS submissions (
          id TEXT PRIMARY KEY, session_id TEXT, store_id INTEGER, payload TEXT,
          result TEXT, status INTEGER, created REAL);
    """)
    try:
        with db:
            yield db
    finally:
        db.close()


def limited(key, maximum=10):
    now = time.time()
    with database() as db:
        db.execute("DELETE FROM attempts WHERE until < ?", (now,))
        db.execute("INSERT INTO attempts VALUES (?, 1, ?) ON CONFLICT(key) DO UPDATE SET count=count+1", (key, now + 300))
        return db.execute("SELECT count FROM attempts WHERE key=?", (key,)).fetchone()[0] > maximum


def _allowed_scanner_origins() -> set[str]:
    """Origins που επιτρέπονται για POST (public URL + τοπικό host πίσω από IIS)."""
    allowed = {request.host_url.rstrip("/")}
    public = str(Config.PUBLIC_BASE_URL or "").strip().rstrip("/")
    if public:
        allowed.add(public)
    return {o for o in allowed if o}


@scanner_bp.before_request
def guard():
    if request.method == "POST":
        origin = (request.headers.get("Origin") or "").rstrip("/")
        if request.headers.get("X-Scanner-Request") != "1" or (
            origin and origin not in _allowed_scanner_origins()
        ):
            return jsonify(error="Μη έγκυρη προέλευση αιτήματος"), 403
        if not isinstance(request.get_json(silent=True), dict):
            return jsonify(error="Αναμενόταν αντικείμενο JSON"), 400
    if not request.path.startswith("/scanner/api/") or request.endpoint in ("scanner.login", "scanner.connectivity"):
        return None
    sid = request.cookies.get(COOKIE, "")
    digest = hashlib.sha256(sid.encode()).hexdigest()
    with database() as db:
        row = db.execute("SELECT * FROM sessions WHERE id=? AND expires>?", (digest, time.time())).fetchone()
    if not row:
        return jsonify(error="Απαιτείται σύνδεση", login_required=True), 401
    g.scanner = dict(row)
    if row["store_id"]:
        cfg = get_store_config(row["store_id"])
        allowed = json.loads(row["stores"])
        if not cfg or str(cfg["id"]) not in allowed or not binding_matches(cfg, allowed[str(cfg["id"])]):
            return jsonify(error="Η πρόσβαση στο κατάστημα δεν είναι πλέον διαθέσιμη"), 403
        g.scanner_store = store_api_context(cfg)


@scanner_bp.after_request
def headers(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: https://pbs.twimg.com; connect-src 'self'; media-src 'self' blob:; worker-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    return response


@scanner_bp.get("/")
def index():
    return render_template("scanner.html")


@scanner_bp.get("/api/connectivity")
def connectivity():
    # No DB/auth/upstream work: only prove a fresh round trip to this server.
    return jsonify(service="erganios-scanner", nonce=request.args.get("nonce", "")[:64])


@scanner_bp.get("/sw.js")
def service_worker():
    response = current_app.send_static_file("scanner/sw.js")
    response.headers["Service-Worker-Allowed"] = "/scanner/"
    return response


@scanner_bp.post("/api/login")
def login():
    body = request.get_json(silent=True) or {}
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    if limited("login:" + str(request.remote_addr)):
        return jsonify(error="Πολλές προσπάθειες. Δοκιμάστε σε 5 λεπτά."), 429
    if not username or not password or len(username) > 200 or len(password) > 500:
        return jsonify(error="Συμπληρώστε κωδικούς ΕΡΓΑΝΗ"), 400
    # Both configured login types use their existing Ergani verification path.
    candidates = [s for s in list_store_configs() if username in (str(s.get("web_username") or "").strip(), str(s.get("username") or "").strip())]
    allowed = {}
    for cfg in candidates:
        ctx = store_api_context(cfg)
        client = ErganiClient(ctx["api_base_url"], timeout=20)
        try:
            if str(cfg.get("username") or "").strip() == username:
                from app.portal_schedule_sync import _login_session
                portal_ctx = dict(ctx, username=username, password=password)
                try:
                    portal_session = _login_session(portal_ctx)
                    portal_session.close()
                except (RuntimeError, ValueError):
                    continue
                allowed[str(cfg["id"])] = {"field": "username", "username": username}
                continue
            response = client.authenticate(username, password, "02")
            data = json_or_text(response)
            if not response.ok or not isinstance(data, dict) or not data.get("accessToken"):
                continue
            identity = client.execute_service("EX_BASE_01", [], data["accessToken"])
            if identity.ok and parse_employer_afm(json_or_text(identity)) == str(ctx["employer_afm"]).strip():
                allowed[str(cfg["id"])] = username
        except requests.RequestException:
            return jsonify(error="Το ΕΡΓΑΝΗ δεν ανταποκρίνεται. Δοκιμάστε ξανά."), 503
    if not allowed:
        return jsonify(error="Μη έγκυροι κωδικοί ή μη συνδεδεμένο κατάστημα στο erganiOS"), 401
    token = secrets.token_urlsafe(32)
    sid = hashlib.sha256(token.encode()).hexdigest()
    with database() as db:
        db.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
        db.execute("INSERT INTO sessions(id,stores,store_id,expires) VALUES(?,?,?,?)", (sid, json.dumps(allowed), int(next(iter(allowed))), time.time() + 43200))
    response = jsonify(success=True)
    response.set_cookie(COOKIE, token, max_age=43200, secure=request.is_secure, httponly=True, samesite="Strict", path="/scanner/")
    return response


@scanner_bp.get("/api/session")
def status():
    stores = []
    for sid, username in json.loads(g.scanner["stores"]).items():
        cfg = get_store_config(int(sid))
        if cfg and binding_matches(cfg, username):
            details = store_menu_details(cfg["employer_afm"], cfg["branch_aa"])
            stores.append({"id": cfg["id"], "name": details["legal_name"] or "Μη διαθέσιμη επωνυμία", "branch_aa": cfg["branch_aa"], "employer_afm": cfg["employer_afm"], "username": cfg.get("username") or "", "branch_description": details["branch_description"], "last_card_at": details["last_card_at"]})
    if not g.scanner["store_id"] and stores:
        g.scanner["store_id"] = stores[0]["id"]
        with database() as db:
            db.execute("UPDATE sessions SET store_id=? WHERE id=?", (stores[0]["id"], g.scanner["id"]))
    cfg = get_store_config(g.scanner["store_id"]) if g.scanner["store_id"] else {}
    owner = hashlib.sha256(g.scanner["stores"].encode()).hexdigest()
    return jsonify(stores=stores, store_id=g.scanner["store_id"], owner=owner, pin_enabled=bool(g.scanner["pin"]), last_sync=str(cfg.get("work_log_last_sync_at") or cfg.get("last_sync_at") or ""))


@scanner_bp.post("/api/store")
def select_store():
    sid = str((request.get_json(silent=True) or {}).get("store_id", ""))
    if sid not in json.loads(g.scanner["stores"]):
        return jsonify(error="Δεν έχετε πρόσβαση στο κατάστημα"), 403
    with database() as db:
        db.execute("UPDATE sessions SET store_id=? WHERE id=?", (int(sid), g.scanner["id"]))
    return jsonify(success=True)


@scanner_bp.post("/api/logout")
def logout():
    with database() as db:
        db.execute("DELETE FROM sessions WHERE id=?", (g.scanner["id"],))
    response = jsonify(success=True)
    response.delete_cookie(COOKIE, path="/scanner/")
    return response


@scanner_bp.post("/api/pin")
def pin():
    body = request.get_json(silent=True) or {}
    if limited("pin:" + g.scanner["id"], 8):
        return jsonify(error="Πολλές προσπάθειες PIN. Περιμένετε 5 λεπτά."), 429
    old = str(body.get("pin", ""))
    if g.scanner["pin"] and not check_password_hash(g.scanner["pin"], old):
        return jsonify(error="Λάθος PIN"), 403
    new = body.get("new_pin")
    if new is not None and new != "" and not re.fullmatch(r"\d{4,8}", str(new)):
        return jsonify(error="Το PIN πρέπει να έχει 4–8 ψηφία"), 400
    with database() as db:
        db.execute("UPDATE sessions SET unlocked=? WHERE id=?", (time.time() + 120, g.scanner["id"]))
        if new is not None:
            db.execute("UPDATE sessions SET pin=? WHERE id=?", (generate_password_hash(str(new)) if new else None, g.scanner["id"]))
    return jsonify(success=True)


def store():
    return getattr(g, "scanner_store", None)


@scanner_bp.get("/api/recent")
def recent():
    ctx = store()
    if not ctx:
        return jsonify(error="Επιλέξτε κατάστημα"), 400
    if g.scanner["pin"] and g.scanner["unlocked"] < time.time():
        return jsonify(error="Απαιτείται PIN διαχείρισης", pin_required=True), 403
    try:
        page = int(request.args.get("page", "0"))
        if not 0 <= page <= 100000:
            raise ValueError()
    except ValueError:
        return jsonify(error="Μη έγκυρη σελίδα"), 400
    from app.repo_scanner import recent_punches
    events, has_next = recent_punches(ctx["employer_afm"], ctx["branch_aa"], page)
    return jsonify(events=events, has_next=has_next, has_previous=page > 0)


def employee_from_qr(raw, ctx):
    # Accept only a single unambiguous AFM present in this branch's active roster.
    if not isinstance(raw, str) or len(raw) > 4096:
        return None
    candidates = set(re.findall(r"(?<!\d)\d{9}(?!\d)", raw))
    employees = list_active_employees_for_store(ctx["employer_afm"], ctx["branch_aa"])
    matches = {str(e["afm"]): e for e in employees if str(e["afm"]) in candidates}
    return next(iter(matches.values())) if len(matches) == 1 else None


@scanner_bp.post("/api/preview")
def preview():
    ctx = store()
    if not ctx:
        return jsonify(error="Επιλέξτε κατάστημα"), 400
    body = request.get_json(silent=True) or {}
    employee = employee_from_qr(body.get("qr"), ctx)
    if not employee or body.get("event") not in ("in", "out"):
        return jsonify(error="Η κάρτα δεν αντιστοιχεί σε ενεργό εργαζόμενο του παραρτήματος"), 400
    return jsonify(employee_afm=employee["afm"], name=f"{employee.get('eponymo') or ''} {employee.get('onoma') or ''}".strip(), event=body["event"], event_at=datetime.now(tz_athens()).isoformat(timespec="seconds"))


@scanner_bp.post("/api/submit")
def submit():
    ctx = store()
    if not ctx:
        return jsonify(error="Επιλέξτε κατάστημα"), 400
    body = request.get_json(silent=True) or {}
    if str(body.get("store_id")) != str(ctx["id"]):
        return jsonify(error="Το κατάστημα άλλαξε. Επαναφέρετε το αρχικό κατάστημα της σάρωσης."), 409
    key = str(body.get("request_id", ""))
    if not re.fullmatch(r"[a-zA-Z0-9-]{20,64}", key):
        return jsonify(error="Μη έγκυρο αναγνωριστικό αποστολής"), 400
    employee = employee_from_qr(body.get("qr"), ctx)
    if not employee or body.get("event") not in ("in", "out"):
        return jsonify(error="Μη έγκυρη κάρτα ή ενέργεια"), 400
    try:
        at = datetime.fromisoformat(str(body.get("event_at", "")).replace("Z", "+00:00"))
        if at.tzinfo is None or (at - datetime.now(tz_athens())).total_seconds() > 30:
            raise ValueError()
    except ValueError:
        return jsonify(error="Μη έγκυρη ώρα σάρωσης"), 400
    payload = {"employee_afm": employee["afm"], "event": body["event"], "event_at": at.isoformat(), "reference_date": at.astimezone(tz_athens()).date().isoformat(), "source": "scanner_pwa"}
    canonical = json.dumps(payload, sort_keys=True)
    # Commit intent before contacting Ergani. Unknown results are never resent.
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        old = db.execute("SELECT * FROM submissions WHERE id=?", (key,)).fetchone()
        if old:
            if old["store_id"] != ctx["id"] or old["payload"] != canonical:
                return jsonify(error="Σύγκρουση αναγνωριστικού αποστολής"), 409
            if old["result"]:
                return jsonify(json.loads(old["result"])), old["status"]
            return jsonify(error="Η υποβολή έχει αβέβαιο αποτέλεσμα. Ελέγξτε τις αποστολές πριν από νέα σάρωση.", uncertain=True), 409
        if (datetime.now(tz_athens()) - at).total_seconds() > 900:
            from app.work_card_payload import AITIOLOGIA_CODES
            if body.get("aitiologia") not in AITIOLOGIA_CODES:
                return jsonify(error="Απαιτείται αιτιολογία εκπρόθεσμης υποβολής", late=True), 422
            payload["aitiologia"] = body["aitiologia"]
        db.execute("INSERT INTO submissions VALUES(?,?,?,?,NULL,NULL,?)", (key, g.scanner["id"], ctx["id"], canonical, time.time()))
    try:
        client = ErganiClient(ctx["api_base_url"], timeout=20)
        auth = client.authenticate(ctx["web_username"], ctx["web_password"], "02")
        data = json_or_text(auth)
        if not auth.ok or not isinstance(data, dict) or not data.get("accessToken"):
            result, code = {"error": "Αποτυχία σύνδεσης ΕΡΓΑΝΗ", "success": False}, 401
        else:
            from app.routes_work_card import _submit_work_card
            response, code = _submit_work_card(body=payload, erg_s=ctx["employer_afm"], aa_s=ctx["branch_aa"], bearer=data["accessToken"], api_base_url=ctx["api_base_url"], store_id=ctx["id"], client_ip=request.remote_addr, client_device="scanner_pwa")
            raw = response.get_json()
            result = {k: raw.get(k) for k in ("success", "error", "protocol", "persisted", "f_type_label")}
            if code == 202 or code >= 500:
                result["uncertain"] = True
    except Exception:
        current_app.logger.exception("Scanner submission outcome unknown")
        return jsonify(error="Δεν επιβεβαιώθηκε το αποτέλεσμα. Ελέγξτε τις αποστολές.", uncertain=True), 503
    with database() as db:
        db.execute("UPDATE submissions SET result=?,status=? WHERE id=?", (json.dumps(result, ensure_ascii=False), code, key))
    return jsonify(result), code
