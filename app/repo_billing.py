"""Τιμολόγηση πελατών. Νέοι πίνακες μόνο· δεν γράφει σε karta_store_config."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from app.db import cursor
from app.row_util import rows_to_dicts

DEFAULT_VAT = Decimal("24.00")
DOC_TYPES = ("APY", "TPY", "CREDIT")
DOC_TYPE_LABELS = {
    "APY": "ΑΠΥ",
    "TPY": "ΤΠΥ",
    "CREDIT": "Πιστωτικό",
}

_SQL_PATH = Path(__file__).resolve().parents[1] / "sql" / "alter_add_billing.sql"
_SQL_OXYGEN_PATH = Path(__file__).resolve().parents[1] / "sql" / "alter_add_billing_invoice_oxygen.sql"
_SQL_REP_PATH = Path(__file__).resolve().parents[1] / "sql" / "alter_add_billing_customer_representative.sql"
_tables_ready = False


def money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def vat_amount(net: Decimal, rate: Decimal) -> Decimal:
    return money(net * rate / Decimal("100"))


def normalize_afm(raw: Any) -> str:
    return "".join(ch for ch in str(raw or "") if ch.isdigit())


def afm_is_valid(raw: Any) -> bool:
    digits = normalize_afm(raw)
    if len(digits) != 9 or digits == "000000000":
        return False
    total = sum(int(digits[i]) * (2 ** (8 - i)) for i in range(8))
    return total % 11 % 10 == int(digits[8])


def tables_available() -> bool:
    try:
        with cursor(commit=False) as cur:
            cur.execute(
                """
                SELECT 1 FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = N'dbo' AND TABLE_NAME = N'karta_billing_customer'
                """
            )
            return cur.fetchone() is not None
    except Exception:
        return False


def ensure_tables() -> None:
    global _tables_ready
    if _tables_ready and tables_available():
        return
    raw = _SQL_PATH.read_text(encoding="utf-8")
    extra = _SQL_OXYGEN_PATH.read_text(encoding="utf-8") if _SQL_OXYGEN_PATH.exists() else ""
    extra_rep = _SQL_REP_PATH.read_text(encoding="utf-8") if _SQL_REP_PATH.exists() else ""
    batches = [part.strip() for part in (raw + "\nGO\n" + extra + "\nGO\n" + extra_rep).split("GO") if part.strip()]
    with cursor() as cur:
        for batch in batches:
            cur.execute(batch)
    _tables_ready = True


def _json_row(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        if hasattr(value, "isoformat"):
            out[key] = value.isoformat()
        elif isinstance(value, Decimal):
            out[key] = str(value)
        else:
            out[key] = value
    return out


def list_customers() -> list[dict[str, Any]]:
    ensure_tables()
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT
              c.id, c.eponimia, c.epaggelma, c.address, c.afm, c.doy,
              c.email, c.phone, c.representative, c.notes, CAST(c.is_active AS int) AS is_active,
              CONVERT(varchar(33), c.created_at, 126) AS created_at,
              CONVERT(varchar(33), c.updated_at, 126) AS updated_at,
              (
                SELECT COUNT(*) FROM dbo.karta_billing_customer_store s
                WHERE s.customer_id = c.id
              ) AS store_count,
              (
                SELECT COUNT(*) FROM dbo.karta_billing_subscription sub
                WHERE sub.customer_id = c.id AND sub.status = N'active'
              ) AS active_subscriptions
            FROM dbo.karta_billing_customer c
            ORDER BY c.eponimia, c.id
            """
        )
        return [_json_row(row) for row in rows_to_dicts(cur)]


def get_customer(customer_id: int) -> dict[str, Any] | None:
    ensure_tables()
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT
              c.id, c.eponimia, c.epaggelma, c.address, c.afm, c.doy,
              c.email, c.phone, c.representative, c.notes, CAST(c.is_active AS int) AS is_active,
              CONVERT(varchar(33), c.created_at, 126) AS created_at,
              CONVERT(varchar(33), c.updated_at, 126) AS updated_at
            FROM dbo.karta_billing_customer c
            WHERE c.id = ?
            """,
            (int(customer_id),),
        )
        rows = rows_to_dicts(cur)
    if not rows:
        return None
    customer = _json_row(rows[0])
    customer["stores"] = list_customer_stores(int(customer_id))
    customer["subscriptions"] = list_subscriptions(int(customer_id))
    customer["documents"] = list_documents(int(customer_id))
    return customer


def _clean_customer(data: dict[str, Any]) -> dict[str, Any]:
    eponimia = str(data.get("eponimia") or "").strip()
    afm = normalize_afm(data.get("afm"))
    if not eponimia:
        raise ValueError("Η επωνυμία είναι υποχρεωτική.")
    if not afm_is_valid(afm):
        raise ValueError("Μη έγκυρο ΑΦΜ.")
    return {
        "eponimia": eponimia[:200],
        "epaggelma": str(data.get("epaggelma") or "").strip()[:200] or None,
        "address": str(data.get("address") or "").strip()[:400] or None,
        "afm": afm,
        "doy": str(data.get("doy") or "").strip()[:120] or None,
        "email": str(data.get("email") or "").strip()[:200] or None,
        "phone": str(data.get("phone") or "").strip()[:40] or None,
        "representative": str(data.get("representative") or "").strip()[:200] or None,
        "notes": str(data.get("notes") or "").strip()[:1000] or None,
        "is_active": 0 if str(data.get("is_active")).lower() in {"0", "false"} else 1,
    }


def create_customer(data: dict[str, Any]) -> dict[str, Any]:
    ensure_tables()
    payload = _clean_customer(data)
    with cursor() as cur:
        cur.execute(
            """
            INSERT INTO dbo.karta_billing_customer
              (eponimia, epaggelma, address, afm, doy, email, phone, representative, notes, is_active)
            OUTPUT INSERTED.id
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["eponimia"],
                payload["epaggelma"],
                payload["address"],
                payload["afm"],
                payload["doy"],
                payload["email"],
                payload["phone"],
                payload["representative"],
                payload["notes"],
                payload["is_active"],
            ),
        )
        row = cur.fetchone()
    return get_customer(int(row[0])) or {}


