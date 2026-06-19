"""Σύγκριση Excel πριν/μετά HTML pagination."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from urllib.parse import urljoin

from app import repo_store
from app.ergani_env import portal_base_for_env, normalize_ergani_env
from app.portal_excel import fetch_schedule_rows_via_excel, parse_schedule_export
from app.portal_form_util import set_portal_dates
from app.portal_schedule_sync import (
    GRID_EVENT_TARGET,
    REQUEST_TIMEOUT,
    _SCHEDULE_CTRL,
    _SCHEDULE_DATE_FROM_FALLBACK,
    _SCHEDULE_DATE_TO_FALLBACK,
    _collect_all_grid_rows,
    _extract_aspnet_form_data,
    _find_search_form,
    _login_session,
    _open_current_status,
    _pick_pararthma,
    _portal_base,
)


def search(session, ctx, page_html, page_url):
    form = _find_search_form(page_html)
    data = _extract_aspnet_form_data(page_html, include_text=True)
    data[f"{_SCHEDULE_CTRL}$PararthmaSelection$PararthmaListEdit"] = _pick_pararthma(
        page_html, str(ctx.get("branch_aa") or "0")
    )
    data[f"{_SCHEDULE_CTRL}$AfmEdit"] = ""
    data[f"{_SCHEDULE_CTRL}$EponimoBox"] = ""
    data[f"{_SCHEDULE_CTRL}$NameBox"] = ""
    set_portal_dates(
        data,
        page_html,
        "21/05/2026",
        "19/06/2026",
        fallback_from=_SCHEDULE_DATE_FROM_FALLBACK,
        fallback_to=_SCHEDULE_DATE_TO_FALLBACK,
    )
    data[f"{_SCHEDULE_CTRL}$SearchControlSearchButton"] = "Αναζήτηση"
    action = urljoin(page_url, form.get("action") or page_url)
    return session.post(action, data=data, timeout=REQUEST_TIMEOUT, allow_redirects=True)


def main() -> int:
    cfg = repo_store.get_store_config(4)
    env = normalize_ergani_env(cfg.get("ergani_env"))
    ctx = {
        "id": cfg["id"],
        "employer_afm": cfg["employer_afm"],
        "branch_aa": cfg.get("branch_aa") or "0",
        "username": cfg["username"],
        "password": cfg["password"],
        "usertype": cfg.get("usertype") or "01",
        "ergani_env": env,
        "portal_base_url": portal_base_for_env(env),
    }
    session = _login_session(ctx)
    page_html, page_url = _open_current_status(session, _portal_base(ctx))

    r = search(session, ctx, page_html, page_url)
    excel_first = fetch_schedule_rows_via_excel(
        session, r.text, r.url, grid_event_target=GRID_EVENT_TARGET
    )
    print("excel_first", len(excel_first))

    session2 = _login_session(ctx)
    page_html2, page_url2 = _open_current_status(session2, _portal_base(ctx))
    r2 = search(session2, ctx, page_html2, page_url2)
    html_rows = _collect_all_grid_rows(session2, r2.url, r2.text)
    try:
        excel_after = fetch_schedule_rows_via_excel(
            session2, r2.text, r2.url, grid_event_target=GRID_EVENT_TARGET
        )
        print("html_rows", len(html_rows), "excel_after", len(excel_after))
    except Exception as ex:
        print("html_rows", len(html_rows), "excel_after FAIL", ex)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
