from __future__ import annotations

from typing import Any, Iterator


def iter_card_blocks(payload: dict[str, Any]) -> Iterator[tuple[dict[str, Any], list[dict[str, Any]]]]:
    cards = payload.get("Cards") or payload.get("cards")
    if not isinstance(cards, dict):
        return
    raw_list = cards.get("Card") or cards.get("card")
    if raw_list is None:
        return
    if isinstance(raw_list, dict):
        raw_list = [raw_list]
    if not isinstance(raw_list, list):
        return
    for card in raw_list:
        if not isinstance(card, dict):
            continue
        details = card.get("Details") or card.get("details") or {}
        if not isinstance(details, dict):
            details = {}
        cd = details.get("CardDetails") or details.get("cardDetails")
        if cd is None:
            lines: list[dict[str, Any]] = []
        elif isinstance(cd, dict):
            lines = [cd]
        elif isinstance(cd, list):
            lines = [x for x in cd if isinstance(x, dict)]
        else:
            lines = []
        yield card, lines


def extract_employer_afm_from_request(payload: dict[str, Any]) -> str | None:
    for card, _lines in iter_card_blocks(payload):
        v = card.get("f_afm_ergodoti") or card.get("F_afm_ergodoti")
        if v:
            return str(v).strip()[:9]
    return None