def update_customer(customer_id: int, data: dict[str, Any]) -> dict[str, Any]:
    ensure_tables()
    if not get_customer(int(customer_id)):
        raise KeyError("Ο πελάτης δεν βρέθηκε.")
    payload = _clean_customer(data)
    with cursor() as cur:
        cur.execute(
            """
            UPDATE dbo.karta_billing_customer
            SET eponimia=?, epaggelma=?, address=?, afm=?, doy=?,
                email=?, phone=?, representative=?, notes=?, is_active=?,
                updated_at=SYSDATETIMEOFFSET()
            WHERE id=?
            """,
            (
                payload["eponimia"],
                payload["epaggelma"],
                payload["address"],
                payload["afm"],
                payload["doy"],
                payload["email"],
                payload["phone"],
                payload["representative"],
                payload["notes"],
                payload["is_active"],
                int(customer_id),
            ),
        )
    return get_customer(int(customer_id)) or {}


def deactivate_customer(customer_id: int) -> None:
    ensure_tables()
    with cursor() as cur:
        cur.execute(
            """
            UPDATE dbo.karta_billing_customer
            SET is_active=0, updated_at=SYSDATETIMEOFFSET()
            WHERE id=?
            """,
            (int(customer_id),),
        )


def list_customer_stores(customer_id: int) -> list[dict[str, Any]]:
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT
              cs.store_id,
              s.name AS store_name,
              s.employer_afm,
              s.branch_aa
            FROM dbo.karta_billing_customer_store cs
            INNER JOIN dbo.karta_store_config s ON s.id = cs.store_id
            WHERE cs.customer_id = ?
            ORDER BY s.name, s.id
            """,
            (int(customer_id),),
        )
        return [_json_row(row) for row in rows_to_dicts(cur)]


def list_store_assignments() -> list[dict[str, Any]]:
    ensure_tables()
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT
              s.id AS store_id,
              s.name AS store_name,
              s.employer_afm,
              s.branch_aa,
              cs.customer_id,
              c.eponimia AS customer_name
            FROM dbo.karta_store_config s
            LEFT JOIN dbo.karta_billing_customer_store cs ON cs.store_id = s.id
            LEFT JOIN dbo.karta_billing_customer c ON c.id = cs.customer_id
            ORDER BY s.name, s.id
            """
        )
        return [_json_row(row) for row in rows_to_dicts(cur)]


def set_customer_stores(customer_id: int, store_ids: list[int]) -> list[dict[str, Any]]:
    ensure_tables()
    if get_customer(int(customer_id)) is None:
        raise KeyError("Ο πελάτης δεν βρέθηκε.")
    wanted = sorted({int(sid) for sid in store_ids if int(sid) > 0})
    with cursor() as cur:
        if wanted:
            placeholders = ",".join("?" * len(wanted))
            cur.execute(
                f"SELECT id FROM dbo.karta_store_config WHERE id IN ({placeholders})",
                wanted,
            )
            found = {int(row[0]) for row in cur.fetchall()}
            missing = [sid for sid in wanted if sid not in found]
            if missing:
                raise ValueError(f"Άγνωστα καταστήματα: {', '.join(map(str, missing))}")
            cur.execute(
                f"""
                SELECT store_id, customer_id
                FROM dbo.karta_billing_customer_store
                WHERE store_id IN ({placeholders}) AND customer_id <> ?
                """,
                (*wanted, int(customer_id)),
            )
            taken = cur.fetchall()
            if taken:
                raise ValueError("Το κατάστημα ανήκει ήδη σε άλλον πελάτη.")
        cur.execute(
            "DELETE FROM dbo.karta_billing_customer_store WHERE customer_id=?",
            (int(customer_id),),
        )
        for store_id in wanted:
            cur.execute(
                """
                INSERT INTO dbo.karta_billing_customer_store (customer_id, store_id)
                VALUES (?, ?)
                """,
                (int(customer_id), store_id),
            )
    return list_customer_stores(int(customer_id))


