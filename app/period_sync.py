"""Συγχρονισμός περιόδου — εργαζόμενοι (API) + portal ωράριο + πραγματική."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any

from app.db import cursor
from app import repo_apologistic
from app.apologistic_snapshot import generate_store_week
from app.ergani_client import ErganiClient
from app.ergani_parse import parse_branches, parse_employees, parse_employer_profile
from app.http_helpers import json_or_text
from app.karta_log import KartaLogger
from app.portal_schedule_sync import iter_schedule_sync_events
from app.portal_work_log_sync import iter_work_log_sync_events
from app.portal_card_protocol_sync import iter_card_protocol_sync_events
from app.repo_entities import (
    deactivate_stale_employments,
    upsert_employee,
    upsert_employer,
    upsert_employment,
    upsert_parartima,
)
from app.work_card_payload import norm_afm
from config import Config

PERIOD_SYNC_PHASES = 5


def _full_week_ranges_within(from_iso: str, to_iso: str) -> list[tuple[datetime.date, datetime.date]]:
    """
    Επιστρέφει μόνο πλήρεις εβδομάδες (Δευτέρα–Κυριακή) που βρίσκονται εξ ολοκλήρου
    μέσα στο [from_iso..to_iso] (και η εβδομάδα ορίζεται με week_from=Δευτέρα).
    """
    from_date = datetime.strptime(from_iso[:10], "%Y-%m-%d").date()
    to_date = datetime.strptime(to_iso[:10], "%Y-%m-%d").date()
    if from_date > to_date:
        from_date, to_date = to_date, from_date

    # Monday=0 στο Python.
    delta_to_monday = (-from_date.weekday()) % 7
    first_monday = from_date + timedelta(days=delta_to_monday)
    last_week_start = to_date - timedelta(days=6)  # ώστε week_end<=to_date
    if first_monday > last_week_start:
        return []

    weeks: list[tuple[datetime.date, datetime.date]] = []
    week_start = first_monday
    while week_start <= last_week_start:
        weeks.append((week_start, week_start + timedelta(days=6)))
        week_start += timedelta(days=7)
    return weeks


def _iso_chunks(from_iso: str, to_iso: str, *, max_days: int) -> list[tuple[str, str]]:
    """
    Σπάει μεγάλο ISO διάστημα σε συνεχόμενα chunks έως `max_days` ημερών.
    Χρήσιμο γιατί τα portal sync modules δουλεύουν έως 31 ημέρες ανά αναζήτηση.
    """
    start = datetime.strptime(from_iso[:10], "%Y-%m-%d").date()
    end = datetime.strptime(to_iso[:10], "%Y-%m-%d").date()
    if start > end:
        start, end = end, start
    chunks: list[tuple[str, str]] = []
    cursor = start
    span = max(1, int(max_days))
    while cursor <= end:
        chunk_end = min(end, cursor + timedelta(days=span - 1))
        chunks.append((cursor.isoformat(), chunk_end.isoformat()))
        cursor = chunk_end + timedelta(days=1)
    return chunks


def _merge_portal_results(parts: list[dict[str, Any]], *, label: str) -> dict[str, Any]:
    if not parts:
        return {"success": False, "detail": f"Διακόπηκε ο συγχρονισμός {label.lower()}"}
    success = all(bool(part.get("success")) for part in parts)
    work_dates: list[str] = []
    errors: list[str] = []
    logs: list[dict[str, Any]] = []
    count = 0
    days_synced = 0
    fetch_sources: list[str] = []
    portal_base = ""
    for part in parts:
        count += int(part.get("count") or 0)
        days_synced += int(part.get("days_synced") or 0)
        work_dates.extend([str(x) for x in (part.get("work_dates") or []) if str(x or "").strip()])
        errors.extend([str(x) for x in (part.get("errors") or []) if str(x or "").strip()])
        logs.extend(part.get("logs") or [])
        src = str(part.get("fetch_source") or part.get("source") or "").strip()
        if src and src not in fetch_sources:
            fetch_sources.append(src)
        portal_base = portal_base or str(part.get("portal_base") or "").strip()
    fetch_desc = fetch_sources[0] if len(fetch_sources) == 1 else "multiple"
    detail = f"{count} εγγραφές portal ({days_synced} ημέρες, {fetch_desc})"
    return {
        "success": success,
        "detail": detail,
        "work_date": None,
        "work_dates": work_dates,
        "days_synced": days_synced,
        "count": count,
        "errors": errors[:20],
        "logs": logs[-100:],
        "source": "portal",
        "fetch_source": fetch_desc,
        "portal_base": portal_base or None,
    }


def _sync_employees_api(
    client: ErganiClient,
    bearer: str,
    afm: str,
    aa: str,
    log: KartaLogger,
) -> dict[str, Any]:
    synced = 0
    try:
        r01 = client.execute_service("EX_BASE_01", [], bearer)
        p01 = json_or_text(r01)
        if r01.ok:
            prof = parse_employer_profile(p01)
            with cursor() as cur:
                upsert_employer(cur, afm, eponimia=prof.get("eponimia"))
            log.info("Προσωπικό: εργοδότης ενημερώθηκε (EX_BASE_01)")
        else:
            log.error(f"Προσωπικό: αποτυχία EX_BASE_01 — HTTP {r01.status_code}")

        r02 = client.execute_service("EX_BASE_02", [], bearer)
        p02 = json_or_text(r02)
        if r02.ok:
            branches = parse_branches(p02)
            with cursor() as cur:
                employer_id = upsert_employer(cur, afm)
                if employer_id:
                    for b in branches:
                        upsert_parartima(
                            cur,
                            employer_id,
                            b["aa"],
                            description=b.get("description"),
                        )
            log.info(f"Προσωπικό: παραρτήματα ενημερώθηκαν (EX_BASE_02) — {len(branches)}")
        else:
            log.error(f"Προσωπικό: αποτυχία EX_BASE_02 — HTTP {r02.status_code}")

        r05 = client.execute_service("EX_BASE_05", [], bearer)
        p05 = json_or_text(r05)
        if not r05.ok:
            detail = f"HTTP {r05.status_code}"
            log.error(f"Προσωπικό: αποτυχία EX_BASE_05 — {detail}")
            return {"success": False, "detail": detail, "count": 0}

        employees = parse_employees(p05)
        active_afms: set[str] = set()
        with cursor() as cur:
            employer_id = upsert_employer(cur, afm)
            if not employer_id:
                raise RuntimeError("Δεν δημιουργήθηκε employer_id")
            part_id = upsert_parartima(cur, employer_id, aa)
            for emp in employees:
                e_afm = emp.get("afm")
                if not e_afm:
                    continue
                active_afms.add(norm_afm(e_afm))
                emp_id = upsert_employee(
                    cur,
                    e_afm,
                    emp.get("eponymo"),
                    emp.get("onoma"),
                    flex_arrival_minutes=emp.get("flex_arrival_minutes"),
                )
                if emp_id:
                    upsert_employment(cur, employer_id, emp_id, part_id)
                    synced += 1
            if active_afms:
                deactivate_stale_employments(
                    cur, employer_id, active_afms, parartima_id=part_id
                )
        log.info(f"Προσωπικό: αποθηκεύτηκαν {synced} εργαζόμενοι (EX_BASE_05)", count=synced)
        return {"success": True, "detail": f"{synced} εργαζόμενοι", "count": synced}
    except Exception as ex:
        log.error(str(ex))
        return {"success": False, "detail": str(ex), "count": synced}


def _forward_portal(
    events: Iterator[dict[str, Any]],
    prefix: str,
    log: KartaLogger,
) -> Iterator[dict[str, Any]]:
    for ev in events:
        kind = ev.get("event")
        if kind == "progress" and ev.get("message"):
            yield {**ev, "message": f"{prefix}: {ev['message']}"}
        elif kind == "range_ok":
            log.info(
                ev.get("message") or f"{prefix} OK",
                count=ev.get("count"),
                source=ev.get("source"),
            )
            yield ev
        elif kind == "day_ok":
            log.info(
                ev.get("message") or f"{prefix} OK",
                work_date=ev.get("work_date"),
                count=ev.get("count"),
            )
            yield ev
        elif kind == "day_err":
            log.error(ev.get("message") or f"{prefix} σφάλμα")
            yield ev
        elif kind == "done":
            yield ev
            return
        elif kind == "error":
            yield ev
            return
        else:
            yield ev


def iter_period_sync_events(
    ctx: dict[str, Any],
    bearer: str,
    from_iso: str,
    to_iso: str,
    *,
    run_id: str | None = None,
    max_days: int = 31,
) -> Iterator[dict[str, Any]]:
    log = KartaLogger(
        "period_sync",
        store_id=ctx.get("id"),
        store_name=ctx.get("name"),
        run_id=run_id,
        register_run=run_id is None,
    )
    client = ErganiClient(ctx.get("api_base_url"))
    afm = str(ctx["employer_afm"]).strip()
    aa = str(ctx.get("branch_aa") or "0").strip()[:32] or "0"
    results: dict[str, Any] = {
        "employees": {"success": False},
        "schedule": {"success": False},
        "work_log": {"success": False},
        "card_protocol": {"success": False},
    }

    log.info(
        "Έναρξη συγχρονισμού περιόδου",
        from_iso=from_iso,
        to_iso=to_iso,
        employer_afm=afm,
    )
    yield {
        "event": "progress",
        "message": f"Έναρξη συγχρονισμού ({from_iso} – {to_iso})…",
        "step": 0,
        "total": PERIOD_SYNC_PHASES,
    }

    msg = "Προσωπικό (Ergani API EX_BASE_01/02/05)…"
    log.info(msg)
    yield {"event": "progress", "message": msg, "step": 1, "total": PERIOD_SYNC_PHASES}
    emp = _sync_employees_api(client, bearer, afm, aa, log)
    results["employees"] = emp

    chunks = _iso_chunks(from_iso, to_iso, max_days=max_days)

    msg = "Ψηφιακό ωράριο (portal Ergani)…"
    log.info(msg)
    yield {"event": "progress", "message": msg, "step": 2, "total": PERIOD_SYNC_PHASES}
    schedule_parts: list[dict[str, Any]] = []
    sched_failed = False
    for index, (chunk_from, chunk_to) in enumerate(chunks, start=1):
        log.info(
            f"Ψηφιακό ωράριο: chunk {index}/{len(chunks)} ({chunk_from} – {chunk_to})"
        )
        yield {
            "event": "progress",
            "message": f"Ψηφιακό ωράριο: chunk {index}/{len(chunks)} ({chunk_from} – {chunk_to})…",
            "step": 2,
            "total": PERIOD_SYNC_PHASES,
        }
        chunk_result: dict[str, Any] | None = None
        for ev in _forward_portal(
            iter_schedule_sync_events(
                ctx,
                from_iso=chunk_from,
                to_iso=chunk_to,
                max_days=max_days,
                run_id=run_id,
            ),
            "Ψηφιακό ωράριο",
            log,
        ):
            kind = ev.get("event")
            if kind == "progress":
                yield {**ev, "step": 2, "total": PERIOD_SYNC_PHASES}
            elif kind == "done":
                chunk_result = ev.get("sync") or {}
                break
            elif kind == "error":
                chunk_result = {
                    "success": False,
                    "detail": ev.get("message") or "Αποτυχία ωραρίου",
                }
                break
        if chunk_result:
            schedule_parts.append(chunk_result)
            if not chunk_result.get("success"):
                sched_failed = True
                break
        else:
            sched_failed = True
            break
    if sched_failed and not schedule_parts:
        results["schedule"] = {"success": False, "detail": "Διακόπηκε ο συγχρονισμός ωραρίου"}
    else:
        results["schedule"] = _merge_portal_results(schedule_parts, label="ωραρίου")

    msg = "Πραγματική απασχόληση (portal Ergani)…"
    log.info(msg)
    yield {"event": "progress", "message": msg, "step": 3, "total": PERIOD_SYNC_PHASES}
    work_log_parts: list[dict[str, Any]] = []
    wl_failed = False
    for index, (chunk_from, chunk_to) in enumerate(chunks, start=1):
        log.info(
            f"Πραγματική απασχόληση: chunk {index}/{len(chunks)} ({chunk_from} – {chunk_to})"
        )
        yield {
            "event": "progress",
            "message": f"Πραγματική απασχόληση: chunk {index}/{len(chunks)} ({chunk_from} – {chunk_to})…",
            "step": 3,
            "total": PERIOD_SYNC_PHASES,
        }
        chunk_result: dict[str, Any] | None = None
        for ev in _forward_portal(
            iter_work_log_sync_events(
                ctx,
                from_iso=chunk_from,
                to_iso=chunk_to,
                max_days=max_days,
                run_id=run_id,
            ),
            "Πραγματική απασχόληση",
            log,
        ):
            kind = ev.get("event")
            if kind == "progress":
                yield {**ev, "step": 3, "total": PERIOD_SYNC_PHASES}
            elif kind == "done":
                chunk_result = ev.get("sync") or {}
                break
            elif kind == "error":
                chunk_result = {
                    "success": False,
                    "detail": ev.get("message") or "Αποτυχία πραγματικής",
                }
                break
        if chunk_result:
            work_log_parts.append(chunk_result)
            if not chunk_result.get("success"):
                wl_failed = True
                break
        else:
            wl_failed = True
            break
    if wl_failed and not work_log_parts:
        results["work_log"] = {
            "success": False,
            "detail": "Διακόπηκε ο συγχρονισμός πραγματικής",
        }
    else:
        results["work_log"] = _merge_portal_results(work_log_parts, label="πραγματικής")

    msg = "Πρωτόκολλα χτυπημάτων (portal Ergani)…"
    log.info(msg)
    yield {"event": "progress", "message": msg, "step": 4, "total": PERIOD_SYNC_PHASES}
    protocol_parts: list[dict[str, Any]] = []
    proto_failed = False
    for index, (chunk_from, chunk_to) in enumerate(chunks, start=1):
        log.info(
            f"Πρωτόκολλα: chunk {index}/{len(chunks)} ({chunk_from} – {chunk_to})"
        )
        yield {
            "event": "progress",
            "message": f"Πρωτόκολλα: chunk {index}/{len(chunks)} ({chunk_from} – {chunk_to})…",
            "step": 4,
            "total": PERIOD_SYNC_PHASES,
        }
        chunk_result: dict[str, Any] | None = None
        for ev in _forward_portal(
            iter_card_protocol_sync_events(
                ctx,
                from_iso=chunk_from,
                to_iso=chunk_to,
                max_days=max_days,
                run_id=run_id,
            ),
            "Πρωτόκολλα χτυπημάτων",
            log,
        ):
            kind = ev.get("event")
            if kind == "progress":
                yield {**ev, "step": 4, "total": PERIOD_SYNC_PHASES}
            elif kind == "done":
                chunk_result = ev.get("sync") or {}
                break
            elif kind == "error":
                chunk_result = {
                    "success": False,
                    "detail": ev.get("message") or "Αποτυχία πρωτοκόλλων",
                }
                break
        if chunk_result:
            protocol_parts.append(chunk_result)
            if not chunk_result.get("success"):
                proto_failed = True
                break
        else:
            proto_failed = True
            break
    if proto_failed and not protocol_parts:
        results["card_protocol"] = {
            "success": False,
            "detail": "Διακόπηκε ο συγχρονισμός πρωτοκόλλων",
        }
    else:
        results["card_protocol"] = _merge_portal_results(protocol_parts, label="πρωτοκόλλων")

    ok = (
        results["employees"].get("success")
        and results["schedule"].get("success")
        and results["work_log"].get("success")
        and results["card_protocol"].get("success")
    )
    post_sync_notifications_enqueued = False
    today_iso = datetime.today().strftime("%Y-%m-%d")
    if ok and from_iso <= today_iso <= to_iso:
        from app import repo_store
        from app.scheduled_sync import enqueue_post_sync_notifications

        cfg = repo_store.get_store_config(int(ctx["id"]))
        if cfg:
            post_sync_notifications_enqueued = enqueue_post_sync_notifications(
                cfg,
                work_date_iso=today_iso,
                parent_run_id=run_id,
            )
            if post_sync_notifications_enqueued:
                log.info(
                    "Έγινε enqueue ασύγχρονων ειδοποιήσεων μετά το sync περιόδου",
                    work_date=today_iso,
                )

    apologistic_success = True
    apologistic_weeks_saved = 0
    apologistic_weeks_skipped = 0
    apologistic_weeks_failed = 0
    yield {
        "event": "progress",
        "message": "Απολογιστικό: έλεγχος πλήρων εβδομάδων…",
        "step": 5,
        "total": PERIOD_SYNC_PHASES,
    }
    if not ok:
        log.info("Απολογιστικό: παραλείφθηκε επειδή ο συγχρονισμός περιόδου είχε αποτυχία.")
    elif not Config.KARTA_SCHEDULED_APOLOGISTIC_ENABLED:
        log.info("Απολογιστικό: απενεργοποιημένο από ρύθμιση.")
    elif not repo_apologistic.tables_available():
        log.warning("Απολογιστικό: λείπουν οι πίνακες απολογιστικού.")
    else:
        try:
            from app import repo_store

            weeks = _full_week_ranges_within(from_iso, to_iso)
            if weeks:
                cfg = repo_store.get_store_config(int(ctx["id"])) or dict(ctx)
                log.info(
                    f"Απολογιστικό: βρέθηκαν {len(weeks)} πλήρεις εβδομάδες στο διάστημα."
                )
                for index, (week_from, week_to) in enumerate(weeks, start=1):
                    week_label = f"{week_from.isoformat()} – {week_to.isoformat()}"
                    yield {
                        "event": "progress",
                        "message": f"Απολογιστικό: εβδομάδα {index}/{len(weeks)} ({week_label})…",
                        "step": 5,
                        "total": PERIOD_SYNC_PHASES,
                    }
                    row = generate_store_week(cfg, week_from, week_to)
                    if row.get("success") and not row.get("skipped"):
                        apologistic_weeks_saved += 1
                        log.info(
                            f"Απολογιστικό: OK {week_label}",
                            run_id=row.get("run_id"),
                            days=row.get("days"),
                        )
                    elif row.get("skipped"):
                        apologistic_weeks_skipped += 1
                        log.info(
                            f"Απολογιστικό: SKIP {week_label} — {row.get('reason') or 'παράλειψη'}"
                        )
                    else:
                        apologistic_weeks_failed += 1
                        apologistic_success = False
                        log.error(
                            f"Απολογιστικό: FAIL {week_label} — {row.get('error') or 'άγνωστο σφάλμα'}"
                        )
            else:
                log.info("Δεν υπάρχουν πλήρεις εβδομάδες στο διάστημα για απολογιστικό.")
        except Exception as ex:
            apologistic_success = False
            log.error(f"Αποτυχία παραγωγής απολογιστικού για full weeks: {ex}")
    ok = bool(ok and apologistic_success)
    parts = []
    if results["employees"].get("success"):
        parts.append(f"{results['employees'].get('count', 0)} εργαζόμενοι")
    if results["schedule"].get("success"):
        parts.append(
            f"{results['schedule'].get('count', 0)} ωράριο "
            f"({results['schedule'].get('days_synced', 0)} ημέρες)"
        )
    if results["work_log"].get("success"):
        parts.append(
            f"{results['work_log'].get('count', 0)} πραγματική "
            f"({results['work_log'].get('days_synced', 0)} ημέρες)"
        )
    if results["card_protocol"].get("success"):
        parts.append(
            f"{results['card_protocol'].get('count', 0)} πρωτόκολλα "
            f"({results['card_protocol'].get('days_synced', 0)} chunks)"
        )
    if apologistic_weeks_saved or apologistic_weeks_skipped:
        parts.append(
            f"Απολογιστικό: {apologistic_weeks_saved} εβδομάδες"
            + (
                f" (skipped {apologistic_weeks_skipped})"
                if apologistic_weeks_skipped
                else ""
            )
        )
    elif ok:
        parts.append("Απολογιστικό: χωρίς πλήρεις εβδομάδες")
    if apologistic_weeks_failed:
        parts.append(f"Απολογιστικό αποτυχίες: {apologistic_weeks_failed}")
    summary = (
        "Ολοκληρώθηκε — " + ", ".join(parts)
        if parts
        else "Ολοκληρώθηκε με σφάλματα"
    )
    log.info(summary, success=ok)
    yield {
        "event": "done",
        "success": ok,
        "sync": {
            "success": ok,
            "sync_results": results,
            "post_sync_notifications_enqueued": post_sync_notifications_enqueued,
            "apologistic": {
                "success": apologistic_success,
                "weeks_saved": apologistic_weeks_saved,
                "weeks_skipped": apologistic_weeks_skipped,
                "weeks_failed": apologistic_weeks_failed,
            },
        },
        "message": summary,
        "logs": log.tail(200),
        "error": None if ok else summary,
    }
