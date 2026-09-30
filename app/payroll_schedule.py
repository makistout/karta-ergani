"""Declared schedule evidence for partial-month salary; never punch attendance."""
from datetime import date, datetime, timedelta
from decimal import Decimal
import unicodedata


def schedule_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value or "")[:10], fmt).date()
        except ValueError:
            pass
    return None


def _minute(value):
    text = str(value or "").strip()
    try:
        hour, minute = map(int, text.split(":"))
        if 0 <= hour < 24 and 0 <= minute < 60:
            return hour * 60 + minute
        if hour == 24 and minute == 0:
            return 1440
    except (ValueError, TypeError):
        pass
    raise ValueError("Μη έγκυρη ώρα στο δηλωμένο πρόγραμμα μισθοδοσίας")


def scheduled_salary_units(rows, start, end, weekly_hours):
    if rows is None or weekly_hours is None or weekly_hours <= 0:
        raise ValueError("Η αναλογία μισθού απαιτεί δηλωμένο πρόγραμμα και συμβατικές εβδομαδιαίες ώρες")
    days = {}
    evidence = False
    for row in rows:
        day = schedule_date(row.get("work_date"))
        if day is None or not start <= day <= end:
            continue
        label = "".join(c for c in unicodedata.normalize("NFD", str(row.get("shift_type") or "").upper())
                        if unicodedata.category(c) != "Mn")
        left, right = row.get("hour_from"), row.get("hour_to")
        if not left and not right:
            # Paid leave/holidays cannot be silently treated as unpaid absence.
            if "ΑΔΕΙΑ" in label or "ΑΡΓΙΑ" in label:
                raise ValueError("Άδεια/αργία χωρίς δηλωμένες ώρες: απαιτείται έλεγχος της βάσης μισθού")
            if any(marker in label for marker in ("ΑΝΑΠΑΥΣ", "ΡΕΠΟ", "ΜΗ ΕΡΓΑΣΙΑ")):
                evidence = True
            elif "ΕΡΓΑΣΙΑ" in label:
                raise ValueError("Δηλωμένη εργασία χωρίς ώρες στη μισθοδοσία")
            continue
        first, last = _minute(left), _minute(right)
        if last == first:
            raise ValueError("Ίδια έναρξη και λήξη στο δηλωμένο πρόγραμμα μισθοδοσίας")
        if last < first:
            last += 1440
        item = days.setdefault(day, {"minutes": set(), "breaks": {}})
        item["minutes"].update(range(first, last))
        if row.get("break_in_work") in (0, False, "0"):
            item["breaks"][(first, last)] = max(item["breaks"].get((first, last), 0), int(row.get("break_minutes") or 0))
        evidence = True
    if not evidence:
        raise ValueError("Δεν βρέθηκε δηλωμένο πρόγραμμα μέσα στη σχέση εργασίας για την αναλογία μισθού")
    weeks = {}
    for day, item in days.items():
        week = day - timedelta(days=day.weekday())
        net = max(0, len(item["minutes"]) - sum(item["breaks"].values()))
        weeks[week] = weeks.get(week, 0) + net
    # Extra hours remain in the separate timekeeping families, not base salary.
    weekly_minutes = weekly_hours * 60
    minutes = sum((min(Decimal(value), weekly_minutes) for value in weeks.values()), Decimal(0))
    units = min(Decimal(25), minutes * 6 / weekly_minutes)
    return units, minutes, sorted(day.isoformat() for day in days)
