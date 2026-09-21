"""Phone command portal using office authentication and the existing card pipeline."""
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, render_template, request

from app.http_helpers import resolve_active_store
from app.repo_schedule import list_schedule_for_store
from app.repo_employment_contract import list_current_for_store
from app.work_card_payload import WorkCardPayloadError, norm_afm, tz_athens

mobile_bp = Blueprint("mobile", __name__)


def safe_afm(value):
    try:
        return norm_afm(value or "")
    except WorkCardPayloadError:
        return ""


def attach_punches(people, ctx, day):
    from app.repo_work_log import (
        list_work_log_for_store, normalize_overnight_work_log_rows,
        append_card_punches_missing_from_work_log, enrich_work_log_rows_with_card_punch,
    )
    dates = [day.strftime("%d/%m/%Y")]
    employer, branch = ctx["employer_afm"], ctx["branch_aa"]
    rows = list_work_log_for_store(employer, branch, dates[0])
    rows = normalize_overnight_work_log_rows(rows, employer_afm=employer, branch_aa=branch, ergani_dates=dates)
    append_card_punches_missing_from_work_log(rows, employer, branch, dates)
    enrich_work_log_rows_with_card_punch(rows, employer, branch)
    by_afm = {}
    for row in rows:
        pair = {"in": str(row.get("hour_from") or "").strip(),
                "out": str(row.get("hour_to") or "").strip()}
        punches = by_afm.setdefault(norm_afm(row.get("employee_afm") or ""), [])
        if any(pair.values()) and pair not in punches:
            punches.append(pair)
    for person in people:
        punches = by_afm.get(person["afm"], [])
        person["punches"] = punches
        # Χωρίς ωράριο δεν υπάρχει μέτρο πληρότητας, άρα παραμένουν επιλέξιμοι.
        person["completed"] = (not person.get("off_schedule")
                               and bool(punches)
                               and len(punches) >= len(person["shifts"])
                               and all(p["in"] and p["out"] for p in punches))
    return people


def specialties(ctx):
    return {safe_afm(r.get("employee_afm")): r for r in
            list_current_for_store(ctx["employer_afm"], ctx["branch_aa"], limit=10000)}


def today_roster(ctx, day, contracts=None):
    schedules = list_schedule_for_store(ctx["employer_afm"], ctx["branch_aa"], day.strftime("%d/%m/%Y"))
    contracts = specialties(ctx) if contracts is None else contracts
    people = {}
    for row in schedules:
        # Rest/leave rows have no working hours. Split shifts share one tile.
        if not row.get("hour_from") or not row.get("hour_to"):
            continue
        afm = norm_afm(row.get("employee_afm") or "")
        if not afm:
            continue
        person = people.setdefault(afm, {
            "afm": afm,
            "name": " ".join(str(row.get(k) or "").strip() for k in ("eponymo", "onoma")).strip() or afm,
            "specialty": contracts.get(afm, {}).get("specialty") or "Χωρίς ειδικότητα",
            "shifts": [],
        })
        shift = f'{row["hour_from"]} – {row["hour_to"]}'
        if shift not in person["shifts"]:
            person["shifts"].append(shift)
    return sorted(people.values(), key=lambda p: (p["specialty"], p["name"]))


def off_schedule_roster(ctx, scheduled_afms, contracts=None):
    """Υπόλοιπο προσωπικό του καταστήματος, ώστε η αναζήτηση να τους βρίσκει.

    Καλύπτει και όσους έχουν πρόσφατο ωράριο χωρίς σύνδεση `karta_employment`.
    """
    from app.repo_entities import list_active_employees_for_store
    from app.repo_schedule import list_recent_schedule_roster

    employer, branch = ctx["employer_afm"], ctx["branch_aa"]
    contracts = specialties(ctx) if contracts is None else contracts
    rows = list(list_active_employees_for_store(employer, branch, limit=5000))
    rows += list_recent_schedule_roster(employer, branch, days=30, limit=5000)
    people = {}
    for row in rows:
        afm = safe_afm(row.get("afm"))
        if not afm or afm in scheduled_afms or afm in people:
            continue
        name = " ".join(str(row.get(k) or "").strip() for k in ("eponymo", "onoma")).strip()
        people[afm] = {
            "afm": afm,
            "name": name or afm,
            "specialty": contracts.get(afm, {}).get("specialty") or "Χωρίς ειδικότητα",
            "shifts": [],
            "off_schedule": True,
        }
    return sorted(people.values(), key=lambda p: p["name"])


def store_roster(ctx, day):
    contracts = specialties(ctx)
    scheduled = today_roster(ctx, day, contracts)
    return scheduled + off_schedule_roster(ctx, {p["afm"] for p in scheduled}, contracts)


@mobile_bp.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@mobile_bp.get("/mobile")
def mobile():
    return render_template("mobile.html")


@mobile_bp.get("/api/mobile/roster")
def roster():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify(error="Επιλέξτε κατάστημα"), 400
    day = datetime.now(tz_athens()).date()
    return jsonify(store={"id": ctx["id"], "name": ctx["name"]}, date=day.isoformat(),
                   employees=attach_punches(store_roster(ctx, day), ctx, day),
                   synced_at=str(ctx.get("schedule_last_sync_at") or ""))


@mobile_bp.post("/api/mobile/submit")
def submit():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify(error="Αναμενόταν JSON"), 400
    ctx = resolve_active_store()
    if not ctx or str(body.get("store_id")) != str(ctx["id"]):
        return jsonify(error="Το κατάστημα άλλαξε. Ανανεώστε τη λίστα."), 409
    minutes = body.get("minutes")
    if type(minutes) is not int or minutes not in (0, 5, 10) or body.get("event") not in ("check_in", "check_out"):
        return jsonify(error="Μη έγκυρη εντολή"), 400
    now = datetime.now(tz_athens())
    if body.get("date") != now.date().isoformat():
        return jsonify(error="Η ημέρα άλλαξε. Ανανεώστε τη λίστα."), 409
    afm = norm_afm(str(body.get("employee_afm") or ""))
    if afm not in {p["afm"] for p in store_roster(ctx, now.date())}:
        return jsonify(error="Ο εργαζόμενος δεν ανήκει στο κατάστημα."), 400
    event_at = now - timedelta(minutes=minutes)
    from app.routes_work_card import work_card_submit_office
    return work_card_submit_office(body={
        "employee_afm": afm, "event": body["event"],
        "reference_date": event_at.date().isoformat(),
        "event_at": event_at.isoformat(timespec="seconds"),
        "device_info": "mobile_portal", "source": "mobile_portal",
    })
