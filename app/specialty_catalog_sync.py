"""Κατέβασμα / νυχτερινή ενημέρωση καταλόγου ειδικοτήτων ΣΤΕΠ'92 από Ergani."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from app.ergani_env import api_login_credentials, client_for_store, store_api_context
from app.ergani_parse import extract_catalog_items, unwrap_ergani_data
from app.http_helpers import json_or_text
from app.karta_log import KartaLogger
from app.work_card_payload import tz_athens
from app import repo_specialty_catalog, repo_store, repo_sync_log
from config import Config

OPERATION_SPECIALTY_CATALOG_SYNC = "scheduled_specialty_catalog_sync"
GLOBAL_STORE_ID = 0


def _pick_store_with_api() -> dict[str, Any] | None:
    for cfg in repo_store.list_store_configs():
        if str(cfg.get("web_username") or "").strip() and str(cfg.get("web_password") or "").strip():
            return cfg
    return None


def fetch_step92_items(cfg: dict[str, Any]) -> list[dict[str, str]]:
    ctx = store_api_context(cfg)
    client = client_for_store(cfg)
    api_user, api_pwd, api_ut = api_login_credentials(ctx)
    auth = client.authenticate(api_user, api_pwd, api_ut)
    auth_parsed = json_or_text(auth)
    if not auth.ok or not isinstance(auth_parsed, dict) or not auth_parsed.get("accessToken"):
        raise RuntimeError("Αποτυχία σύνδεσης Ergani API για κατάλογο ΣΤΕΠ")
    bearer = str(auth_parsed["accessToken"])
    params = [{"ParameterName": "Parameter", "ParameterValue": "Step92"}]
    resp = client.execute_service("EX_BASE_03", params, bearer)
    parsed = json_or_text(resp)
    if not resp.ok:
        raise RuntimeError(f"Αποτυχία EX_BASE_03 Step92 (HTTP {resp.status_code})")
    items = extract_catalog_items(unwrap_ergani_data(parsed))
    if not items:
        raise RuntimeError("Κενός κατάλογος ΣΤΕΠ από Ergani")
    return items


def sync_specialty_catalog(*, cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Κατεβάζει Step92 και αντικαθιστά τον τοπικό πίνακα."""
    store = cfg or _pick_store_with_api()
    if not store:
        return {
            "success": False,
            "detail": "Δεν βρέθηκε κατάστημα με web credentials για Ergani API",
            "count": 0,
        }
    try:
        items = fetch_step92_items(store)
        count = repo_specialty_catalog.replace_all(items)
        return {
            "success": True,
            "detail": f"Ενημερώθηκαν {count} ειδικότητες ΣΤΕΠ",
            "count": count,
            "store_id": int(store["id"]),
            "store_name": store.get("name"),
            "synced_at": repo_specialty_catalog.last_synced_at(),
        }
    except Exception as ex:  # noqa: BLE001
        return {
            "success": False,
            "detail": str(ex),
            "count": repo_specialty_catalog.count_rows(),
            "store_id": int(store["id"]),
            "store_name": store.get("name"),
        }


def should_run_specialty_catalog_sync(
    *,
    now: datetime | None = None,
) -> tuple[bool, str]:
    from app.scheduled_sync import _normalized_sync_time, _operation_run_exists

    local_now = (now or datetime.now(tz_athens())).astimezone(tz_athens())
    if not Config.KARTA_SCHEDULED_SPECIALTY_CATALOG_ENABLED:
        return False, "απενεργοποιημένο από ρύθμιση"
    base_date = local_now.date().isoformat()
    run_time = _normalized_sync_time(
        Config.KARTA_SCHEDULED_SPECIALTY_CATALOG_TIME,
        default="03:00",
    )
    if local_now.strftime("%H:%M") < run_time:
        return False, f"αναμονή μέχρι {run_time}"
    if not repo_sync_log.tables_available():
        return False, "λείπουν πίνακες sync log"
    if _operation_run_exists(OPERATION_SPECIALTY_CATALOG_SYNC, GLOBAL_STORE_ID, base_date):
        return False, "έχει ήδη εκτελεστεί σήμερα"
    return True, "έτοιμο"


def run_specialty_catalog_sync_scheduled(
    *,
    parent_run_id: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Νυχτερινή ενημέρωση — μία φορά/ημέρα (store_id=0)."""
    ok_run, reason = should_run_specialty_catalog_sync()
    if not force and not ok_run:
        return {"success": True, "skipped": True, "reason": reason}

    _ = parent_run_id
    log = KartaLogger(
        OPERATION_SPECIALTY_CATALOG_SYNC,
        store_id=GLOBAL_STORE_ID,
        store_name="global",
        run_id=str(uuid.uuid4()),
    )
    log.info("Έναρξη ενημέρωσης καταλόγου ΣΤΕΠ")

    result = sync_specialty_catalog()
    success = bool(result.get("success"))
    detail = str(result.get("detail") or "")
    if success:
        log.info(detail, count=result.get("count"))
    else:
        log.error(detail)

    repo_sync_log.finish_run(
        log.run_id,
        status="done" if success else "error",
        message=detail,
        result={"success": success, "specialty_catalog": result},
    )

    return {
        "success": success,
        "skipped": False,
        "reason": reason if not force else "force",
        "run_id": log.run_id,
        "specialty_catalog": result,
    }