def list_plans(*, active_only: bool = True) -> list[dict[str, Any]]:
    ensure_tables()
    sql = """
        SELECT id, code, name, months,
               CAST(includes_erganios AS int) AS includes_erganios,
               CAST(includes_apologistic AS int) AS includes_apologistic,
               CAST(includes_ai_agent AS int) AS includes_ai_agent,
               amount_net, vat_rate, CAST(is_active AS int) AS is_active
        FROM dbo.karta_billing_plan
    """
    if active_only:
        sql += " WHERE is_active = 1"
    sql += " ORDER BY months ASC, amount_net ASC, name"
    with cursor(commit=False) as cur:
        cur.execute(sql)
        return [_json_row(row) for row in rows_to_dicts(cur)]


def list_subscriptions(customer_id: int) -> list[dict[str, Any]]:
    ensure_tables()
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT
              sub.id, sub.customer_id, sub.plan_id, p.name AS plan_name, p.code AS plan_code,
              CONVERT(varchar(10), sub.starts_on, 23) AS starts_on,
              CONVERT(varchar(10), sub.ends_on, 23) AS ends_on,
              sub.status, sub.amount_net, sub.vat_rate, sub.notes, sub.document_id
            FROM dbo.karta_billing_subscription sub
            INNER JOIN dbo.karta_billing_plan p ON p.id = sub.plan_id
            WHERE sub.customer_id = ?
            ORDER BY sub.starts_on DESC, sub.id DESC
            """,
            (int(customer_id),),
        )
        rows = [_json_row(row) for row in rows_to_dicts(cur)]
    for row in rows:
        row["billed"] = row.get("document_id") not in (None, "")
    return rows


def _parse_date(raw: Any, field: str) -> date:
    text = str(raw or "").strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"Μη έγκυρη ημερομηνία {field}.") from exc


def _int_ids(raw: Any) -> list[int]:
    out: list[int] = []
    for item in raw or []:
        try:
            val = int(item)
        except (TypeError, ValueError):
            continue
        if val > 0:
            out.append(val)
    return out


def plan_issue_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    raw_plans = data.get("plans")
    if isinstance(raw_plans, list):
        for item in raw_plans:
            if not isinstance(item, dict):
                continue
            try:
                plan_id = int(item.get("plan_id") or 0)
            except (TypeError, ValueError):
                continue
            if plan_id <= 0:
                continue
            row: dict[str, Any] = {"plan_id": plan_id}
            if item.get("starts_on"):
                row["starts_on"] = item["starts_on"]
            elif data.get("starts_on"):
                row["starts_on"] = data["starts_on"]
            if item.get("amount_net") not in (None, ""):
                row["amount_net"] = item["amount_net"]
            items.append(row)
    if items:
        return items
    starts = data.get("starts_on")
    for plan_id in _int_ids(data.get("plan_ids")):
        row = {"plan_id": plan_id}
        if starts:
            row["starts_on"] = starts
        items.append(row)
    return items


def _subscription_draft(data: dict[str, Any], plans: dict[int, dict[str, Any]]) -> dict[str, Any]:
    plan_id = int(data.get("plan_id") or 0)
    plan = plans.get(plan_id)
    if not plan:
        raise ValueError("Άγνωστο πακέτο συνδρομής.")
    starts = _parse_date(data.get("starts_on") or date.today().isoformat(), "έναρξης")
    months = int(plan["months"])
    ends = starts + timedelta(days=30 * months) - timedelta(days=1)
    if data.get("ends_on"):
        ends = _parse_date(data.get("ends_on"), "λήξης")
    amount = money(data.get("amount_net") if data.get("amount_net") not in (None, "") else plan["amount_net"])
    rate = money(data.get("vat_rate") if data.get("vat_rate") not in (None, "") else plan["vat_rate"])
    return {
        "plan_id": plan_id,
        "plan_name": plan["name"],
        "plan_code": plan.get("code") or "SUB",
        "starts_on": starts.isoformat(),
        "ends_on": ends.isoformat(),
        "starts": starts,
        "ends": ends,
        "amount_net": amount,
        "vat_rate": rate,
        "notes": str(data.get("notes") or "").strip()[:400] or None,
    }


def add_subscription(customer_id: int, data: dict[str, Any]) -> dict[str, Any]:
    ensure_tables()
    if get_customer(int(customer_id)) is None:
        raise KeyError("Ο πελάτης δεν βρέθηκε.")
    plans = {int(p["id"]): p for p in list_plans(active_only=False)}
    draft = _subscription_draft(data, plans)
    with cursor() as cur:
        cur.execute(
            """
            INSERT INTO dbo.karta_billing_subscription
              (customer_id, plan_id, starts_on, ends_on, status, amount_net, vat_rate, notes)
            OUTPUT INSERTED.id
            VALUES (?, ?, ?, ?, N'active', ?, ?, ?)
            """,
            (
                int(customer_id),
                draft["plan_id"],
                draft["starts"],
                draft["ends"],
                draft["amount_net"],
                draft["vat_rate"],
                draft["notes"],
            ),
        )
        sub_id = int(cur.fetchone()[0])
    return next(item for item in list_subscriptions(int(customer_id)) if int(item["id"]) == sub_id)


def list_all_subscriptions() -> list[dict[str, Any]]:
    ensure_tables()
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT
              sub.id, sub.customer_id, c.eponimia AS customer_name, c.afm,
              sub.plan_id, p.name AS plan_name, p.code AS plan_code,
              CONVERT(varchar(10), sub.starts_on, 23) AS starts_on,
              CONVERT(varchar(10), sub.ends_on, 23) AS ends_on,
              sub.status, sub.amount_net, sub.vat_rate, sub.notes, sub.document_id
            FROM dbo.karta_billing_subscription sub
            INNER JOIN dbo.karta_billing_customer c ON c.id = sub.customer_id
            INNER JOIN dbo.karta_billing_plan p ON p.id = sub.plan_id
            ORDER BY sub.starts_on DESC, sub.id DESC
            """
        )
        rows = [_json_row(row) for row in rows_to_dicts(cur)]
    for row in rows:
        row["billed"] = row.get("document_id") not in (None, "")
    return rows


