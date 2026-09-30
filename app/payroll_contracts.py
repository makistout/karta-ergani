"""Effective-dated payroll contracts, independent of snapshot collection dates."""
from datetime import timedelta
from decimal import Decimal

from app.payroll_schedule import schedule_date, scheduled_salary_units
from app.web_ma_payload import _eu_float, map_characterization, map_week_days


def _signature(row):
    numbers = tuple(_eu_float(row.get(key)) for key in (
        "salary", "hourly_wage", "weekly_hours", "fulltime_contract_weekly_hours",
        "prior_service", "arithmos_teknon"))
    return numbers + (map_characterization(row.get("characterization")),
        map_week_days(row.get("weekly_work_days"))) + tuple(str(row.get(key) or "").strip() for key in (
        "marital_status", "kyria_asfalish", "epikourikiki_kod", "fixed_term_from", "fixed_term_to"))


def contract_segments(history, current, start, end):
    """Newest snapshot per effective date; coalesce non-payroll updates."""
    if not history or start is None or end is None:
        return [{"from": start, "to": end, "contract": current}]
    by_date = {}
    for row in sorted(history, key=lambda r: (str(r.get("synced_at") or ""), int(r.get("id") or 0))):
        effective = schedule_date(row.get("effective_from") or row.get("ergani_updated_at"))
        if effective is not None:
            by_date[effective] = dict(row)
    if not by_date:
        if all(_signature(row) == _signature(current or {}) for row in history):
            return [{"from": start, "to": end, "contract": current}]
        raise ValueError("Το ιστορικό σύμβασης δεν έχει ημερομηνία ισχύος")
    timeline = []
    for effective, row in sorted(by_date.items()):
        if not timeline or _signature(timeline[-1][1]) != _signature(row):
            timeline.append((effective, row))
    # The registry may carry the start of the newest relationship. Never apply
    # it retroactively to an older, explicitly dated contract version.
    hire = schedule_date((current or {}).get("hire_date"))
    departure = (current or {}).get("departure_date")
    segments = []
    for index, (effective, row) in enumerate(timeline):
        last = timeline[index+1][0] - timedelta(days=1) if index+1 < len(timeline) else end
        left, right = max(start, effective), min(end, last)
        if left > right:
            continue
        row["hire_date"] = hire if hire and hire <= effective else effective
        if departure:
            row["departure_date"] = departure
        segments.append({"from": left, "to": right, "contract": row,
                         "effective_from": effective.isoformat(), "contract_id": row.get("id")})
    if not segments:
        raise ValueError("Δεν υπάρχει σύμβαση που να ισχύει στην επιλεγμένη περίοδο")
    if len(segments) == 1 and _signature(segments[0]["contract"]) == _signature(current or {}):
        segments[0]["contract"] = dict(current)
    if segments[0]["from"] > start:
        # A first recorded contract can start mid-period (a genuine hire).
        # Its own start date drives proration, not the synchronization date.
        segments[0]["from"] = start
    return segments


