"""
Αντιστοίχιση πρωτοκόλλων Ergani με χτυπήματα.

1. Δικά μας χτυπήματα (karta_card_event + karta_declaration.protocol) →
   protocol_from / protocol_to στην αντίστοιχη γραμμή πραγματικής.
2. 1-1 στα υπόλοιπα: μοναδικό πρωτόκολλο ↔ μοναδική κενή ώρα πραγματικής
   στην ίδια στιγμή. Τα δικά μας (ήδη γεμάτα) και τα πρωτόκολλά τους
   εξαιρούνται, ώστε π.χ. δύο 08:22 → το δικό μας γεμίζει πρώτο, το άλλο
   παίρνει το εναπομείναν πρωτόκολλο.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from app.db import cursor
from app.date_util import format_f_date_time
from app.telegram_punch_service import ergani_date_to_iso
from app.work_card_payload import norm_afm, tz_athens

MatchKey = tuple[int, str, str]  # store_id, calendar_date_iso, HH:MM


@dataclass(frozen=True)
class ProtocolDeductionMatch:
    store_id: int
    calendar_date: str
    work_date: str
    time_hm: str
    f_type: str
    protocol_id: int
    protocol: str
    submit_date_text: str | None
    employee_afm: str | None
    work_log_id: int | None
    declaration_id: int | None
    card_event_id: int | None


def _submit_local_parts(submit_at: Any) -> tuple[str, str] | None:
    if submit_at is None:
        return None
    if isinstance(submit_at, datetime):
        dt = submit_at
    else:
        try:
            dt = datetime.fromisoformat(str(submit_at).replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz_athens())
    else:
        dt = dt.astimezone(tz_athens())
    return dt.date().isoformat(), dt.strftime("%H:%M")


def _time_hm(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if "T" in raw or " " in raw:
        raw = format_f_date_time(raw)
    return raw[:5] if len(raw) >= 5 else raw


def _is_overnight_exit(hour_from: str, hour_to: str) -> bool:
    hf = _time_hm(hour_from)
    ht = _time_hm(hour_to)
    if not hf or not ht:
        return False
    return ht < hf


def _protocol_rows_for_range(
    store_id: int,
    from_iso: str,
    to_iso: str,
    *,
    require_unlinked: bool = True,
) -> list[dict[str, Any]]:
    start = str(from_iso).strip()[:10]
    end = str(to_iso).strip()[:10]
    if end < start:
        start, end = end, start
    linked_filter = "AND p.declaration_id IS NULL" if require_unlinked else ""
    sql = f"""
        SELECT
            p.id,
            p.store_id,
            p.protocol,
            CAST(p.submit_at AS datetime2) AS submit_at,
            p.submit_date_text,
            p.declaration_type,
            p.overdue,
            p.declaration_id
        FROM dbo.karta_ergani_protocol p
        WHERE p.store_id = ?
          AND p.submit_at IS NOT NULL
          AND (p.overdue IS NULL OR p.overdue = 0)
          {linked_filter}
          AND CAST(p.submit_at AS date) >= ?
          AND CAST(p.submit_at AS date) <= ?
    """
    with cursor(commit=False) as cur:
        cur.execute(sql, (int(store_id), start, end))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def _work_log_rows_for_range(
    employer_afm: str,
    branch_aa: str,
    from_iso: str,
    to_iso: str,
) -> list[dict[str, Any]]:
    afm = norm_afm(employer_afm)
    aa = str(branch_aa or "0").strip()[:32] or "0"
    start = str(from_iso).strip()[:10]
    end = str(to_iso).strip()[:10]
    if end < start:
        start, end = end, start
    sql = """
        SELECT
            w.id,
            w.employee_afm,
            w.work_date,
            w.hour_from,
            w.hour_to,
            w.protocol_from,
            w.protocol_to
        FROM dbo.karta_work_log w
        WHERE w.employer_afm = ?
          AND w.branch_aa = ?
          AND TRY_CONVERT(date, w.work_date, 103) >= ?
          AND TRY_CONVERT(date, w.work_date, 103) <= ?
    """
    with cursor(commit=False) as cur:
        cur.execute(sql, (afm, aa, start, end))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def _expand_work_log_slots(
    store_id: int,
    rows: list[dict[str, Any]],
    *,
    skip_filled: bool = False,
) -> list[dict[str, Any]]:
    """hour_from/hour_to → χρονοθέσεις με ημερολογιακή ημέρα υποβολής."""
    slots: list[dict[str, Any]] = []
    for row in rows:
        work_date_iso = ergani_date_to_iso(str(row.get("work_date") or ""))
        if not work_date_iso:
            continue
        try:
            work_day = date.fromisoformat(work_date_iso)
        except ValueError:
            continue
        hf = _time_hm(row.get("hour_from"))
        ht = _time_hm(row.get("hour_to"))
        pf = str(row.get("protocol_from") or "").strip()
        pt = str(row.get("protocol_to") or "").strip()
        emp = str(row.get("employee_afm") or "").strip() or None
        wl_id = int(row["id"]) if row.get("id") is not None else None
        base = {
            "store_id": int(store_id),
            "work_date": work_date_iso,
            "employee_afm": emp,
            "work_log_id": wl_id,
        }
        if hf and not (skip_filled and pf):
            slots.append(
                {
                    **base,
                    "calendar_date": work_date_iso,
                    "time_hm": hf,
                    "f_type": "0",
                }
            )
        if ht and not (skip_filled and pt):
            cal = (
                (work_day + timedelta(days=1)).isoformat()
                if _is_overnight_exit(hf, ht)
                else work_date_iso
            )
            slots.append(
                {
                    **base,
                    "calendar_date": cal,
                    "time_hm": ht,
                    "f_type": "1",
                }
            )
    return slots


def _group_protocols(rows: list[dict[str, Any]]) -> dict[MatchKey, list[dict[str, Any]]]:
    grouped: dict[MatchKey, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        parts = _submit_local_parts(row.get("submit_at"))
        if not parts:
            continue
        cal_date, time_hm = parts
        if not time_hm:
            continue
        key = (int(row["store_id"]), cal_date, time_hm)
        grouped[key].append(row)
    return grouped


def _group_work_log_slots(
    store_id: int,
    rows: list[dict[str, Any]],
    *,
    skip_filled: bool = False,
) -> dict[MatchKey, list[dict[str, Any]]]:
    grouped: dict[MatchKey, list[dict[str, Any]]] = defaultdict(list)
    for slot in _expand_work_log_slots(store_id, rows, skip_filled=skip_filled):
        key = (int(store_id), slot["calendar_date"], slot["time_hm"])
        grouped[key].append(slot)
    return grouped


def _used_protocols_from_work_log(rows: list[dict[str, Any]]) -> set[str]:
    used: set[str] = set()
    for row in rows:
        for col in ("protocol_from", "protocol_to"):
            proto = str(row.get(col) or "").strip()
            if proto:
                used.add(proto)
    return used


def _card_events_for_range(
    employer_afm: str,
    branch_aa: str,
    from_iso: str,
    to_iso: str,
) -> list[dict[str, Any]]:
    afm = norm_afm(employer_afm)
    aa = str(branch_aa or "0").strip()[:32] or "0"
    start = str(from_iso).strip()[:10]
    end = str(to_iso).strip()[:10]
    if end < start:
        start, end = end, start
    try:
        start_ext = (date.fromisoformat(start) - timedelta(days=1)).isoformat()
    except ValueError:
        start_ext = start
    sql = """
        SELECT
            e.id,
            e.declaration_id,
            e.f_afm,
            e.f_type,
            e.f_reference_date,
            e.f_date,
            d.protocol,
            d.submit_date_text
        FROM dbo.karta_card_event e
        INNER JOIN dbo.karta_declaration d ON d.id = e.declaration_id
        WHERE e.f_afm_ergodoti = ?
          AND e.f_aa = ?
          AND d.success = 1
          AND e.f_reference_date >= ?
          AND e.f_reference_date <= ?
          AND e.f_type IN (N'0', N'1')
    """
    with cursor(commit=False) as cur:
        cur.execute(sql, (afm, aa, start_ext, end))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def _own_event_index(
    events: list[dict[str, Any]],
) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    """(employee_afm, work_date_iso, f_type, HH:MM) → card event με πρωτόκολλο."""
    index: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for ev in events:
        emp = norm_afm(ev.get("f_afm") or "")
        wd = str(ev.get("f_reference_date") or "").strip()[:10]
        ft = str(ev.get("f_type") or "").strip()
        hm = _time_hm(ev.get("f_date"))
        if not emp or not wd or ft not in ("0", "1") or not hm:
            continue
        key = (emp, wd, ft, hm)
        proto = str(ev.get("protocol") or "").strip()
        prev = index.get(key)
        if prev is None or (proto and not str(prev.get("protocol") or "").strip()):
            index[key] = ev
    return index


def apply_own_punch_protocols(
    store_id: int,
    employer_afm: str,
    branch_aa: str,
    *,
    from_iso: str,
    to_iso: str,
) -> dict[str, Any]:
    """Δικά μας χτυπήματα → protocol_from/to στην πραγματική (κενό πεδίο μόνο)."""
    wl_rows = _work_log_rows_for_range(employer_afm, branch_aa, from_iso, to_iso)
    events = _own_event_index(
        _card_events_for_range(employer_afm, branch_aa, from_iso, to_iso)
    )
    if not wl_rows or not events:
        return {"work_log_updated": 0, "linked": 0}

    updated = 0
    linked = 0
    with cursor() as cur:
        for row in wl_rows:
            emp = norm_afm(row.get("employee_afm") or "")
            work_iso = ergani_date_to_iso(str(row.get("work_date") or ""))
            wl_id = row.get("id")
            if not emp or not work_iso or wl_id is None:
                continue
            for f_type, hour, col in (
                ("0", _time_hm(row.get("hour_from")), "protocol_from"),
                ("1", _time_hm(row.get("hour_to")), "protocol_to"),
            ):
                if not hour:
                    continue
                if str(row.get(col) or "").strip():
                    continue
                ev = events.get((emp, work_iso, f_type, hour))
                proto = str((ev or {}).get("protocol") or "").strip()
                if not ev or not proto:
                    continue
                cur.execute(
                    f"""
                    UPDATE dbo.karta_work_log
                    SET {col} = ?
                    WHERE id = ?
                      AND ({col} IS NULL OR LTRIM(RTRIM({col})) = N'')
                    """,
                    (proto[:128], int(wl_id)),
                )
                if cur.rowcount <= 0:
                    continue
                updated += 1
                row[col] = proto
                decl_id = ev.get("declaration_id")
                if decl_id is None:
                    continue
                cur.execute(
                    """
                    UPDATE dbo.karta_ergani_protocol
                    SET declaration_id = ?
                    WHERE store_id = ?
                      AND protocol = ?
                      AND declaration_id IS NULL
                    """,
                    (int(decl_id), int(store_id), proto[:128]),
                )
                if cur.rowcount > 0:
                    linked += 1
    return {"work_log_updated": updated, "linked": linked}


def _find_card_event(
    employer_afm: str,
    branch_aa: str,
    *,
    employee_afm: str | None,
    work_date: str,
    time_hm: str,
    f_type: str,
    require_missing_protocol: bool,
) -> tuple[int | None, int | None]:
    if not employee_afm:
        return None, None
    afm = norm_afm(employer_afm)
    aa = str(branch_aa or "0").strip()[:32] or "0"
    protocol_filter = (
        "AND (d.protocol IS NULL OR LTRIM(RTRIM(d.protocol)) = N'')"
        if require_missing_protocol
        else ""
    )
    sql = f"""
        SELECT e.id, e.declaration_id, e.f_date
        FROM dbo.karta_card_event e
        INNER JOIN dbo.karta_declaration d ON d.id = e.declaration_id
        WHERE e.f_afm_ergodoti = ?
          AND e.f_aa = ?
          AND e.f_afm = ?
          AND e.f_reference_date = ?
          AND e.f_type = ?
          AND d.success = 1
          {protocol_filter}
    """
    with cursor(commit=False) as cur:
        cur.execute(
            sql,
            (afm, aa, norm_afm(employee_afm), work_date[:10], f_type),
        )
        for event_id, decl_id, f_date in cur.fetchall():
            if _time_hm(f_date) == time_hm:
                return int(decl_id), int(event_id)
    return None, None


def find_one_to_one_matches(
    store_id: int,
    employer_afm: str,
    branch_aa: str,
    *,
    from_iso: str,
    to_iso: str,
    require_missing_protocol: bool = False,
    require_unlinked_protocol: bool = False,
) -> list[ProtocolDeductionMatch]:
    """Βέβαιες 1-1: μοναδική κενή ώρα πραγματικής ↔ μοναδικό αχρησιμοποίητο πρωτόκολλο."""
    wl_rows = _work_log_rows_for_range(employer_afm, branch_aa, from_iso, to_iso)
    used = _used_protocols_from_work_log(wl_rows)
    proto_rows = [
        p
        for p in _protocol_rows_for_range(
            store_id, from_iso, to_iso, require_unlinked=require_unlinked_protocol
        )
        if str(p.get("protocol") or "").strip() not in used
    ]
    protocols = _group_protocols(proto_rows)
    work_slots = _group_work_log_slots(store_id, wl_rows, skip_filled=True)
    matches: list[ProtocolDeductionMatch] = []
    for key, proto_list in protocols.items():
        if len(proto_list) != 1:
            continue
        slot_list = work_slots.get(key) or []
        if len(slot_list) != 1:
            continue
        p = proto_list[0]
        s = slot_list[0]
        decl_id, event_id = _find_card_event(
            employer_afm,
            branch_aa,
            employee_afm=s.get("employee_afm"),
            work_date=str(s.get("work_date") or ""),
            time_hm=key[2],
            f_type=str(s.get("f_type") or ""),
            require_missing_protocol=require_missing_protocol,
        )
        if require_missing_protocol and decl_id is None:
            continue
        matches.append(
            ProtocolDeductionMatch(
                store_id=int(store_id),
                calendar_date=key[1],
                work_date=str(s.get("work_date") or key[1]),
                time_hm=key[2],
                f_type=str(s.get("f_type") or ""),
                protocol_id=int(p["id"]),
                protocol=str(p.get("protocol") or "").strip(),
                submit_date_text=(
                    str(p.get("submit_date_text") or "").strip() or None
                ),
                employee_afm=s.get("employee_afm"),
                work_log_id=s.get("work_log_id"),
                declaration_id=decl_id,
                card_event_id=event_id,
            )
        )
    return matches


def find_work_log_protocol_matches(
    store_id: int,
    employer_afm: str,
    branch_aa: str,
    *,
    from_iso: str,
    to_iso: str,
    require_unlinked_protocol: bool = False,
) -> list[ProtocolDeductionMatch]:
    """1-1 αντιστοιχίσεις πραγματικής ↔ πρωτόκολλου (χωρίς απαίτηση card_event)."""
    return find_one_to_one_matches(
        store_id,
        employer_afm,
        branch_aa,
        from_iso=from_iso,
        to_iso=to_iso,
        require_missing_protocol=False,
        require_unlinked_protocol=require_unlinked_protocol,
    )


def apply_protocol_sync(
    store_id: int,
    employer_afm: str,
    branch_aa: str,
    *,
    from_iso: str,
    to_iso: str,
) -> dict[str, Any]:
    """Δικά μας πρωτόκολλα στην πραγματική, μετά 1-1 στα υπόλοιπα κενά."""
    own = apply_own_punch_protocols(
        store_id,
        employer_afm,
        branch_aa,
        from_iso=from_iso,
        to_iso=to_iso,
    )
    own_updated = int(own.get("work_log_updated") or 0)
    matches = find_one_to_one_matches(
        store_id,
        employer_afm,
        branch_aa,
        from_iso=from_iso,
        to_iso=to_iso,
        require_missing_protocol=False,
        require_unlinked_protocol=False,
    )
    if not matches and own_updated <= 0:
        return {
            "success": True,
            "matched": 0,
            "work_log_updated": 0,
            "own_updated": 0,
            "declaration_updated": 0,
            "updated": 0,
            "detail": "Καμία 1-1 αντιστοίχιση",
        }

    work_log_updated = 0
    declaration_updated = 0
    with cursor() as cur:
        for m in matches:
            if not m.protocol:
                continue
            proto = m.protocol[:128]

            if m.work_log_id is not None:
                col = "protocol_from" if m.f_type == "0" else "protocol_to"
                cur.execute(
                    f"""
                    UPDATE dbo.karta_work_log
                    SET {col} = ?
                    WHERE id = ?
                      AND ({col} IS NULL OR LTRIM(RTRIM({col})) = N'')
                    """,
                    (proto, int(m.work_log_id)),
                )
                if cur.rowcount > 0:
                    work_log_updated += 1

            if m.declaration_id is None:
                continue
            cur.execute(
                """
                UPDATE dbo.karta_declaration
                SET protocol = ?,
                    submit_date_text = COALESCE(?, submit_date_text)
                WHERE id = ?
                  AND (protocol IS NULL OR LTRIM(RTRIM(protocol)) = N'')
                """,
                (proto, m.submit_date_text, m.declaration_id),
            )
            if cur.rowcount <= 0:
                continue
            declaration_updated += 1
            cur.execute(
                """
                UPDATE dbo.karta_ergani_protocol
                SET declaration_id = ?
                WHERE id = ?
                  AND declaration_id IS NULL
                """,
                (m.declaration_id, m.protocol_id),
            )

    total_wl = own_updated + work_log_updated
    total = total_wl + declaration_updated
    detail = (
        f"δικά μας {own_updated}, 1-1 πραγματική {work_log_updated}, "
        f"δηλώσεις {declaration_updated} ({len(matches)} θέσεις 1-1)"
    )
    return {
        "success": True,
        "matched": len(matches),
        "work_log_updated": total_wl,
        "own_updated": own_updated,
        "one_to_one_updated": work_log_updated,
        "declaration_updated": declaration_updated,
        "updated": total,
        "detail": detail,
    }


def apply_one_to_one_matches(
    store_id: int,
    employer_afm: str,
    branch_aa: str,
    *,
    from_iso: str,
    to_iso: str,
) -> dict[str, Any]:
    """Συμβατότητα — καλεί apply_protocol_sync."""
    return apply_protocol_sync(
        store_id,
        employer_afm,
        branch_aa,
        from_iso=from_iso,
        to_iso=to_iso,
    )


def apply_all_stores_one_to_one_matches(
    *,
    from_iso: str | None = None,
    to_iso: str | None = None,
    store_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Μαζική εφαρμογή 1-1 αντιστοιχίσεων για όλα τα καταστήματα."""
    from app.repo_ergani_protocol import earliest_store_activity_date
    from app.repo_store import list_store_configs

    today = date.today().isoformat()
    end = (to_iso or today)[:10]
    stores = list_store_configs()
    if store_ids:
        wanted = {int(x) for x in store_ids}
        stores = [s for s in stores if int(s["id"]) in wanted]

    total_updated = 0
    total_matched = 0
    rows: list[dict[str, Any]] = []
    range_from = (from_iso or "").strip()[:10] if from_iso else None
    for cfg in stores:
        sid = int(cfg["id"])
        afm = str(cfg.get("employer_afm") or "")
        aa = str(cfg.get("branch_aa") or "0")
        start = (from_iso or "").strip()[:10] if from_iso else None
        if not start:
            earliest = earliest_store_activity_date(sid, afm, aa)
            start = earliest.isoformat() if earliest else end
        if range_from is None or start < range_from:
            range_from = start
        result = apply_protocol_sync(sid, afm, aa, from_iso=start, to_iso=end)
        total_updated += int(result.get("updated") or 0)
        total_matched += int(result.get("matched") or 0)
        wl_upd = int(result.get("work_log_updated") or 0)
        if wl_upd > 0 or int(result.get("updated") or 0) > 0 or int(result.get("matched") or 0) > 0:
            rows.append(
                {
                    "store_id": sid,
                    "store_name": cfg.get("name"),
                    "matched": result.get("matched"),
                    "updated": result.get("updated"),
                    "work_log_updated": wl_upd,
                    "declaration_updated": result.get("declaration_updated"),
                    "detail": result.get("detail"),
                }
            )

    return {
        "from_iso": range_from or end,
        "to_iso": end,
        "matched": total_matched,
        "updated": total_updated,
        "stores": rows,
    }