def unbilled_subscriptions(customer_id: int) -> list[dict[str, Any]]:
    return [
        row
        for row in list_subscriptions(int(customer_id))
        if row.get("status") == "active" and row.get("document_id") in (None, "")
    ]


def normalize_plan_name(name: Any) -> str:
    return " ".join(str(name or "").split()).casefold()


def _plan_name_taken(name: str, *, exclude_id: int | None = None) -> bool:
    target = normalize_plan_name(name)
    if not target:
        return False
    for plan in list_plans(active_only=False):
        if exclude_id is not None and int(plan["id"]) == int(exclude_id):
            continue
        if normalize_plan_name(plan.get("name")) == target:
            return True
    return False


def _unique_plan_name(base: str) -> str:
    candidate = str(base or "").strip()[:200] or "Πακέτο"
    if not _plan_name_taken(candidate):
        return candidate
    n = 2
    while True:
        suffix = f" ({n})"
        cand = (candidate[: 200 - len(suffix)] + suffix)
        if not _plan_name_taken(cand):
            return cand
        n += 1


def _unique_plan_code(base: str) -> str:
    codes = {str(plan.get("code") or "").casefold() for plan in list_plans(active_only=False)}
    candidate = str(base or "plan").strip()[:64] or "plan"
    if candidate.casefold() not in codes:
        return candidate
    n = 2
    while True:
        suffix = f"_{n}"
        cand = (candidate[: 64 - len(suffix)] + suffix)
        if cand.casefold() not in codes:
            return cand
        n += 1


def update_plan(plan_id: int, data: dict[str, Any]) -> dict[str, Any]:
    ensure_tables()
    name = str(data.get("name") or "").strip()[:200]
    amount = money(data.get("amount_net"))
    rate = money(data.get("vat_rate") if data.get("vat_rate") not in (None, "") else DEFAULT_VAT)
    active = 0 if str(data.get("is_active")).lower() in {"0", "false"} else 1
    if not name:
        raise ValueError("Το όνομα πακέτου είναι υποχρεωτικό.")
    if _plan_name_taken(name, exclude_id=int(plan_id)):
        raise ValueError("Υπάρχει ήδη πακέτο με το ίδιο όνομα.")
    with cursor() as cur:
        cur.execute(
            """
            UPDATE dbo.karta_billing_plan
            SET name=?, amount_net=?, vat_rate=?, is_active=?
            WHERE id=?
            """,
            (name, amount, rate, active, int(plan_id)),
        )
    plans = {int(p["id"]): p for p in list_plans(active_only=False)}
    if int(plan_id) not in plans:
        raise KeyError("Το πακέτο δεν βρέθηκε.")
    return plans[int(plan_id)]


def duplicate_plan(plan_id: int) -> dict[str, Any]:
    ensure_tables()
    plans = {int(p["id"]): p for p in list_plans(active_only=False)}
    src = plans.get(int(plan_id))
    if not src:
        raise KeyError("Το πακέτο δεν βρέθηκε.")
    name = _unique_plan_name(f"{src.get('name') or 'Πακέτο'} αντίγραφο")
    code = _unique_plan_code(f"{src.get('code') or 'plan'}_copy")
    with cursor() as cur:
        cur.execute(
            """
            INSERT INTO dbo.karta_billing_plan
              (code, name, months, includes_erganios, includes_apologistic, includes_ai_agent,
               amount_net, vat_rate, is_active)
            OUTPUT INSERTED.id
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                code,
                name,
                int(src.get("months") or 12),
                int(src.get("includes_erganios") or 0),
                int(src.get("includes_apologistic") or 0),
                int(src.get("includes_ai_agent") or 0),
                money(src.get("amount_net")),
                money(src.get("vat_rate") if src.get("vat_rate") not in (None, "") else DEFAULT_VAT),
                1,
            ),
        )
        new_id = int(cur.fetchone()[0])
    created = {int(p["id"]): p for p in list_plans(active_only=False)}.get(new_id)
    if not created:
        raise RuntimeError("Το αντίγραφο πακέτου δεν δημιουργήθηκε.")
    return created


def cancel_subscription(subscription_id: int) -> None:
    ensure_tables()
    with cursor() as cur:
        cur.execute(
            """
            UPDATE dbo.karta_billing_subscription
            SET status = N'cancelled'
            WHERE id = ? AND status = N'active'
            """,
            (int(subscription_id),),
        )


def list_entries(customer_id: int) -> list[dict[str, Any]]:
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT
              e.id, e.customer_id, e.kind, e.description, e.amount_net, e.vat_rate,
              CONVERT(varchar(10), e.entry_date, 23) AS entry_date,
              e.subscription_id, e.document_id
            FROM dbo.karta_billing_entry e
            WHERE e.customer_id = ?
            ORDER BY e.entry_date DESC, e.id DESC
            """,
            (int(customer_id),),
        )
        rows = [_json_row(row) for row in rows_to_dicts(cur)]
    for row in rows:
        net = money(row["amount_net"])
        vat = vat_amount(net, money(row["vat_rate"]))
        sign = Decimal("-1") if row["kind"] == "credit" else Decimal("1")
        row["vat_amount"] = str(vat)
        row["gross"] = str(money((net + vat) * sign))
        row["open"] = row.get("document_id") in (None, "")
    return rows