def segmented_payroll(employee, segments, days, schedule, params, period_type, period_from, period_to):
    from app.payroll import (ZONE_KEYS, EXTRA_FAMILIES, payroll_for_employee, period_salary_amount,
        money, recalculate_employee_row, _is_worker, _weekly_hours, _as_contract_date, _payout_monthly)
    if len(segments) == 1:
        return payroll_for_employee(employee=employee, contract=segments[0]["contract"], params=params,
            period_type=period_type, period_from=period_from, period_to=period_to, schedule_rows=schedule)
    if not days:
        raise ValueError("Η αλλαγή σύμβασης απαιτεί ημερήσια ανάλυση ωρομέτρησης")
    fields = ["premium_minutes"] + [field for field, _, _ in EXTRA_FAMILIES]
    for field in fields:
        for zone in ZONE_KEYS:
            actual = sum(int((d.get(field) or {}).get(zone) or 0) for d in days
                if schedule_date(d.get("work_date")) is not None
                and period_from <= schedule_date(d.get("work_date")) <= period_to)
            expected = int((employee.get(field) or (employee if field == 'premium_minutes' else {})).get(zone) or 0)
            if actual != expected:
                raise ValueError("Η ημερήσια ανάλυση δεν συμφωνεί με τα σύνολα ωρομέτρησης")
    weights = []
    workers_only = all(_is_worker(seg["contract"]) for seg in segments)
    complete = True
    for seg in segments:
        contract = seg["contract"]
        hire = _as_contract_date(contract.get("hire_date")) or seg["from"]
        ends = [_as_contract_date(contract.get(key)) for key in ("departure_date", "fixed_term_to")]
        fixed_start = _as_contract_date(contract.get("fixed_term_from")) or seg["from"]
        left = max(seg["from"], hire, fixed_start)
        right = min([seg["to"]] + [d for d in ends if d is not None])
        complete = complete and left == seg["from"] and right == seg["to"]
        if left > right or workers_only:
            weights.append(Decimal(0))
        else:
            units, _, _ = scheduled_salary_units(schedule, left, right, _weekly_hours(contract))
            weights.append(units)
    total_weight = sum(weights, Decimal(0))
    if complete and not total_weight and not workers_only:
        raise ValueError("Δεν υπάρχουν δηλωμένες ώρες για επιμερισμό μισθού μεταξύ συμβάσεων")
    parts = []
    for index, seg in enumerate(segments):
        item = {key: employee.get(key) for key in ("employee_afm", "eponymo", "onoma")}
        for field in fields:
            item[field] = {zone: 0 for zone in ZONE_KEYS}
        for day in days:
            when = schedule_date(day.get("work_date"))
            if when is None:
                raise ValueError("Μη έγκυρη ημερομηνία ωρομέτρησης στον επιμερισμό")
            if seg["from"] <= when <= seg["to"]:
                for field in fields:
                    for zone in ZONE_KEYS:
                        item[field][zone] += int((day.get(field) or {}).get(zone) or 0)
        contract = seg["contract"]
        full = period_salary_amount(contract, params, period_type=period_type)
        if complete and total_weight:
            salary = money(full * weights[index] / total_weight)
        else:
            divisor = Decimal(25 if period_type == "month" else 6)
            salary = money(full * weights[index] / divisor)
        segment_params = dict(params)
        if index < len(segments)-1:
            if not _payout_monthly(params, 'bonus_payout', 'κάθε_μήνας_περιόδου'):
                segment_params.update(bonus_christmas_pay_month='0', bonus_easter_pay_month='0')
            if not _payout_monthly(params, 'leave_payout', 'κάθε_μήνας'):
                segment_params['leave_allowance_pay_month'] = '0'
        part = payroll_for_employee(employee=item, contract=contract, params=segment_params,
            period_type=period_type, period_from=seg['from'], period_to=seg['to'],
            schedule_rows=schedule, salary_override=salary)
        label = f"{seg['from']:%d/%m/%Y}–{seg['to']:%d/%m/%Y}"
        for line in part["lines"]:
            line["contract_segment"] = label
        parts.append(part)
    # Single-period withholding: never annualize each segment as a full salary.
    # A fund switch needs independent APD insurance packages, which the current
    # APD preview cannot represent. Reject rather than use the final fund silently.
    funds = {tuple((b['code'], b['employee_percent'], b['employer_percent']) for b in p['efka_branches'])
             for p in parts if p['total'] or p is parts[-1]}
    if len(funds) != 1:
        raise ValueError("Αλλαγή ασφαλιστικού πακέτου μέσα στην περίοδο: απαιτείται χωριστή ασφαλιστική ανάλυση")
    result = dict(parts[-1])
    for key in ("salary_payable_days", "salary_unpaid_days", "salary_days_basis", "salary_schedule_dates", "salary_schedule_minutes"):
        result.pop(key, None)
    result['period_salary'] = float(money(sum((Decimal(str(p['period_salary'])) for p in parts), Decimal(0))))
    result['allowance_base'] = sum(p['allowance_base'] for p in parts)
    result['lines'] = [line for part in parts for line in part['lines']]
    result['warnings'] = list(dict.fromkeys(w for p in parts for w in p['warnings']))
    result['contract_segments'] = [{
        'from': seg['from'].isoformat(), 'to': seg['to'].isoformat(),
        'effective_from': seg.get('effective_from'), 'contract_id': seg.get('contract_id'),
        'salary': seg['contract'].get('salary'), 'weekly_hours': seg['contract'].get('weekly_hours'),
        'hourly_wage': part['hourly_wage'], 'legal_hourly': part['legal_hourly'],
        'schedule_units': float(weight), 'salary_share': float(weight / total_weight) if complete and total_weight else float(weight / Decimal(25 if period_type == 'month' else 6)),
        'period_salary': part['period_salary'], 'total': part['total'],
    } for seg, part, weight in zip(segments, parts, weights)]
    return recalculate_employee_row(result, params=params, period_type=period_type)
