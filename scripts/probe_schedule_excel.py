"""Δοκιμή Excel export ψηφιακού ωραρίου."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from urllib.parse import urljoin

from app import repo_store
from app.ergani_env import portal_base_for_env, normalize_ergani_env
from app.portal_excel import _parse_xlsx, download_grid_excel, parse_schedule_export
from app.portal_form_util import set_portal_dates
from app.portal_schedule_sync import (
    GRID_EVENT_TARGET,
    REQUEST_TIMEOUT,
    _SCHEDULE_CTRL,
    _SCHEDULE_DATE_FROM_FALLBACK,
    _SCHEDULE_DATE_TO_FALLBACK,
    _extract_aspnet_form_data,
    _find_search_form,
    _login_session,
    _open_current_status,
    _pick_pararthma,
    _portal_base,
)


def main() -> int:
    cfg = repo_store.get_store_config(4)
    if not cfg:
        print("no store")
        return 1
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
    form = _find_search_form(page_html)
    if not form:
        print("no form")
        return 1
    data = _extract_aspnet_form_data(page_html, include_text=True)
    branch_aa = str(ctx.get("branch_aa") or "0").strip()
    data[f"{_SCHEDULE_CTRL}$PararthmaSelection$PararthmaListEdit"] = _pick_pararthma(
        page_html, branch_aa
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
    r = session.post(action, data=data, timeout=REQUEST_TIMEOUT, allow_redirects=True)
    content, ctype = download_grid_excel(
        session, r.text, r.url, grid_event_target=GRID_EVENT_TARGET
    )
    raw = _parse_xlsx(content)
    print(f"ctype={ctype} raw_rows={len(raw)}")
    for row in raw[:6]:
        print(row)
    parsed = parse_schedule_export(content, ctype)
    print(f"parsed_rows={len(parsed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