def add_entry(customer_id: int, data: dict[str, Any]) -> dict[str, Any]:
    ensure_tables()
    if get_customer(int(customer_id)) is None:
        raise KeyError("Ο πελάτης δεν βρέθηκε.")
    kind = str(data.get("kind") or "charge").strip().lower()
    if kind not in {"charge", "credit"}:
        raise ValueError("Η κίνηση πρέπει να είναι χρέωση ή πίστωση.")
    description = str(data.get("description") or "").strip()
    if not description:
        raise ValueError("Η περιγραφή είναι υποχρεωτική.")
    amount = money(data.get("amount_net"))
    if amount <= 0:
        raise ValueError("Το ποσό πρέπει να είναι μεγαλύτερο από μηδέν.")
    rate = money(data.get("vat_rate") if data.get("vat_rate") not in (None, "") else DEFAULT_VAT)
    entry_date = _parse_date(data.get("entry_date") or date.today().isoformat(), "κίνησης")
    with cursor() as cur:
        cur.execute(
            """
            INSERT INTO dbo.karta_billing_entry
              (customer_id, kind, description, amount_net, vat_rate, entry_date)
            OUTPUT INSERTED.id
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (int(customer_id), kind, description[:400], amount, rate, entry_date),
        )
        entry_id = int(cur.fetchone()[0])
    return next(item for item in list_entries(int(customer_id)) if int(item["id"]) == entry_id)


def _document_select() -> str:
    return """
            SELECT
              d.id, d.customer_id, c.eponimia AS customer_name, c.afm,
              d.doc_type, d.series, d.number, d.invoice_type, d.related_document_id,
              CONVERT(varchar(10), d.issued_on, 23) AS issued_on,
              d.status, d.total_net, d.total_vat, d.total_gross, d.notes,
              d.mark, d.uid, d.icode, d.authentication_code, d.qr_url, d.oxygen_id, d.oxygen_error
            FROM dbo.karta_billing_document d
            INNER JOIN dbo.karta_billing_customer c ON c.id = d.customer_id
    """


def list_documents(customer_id: int | None = None) -> list[dict[str, Any]]:
    ensure_tables()
    sql = _document_select()
    params: tuple = ()
    if customer_id is not None:
        sql += " WHERE d.customer_id = ?"
        params = (int(customer_id),)
    sql += " ORDER BY d.id DESC"
    with cursor(commit=False) as cur:
        cur.execute(sql, params)
        rows = [_json_row(row) for row in rows_to_dicts(cur)]
    by_id = {int(row["id"]): row for row in rows}
    for row in rows:
        row["form_url"] = f"/ui/billing/invoice/{int(row['id'])}"
        row["doc_type_label"] = DOC_TYPE_LABELS.get(str(row["doc_type"]), row["doc_type"])
    credited = {
        int(row["related_document_id"]): row
        for row in rows
        if row.get("related_document_id") not in (None, "")
        and str(row.get("doc_type")) == "CREDIT"
        and str(row.get("status")) == "issued"
    }
    for row in rows:
        credit = credited.get(int(row["id"]))
        row["credit_id"] = int(credit["id"]) if credit else None
        row["credit_form_url"] = credit["form_url"] if credit else None
        if credit and credit.get("number") not in (None, ""):
            row["credit_label"] = f"{credit.get('series') or ''}-{credit['number']}"
        else:
            row["credit_label"] = None
        related = (
            by_id.get(int(row["related_document_id"]))
            if row.get("related_document_id") not in (None, "")
            else None
        )
        if related and related.get("number") not in (None, ""):
            row["related_label"] = f"{related.get('series') or ''}-{related['number']}"
        else:
            row["related_label"] = None
        row["can_credit"] = bool(
            str(row.get("status")) == "issued"
            and str(row.get("doc_type")) in {"APY", "TPY"}
            and not credit
        )
    return rows


def next_document_number(doc_type: str, series: str) -> int:
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT ISNULL(MAX(number), 0) + 1
            FROM dbo.karta_billing_document
            WHERE doc_type=? AND series=?
            """,
            (doc_type, series),
        )
        return int(cur.fetchone()[0])