def analyze_one_to_one_matches(
    *,
    from_iso: str | None = None,
    to_iso: str | None = None,
) -> dict[str, Any]:
    """Στατιστικά 1-1: πραγματική (work_log) ↔ πρωτόκολλα Ergani."""
    from app.repo_store import list_store_configs

    today = date.today().isoformat()
    start = (from_iso or "1900-01-01")[:10]
    end = (to_iso or today)[:10]

    total_work_log = 0
    total_applicable = 0
    per_store: list[dict[str, Any]] = []
    for cfg in list_store_configs():
        sid = int(cfg["id"])
        afm = str(cfg.get("employer_afm") or "")
        aa = str(cfg.get("branch_aa") or "0")
        wl_matches = find_work_log_protocol_matches(
            sid, afm, aa, from_iso=start, to_iso=end
        )
        card_matches = find_one_to_one_matches(
            sid,
            afm,
            aa,
            from_iso=start,
            to_iso=end,
            require_missing_protocol=True,
            require_unlinked_protocol=True,
        )
        total_work_log += len(wl_matches)
        total_applicable += len(card_matches)
        if wl_matches:
            per_store.append(
                {
                    "store_id": sid,
                    "store_name": cfg.get("name"),
                    "work_log_matches": len(wl_matches),
                    "card_updates": len(card_matches),
                }
            )

    return {
        "from_iso": start,
        "to_iso": end,
        "total_work_log_matches": total_work_log,
        "total_card_updates": total_applicable,
        "stores_with_matches": len(per_store),
        "per_store": sorted(
            per_store, key=lambda x: -int(x.get("work_log_matches") or 0)
        ),
    }
