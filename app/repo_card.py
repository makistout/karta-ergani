"""Κτυπήματα κάρτας και δηλώσεις — pyodbc."""

from __future__ import annotations

import json
from typing import Any

import pyodbc

from app.db import connection, cursor
from app.payload_parse import extract_employer_afm_from_request, iter_card_blocks
from app.repo_entities import (
    upsert_employee,
    upsert_employer,
    upsert_employment,
    upsert_parartima,
)
from app.row_util import rows_to_dicts
from app.work_card_payload import norm_afm


def _field(d: dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if k in d:
            return d[k]
    return None


def parse_ergani_submit_response(response_body: str | None) -> tuple[str | None, str | None, str | None]:
    """Εξαγωγή id, protocol, submitDate από απάντηση Ergani (πίνακας με ένα αντικείμενο)."""
    if not response_body:
        return None, None, None
    try:
        parsed = json.loads(response_body)
    except json.JSONDecodeError:
        return None, None, None
    item: dict[str, Any] | None = None
    if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
        item = parsed[0]
    elif isinstance(parsed, dict):
        item = parsed
    if not item:
        return None, None, None
    ergani_id = item.get("id")
    return (
        str(ergani_id).strip() if ergani_id is not None else None,
        str(item.get("protocol") or "").strip() or None,
        str(item.get("submitDate") or "").strip() or None,
    )


def insert_declaration(
    cur: pyodbc.Cursor,
    submission_code: str,
    employer_afm: str | None,
    protocol: str | None,
    submit_date_text: str | None,
    ergani_submission_id: str | None,
    http_status: int,
    success: bool,
    request_json: str,
    response_json: str | None,
    *,
    client_ip: str | None = None,
    client_device: str | None = None,
) -> int:
    cur.execute(
        """
        INSERT INTO dbo.karta_declaration (
            submission_code, direction, employer_afm, protocol, submit_date_text,
            ergani_submission_id, http_status, success, request_json, response_json,
            client_ip, client_device
        )
        OUTPUT INSERTED.id
        VALUES (?, N'submit', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            submission_code,
            employer_afm,
            protocol,
            submit_date_text,
            ergani_submission_id,
            http_status,
            1 if success else 0,
            request_json,
            response_json,
            (client_ip or "").strip()[:45] or None,
            (client_device or "").strip()[:2000] or None,
        ),
    )
    row = cur.fetchone()
    return int(row[0])


def insert_card_event(
    cur: pyodbc.Cursor,
    declaration_id: int,
    employee_id: int | None,
    card: dict[str, Any],
    detail: dict[str, Any],
) -> None:
    cur.execute(
        """
        INSERT INTO dbo.karta_card_event (
            declaration_id, employee_id, f_afm_ergodoti, f_aa, f_comments,
            f_afm, f_eponymo, f_onoma, f_type, f_reference_date, f_date, f_aitiologia
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            declaration_id,
            employee_id,
            norm_afm(_field(card, "f_afm_ergodoti", "F_afm_ergodoti")),
            str(_field(card, "f_aa", "F_aa") or "")[:32] or None,
            str(_field(card, "f_comments", "F_comments") or "") or None,
            norm_afm(_field(detail, "f_afm", "F_afm")),
            str(_field(detail, "f_eponymo", "F_eponymo") or "")[:200] or None,
            str(_field(detail, "f_onoma", "F_onoma") or "")[:200] or None,
            str(_field(detail, "f_type", "F_type") or "")[:16] or None,
            str(_field(detail, "f_reference_date", "F_reference_date") or "")[:32] or None,
            str(_field(detail, "f_date", "F_date") or "")[:64] or None,
            str(_field(detail, "f_aitiologia", "F_aitiologia") or "") or None,
        ),
    )


def persist_wrk_card_submit(
    submission_code: str,
    http_status: int,
    success: bool,
    request_dict: dict[str, Any],
    response_body: str | None,
    protocol: str | None,
    submit_date_text: str | None,
    ergani_submission_id: str | None = None,
    *,
    client_ip: str | None = None,
    client_device: str | None = None,
) -> None:
    req_str = json.dumps(request_dict, ensure_ascii=False)
    emp_afm = extract_employer_afm_from_request(request_dict)
    parsed_id, parsed_proto, parsed_date = parse_ergani_submit_response(response_body)
    if not protocol:
        protocol = parsed_proto
    if not submit_date_text:
        submit_date_text = parsed_date
    if not ergani_submission_id:
        ergani_submission_id = parsed_id
    with connection() as conn:
        cur = conn.cursor()
        decl_id = insert_declaration(
            cur,
            submission_code,
            emp_afm,
            protocol,
            submit_date_text,
            ergani_submission_id,
            http_status,
            success,
            req_str,
            response_body,
            client_ip=client_ip,
            client_device=client_device,
        )
        if not success:
            return
        for card, lines in iter_card_blocks(request_dict):
            erg_afm = norm_afm(card.get("f_afm_ergodoti") or card.get("F_afm_ergodoti"))
            employer_id = upsert_employer(cur, erg_afm)
            if not employer_id:
                continue
            part_id = upsert_parartima(
                cur, employer_id, str(card.get("f_aa") or card.get("F_aa") or "0")
            )
            for d in lines:
                eafm = norm_afm(d.get("f_afm") or d.get("F_afm"))
                emp_id = upsert_employee(
                    cur,
                    eafm,
                    str(d.get("f_eponymo") or d.get("F_eponymo") or "") or None,
                    str(d.get("f_onoma") or d.get("F_onoma") or "") or None,
                )
                if emp_id:
                    upsert_employment(cur, employer_id, emp_id, part_id)
                insert_card_event(cur, decl_id, emp_id, card, d)


def card_event_exists(employee_afm: str, reference_date: str, f_type: str) -> bool:
    sql = """
        SELECT COUNT(*) FROM dbo.karta_card_event
        WHERE f_afm = ? AND f_reference_date = ? AND f_type = ?
    """
    with cursor(commit=False) as cur:
        cur.execute(
            sql,
            (str(employee_afm).strip(), str(reference_date).strip(), str(f_type).strip()),
        )
        row = cur.fetchone()
        return bool(row and row[0] > 0)


def list_card_events_for_store_date(
    employer_afm: str,
    branch_aa: str,
    reference_date_iso: str,
    *,
    limit: int = 2000,
) -> list[dict[str, Any]]:
    """Δηλώσεις κάρτας (WRKCardSE) για εργοδότη/παράρτημα και ημέρα (ISO yyyy-mm-dd)."""
    erg = norm_afm(employer_afm)
    aa = str(branch_aa or "0").strip()[:32] or "0"
    ref = str(reference_date_iso).strip()[:10]
    lim = max(1, min(int(limit), 5000))
    sql = f"""
        SELECT TOP ({lim})
            e.id, e.f_afm, e.f_eponymo, e.f_onoma, e.f_type,
            e.f_reference_date, e.f_date, e.f_aitiologia,
            emp.flex_arrival_minutes,
            d.success, d.protocol
        FROM dbo.karta_card_event e
        INNER JOIN dbo.karta_declaration d ON d.id = e.declaration_id
        LEFT JOIN dbo.karta_employee emp ON emp.afm = e.f_afm
        WHERE e.f_afm_ergodoti = ? AND e.f_aa = ?
          AND e.f_reference_date = ?
          AND d.success = 1
        ORDER BY e.id DESC
    """
    with cursor(commit=False) as cur:
        cur.execute(sql, (erg, aa, ref))
        return rows_to_dicts(cur)


def list_card_events_for_store_range(
    employer_afm: str,
    branch_aa: str,
    from_iso: str,
    to_iso: str,
    *,
    limit: int = 2000,
) -> list[dict[str, Any]]:
    """Δηλώσεις κάρτας για διάστημα ημερών (ISO yyyy-mm-dd)."""
    erg = norm_afm(employer_afm)
    aa = str(branch_aa or "0").strip()[:32] or "0"
    start = str(from_iso).strip()[:10]
    end = str(to_iso).strip()[:10]
    if end < start:
        start, end = end, start
    lim = max(1, min(int(limit), 5000))
    sql = f"""
        SELECT TOP ({lim})
            e.id, e.f_afm, e.f_eponymo, e.f_onoma, e.f_type,
            e.f_reference_date, e.f_date, e.f_aitiologia,
            emp.flex_arrival_minutes,
            d.success, d.protocol, d.submit_date_text, d.ergani_submission_id,
            CAST(d.created_at AS datetime2) AS declaration_created_at
        FROM dbo.karta_card_event e
        INNER JOIN dbo.karta_declaration d ON d.id = e.declaration_id
        LEFT JOIN dbo.karta_employee emp ON emp.afm = e.f_afm
        WHERE e.f_afm_ergodoti = ? AND e.f_aa = ?
          AND e.f_reference_date >= ? AND e.f_reference_date <= ?
          AND d.success = 1
        ORDER BY e.f_reference_date DESC, e.id DESC
    """
    with cursor(commit=False) as cur:
        cur.execute(sql, (erg, aa, start, end))
        return rows_to_dicts(cur)


def list_card_events(limit: int = 100) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit), 500))
    sql = f"""
        SELECT TOP ({lim})
            e.id, e.declaration_id, e.employee_id,
            e.f_afm_ergodoti, e.f_aa, e.f_comments,
            e.f_afm, e.f_eponymo, e.f_onoma, e.f_type,
            e.f_reference_date, e.f_date, e.f_aitiologia,
            d.protocol, d.submit_date_text, d.ergani_submission_id,
            d.http_status, d.success, d.response_json
        FROM dbo.karta_card_event e
        INNER JOIN dbo.karta_declaration d ON d.id = e.declaration_id
        ORDER BY e.id DESC
    """
    with cursor(commit=False) as cur:
        cur.execute(sql)
        return rows_to_dicts(cur)