def format_euro(value: Any) -> str:
    text = f"{money(value):,.2f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def document_lines(document_id: int, customer_id: int | None = None) -> list[dict[str, Any]]:
    ensure_tables()
    sql = """
        SELECT
          sub.id, p.name AS plan_name, p.code AS plan_code,
          CONVERT(varchar(10), sub.starts_on, 23) AS starts_on,
          CONVERT(varchar(10), sub.ends_on, 23) AS ends_on,
          sub.amount_net, sub.vat_rate
        FROM dbo.karta_billing_subscription sub
        INNER JOIN dbo.karta_billing_plan p ON p.id = sub.plan_id
        WHERE sub.document_id = ?
    """
    params: tuple = (int(document_id),)
    if customer_id is not None:
        sql += " AND sub.customer_id = ?"
        params = (int(document_id), int(customer_id))
    sql += " ORDER BY sub.id"
    with cursor(commit=False) as cur:
        cur.execute(sql, params)
        rows = [_json_row(row) for row in rows_to_dicts(cur)]
    lines = []
    for item in rows:
        net = money(item["amount_net"])
        rate = money(item["vat_rate"])
        vat = vat_amount(net, rate)
        lines.append(
            {
                "description": item.get("plan_name") or "Συνδρομή",
                "quantity": 1,
                "net": str(net),
                "vat_rate": str(rate),
                "vat": str(vat),
                "gross": str(money(net + vat)),
            }
        )
    return lines


def get_document(document_id: int) -> dict[str, Any] | None:
    docs = [row for row in list_documents() if int(row["id"]) == int(document_id)]
    if not docs:
        return None
    doc = dict(docs[0])
    customer = get_customer(int(doc["customer_id"]))
    if customer:
        customer = {
            key: customer[key]
            for key in (
                "id",
                "eponimia",
                "epaggelma",
                "address",
                "afm",
                "doy",
                "email",
                "phone",
            )
            if key in customer
        }
    source_id = int(document_id)
    if str(doc.get("doc_type")) == "CREDIT" and doc.get("related_document_id") not in (None, ""):
        source_id = int(doc["related_document_id"])
    lines = document_lines(source_id, int(doc["customer_id"]))
    if not lines:
        net = money(doc.get("total_net"))
        vat = money(doc.get("total_vat"))
        lines = [
            {
                "description": "Πιστωτικό τιμολόγιο" if str(doc.get("doc_type")) == "CREDIT" else "Υπηρεσίες erganiOS",
                "quantity": 1,
                "net": str(net),
                "vat_rate": "24.00",
                "vat": str(vat),
                "gross": str(money(doc.get("total_gross"))),
            }
        ]
    doc["customer"] = customer
    doc["lines"] = lines
    return doc


def issue_from_subscriptions(customer_id: int, data: dict[str, Any]) -> dict[str, Any]:
    from app.oxygen_invoice import build_invoice_payload, oxygen_configured, send_invoice

    ensure_tables()
    customer = get_customer(int(customer_id))
    if not customer:
        raise KeyError("Ο πελάτης δεν βρέθηκε.")
    doc_type = str(data.get("doc_type") or "TPY").strip().upper()
    if doc_type not in DOC_TYPES:
        raise ValueError("Μη έγκυρος τύπος παραστατικού.")
    series = str(data.get("series") or "1").strip()[:16] or "1"
    plan_items = plan_issue_items(data)
    wanted = _int_ids(data.get("subscription_ids"))
    if not plan_items and not wanted:
        raise ValueError("Επιλέξτε τουλάχιστον μία συνδρομή.")
    plans = {int(p["id"]): p for p in list_plans(active_only=False)}
    pending = [_subscription_draft(item, plans) for item in plan_items]
    selected: list[dict[str, Any]] = list(pending)
    if wanted:
        open_subs = {int(item["id"]): item for item in unbilled_subscriptions(int(customer_id))}
        existing = [open_subs[sid] for sid in wanted if sid in open_subs]
        if len(existing) != len(set(wanted)):
            raise ValueError("Κάποιες συνδρομές δεν είναι διαθέσιμες για τιμολόγηση.")
        selected.extend(existing)
    total_net = Decimal("0")
    total_vat = Decimal("0")
    lines = []
    for item in selected:
        net = money(item["amount_net"])
        if net <= 0:
            raise ValueError(f"Η συνδρομή «{item['plan_name']}» δεν έχει ποσό.")
        rate = money(item["vat_rate"])
        vat = vat_amount(net, rate)
        total_net += net
        total_vat += vat
        period = f"{item.get('starts_on') or ''} έως {item.get('ends_on') or ''}".strip()
        lines.append(
            {
                "code": item.get("plan_code") or "SUB",
                "description": f"{item['plan_name']} ({period})",
                "net": net,
                "vat": vat,
                "gross": money(net + vat),
                "vat_rate": rate,
            }
        )
    total_gross = money(total_net + total_vat)
    number = next_document_number(doc_type, series)
    payload = build_invoice_payload(
        customer=customer,
        lines=lines,
        doc_type=doc_type,
        series=series,
        number=number,
        total_net=total_net,
        total_vat=total_vat,
        total_gross=total_gross,
    )
    oxygen_body: dict[str, Any] = {}
    oxygen_error = None
    if oxygen_configured():
        try:
            oxygen_body = send_invoice(payload)
        except Exception as exc:
            raise RuntimeError(str(exc)) from exc
    else:
        oxygen_error = "Χωρίς Oxygen credentials — αποθηκεύτηκε μόνο τοπικά."

    from app.oxygen_invoice import INVOICE_TYPES

    with cursor() as cur:
        cur.execute(
            """
            INSERT INTO dbo.karta_billing_document
              (customer_id, doc_type, series, number, issued_on, status,
               total_net, total_vat, total_gross, notes, invoice_type,
               mark, uid, icode, authentication_code, oxygen_id, qr_url, oxygen_error)
            OUTPUT INSERTED.id
            VALUES (?, ?, ?, ?, CAST(SYSUTCDATETIME() AS date), N'issued',
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(customer_id),
                doc_type,
                series,
                number,
                money(total_net),
                money(total_vat),
                total_gross,
                str(data.get("notes") or "").strip()[:1000] or None,
                INVOICE_TYPES.get(doc_type),
                str(oxygen_body.get("mark") or "")[:64] or None,
                str(oxygen_body.get("uid") or "")[:80] or None,
                str(oxygen_body.get("icode") or "")[:64] or None,
                str(oxygen_body.get("authentication_code") or "")[:128] or None,
                str(oxygen_body.get("id") or "")[:64] or None,
                str(oxygen_body.get("url") or "")[:500] or None,
                oxygen_error,
            ),
        )
        doc_id = int(cur.fetchone()[0])
        for item in pending:
            cur.execute(
                """
                INSERT INTO dbo.karta_billing_subscription
                  (customer_id, plan_id, starts_on, ends_on, status, amount_net, vat_rate, notes, document_id)
                VALUES (?, ?, ?, ?, N'active', ?, ?, ?, ?)
                """,
                (
                    int(customer_id),
                    item["plan_id"],
                    item["starts"],
                    item["ends"],
                    item["amount_net"],
                    item["vat_rate"],
                    item["notes"],
                    doc_id,
                ),
            )
        for item in selected:
            if item.get("id") in (None, ""):
                continue
            cur.execute(
                "UPDATE dbo.karta_billing_subscription SET document_id=? WHERE id=? AND document_id IS NULL",
                (doc_id, int(item["id"])),
            )
    return next(item for item in list_documents() if int(item["id"]) == doc_id)


def issue_credit(document_id: int) -> dict[str, Any]:
    from app.oxygen_invoice import (
        build_invoice_payload,
        credit_invoice_type,
        oxygen_configured,
        send_invoice,
    )

    ensure_tables()
    original = get_document(int(document_id))
    if not original:
        raise KeyError("Το παραστατικό δεν βρέθηκε.")
    if str(original.get("status")) != "issued":
        raise ValueError("Πιστωτικό εκδίδεται μόνο σε εκδοθέν παραστατικό.")
    source_type = str(original.get("doc_type") or "").upper()
    if source_type not in {"APY", "TPY"}:
        raise ValueError("Πιστωτικό εκδίδεται μόνο για ΑΠΥ ή ΤΠΥ.")
    if original.get("credit_id"):
        raise ValueError("Υπάρχει ήδη πιστωτικό για αυτό το παραστατικό.")
    customer = get_customer(int(original["customer_id"]))
    if not customer:
        raise KeyError("Ο πελάτης δεν βρέθηκε.")
    correlated_id = str(original.get("oxygen_id") or "").strip()
    if oxygen_configured() and not correlated_id:
        raise ValueError("Το αρχικό παραστατικό δεν έχει Oxygen id για συσχέτιση.")
    lines = []
    total_net = Decimal("0")
    total_vat = Decimal("0")
    for item in original.get("lines") or []:
        net = money(item.get("net"))
        vat = money(item.get("vat"))
        if net <= 0:
            continue
        total_net += net
        total_vat += vat
        lines.append(
            {
                "code": "CRD",
                "description": item.get("description") or "Πιστωτικό",
                "net": net,
                "vat": vat,
                "gross": money(net + vat),
                "vat_rate": money(item.get("vat_rate") or "24"),
            }
        )
    if not lines:
        raise ValueError("Δεν υπάρχουν γραμμές για πιστωτικό.")
    total_gross = money(total_net + total_vat)
    series = "Π"
    number = next_document_number("CREDIT", series)
    invoice_type = credit_invoice_type(source_type)
    payload = build_invoice_payload(
        customer=customer,
        lines=lines,
        doc_type="CREDIT",
        series=series,
        number=number,
        total_net=total_net,
        total_vat=total_vat,
        total_gross=total_gross,
        correlated_id=correlated_id or None,
        source_doc_type=source_type,
    )
    oxygen_body: dict[str, Any] = {}
    oxygen_error = None
    if oxygen_configured():
        try:
            oxygen_body = send_invoice(payload)
        except Exception as exc:
            raise RuntimeError(str(exc)) from exc
    else:
        oxygen_error = "Χωρίς Oxygen credentials — αποθηκεύτηκε μόνο τοπικά."
    notes = f"Πιστωτικό για {original.get('series') or ''}-{original.get('number')}"
    with cursor() as cur:
        cur.execute(
            """
            INSERT INTO dbo.karta_billing_document
              (customer_id, doc_type, series, number, issued_on, status,
               total_net, total_vat, total_gross, notes, invoice_type,
               related_document_id, mark, uid, icode, authentication_code,
               oxygen_id, qr_url, oxygen_error)
            OUTPUT INSERTED.id
            VALUES (?, N'CREDIT', ?, ?, CAST(SYSUTCDATETIME() AS date), N'issued',
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(original["customer_id"]),
                series,
                number,
                money(total_net),
                money(total_vat),
                total_gross,
                notes,
                invoice_type,
                int(original["id"]),
                str(oxygen_body.get("mark") or "")[:64] or None,
                str(oxygen_body.get("uid") or "")[:80] or None,
                str(oxygen_body.get("icode") or "")[:64] or None,
                str(oxygen_body.get("authentication_code") or "")[:128] or None,
                str(oxygen_body.get("id") or "")[:64] or None,
                str(oxygen_body.get("url") or "")[:500] or None,
                oxygen_error,
            ),
        )
        credit_id = int(cur.fetchone()[0])
        cur.execute(
            """
            UPDATE dbo.karta_billing_subscription
            SET status=N'cancelled'
            WHERE document_id=? AND status=N'active'
            """,
            (int(original["id"]),),
        )
    return next(item for item in list_documents() if int(item["id"]) == credit_id)


def create_document(customer_id: int, data: dict[str, Any]) -> dict[str, Any]:
    ensure_tables()
    if get_customer(int(customer_id)) is None:
        raise KeyError("Ο πελάτης δεν βρέθηκε.")
    doc_type = str(data.get("doc_type") or "TPY").strip().upper()
    if doc_type not in DOC_TYPES:
        raise ValueError("Μη έγκυρος τύпаος παραστατικού.")
    series = str(data.get("series") or "A").strip()[:16] or "A"
    notes = str(data.get("notes") or "").strip()[:1000] or None
    entry_ids = []
    for raw in data.get("entry_ids") or []:
        try:
            entry_ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    entries = [item for item in list_entries(int(customer_id)) if item.get("open")]
    if entry_ids:
        wanted = set(entry_ids)
        entries = [item for item in entries if int(item["id"]) in wanted]
    if not entries:
        raise ValueError("Δεν υπάρχουν ανοιχτές κινήσεις για παραστατικό.")
    total_net = Decimal("0")
    total_vat = Decimal("0")
    for item in entries:
        net = money(item["amount_net"])
        vat = vat_amount(net, money(item["vat_rate"]))
        if item["kind"] == "credit":
            total_net -= net
            total_vat -= vat
        else:
            total_net += net
            total_vat += vat
    total_gross = money(total_net + total_vat)
    with cursor() as cur:
        cur.execute(
            """
            INSERT INTO dbo.karta_billing_document
              (customer_id, doc_type, series, status, total_net, total_vat, total_gross, notes)
            OUTPUT INSERTED.id
            VALUES (?, ?, ?, N'draft', ?, ?, ?, ?)
            """,
            (int(customer_id), doc_type, series, money(total_net), money(total_vat), total_gross, notes),
        )
        doc_id = int(cur.fetchone()[0])
        for item in entries:
            cur.execute(
                "UPDATE dbo.karta_billing_entry SET document_id=? WHERE id=? AND document_id IS NULL",
                (doc_id, int(item["id"])),
            )
    return next(item for item in list_documents(int(customer_id)) if int(item["id"]) == doc_id)


def issue_document(document_id: int) -> dict[str, Any]:
    ensure_tables()
    with cursor() as cur:
        cur.execute(
            """
            SELECT id, customer_id, doc_type, series, number, status
            FROM dbo.karta_billing_document WHERE id=?
            """,
            (int(document_id),),
        )
        row = cur.fetchone()
        if not row:
            raise KeyError("Το παραστατικό δεν βρέθηκε.")
        customer_id = int(row[1])
        if str(row[5]) != "draft":
            raise ValueError("Μόνο πρόχειρο παραστατικό μπορεί να εκδοθεί.")
        cur.execute(
            """
            SELECT ISNULL(MAX(number), 0) + 1
            FROM dbo.karta_billing_document
            WHERE doc_type=? AND series=? AND status=N'issued'
            """,
            (row[2], row[3]),
        )
        number = int(cur.fetchone()[0])
        cur.execute(
            """
            UPDATE dbo.karta_billing_document
            SET status=N'issued', number=?, issued_on=CAST(SYSUTCDATETIME() AS date)
            WHERE id=?
            """,
            (number, int(document_id)),
        )
    return next(item for item in list_documents(customer_id) if int(item["id"]) == int(document_id))


def cancel_document(document_id: int) -> None:
    ensure_tables()
    with cursor() as cur:
        cur.execute(
            "SELECT id, status FROM dbo.karta_billing_document WHERE id=?",
            (int(document_id),),
        )
        row = cur.fetchone()
        if not row:
            raise KeyError("Το παραστατικό δεν βρέθηκε.")
        cur.execute(
            "UPDATE dbo.karta_billing_entry SET document_id=NULL WHERE document_id=?",
            (int(document_id),),
        )
        cur.execute(
            "UPDATE dbo.karta_billing_document SET status=N'cancelled' WHERE id=?",
            (int(document_id),),
        )
