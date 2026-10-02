"""Μισθοδοσία: ώρες × σύμβαση × συντελεστές + επιδόματα ΕΓΣΣΕ + δώρα/άδεια + ΕΦΚΑ + ΦΜΥ."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom.minidom import parseString

from app.employment_contract_parse import map_marital_status
from app.payroll_schedule import scheduled_salary_units
from app.web_ma_payload import (
    _eu_float,
    epikourikiki_codes_from_data,
    main_insurance_short_label,
    map_characterization,
    map_week_days,
    normalize_kyria_asfalish,
    SUPPLEMENTARY_INSURANCE_FUNDS,
    supplementary_fund_short_label,
)

ZONE_KEYS = ("day", "night", "sunday_holiday", "night_sunday_holiday")
ZONE_LABELS = {
    "day": "Ημέρας",
    "night": "Νύχτας",
    "sunday_holiday": "Κυρ/Αργίας",
    "night_sunday_holiday": "Νύχτας/Κυρ-Αργίας",
}

# Οικογένειες έξτρα ωρών: πάντα πληρώνεται η ώρα + ποσοστό οικογένειας.
EXTRA_FAMILIES: tuple[tuple[str, str, str], ...] = (
    ("overwork_breakdown", "overwork_percent", "Υπερεργασία"),
    ("partial_additional_12_breakdown", "partial_additional_percent", "Πρόσθετη μερικής"),
    ("overtime_40_breakdown", "overtime_40_percent", "Υπερωρία 40%"),
    ("overtime_60_breakdown", "overtime_60_percent", "Υπερωρία 60%"),
    ("overtime_120_breakdown", "overtime_120_percent", "Κατ’ εξαίρεση"),
    ("sixth_day_breakdown", "sixth_day_percent", "6η ημέρα"),
    ("sixth_day_above_48_breakdown", "sixth_day_above_48_percent", "6η άνω των 48"),
    (
        "exception_sixth_day_above_48_breakdown",
        "exception_sixth_above_48_percent",
        "Κατ’ εξαίρεση 6η άνω των 48",
    ),
)

PARAMETER_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "code": "night_percent",
        "label": "Νυχτερινή προσαύξηση (%)",
        "group_code": "zones",
        "group_label": "Ζώνες ΕΓΣΣΕ",
        "value_kind": "percent",
        "default": "25",
        "legal_ref": "ΕΓΣΣΕ",
        "sort_order": 10,
        "note": "Στα λεπτά που η ωρομέτρηση χαρακτήρισε ήδη νύχτα.",
    },
    {
        "code": "sunday_holiday_percent",
        "label": "Κυριακή / αργία (%)",
        "group_code": "zones",
        "group_label": "Ζώνες ΕΓΣΣΕ",
        "value_kind": "percent",
        "default": "75",
        "legal_ref": "ΕΓΣΣΕ",
        "sort_order": 20,
        "note": "Αθροίζεται με τη νύχτα όταν συμπίπτουν (όχι πολλαπλασιαστικά).",
    },
    {
        "code": "night_start",
        "label": "Έναρξη νύχτας",
        "group_code": "zones",
        "group_label": "Ζώνες ΕΓΣΣΕ",
        "value_kind": "time",
        "default": "22:00",
        "legal_ref": "ΕΓΣΣΕ",
        "sort_order": 30,
        "note": "Αποθηκεύεται για αλλαγή νόμου. Η τρέχουσα ωρομέτρηση κόβει ήδη 22:00–06:00.",
    },
    {
        "code": "night_end",
        "label": "Λήξη νύχτας",
        "group_code": "zones",
        "group_label": "Ζώνες ΕΓΣΣΕ",
        "value_kind": "time",
        "default": "06:00",
        "legal_ref": "ΕΓΣΣΕ",
        "sort_order": 40,
        "note": "Βλ. έναρξη νύχτας.",
    },
    {
        "code": "zone_premium_base",
        "label": "Βάση νύχτας/Κυριακής",
        "group_code": "zones",
        "group_label": "Ζώνες ΕΓΣΣΕ",
        "value_kind": "choice",
        "default": "legal",
        "choices": ("legal", "contractual"),
        "legal_ref": "ΕΓΣΣΕ · επί νομίμου",
        "sort_order": 50,
        "note": "legal = νόμιμο ωρομίσθιο, contractual = καταβαλλόμενο.",
    },
    {
        "code": "overwork_percent",
        "label": "Υπερεργασία (%)",
        "group_code": "families",
        "group_label": "Οικογένειες ωρομέτρησης",
        "value_kind": "percent",
        "default": "20",
        "legal_ref": "Ν. 2874/2000",
        "sort_order": 110,
        "note": "",
    },
    {
        "code": "partial_additional_percent",
        "label": "Πρόσθετη μερικής (%)",
        "group_code": "families",
        "group_label": "Οικογένειες ωρομέτρησης",
        "value_kind": "percent",
        "default": "12",
        "legal_ref": "Ν. 3846/2010",
        "sort_order": 120,
        "note": "",
    },
    {
        "code": "overtime_40_percent",
        "label": "Υπερωρία εντός 150 ωρών (%)",
        "group_code": "families",
        "group_label": "Οικογένειες ωρομέτρησης",
        "value_kind": "percent",
        "default": "40",
        "legal_ref": "Ν. 4808/2021 άρθ. 25",
        "sort_order": 130,
        "note": "",
    },
    {
        "code": "overtime_60_percent",
        "label": "Υπερωρία μετά τις 150 ώρες (%)",
        "group_code": "families",
        "group_label": "Οικογένειες ωρομέτρησης",
        "value_kind": "percent",
        "default": "60",
        "legal_ref": "Ν. 4808/2021 άρθ. 25",
        "sort_order": 140,
        "note": "",
    },
    {
        "code": "overtime_120_percent",
        "label": "Κατ’ εξαίρεση υπερωρία (%)",
        "group_code": "families",
        "group_label": "Οικογένειες ωρομέτρησης",
        "value_kind": "percent",
        "default": "120",
        "legal_ref": "Ν. 4808/2021 άρθ. 25",
        "sort_order": 150,
        "note": "",
    },
    {
        "code": "sixth_day_percent",
        "label": "6η ημέρα (%)",
        "group_code": "families",
        "group_label": "Οικογένειες ωρομέτρησης",
        "value_kind": "percent",
        "default": "40",
        "legal_ref": "Ν. 5053/2023 άρθ. 25–26 (το Excel ωρών λέει 30%)",
        "sort_order": 160,
        "note": "Προεπιλογή το νόμιμο 40%. Άλλαξε σε 30 αν ισχύει κλαδική.",
    },
    {
        "code": "sixth_day_above_48_percent",
        "label": "6η ημέρα άνω των 48 ωρών (%)",
        "group_code": "families",
        "group_label": "Οικογένειες ωρομέτρησης",
        "value_kind": "percent",
        "default": "120",
        "legal_ref": "Οδηγία 2003/88/ΕΚ · όριο 48 ωρών",
        "sort_order": 170,
        "note": "Μόνο εστίαση, όπως στην ωρομέτρηση.",
    },
    {
        "code": "exception_sixth_above_48_percent",
        "label": "Κατ’ εξαίρεση 6η άνω των 48 (%)",
        "group_code": "families",
        "group_label": "Οικογένειες ωρομέτρησης",
        "value_kind": "percent",
        "default": "120",
        "legal_ref": "Ν. 4808/2021 άρθ. 25",
        "sort_order": 180,
        "note": "",
    },
    {
        "code": "month_factor_worker",
        "label": "Συντελεστής μήνα εργάτη",
        "group_code": "factors",
        "group_label": "Συντελεστές ΕΡΓΑΝΗ",
        "value_kind": "factor",
        "default": "4.333",
        "legal_ref": "Τύπος ΕΡΓΑΝΗ WebMA",
        "sort_order": 210,
        "note": "μεικτές = εβδ. ώρες × συντελεστή × ωρομίσθιο",
    },
    {
        "code": "month_factor_employee",
        "label": "Συντελεστής μήνα υπαλλήλου",
        "group_code": "factors",
        "group_label": "Συντελεστές ΕΡΓΑΝΗ",
        "value_kind": "factor",
        "default": "4.166",
        "legal_ref": "Τύπος ΕΡΓΑΝΗ WebMA",
        "sort_order": 220,
        "note": "",
    },
    {
        "code": "min_monthly_salary",
        "label": "Κατώτατος μηνιαίος υπαλλήλου (€)",
        "group_code": "minimum",
        "group_label": "Κατώτατες αποδοχές",
        "value_kind": "money",
        "default": "920",
        "legal_ref": "Κατώτατος από 1.4.2026",
        "sort_order": 310,
        "note": "Χρησιμοποίησε νέα ισχύ από ημερομηνία όταν αλλάζει ο νόμος.",
    },
    {
        "code": "min_daily_wage",
        "label": "Κατώτατο ημερομίσθιο εργάτη (€)",
        "group_code": "minimum",
        "group_label": "Κατώτατες αποδοχές",
        "value_kind": "money",
        "default": "41.09",
        "legal_ref": "Κατώτατος από 1.4.2026",
        "sort_order": 320,
        "note": "",
    },
    {
        "code": "fulltime_weekly_hours",
        "label": "Εβδομαδιαίες ώρες πλήρους απασχόλησης",
        "group_code": "minimum",
        "group_label": "Κατώτατες αποδοχές",
        "value_kind": "number",
        "default": "40",
        "legal_ref": "Σύγκριση μερικής προς πλήρη",
        "sort_order": 330,
        "note": (
            "Νόμιμο ωρομίσθιο εργάτη = ημερομίσθιο ÷ (ώρες πλήρους / ημέρες εβδομάδας). "
            "Όχι οι μειωμένες ώρες της μερικής σύμβασης."
        ),
    },
    {
        "code": "annual_overtime_limit_hours",
        "label": "Ετήσιο όριο νόμιμης υπερωρίας (ώρες)",
        "group_code": "limits",
        "group_label": "Όρια",
        "value_kind": "number",
        "default": "150",
        "legal_ref": "Ν. 4808/2021 άρθ. 25",
        "sort_order": 410,
        "note": "Η ωρομέτρηση έχει ήδη χωρίσει 40/60. Εδώ για τεκμηρίωση/μελλοντική χρήση.",
    },
    {
        "code": "marriage_percent",
        "label": "Επίδομα γάμου (%)",
        "group_code": "allowances",
        "group_label": "Επιδόματα ΕΓΣΣΕ",
        "value_kind": "percent",
        "default": "10",
        "legal_ref": "ΕΓΣΣΕ 2010",
        "sort_order": 510,
        "note": "Ποσοστό επί της βάσης επιδομάτων. 0 = χωρίς επίδομα γάμου.",
    },
    {
        "code": "marriage_marital_codes",
        "label": "Κωδικοί οικογ. κατάστασης για γάμο",
        "group_code": "allowances",
        "group_label": "Επιδόματα ΕΓΣΣΕ",
        "value_kind": "text",
        "default": "1,2,3",
        "legal_ref": "Κωδικοί Ergani",
        "sort_order": 520,
        "note": "0 άγαμος, 1 έγγαμος, 2 διαζευγμένος, 3 χήρος. Κενό = κανείς.",
    },
    {
        "code": "child_allowance_1_percent",
        "label": "Επίδομα 1 τέκνου (%)",
        "group_code": "allowances",
        "group_label": "Επιδόματα ΕΓΣΣΕ",
        "value_kind": "percent",
        "default": "5",
        "legal_ref": "ΕΓΣΣΕ 2010",
        "sort_order": 530,
        "note": "",
    },
    {
        "code": "child_allowance_2_percent",
        "label": "Επίδομα 2 τέκνων (%)",
        "group_code": "allowances",
        "group_label": "Επιδόματα ΕΓΣΣΕ",
        "value_kind": "percent",
        "default": "6",
        "legal_ref": "ΕΓΣΣΕ 2010",
        "sort_order": 540,
        "note": "",
    },
    {
        "code": "child_allowance_3_percent",
        "label": "Επίδομα 3 τέκνων (%)",
        "group_code": "allowances",
        "group_label": "Επιδόματα ΕΓΣΣΕ",
        "value_kind": "percent",
        "default": "10",
        "legal_ref": "ΕΓΣΣΕ 2010",
        "sort_order": 550,
        "note": "",
    },
    {
        "code": "child_allowance_4_percent",
        "label": "Επίδομα 4 τέκνων (%)",
        "group_code": "allowances",
        "group_label": "Επιδόματα ΕΓΣΣΕ",
        "value_kind": "percent",
        "default": "15",
        "legal_ref": "ΕΓΣΣΕ 2010",
        "sort_order": 560,
        "note": "",
    },
    {
        "code": "child_allowance_5plus_percent",
        "label": "Επίδομα 5+ τέκνων (%)",
        "group_code": "allowances",
        "group_label": "Επιδόματα ΕΓΣΣΕ",
        "value_kind": "percent",
        "default": "18",
        "legal_ref": "ΕΓΣΣΕ 2010",
        "sort_order": 570,
        "note": "Για 5 τέκνα και πάνω.",
    },
    {
        "code": "seniority_years_per_step",
        "label": "Έτη ανά κλίμακα προϋπηρεσίας",
        "group_code": "allowances",
        "group_label": "Επιδόματα ΕΓΣΣΕ",
        "value_kind": "number",
        "default": "3",
        "legal_ref": "ΕΓΣΣΕ 2010",
        "sort_order": 580,
        "note": "Πλήρη βήματα: έτη ÷ αυτόν τον αριθμό (κάτω ακέραιο).",
    },
    {
        "code": "seniority_percent_per_step",
        "label": "Ποσοστό ανά κλίμακα προϋπηρεσίας (%)",
        "group_code": "allowances",
        "group_label": "Επιδόματα ΕΓΣΣΕ",
        "value_kind": "percent",
        "default": "5",
        "legal_ref": "ΕΓΣΣΕ 2010",
        "sort_order": 590,
        "note": "0 = χωρίς επίδομα προϋπηρεσίας.",
    },
    {
        "code": "seniority_max_steps",
        "label": "Μέγιστες κλίμακες προϋπηρεσίας",
        "group_code": "allowances",
        "group_label": "Επιδόματα ΕΓΣΣΕ",
        "value_kind": "number",
        "default": "6",
        "legal_ref": "ΕΓΣΣΕ 2010",
        "sort_order": 600,
        "note": "Π.χ. 6 × 5% = 30% μέγιστο.",
    },
    {
        "code": "allowance_base",
        "label": "Βάση επιδομάτων",
        "group_code": "allowances",
        "group_label": "Επιδόματα ΕΓΣΣΕ",
        "value_kind": "choice",
        "default": "period",
        "choices": ("period",),
        "legal_ref": "Επί των τακτικών αποδοχών",
        "sort_order": 610,
        "note": "period = μισθός περιόδου υπαλλήλου, αλλιώς αμοιβή ωρών βάσης εργάτη.",
    },
    {
        "code": "efka_pension_employee_percent",
        "label": "Κύρια σύνταξη — ασφαλισμένος (%)",
        "group_code": "efka",
        "group_label": "Εισφορές ΕΦΚΑ",
        "value_kind": "percent",
        "default": "6.67",
        "legal_ref": "Ν. 4387/2016 άρθ. 38",
        "sort_order": 710,
        "note": "Ιδιωτικός τομέας, κοινό καθεστώς μισθωτών.",
    },
    {
        "code": "efka_pension_employer_percent",
        "label": "Κύρια σύνταξη — εργοδότης (%)",
        "group_code": "efka",
        "group_label": "Εισφορές ΕΦΚΑ",
        "value_kind": "percent",
        "default": "13.33",
        "legal_ref": "Ν. 4387/2016 άρθ. 38",
        "sort_order": 720,
        "note": "",
    },
    {
        "code": "efka_health_kind_employee_percent",
        "label": "Υγεία σε είδος — ασφαλισμένος (%)",
        "group_code": "efka",
        "group_label": "Εισφορές ΕΦΚΑ",
        "value_kind": "percent",
        "default": "1.65",
        "legal_ref": "Ν. 4387/2016 · ΕΟΠΥΥ",
        "sort_order": 730,
        "note": "",
    },
    {
        "code": "efka_health_kind_employer_percent",
        "label": "Υγεία σε είδος — εργοδότης (%)",
        "group_code": "efka",
        "group_label": "Εισφορές ΕΦΚΑ",
        "value_kind": "percent",
        "default": "3.80",
        "legal_ref": "Ν. 4387/2016 · μειώσεις εργοδοτικών",
        "sort_order": 740,
        "note": "",
    },
    {
        "code": "efka_health_cash_employee_percent",
        "label": "Υγεία σε χρήμα — ασφαλισμένος (%)",
        "group_code": "efka",
        "group_label": "Εισφορές ΕΦΚΑ",
        "value_kind": "percent",
        "default": "0.40",
        "legal_ref": "Ν. 4387/2016 · ΕΟΠΥΥ",
        "sort_order": 750,
        "note": "",
    },
    {
        "code": "efka_health_cash_employer_percent",
        "label": "Υγεία σε χρήμα — εργοδότης (%)",
        "group_code": "efka",
        "group_label": "Εισφορές ΕΦΚΑ",
        "value_kind": "percent",
        "default": "0.25",
        "legal_ref": "Ν. 4387/2016 · ΕΟΠΥΥ",
        "sort_order": 760,
        "note": "",
    },
    {
        "code": "efka_auxiliary_employee_percent",
        "label": "ΕΤΕΑΕΠ — ασφαλισμένος (%)",
        "group_code": "efka",
        "group_label": "Εισφορές ΕΦΚΑ",
        "value_kind": "percent",
        "default": "3",
        "legal_ref": "Από 1.6.2022 · 3% + 3% · κωδ. 001 Ergani",
        "sort_order": 770,
        "note": "Κλάδος επικουρικής e-ΕΦΚΑ. Το ΤΕΚΑ και τα επαγγελματικά ταμεία έχουν δικά τους ποσοστά.",
    },
    {
        "code": "efka_auxiliary_employer_percent",
        "label": "ΕΤΕΑΕΠ — εργοδότης (%)",
        "group_code": "efka",
        "group_label": "Εισφορές ΕΦΚΑ",
        "value_kind": "percent",
        "default": "3",
        "legal_ref": "Από 1.6.2022 · 3% + 3% · κωδ. 001 Ergani",
        "sort_order": 780,
        "note": "",
    },
    {
        "code": "efka_teka_employee_percent",
        "label": "ΤΕΚΑ — ασφαλισμένος (%)",
        "group_code": "efka",
        "group_label": "Εισφορές ΕΦΚΑ",
        "value_kind": "percent",
        "default": "3",
        "legal_ref": "Ν. 4826/2021 · από 1.1.2025 3% + 3% · κωδ. 002 Ergani",
        "sort_order": 782,
        "note": "Επικουρική ΤΕΚΑ αντί ΕΤΕΑΕΠ όταν η σύμβαση έχει κωδ. 002. Ίδιο ποσοστό με ΕΤΕΑΕΠ από 1.1.2025.",
    },
    {
        "code": "efka_teka_employer_percent",
        "label": "ΤΕΚΑ — εργοδότης (%)",
        "group_code": "efka",
        "group_label": "Εισφορές ΕΦΚΑ",
        "value_kind": "percent",
        "default": "3",
        "legal_ref": "Ν. 4826/2021 · από 1.1.2025 3% + 3% · κωδ. 002 Ergani",
        "sort_order": 783,
        "note": "",
    },
    {
        "code": "efka_dypa_employee_percent",
        "label": "ΔΥΠΑ συνεισπραττόμενες — ασφαλισμένος (%)",
        "group_code": "efka",
        "group_label": "Εισφορές ΕΦΚΑ",
        "value_kind": "percent",
        "default": "1.65",
        "legal_ref": "Ανεργία / ΛΑΕΚ κ.λπ. υπέρ ΔΥΠΑ",
        "sort_order": 790,
        "note": "Πακέτο ιδιωτικού τομέα 2026 (σύνολο ασφαλισμένου 13,37%).",
    },
    {
        "code": "efka_dypa_employer_percent",
        "label": "ΔΥΠΑ συνεισπραττόμενες — εργοδότης (%)",
        "group_code": "efka",
        "group_label": "Εισφορές ΕΦΚΑ",
        "value_kind": "percent",
        "default": "1.41",
        "legal_ref": "Ανεργία / ΛΑΕΚ κ.λπ. υπέρ ΔΥΠΑ",
        "sort_order": 800,
        "note": "Σύνολο εργοδότη 21,79% με τους παραπάνω κλάδους.",
    },
    {
        "code": "efka_heavy_employee_percent",
        "label": "Βαρέα και ανθυγιεινά — ασφαλισμένος (%)",
        "group_code": "efka",
        "group_label": "Εισφορές ΕΦΚΑ",
        "value_kind": "percent",
        "default": "0",
        "legal_ref": "ΒΑΕ ΙΚΑ",
        "sort_order": 810,
        "note": "0 = χωρίς ΒΑΕ. Βάλε το νόμιμο ποσοστό αν ισχύει για το κατάστημα.",
    },
    {
        "code": "efka_heavy_employer_percent",
        "label": "Βαρέα και ανθυγιεινά — εργοδότης (%)",
        "group_code": "efka",
        "group_label": "Εισφορές ΕΦΚΑ",
        "value_kind": "percent",
        "default": "0",
        "legal_ref": "ΒΑΕ ΙΚΑ",
        "sort_order": 820,
        "note": "",
    },
    {
        "code": "efka_monthly_ceiling",
        "label": "Ανώτατο όριο ασφαλιστέων αποδοχών (€ / μήνα)",
        "group_code": "efka",
        "group_label": "Εισφορές ΕΦΚΑ",
        "value_kind": "money",
        "default": "7761.94",
        "legal_ref": "Εγκ. e-ΕΦΚΑ 4/2026 από 1.1.2026",
        "sort_order": 830,
        "note": "Στην εβδομάδα διαιρείται με τον συντελεστή μήνα. 0 = χωρίς πλαφόν.",
    },
    {
        "code": "efka_premium_exempt",
        "label": "Απαλλαγή προσαυξήσεων από ΕΦΚΑ",
        "group_code": "efka",
        "group_label": "Εισφορές ΕΦΚΑ",
        "value_kind": "choice",
        "default": "ναι",
        "choices": ("ναι", "όχι"),
        "legal_ref": "Ν. 5184/2025 άρθ. 41 · εγκ. e-ΕΦΚΑ 8/2025",
        "sort_order": 840,
        "note": "ναι = η προσαύξηση νύχτας/Κυριακής/υπερωρίας δεν ασφαλίζεται (πλήρης απασχόληση από 6.3.2025). Η αξία της ώρας και τα επιδόματα ασφαλίζονται.",
    },
)


def _tax_item(
    code: str,
    label: str,
    default: str,
    sort_order: int,
    *,
    kind: str = "percent",
    legal: str = "Ν. 5246/2025 άρθ. 3 · ΚΦΕ 15",
    note: str = "",
    choices: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "code": code,
        "label": label,
        "group_code": "tax",
        "group_label": "ΦΜΥ / φόρος εισοδήματος",
        "value_kind": kind,
        "default": default,
        "legal_ref": legal,
        "sort_order": sort_order,
        "note": note,
    }
    if choices:
        item["choices"] = choices
    return item


PARAMETER_CATALOG = PARAMETER_CATALOG + (
    _tax_item("tax_bracket_1_upto", "Κλιμάκιο 1 έως (€)", "10000", 900, kind="money"),
    _tax_item("tax_bracket_2_upto", "Κλιμάκιο 2 έως (€)", "20000", 910, kind="money"),
    _tax_item("tax_bracket_3_upto", "Κλιμάκιο 3 έως (€)", "30000", 920, kind="money"),
    _tax_item("tax_bracket_4_upto", "Κλιμάκιο 4 έως (€)", "40000", 930, kind="money"),
    _tax_item("tax_bracket_5_upto", "Κλιμάκιο 5 έως (€)", "60000", 940, kind="money"),
    _tax_item("tax_b1_percent_0", "Κλιμάκιο 1 — 0 τέκνα (%)", "9", 950),
    _tax_item("tax_b1_percent_1", "Κλιμάκιο 1 — 1 τέκνο (%)", "9", 951),
    _tax_item("tax_b1_percent_2", "Κλιμάκιο 1 — 2 τέκνα (%)", "9", 952),
    _tax_item("tax_b1_percent_3", "Κλιμάκιο 1 — 3 τέκνα (%)", "9", 953),
    _tax_item("tax_b1_percent_4plus", "Κλιμάκιο 1 — 4+ τέκνα (%)", "0", 954),
    _tax_item("tax_b2_percent_0", "Κλιμάκιο 2 — 0 τέκνα (%)", "20", 960),
    _tax_item("tax_b2_percent_1", "Κλιμάκιο 2 — 1 τέκνο (%)", "18", 961),
    _tax_item("tax_b2_percent_2", "Κλιμάκιο 2 — 2 τέκνα (%)", "16", 962),
    _tax_item("tax_b2_percent_3", "Κλιμάκιο 2 — 3 τέκνα (%)", "9", 963),
    _tax_item("tax_b2_percent_4plus", "Κλιμάκιο 2 — 4+ τέκνα (%)", "0", 964),
    _tax_item(
        "tax_b3_percent_0", "Κλιμάκιο 3 — 0 τέκνα (%)", "26", 970,
        note="Ανά τέκνο αφαιρείται το βήμα παρακάτω.",
    ),
    _tax_item("tax_b3_child_step_percent", "Κλιμάκιο 3 — μείωση ανά τέκνο (% μονάδες)", "2", 971),
    _tax_item("tax_b4_percent", "Κλιμάκιο 4 (%)", "34", 980),
    _tax_item("tax_b5_percent", "Κλιμάκιο 5 (%)", "39", 981),
    _tax_item("tax_b6_percent", "Υπερβάλλον κλιμάκιο (%)", "44", 982),
    _tax_item(
        "tax_default_age_group", "Προεπιλογή ηλικιακής ομάδας ΦΜΥ", "over_30", 990,
        kind="choice", choices=("over_30", "age_26_30", "under_25"),
        note="over_30 = άνω των 30. Χωρίς ημερομηνία γέννησης στη σύμβαση· αλλάζει στο modal.",
    ),
    _tax_item("tax_young25_b1_percent", "Έως 25 ετών — κλιμάκιο 1 (%)", "0", 1000),
    _tax_item("tax_young25_b2_percent", "Έως 25 ετών — κλιμάκιο 2 (%)", "0", 1001),
    _tax_item("tax_young30_b1_percent", "26–30 ετών — κλιμάκιο 1 (%)", "9", 1010),
    _tax_item("tax_young30_b2_percent", "26–30 ετών — κλιμάκιο 2 (%)", "9", 1011),
    _tax_item(
        "tax_credit_0", "Μείωση φόρου άρθ. 16 — 0 τέκνα (€)", "777", 1020,
        kind="money", legal="ΚΦΕ άρθ. 16 · Ν. 5045/2023 άρθ. 43",
    ),
    _tax_item("tax_credit_1", "Μείωση φόρου — 1 τέκνο (€)", "900", 1021, kind="money", legal="ΚΦΕ άρθ. 16"),
    _tax_item("tax_credit_2", "Μείωση φόρου — 2 τέκνα (€)", "1120", 1022, kind="money", legal="ΚΦΕ άρθ. 16"),
    _tax_item("tax_credit_3", "Μείωση φόρου — 3 τέκνα (€)", "1340", 1023, kind="money", legal="ΚΦΕ άρθ. 16"),
    _tax_item("tax_credit_4", "Μείωση φόρου — 4 τέκνα (€)", "1580", 1024, kind="money", legal="ΚΦΕ άρθ. 16"),
    _tax_item("tax_credit_5", "Μείωση φόρου — 5 τέκνα (€)", "1780", 1025, kind="money", legal="ΚΦΕ άρθ. 16"),
    _tax_item(
        "tax_credit_extra_per_child", "Μείωση φόρου — ανά τέκνο μετά το 5ο (€)", "220", 1026,
        kind="money", legal="ΚΦΕ άρθ. 16",
    ),
    _tax_item(
        "tax_credit_taper_from", "Περιορισμός μείωσης από εισόδημα (€)", "12000", 1030,
        kind="money", legal="ΚΦΕ άρθ. 16",
        note="Πάνω από αυτό, η μείωση πέφτει κατά το ποσό ανά βήμα. Όχι για 5+ τέκνα.",
    ),
    _tax_item("tax_credit_taper_amount", "Περιορισμός μείωσης ανά βήμα (€)", "20", 1031, kind="money", legal="ΚΦΕ άρθ. 16"),
    _tax_item("tax_credit_taper_step", "Βήμα εισοδήματος περιορισμού (€)", "1000", 1032, kind="money", legal="ΚΦΕ άρθ. 16"),
    _tax_item(
        "tax_credit_taper_exempt_from_children", "Χωρίς περιορισμό μείωσης από Ν τέκνα", "5", 1033,
        kind="number", legal="ΚΦΕ άρθ. 16",
    ),
    _tax_item(
        "fmy_annual_salaries", "Μισθοί έτους για ετήσιο ΦΜΥ", "14", 1040,
        kind="number", legal="Παρακράτηση ΦΜΥ · 14 μισθοί",
        note="Μηνιαίο φορολογητέο × 14 = ετήσιο. Στην εβδομάδα πολλαπλασιάζεται και με τον συντελεστή μήνα.",
    ),
)


def _bonus_item(
    code: str,
    label: str,
    default: str,
    sort_order: int,
    *,
    kind: str = "number",
    legal: str = "ΕΓΣΣΕ 2010 άρθ. 1 · Π.Δ. 80/2023",
    note: str = "",
    choices: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "code": code,
        "label": label,
        "group_code": "bonuses",
        "group_label": "Δώρα / επίδομα αδείας",
        "value_kind": kind,
        "default": default,
        "legal_ref": legal,
        "sort_order": sort_order,
        "note": note,
    }
    if choices:
        item["choices"] = choices
    return item


PARAMETER_CATALOG = PARAMETER_CATALOG + (
    _bonus_item(
        "bonus_on_week", "Δώρα και στην εβδομάδα", "όχι", 1100,
        kind="choice", choices=("ναι", "όχι"),
        note="ναι = εμφάνιση και στην εβδομαδιαία ωρομέτρηση. όχι = μόνο σε μηνιαία.",
    ),
    _bonus_item(
        "bonus_include_allowances", "Βάση δώρων περιλαμβάνει επιδόματα ΕΓΣΣΕ", "ναι", 1105,
        kind="choice", choices=("ναι", "όχι"),
        note="Τακτικές αποδοχές: μισθός + γάμος/τέκνα/προϋπηρεσία.",
    ),
    _bonus_item(
        "bonus_leave_coeff", "Συντελεστής αδείας στα δώρα", "0.041666", 1110,
        kind="factor",
        note="Το δώρο × (1 + συντελεστής). 0 = χωρίς προσαύξηση αδείας.",
    ),
    _bonus_item(
        "bonus_payout", "Καταβολή δώρων", "μήνας_καταβολής", 1112,
        kind="choice", choices=("μήνας_καταβολής", "κάθε_μήνας_περιόδου"),
        note="μήνας_καταβολής = όλο το δώρο στον μήνα 12 / 4. κάθε_μήνας_περιόδου = αναλογία ημερών κάθε μήνα (Χριστούγεννα 5–12, Πάσχα 1–4).",
    ),
    _bonus_item(
        "leave_payout", "Καταβολή επιδόματος αδείας", "μήνας_καταβολής", 1113,
        kind="choice", choices=("μήνας_καταβολής", "κάθε_μήνας"),
        legal="Α.Ν. 539/1945 · ΕΓΣΣΕ 2010",
        note="μήνας_καταβολής = όλο στον μήνα επιδόματος. κάθε_μήνας = αναλογία ημερών κάθε μήνα του έτους.",
    ),
    _bonus_item(
        "bonus_christmas_pay_month", "Μήνας καταβολής δώρου Χριστουγέννων", "12", 1120,
        note="0 = χωρίς αυτόματη καταβολή. Αγνοείται όταν η καταβολή δώρων είναι κάθε μήνας περιόδου. Νομίμως έως 21/12.",
    ),
    _bonus_item(
        "bonus_christmas_from_md", "Δώρο Χριστουγέννων από (ΜΜ-ΗΗ)", "05-01", 1121,
        kind="text",
        note="Περίοδος υπολογισμού. 1/5–31/12.",
    ),
    _bonus_item(
        "bonus_christmas_to_md", "Δώρο Χριστουγέννων έως (ΜΜ-ΗΗ)", "12-31", 1122,
        kind="text",
    ),
    _bonus_item(
        "bonus_christmas_employee_months", "Πλήρες δώρο Χριστουγέννων υπαλλήλου (μισθοί)", "1", 1123,
        kind="factor",
    ),
    _bonus_item(
        "bonus_christmas_worker_days", "Πλήρες δώρο Χριστουγέννων εργάτη (ημερομίσθια)", "25", 1124,
    ),
    _bonus_item(
        "bonus_christmas_step_days", "Αναλογία Χριστουγέννων ανά Ν ημερολογιακές", "19", 1125,
        note="Για κάθε Ν ημέρες σχέσης: τα μερίδια παρακάτω. Πλήρης περίοδος = πλήρες δώρο.",
    ),
    _bonus_item(
        "bonus_christmas_step_shares", "Μερίδια Χριστουγέννων ανά βήμα", "2", 1126,
        note="Υπάλληλος: μερίδια / 25 του μισθού. Εργάτης: τόσα ημερομίσθια.",
    ),
    _bonus_item(
        "bonus_christmas_step_divisor", "Διαιρέτης μεριδίων Χριστουγέννων υπαλλήλου", "25", 1127,
    ),
    _bonus_item(
        "bonus_easter_pay_month", "Μήνας καταβολής δώρου Πάσχα", "4", 1130,
        note="0 = χωρίς αυτόματη καταβολή. Νομίμως έως Μεγάλη Τετάρτη.",
    ),
    _bonus_item(
        "bonus_easter_from_md", "Δώρο Πάσχα από (ΜΜ-ΗΗ)", "01-01", 1131,
        kind="text",
        note="Περίοδος υπολογισμού. 1/1–30/4.",
    ),
    _bonus_item(
        "bonus_easter_to_md", "Δώρο Πάσχα έως (ΜΜ-ΗΗ)", "04-30", 1132,
        kind="text",
    ),
    _bonus_item(
        "bonus_easter_employee_months", "Πλήρες δώρο Πάσχα υπαλλήλου (μισθοί)", "0.5", 1133,
        kind="factor",
    ),
    _bonus_item(
        "bonus_easter_worker_days", "Πλήρες δώρο Πάσχα εργάτη (ημερομίσθια)", "15", 1134,
    ),
    _bonus_item(
        "bonus_easter_step_days", "Αναλογία Πάσχα ανά Ν ημερολογιακές", "8", 1135,
        note="Υπάλληλος: μερίδια / 15 του μισού μισθού. Εργάτης: 1 ημερομίσθιο ανά Ν ημέρες.",
    ),
    _bonus_item(
        "bonus_easter_step_shares", "Μερίδια Πάσχα ανά βήμα", "1", 1136,
    ),
    _bonus_item(
        "bonus_easter_step_divisor", "Διαιρέτης μεριδίων Πάσχα υπαλλήλου", "15", 1137,
    ),
    _bonus_item(
        "leave_allowance_pay_month", "Μήνας καταβολής επιδόματος αδείας", "7", 1150,
        legal="Α.Ν. 539/1945 · ΕΓΣΣΕ 2010",
        note="0 = χωρίς αυτόματη καταβολή. Συνήθως μαζί με την ετήσια άδεια.",
    ),
    _bonus_item(
        "leave_days_5day", "Ημέρες αδείας 5ήμερο / έτος", "20", 1151,
        legal="Ν. 3302/2004 · Ν. 4093/2012",
    ),
    _bonus_item(
        "leave_days_6day", "Ημέρες αδείας 6ήμερο / έτος", "24", 1152,
        legal="Ν. 3302/2004 · Ν. 4093/2012",
    ),
    _bonus_item(
        "leave_daily_divisor", "Διαιρέτης ημερομισθίου αδείας υπαλλήλου", "25", 1153,
        legal="Α.Ν. 539/1945",
        note="Επίδομα = (βάση / διαιρέτη) × ημέρες αδείας.",
    ),
    _bonus_item(
        "leave_year_months", "Μήνες πλήρους δικαιώματος αδείας", "12", 1154,
        note="Αναλογία: μήνες απασχόλησης στο έτος / αυτό. Πρόσληψη πριν την 1/1 = πλήρες.",
    ),
)


def _fund_item(
    code: str,
    label: str,
    default: str,
    sort_order: int,
    *,
    legal: str,
    note: str = "",
) -> dict[str, Any]:
    return {
        "code": code,
        "label": label,
        "group_code": "funds",
        "group_label": "Ειδικά ταμεία / ΤΕΚΑ",
        "value_kind": "percent",
        "default": default,
        "legal_ref": legal,
        "sort_order": sort_order,
        "note": note,
    }


def _occupational_fund_catalog() -> tuple[dict[str, Any], ...]:
    items: list[dict[str, Any]] = []
    order = 870
    for fund in SUPPLEMENTARY_INSURANCE_FUNDS:
        code = str(fund["code"])
        if code in {"001", "002"}:
            continue
        short = supplementary_fund_short_label(code)
        items.append(_fund_item(
            f"efka_aux_{code}_employee_percent",
            f"{short} — ασφαλισμένος (%)",
            "0",
            order,
            legal="Επαγγελματικό ταμείο · καταστατικό",
            note=f"{fund['label']}. 0 = χωρίς εισφορά μέχρι να οριστεί το ποσοστό.",
        ))
        items.append(_fund_item(
            f"efka_aux_{code}_employer_percent",
            f"{short} — εργοδότης (%)",
            "0",
            order + 1,
            legal="Επαγγελματικό ταμείο · καταστατικό",
            note="",
        ))
        order += 10
    return tuple(items)


PARAMETER_CATALOG = PARAMETER_CATALOG + (
    _fund_item(
        "efka_lump_employee_percent",
        "Εφάπαξ — ασφαλισμένος (%)",
        "0",
        860,
        legal="Πρόσθετη ασφαλιστική παροχή",
        note="0 = χωρίς εφάπαξ. Ισχύει για όλους όταν οριστεί ποσοστό.",
    ),
    _fund_item(
        "efka_lump_employer_percent",
        "Εφάπαξ — εργοδότης (%)",
        "0",
        861,
        legal="Πρόσθετη ασφαλιστική παροχή",
        note="",
    ),
) + _occupational_fund_catalog()

CATALOG_BY_CODE = {str(item["code"]): item for item in PARAMETER_CATALOG}

# Παλαιότερος κατώτατος ώστε ο μήνας πριν την 1.4.2026 να μην πάρει 920.
MINIMUM_WAGE_HISTORY: tuple[dict[str, str], ...] = (
    {
        "valid_from": "2025-04-01",
        "min_monthly_salary": "880",
        "min_daily_wage": "39.30",
        "legal_ref": "Κατώτατος από 1.4.2025",
    },
    {
        "valid_from": "2026-04-01",
        "min_monthly_salary": "920",
        "min_daily_wage": "41.09",
        "legal_ref": "Κατώτατος από 1.4.2026",
    },
)

EFKA_CEILING_HISTORY: tuple[dict[str, str], ...] = (
    {
        "valid_from": "2025-01-01",
        "efka_monthly_ceiling": "7572.62",
        "legal_ref": "Ανώτατο όριο ασφαλιστέων 2025",
    },
    {
        "valid_from": "2026-01-01",
        "efka_monthly_ceiling": "7761.94",
        "legal_ref": "Εγκ. e-ΕΦΚΑ 4/2026 από 1.1.2026",
    },
)

EFKA_CORE_BEFORE_AUX: tuple[tuple[str, str, str, str], ...] = (
    ("pension", "Κύρια σύνταξη", "efka_pension_employee_percent", "efka_pension_employer_percent"),
    ("health_kind", "Υγεία σε είδος", "efka_health_kind_employee_percent", "efka_health_kind_employer_percent"),
    ("health_cash", "Υγεία σε χρήμα", "efka_health_cash_employee_percent", "efka_health_cash_employer_percent"),
)
EFKA_CORE_AFTER_AUX: tuple[tuple[str, str, str, str], ...] = (
    ("dypa", "ΔΥΠΑ συνεισπραττόμενες", "efka_dypa_employee_percent", "efka_dypa_employer_percent"),
    ("heavy", "Βαρέα και ανθυγιεινά", "efka_heavy_employee_percent", "efka_heavy_employer_percent"),
)
# Συμβατότητα παλιών αναφορών: το auxiliary δεν εφαρμόζεται πλέον σε όλους.
EFKA_BRANCHES: tuple[tuple[str, str, str, str], ...] = EFKA_CORE_BEFORE_AUX + (
    ("auxiliary", "ΕΤΕΑΕΠ", "efka_auxiliary_employee_percent", "efka_auxiliary_employer_percent"),
) + EFKA_CORE_AFTER_AUX


def catalog_groups() -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in PARAMETER_CATALOG:
        code = str(item["group_code"])
        if code in seen:
            continue
        seen.add(code)
        groups.append({"code": code, "label": item["group_label"]})
    return groups


def default_parameter_map() -> dict[str, str]:
    return {str(item["code"]): str(item["default"]) for item in PARAMETER_CATALOG}


MISSING_CONTRACT_WAGE_WARNING = "Λείπει ωρομίσθιο ή μεικτές/εβδ. ώρες στη σύμβαση"


def payroll_afm_key(value: Any) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if not digits:
        return ""
    return digits[:9].zfill(9)


def payroll_employee_display_name(row: dict[str, Any] | None) -> str:
    data = row or {}
    eponymo = str(data.get("eponymo") or "").strip()
    onoma = str(data.get("onoma") or "").strip()
    full = f"{eponymo} {onoma}".strip()
    if full:
        return full
    named = str(data.get("name") or "").strip()
    if named:
        return named
    afm = payroll_afm_key(data.get("employee_afm") or data.get("afm"))
    return f"ΑΦΜ {afm}" if afm else "τον εργαζόμενο"


def missing_wage_wait_message(name: str, *, step: int, total: int) -> str:
    label = (name or "").strip() or "τον εργαζόμενο"
    return (
        f"Δεν έχουμε στοιχεία για {label}. "
        f"Τα ενημερώνουμε από το Μητρώο Εργάνη… Παρακαλώ περιμένετε. "
        f"({step}/{total})"
    )


def missing_contract_wage_employees(payroll: dict[str, Any] | None) -> list[dict[str, str]]:
    """Εργαζόμενοι μισθοδοσίας χωρίς ωρομίσθιο / μισθό / εβδ. ώρες στη σύμβαση."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in (payroll or {}).get("employees") or []:
        warnings = row.get("warnings") or []
        if MISSING_CONTRACT_WAGE_WARNING not in warnings:
            continue
        afm = payroll_afm_key(row.get("employee_afm"))
        if not afm or afm in seen:
            continue
        seen.add(afm)
        out.append({
            "employee_afm": afm,
            "eponymo": str(row.get("eponymo") or "").strip(),
            "onoma": str(row.get("onoma") or "").strip(),
            "name": payroll_employee_display_name(row),
        })
    return out


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()[:10]
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        try:
            return datetime.strptime(text, "%d/%m/%Y").date()
        except ValueError:
            return None


def money(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        amount = value
    else:
        parsed = _eu_float(value)
        amount = Decimal("0") if parsed is None else Decimal(str(parsed))
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def hours_from_minutes(minutes: Any) -> Decimal:
    return (Decimal(int(minutes or 0)) / Decimal(60)).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP
    )


def param_number(params: dict[str, str], code: str) -> Decimal:
    raw = params.get(code)
    if raw is None or str(raw).strip() == "":
        raw = CATALOG_BY_CODE.get(code, {}).get("default") or "0"
    parsed = _eu_float(raw)
    if parsed is None:
        parsed = _eu_float(CATALOG_BY_CODE.get(code, {}).get("default")) or 0
    return Decimal(str(parsed))


def zone_rate(zone: str, params: dict[str, str]) -> Decimal:
    night = param_number(params, "night_percent") / Decimal(100)
    sunday = param_number(params, "sunday_holiday_percent") / Decimal(100)
    if zone == "night":
        return night
    if zone == "sunday_holiday":
        return sunday
    if zone == "night_sunday_holiday":
        return night + sunday
    return Decimal("0")


def resolve_parameters(
    rows: list[dict[str, Any]],
    *,
    store_id: int = 0,
    as_of: date | None = None,
) -> dict[str, str]:
    """Εταιρικό (store_id=0) με override καταστήματος, ισχύ την as_of."""
    when = as_of or date.today()
    resolved = default_parameter_map()
    company: dict[str, tuple[date, str]] = {}
    store: dict[str, tuple[date, str]] = {}
    wanted_store = int(store_id or 0)
    for row in rows:
        code = str(row.get("code") or "").strip()
        if not code:
            continue
        start = _as_date(row.get("valid_from")) or date(2000, 1, 1)
        end = _as_date(row.get("valid_to"))
        if start > when:
            continue
        if end is not None and end < when:
            continue
        sid = int(row.get("store_id") or 0)
        value = str(row.get("value") if row.get("value") is not None else "")
        target = store if sid == wanted_store and wanted_store else company if sid == 0 else None
        if target is None:
            continue
        previous = target.get(code)
        if previous is None or start >= previous[0]:
            target[code] = (start, value)
    for code, (_start, value) in company.items():
        resolved[code] = value
    if wanted_store:
        for code, (_start, value) in store.items():
            resolved[code] = value
    return resolved


def _weekly_hours(contract: dict[str, Any] | None) -> Decimal | None:
    """Ώρες αυτής της σχέσης — όχι το σύνολο από όλες τις ενεργές σχέσεις Ergani."""
    parsed = _eu_float((contract or {}).get("weekly_hours"))
    return None if parsed is None or parsed <= 0 else Decimal(str(parsed))


def _fulltime_weekly_hours(
    contract: dict[str, Any] | None, params: dict[str, str]
) -> Decimal:
    """Ώρες πλήρους εβδομάδας για νόμιμο ωρομίσθιο — όχι οι μειωμένες της μερικής."""
    fallback = param_number(params, "fulltime_weekly_hours")
    if fallback <= 0:
        fallback = Decimal("40")
    parsed = _eu_float((contract or {}).get("fulltime_contract_weekly_hours"))
    fulltime = Decimal(str(parsed)) if parsed and parsed > 0 else fallback
    weekly = _weekly_hours(contract)
    if weekly is not None and fulltime <= weekly < fallback:
        return fallback
    return fulltime


def _weekly_days(contract: dict[str, Any] | None) -> int:
    mapped = map_week_days((contract or {}).get("weekly_work_days"))
    try:
        days = int(mapped or 0)
    except (TypeError, ValueError):
        days = 0
    return days if days in {5, 6} else 5


def _is_worker(contract: dict[str, Any] | None) -> bool:
    mapped = map_characterization((contract or {}).get("characterization"))
    return mapped == "0"


def hourly_from_contract(
    contract: dict[str, Any] | None, params: dict[str, str]
) -> tuple[Decimal | None, list[str]]:
    warnings: list[str] = []
    hourly = _eu_float((contract or {}).get("hourly_wage"))
    if hourly and hourly > 0:
        return money(hourly), warnings
    salary = _eu_float((contract or {}).get("salary"))
    weekly = _weekly_hours(contract)
    if not salary or salary <= 0 or weekly is None:
        warnings.append(MISSING_CONTRACT_WAGE_WARNING)
        return None, warnings
    factor_code = "month_factor_worker" if _is_worker(contract) else "month_factor_employee"
    factor = param_number(params, factor_code)
    if factor <= 0:
        warnings.append("Μη έγκυρος συντελεστής μήνα")
        return None, warnings
    return money(Decimal(str(salary)) / (weekly * factor)), warnings


def legal_hourly(
    contract: dict[str, Any] | None, params: dict[str, str]
) -> Decimal | None:
    fulltime = _fulltime_weekly_hours(contract, params)
    if _is_worker(contract):
        daily = param_number(params, "min_daily_wage")
        hours_per_day = fulltime / Decimal(_weekly_days(contract))
        if hours_per_day <= 0:
            return None
        return money(daily / hours_per_day)
    factor = param_number(params, "month_factor_employee")
    monthly = param_number(params, "min_monthly_salary")
    if factor <= 0 or fulltime <= 0:
        return None
    return money(monthly / (fulltime * factor))


def period_salary_amount(
    contract: dict[str, Any] | None,
    params: dict[str, str],
    *,
    period_type: str,
    period_from: date | None = None,
    period_to: date | None = None,
    schedule_rows: list[dict[str, Any]] | None = None,
) -> Decimal:
    if _is_worker(contract):
        return money(0)
    salary = _eu_float((contract or {}).get("salary"))
    if not salary or salary <= 0:
        return money(0)
    if period_type == "month":
        details = salary_period_details(contract, period_from, period_to, schedule_rows)
        return money(Decimal(str(salary)) * Decimal(str(details["salary_payable_days"])) / Decimal(25))
    factor = param_number(params, "month_factor_employee")
    if factor <= 0:
        return money(0)
    return money(Decimal(str(salary)) / factor)


def salary_period_details(contract, period_from, period_to, schedule_rows=None):
    """25ths from declared hours, including weekends; never assume weekdays."""
    result = {"salary_payable_days": 25.0, "salary_unpaid_days": 0.0,
              "salary_prorated": False, "salary_days_basis": "Πλήρης μήνας: 25/25"}
    if period_from is None or period_to is None:
        return result
    hire = _as_contract_date((contract or {}).get("hire_date"))
    ends = [_as_contract_date((contract or {}).get(key)) for key in ("departure_date", "fixed_term_to")]
    departure = min((value for value in ends if value is not None), default=None)
    start = max(period_from, hire) if hire else period_from
    end = min(period_to, departure) if departure else period_to
    if start == period_from and end == period_to:
        return result
    if end < start:
        result.update(salary_payable_days=0.0, salary_prorated=True,
                      salary_days_basis="Εκτός σχέσης εργασίας: 0/25")
        return result
    try:
        payable, minutes, dates = scheduled_salary_units(schedule_rows, start, end, _weekly_hours(contract))
    except ValueError as exc:
        name = " ".join(str((contract or {}).get(key) or "") for key in ("eponymo", "onoma")).strip()
        raise ValueError(f"{name or 'Εργαζόμενος'}: {exc}") from exc
    result.update(salary_payable_days=float(payable), salary_prorated=True,
                  salary_schedule_dates=dates, salary_schedule_minutes=float(minutes),
                  salary_days_basis=f"Δηλωμένο πρόγραμμα: {_fmt_hours(minutes / 60)} ώρες × 6/{_fmt_factor(_weekly_hours(contract))} = {_fmt_factor(payable)} μονάδες μισθού /25")
    return result


def _dec(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    parsed = _eu_float(value)
    return Decimal("0") if parsed is None else Decimal(str(parsed))


def _fmt_hours(hours: Decimal) -> str:
    return f"{hours.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}".replace(".", ",")


def _fmt_money(value: Decimal) -> str:
    return f"{money(value)}".replace(".", ",")


def _fmt_factor(value: Decimal) -> str:
    text = f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}".replace(".", ",")
    if "," in text:
        text = text.rstrip("0").rstrip(",")
    return text or "0"


def _line_formula(
    *,
    hours: Decimal,
    hourly: Decimal,
    family_percent: Decimal,
    zone_hourly: Decimal,
    zone_percent: Decimal,
    pay_hour: bool,
    amount: Decimal,
    family_label: str,
    zone: str,
    line_kind: str = "hour",
    preset_formula: str = "",
) -> str:
    if str(line_kind or "hour") == "bonus":
        return str(preset_formula or "").strip() or (
            f"{family_label} = {_fmt_money(amount)} €"
        )
    if str(line_kind or "hour") == "allowance":
        return (
            f"{_fmt_money(hourly)} € × {_fmt_factor(family_percent)}% "
            f"({family_label}) = {_fmt_money(amount)} €"
        )
    hrs = _fmt_hours(hours)
    zone_label = ZONE_LABELS.get(zone, zone)
    if not pay_hour and zone_percent <= 0:
        return (
            f"{hrs} ώρες {family_label} {zone_label}: ήδη μέσα στον μηνιαίο μισθό, "
            "χωρίς επιπλέον ευρώ."
        )
    if not pay_hour:
        return (
            f"{hrs} ώρες × {_fmt_money(zone_hourly)} € × {_fmt_factor(zone_percent)}% "
            f"({zone_label}) = {_fmt_money(amount)} €"
        )
    family_factor = Decimal(1) + family_percent / Decimal(100)
    if zone_percent <= 0:
        extra = (
            f" ({family_label} {_fmt_factor(family_percent)}%)" if family_percent else ""
        )
        return (
            f"{hrs} ώρες × {_fmt_money(hourly)} € × {_fmt_factor(family_factor)}"
            f"{extra} = {_fmt_money(amount)} €"
        )
    return (
        f"{hrs} ώρες × ({_fmt_money(hourly)} € × {_fmt_factor(family_factor)} "
        f"+ {_fmt_money(zone_hourly)} € × {_fmt_factor(zone_percent)}%) = {_fmt_money(amount)} €"
    )


def line_amount_from_fields(
    hours: Any,
    hourly: Any,
    family_percent: Any,
    zone_hourly: Any,
    zone_percent: Any,
    pay_hour: bool,
    line_kind: str = "hour",
) -> Decimal:
    if str(line_kind or "hour") == "bonus":
        return money(hourly)
    if str(line_kind or "hour") == "allowance":
        return money(_dec(hourly) * _dec(family_percent) / Decimal(100))
    hrs = _dec(hours)
    if hrs <= 0:
        return money(0)
    hour_pay = (
        _dec(hourly) * (Decimal(1) + _dec(family_percent) / Decimal(100))
        if pay_hour
        else Decimal(0)
    )
    zone_pay = _dec(zone_hourly) * (_dec(zone_percent) / Decimal(100))
    return money(hrs * (hour_pay + zone_pay))


def _is_allowance_line(line: dict[str, Any]) -> bool:
    return str(line.get("line_kind") or "hour") == "allowance"


def _is_bonus_line(line: dict[str, Any]) -> bool:
    return str(line.get("line_kind") or "hour") == "bonus"


def enrich_payroll_line(line: dict[str, Any]) -> dict[str, Any]:
    hours = _dec(line.get("hours"))
    hourly = _dec(line.get("hourly"))
    family_percent = _dec(line.get("family_percent"))
    zone_hourly = _dec(line.get("zone_hourly"))
    zone_percent = _dec(line.get("zone_percent"))
    pay_hour = bool(line.get("pay_hour"))
    line_kind = str(line.get("line_kind") or "hour")
    amount = line_amount_from_fields(
        hours, hourly, family_percent, zone_hourly, zone_percent, pay_hour, line_kind
    )
    updated = dict(line)
    updated["hours"] = float(hours)
    updated["hourly"] = float(hourly)
    updated["family_percent"] = float(family_percent)
    updated["zone_hourly"] = float(zone_hourly)
    updated["zone_percent"] = float(zone_percent)
    updated["pay_hour"] = pay_hour
    updated["line_kind"] = line_kind
    updated["amount"] = float(amount)
    updated["formula"] = _line_formula(
        hours=hours,
        hourly=hourly,
        family_percent=family_percent,
        zone_hourly=zone_hourly,
        zone_percent=zone_percent,
        pay_hour=pay_hour,
        amount=amount,
        family_label=str(line.get("family") or ""),
        zone=str(line.get("zone") or ""),
        line_kind=line_kind,
        preset_formula=str(line.get("formula") or ""),
    )
    return updated


def recalculate_employee_row(
    row: dict[str, Any],
    params: dict[str, str] | None = None,
    period_type: str | None = None,
) -> dict[str, Any]:
    lines = [enrich_payroll_line(line) for line in (row.get("lines") or [])]
    extra = money(
        sum(
            (
                Decimal(str(line["amount"]))
                for line in lines
                if line.get("family") != "Βάση" and _is_hour_line(line)
            ),
            Decimal("0"),
        )
    )
    base = money(
        sum(
            (Decimal(str(line["amount"])) for line in lines if line.get("family") == "Βάση" and _is_hour_line(line)),
            Decimal("0"),
        )
    )
    allowances = money(
        sum(
            (Decimal(str(line["amount"])) for line in lines if _is_allowance_line(line)),
            Decimal("0"),
        )
    )
    bonuses = money(
        sum(
            (Decimal(str(line["amount"])) for line in lines if _is_bonus_line(line)),
            Decimal("0"),
        )
    )
    period = money(row.get("period_salary"))
    updated = dict(row)
    updated["lines"] = lines
    updated["period_salary"] = float(period)
    updated["base_pay"] = float(base)
    updated["extra_pay"] = float(extra)
    updated["allowances_total"] = float(allowances)
    updated["bonuses_total"] = float(bonuses)
    updated["total"] = float(money(period + extra + base + allowances + bonuses))
    when = period_type or str(updated.get("period_type") or "month")
    return apply_withholdings_to_row(updated, params, period_type=when)


def _breakdown_lines(
    breakdown: dict[str, Any] | None,
    *,
    family_label: str,
    family_percent: Decimal,
    hourly: Decimal,
    zone_hourly: Decimal,
    params: dict[str, str],
    pay_hour: bool,
) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for zone in ZONE_KEYS:
        hrs = hours_from_minutes((breakdown or {}).get(zone))
        if hrs <= 0:
            continue
        zone_percent = (zone_rate(zone, params) * Decimal(100)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        lines.append(enrich_payroll_line({
            "line_kind": "hour",
            "family": family_label,
            "zone": ZONE_LABELS[zone],
            "zone_key": zone,
            "hours": float(hrs),
            "hourly": float(hourly),
            "family_percent": float(family_percent),
            "zone_hourly": float(zone_hourly),
            "zone_percent": float(zone_percent),
            "pay_hour": pay_hour,
        }))
    return lines


def _int_count(value: Any) -> int:
    parsed = _eu_float(value)
    if parsed is None:
        return 0
    return max(0, int(parsed))


def children_count_from_contract(contract: dict[str, Any] | None) -> int:
    return _int_count((contract or {}).get("arithmos_teknon"))


def prior_service_years_from_contract(contract: dict[str, Any] | None) -> Decimal:
    parsed = _eu_float((contract or {}).get("prior_service"))
    if parsed is None or parsed < 0:
        return Decimal("0")
    return Decimal(str(parsed))


def marital_code_from_contract(contract: dict[str, Any] | None) -> str:
    return map_marital_status((contract or {}).get("marital_status"))


def marriage_allowance_percent(marital_code: str, params: dict[str, str]) -> Decimal:
    codes = {
        part.strip()
        for part in str(params.get("marriage_marital_codes") or "").split(",")
        if part.strip()
    }
    if marital_code and marital_code in codes:
        return param_number(params, "marriage_percent")
    return Decimal("0")


def child_allowance_percent(children: int, params: dict[str, str]) -> Decimal:
    if children <= 0:
        return Decimal("0")
    if children >= 5:
        return param_number(params, "child_allowance_5plus_percent")
    return param_number(params, f"child_allowance_{children}_percent")


def seniority_allowance_percent(years: Decimal, params: dict[str, str]) -> Decimal:
    step_years = param_number(params, "seniority_years_per_step")
    per_step = param_number(params, "seniority_percent_per_step")
    max_steps = param_number(params, "seniority_max_steps")
    if step_years <= 0 or per_step <= 0 or years <= 0:
        return Decimal("0")
    steps = int(years // step_years)
    if max_steps > 0:
        steps = min(steps, int(max_steps))
    if steps <= 0:
        return Decimal("0")
    return per_step * Decimal(steps)


def _allowance_line(family: str, base: Decimal, percent: Decimal) -> dict[str, Any]:
    return enrich_payroll_line({
        "line_kind": "allowance",
        "family": family,
        "zone": "—",
        "zone_key": "",
        "hours": 0,
        "hourly": float(base),
        "family_percent": float(percent),
        "zone_hourly": 0,
        "zone_percent": 0,
        "pay_hour": False,
    })


def allowance_lines_for(
    *,
    base: Decimal,
    children: int,
    marital_code: str,
    prior_years: Decimal,
    params: dict[str, str],
) -> list[dict[str, Any]]:
    return [
        _allowance_line("Επίδομα γάμου", base, marriage_allowance_percent(marital_code, params)),
        _allowance_line("Επίδομα τέκνων", base, child_allowance_percent(children, params)),
        _allowance_line(
            "Επίδομα προϋπηρεσίας",
            base,
            seniority_allowance_percent(prior_years, params),
        ),
    ]


def _param_yes(params: dict[str, str], code: str, default: str = "ναι") -> bool:
    raw = str(params.get(code) or default).strip().lower()
    return raw in {"ναι", "yes", "1", "true"}


def _payout_monthly(params: dict[str, str], code: str, monthly_value: str) -> bool:
    raw = str(params.get(code) or "μήνας_καταβολής").strip().lower().replace(" ", "_")
    return raw == monthly_value.strip().lower().replace(" ", "_")


def _share_of(
    total: Decimal,
    part_days: int,
    whole_days: int,
) -> Decimal:
    if total <= 0 or part_days <= 0 or whole_days <= 0:
        return money(0)
    return money(total * Decimal(part_days) / Decimal(whole_days))


def _parse_md(value: Any, fallback_month: int, fallback_day: int) -> tuple[int, int]:
    text = str(value or "").strip().replace("/", "-")
    parts = [part for part in text.split("-") if part]
    if len(parts) >= 2:
        try:
            month = int(parts[-2])
            day = int(parts[-1])
            if 1 <= month <= 12 and 1 <= day <= 31:
                return month, day
        except ValueError:
            pass
    return fallback_month, fallback_day


def _date_in_year(year: int, month: int, day: int) -> date:
    for candidate in (day, 28, 27):
        try:
            return date(year, month, candidate)
        except ValueError:
            continue
    return date(year, month, 1)


def _as_contract_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return _as_date(value)


def _overlap_days(
    hire: date | None,
    departure: date | None,
    start: date,
    end: date,
) -> tuple[int, bool]:
    """Ημέρες εργασιακής σχέσης μέσα στο [start, end]. missing_hire=True αν δεν υπάρχει πρόσληψη."""
    missing = hire is None
    begin = start if hire is None else max(hire, start)
    stop = end if departure is None else min(departure, end)
    if stop < begin:
        return 0, missing
    return (stop - begin).days + 1, missing


def daily_wage_for(
    *,
    contract: dict[str, Any] | None,
    params: dict[str, str],
    hourly: Decimal | None,
    period_salary: Decimal,
    allowances: Decimal,
    include_allowances: bool,
) -> Decimal:
    base = period_salary
    if include_allowances:
        base += allowances
    if _is_worker(contract):
        weekly = _weekly_hours(contract)
        days = Decimal(_weekly_days(contract))
        if hourly and hourly > 0 and days > 0 and weekly is not None:
            return money(hourly * weekly / days)
        daily = param_number(params, "min_daily_wage")
        fulltime = _fulltime_weekly_hours(contract, params)
        if weekly is not None and fulltime > 0:
            return money(daily * weekly / fulltime)
        return money(daily)
    divisor = param_number(params, "leave_daily_divisor")
    if divisor <= 0:
        divisor = Decimal("25")
    return money(base / divisor)


def _gift_amount(
    *,
    days: int,
    period_days: int,
    full_period: bool,
    is_worker: bool,
    monthly_base: Decimal,
    daily: Decimal,
    employee_months: Decimal,
    worker_days: Decimal,
    step_days: Decimal,
    step_shares: Decimal,
    step_divisor: Decimal,
    leave_coeff: Decimal,
) -> Decimal:
    if days <= 0 or period_days <= 0:
        return money(0)
    if is_worker:
        full = money(daily * worker_days)
    else:
        full = money(monthly_base * employee_months)
    if full_period or days >= period_days:
        raw = full
    else:
        if step_days <= 0:
            return money(0)
        steps = Decimal(days) / step_days
        if is_worker:
            raw = money(daily * step_shares * steps)
        else:
            divisor = step_divisor if step_divisor > 0 else Decimal("1")
            raw = money(monthly_base * employee_months * (step_shares / divisor) * steps)
        if raw > full:
            raw = full
    coeff = leave_coeff if leave_coeff > 0 else Decimal("0")
    return money(raw * (Decimal("1") + coeff))


def _bonus_line(family: str, amount: Decimal, *, hours: Decimal, formula: str) -> dict[str, Any]:
    return enrich_payroll_line({
        "line_kind": "bonus",
        "family": family,
        "zone": "—",
        "zone_key": "",
        "hours": float(hours),
        "hourly": float(amount),
        "family_percent": 0,
        "zone_hourly": 0,
        "zone_percent": 0,
        "pay_hour": False,
        "formula": formula,
    })


def seasonal_bonus_lines_for(
    *,
    contract: dict[str, Any] | None,
    params: dict[str, str],
    period_type: str,
    period_from: date | None,
    period_to: date | None,
    hourly: Decimal | None,
    period_salary: Decimal,
    allowances: Decimal,
    warnings: list[str],
) -> list[dict[str, Any]]:
    if period_from is None or period_to is None:
        return []
    if period_type != "month" and not _param_yes(params, "bonus_on_week", "όχι"):
        return []
    include_allowances = _param_yes(params, "bonus_include_allowances")
    monthly_base = period_salary
    if include_allowances:
        monthly_base += allowances
    daily = daily_wage_for(
        contract=contract,
        params=params,
        hourly=hourly,
        period_salary=period_salary,
        allowances=allowances,
        include_allowances=include_allowances,
    )
    worker = _is_worker(contract)
    hire = _as_contract_date((contract or {}).get("hire_date"))
    departure = _as_contract_date(
        (contract or {}).get("departure_date") or (contract or {}).get("fixed_term_to")
    )
    leave_coeff = param_number(params, "bonus_leave_coeff")
    pay_month = period_to.month
    year = period_to.year
    lines: list[dict[str, Any]] = []

    def add_gift(prefix: str, label: str, fallback_from: tuple[int, int], fallback_to: tuple[int, int]) -> None:
        month_code = f"bonus_{prefix}_pay_month"
        wanted = int(param_number(params, month_code))
        if wanted <= 0:
            return
        monthly = _payout_monthly(params, "bonus_payout", "κάθε_μήνας_περιόδου")
        if not monthly and wanted != pay_month:
            return
        from_m, from_d = _parse_md(params.get(f"bonus_{prefix}_from_md"), *fallback_from)
        to_m, to_d = _parse_md(params.get(f"bonus_{prefix}_to_md"), *fallback_to)
        start = _date_in_year(year, from_m, from_d)
        end = _date_in_year(year, to_m, to_d)
        if end < start:
            return
        days, missing_hire = _overlap_days(hire, departure, start, end)
        period_days = (end - start).days + 1
        full_period = (
            (hire is None or hire <= start)
            and (departure is None or departure >= end)
            and days >= period_days
        )
        if missing_hire:
            warnings.append(f"Χωρίς ημερομηνία πρόσληψης· {label} ως πλήρες διάστημα")
        entitled = _gift_amount(
            days=days,
            period_days=period_days,
            full_period=full_period or missing_hire,
            is_worker=worker,
            monthly_base=monthly_base,
            daily=daily,
            employee_months=param_number(params, f"bonus_{prefix}_employee_months"),
            worker_days=param_number(params, f"bonus_{prefix}_worker_days"),
            step_days=param_number(params, f"bonus_{prefix}_step_days"),
            step_shares=param_number(params, f"bonus_{prefix}_step_shares"),
            step_divisor=param_number(params, f"bonus_{prefix}_step_divisor"),
            leave_coeff=leave_coeff,
        )
        if entitled <= 0:
            return
        month_days = days
        amount = entitled
        if monthly:
            month_days, _ = _overlap_days(
                hire, departure, max(period_from, start), min(period_to, end),
            )
            amount = _share_of(entitled, month_days, days)
            if amount <= 0:
                return
        unit = "ημερομίσθια" if worker else "μισθοί"
        share_txt = ""
        if monthly:
            share_txt = (
                f" · μήνας {month_days}/{days} ημέρες σχέσης περιόδου "
            )
        formula = (
            f"{label}: {days} ημέρες σχέσης {start.strftime('%d/%m')}–{end.strftime('%d/%m')} "
            f"{share_txt}"
            f"· βάση {_fmt_money(daily if worker else monthly_base)} € "
            f"· πλήρες {_fmt_factor(param_number(params, f'bonus_{prefix}_worker_days' if worker else f'bonus_{prefix}_employee_months'))} {unit} "
            f"× (1 + {_fmt_factor(leave_coeff)}) = {_fmt_money(amount)} €"
        )
        lines.append(_bonus_line(label, amount, hours=Decimal(month_days), formula=formula))

    add_gift("christmas", "Δώρο Χριστουγέννων", (5, 1), (12, 31))
    add_gift("easter", "Δώρο Πάσχα", (1, 1), (4, 30))

    leave_month = int(param_number(params, "leave_allowance_pay_month"))
    leave_monthly = _payout_monthly(params, "leave_payout", "κάθε_μήνας")
    if leave_month > 0 and (leave_monthly or leave_month == pay_month):
        week_days = _weekly_days(contract)
        annual_days = param_number(
            params, "leave_days_6day" if week_days >= 6 else "leave_days_5day"
        )
        year_months = param_number(params, "leave_year_months")
        if year_months <= 0:
            year_months = Decimal("12")
        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)
        year_days, missing_hire = _overlap_days(hire, departure, year_start, year_end)
        if missing_hire:
            warnings.append("Χωρίς ημερομηνία πρόσληψης· επίδομα αδείας ως πλήρες έτος")
            months_worked = year_months
        elif year_days <= 0:
            months_worked = Decimal("0")
        elif hire is None or hire <= year_start:
            months_worked = year_months
        else:
            end_m = 12 if leave_monthly else period_to.month
            start_m = hire.month
            months_worked = Decimal(max(0, end_m - start_m + 1))
            if months_worked > year_months:
                months_worked = year_months
        leave_days = money(annual_days * months_worked / year_months) if year_months else money(0)
        entitled = money(daily * _dec(leave_days))
        amount = entitled
        shown_days = _dec(leave_days)
        if leave_monthly and entitled > 0:
            month_days, _ = _overlap_days(
                hire, departure, max(period_from, year_start), min(period_to, year_end),
            )
            amount = _share_of(entitled, month_days, year_days if year_days else month_days)
            shown_days = Decimal(month_days)
        if amount > 0:
            share_txt = ""
            if leave_monthly:
                share_txt = f" · μήνας {int(shown_days)}/{year_days} ημέρες έτους "
            formula = (
                f"Επίδομα αδείας: {_fmt_factor(leave_days)} ημέρες έτους "
                f"({_fmt_factor(months_worked)}/{_fmt_factor(year_months)} του έτους, "
                f"{week_days}ήμερο {_fmt_factor(annual_days)} ημέρες){share_txt}× "
                f"{_fmt_money(daily)} € = {_fmt_money(amount)} €"
            )
            lines.append(_bonus_line(
                "Επίδομα αδείας", amount, hours=shown_days, formula=formula,
            ))
    return lines


def _is_hour_line(line: dict[str, Any]) -> bool:
    return str(line.get("line_kind") or "hour") == "hour"


def efka_premium_exempt(params: dict[str, str] | None, row: dict[str, Any] | None = None) -> bool:
    if params:
        raw = str(params.get("efka_premium_exempt") or "ναι").strip().lower()
        return raw in {"ναι", "yes", "1", "true"}
    if row is None:
        return True
    return bool(row.get("efka_premium_exempt", True))


def supplementary_param_codes(fund_code: str) -> tuple[str, str]:
    code = str(fund_code or "001").zfill(3)
    if code == "002":
        return "efka_teka_employee_percent", "efka_teka_employer_percent"
    if code != "001":
        return (
            f"efka_aux_{code}_employee_percent",
            f"efka_aux_{code}_employer_percent",
        )
    return "efka_auxiliary_employee_percent", "efka_auxiliary_employer_percent"


def auxiliary_fund_fields(contract: dict[str, Any] | None) -> dict[str, str]:
    code = (epikourikiki_codes_from_data(contract or {}) or ["001"])[0]
    return {
        "epikourikiki_kod": code,
        "auxiliary_fund_label": supplementary_fund_short_label(code),
    }


def supplementary_branch_code(fund_code: str) -> str:
    code = str(fund_code or "001").zfill(3)
    if code == "001":
        return "auxiliary"
    if code == "002":
        return "teka"
    return f"aux_{code}"


def _efka_core_branches(params: dict[str, str], specs: tuple[tuple[str, str, str, str], ...]) -> list[dict[str, Any]]:
    branches: list[dict[str, Any]] = []
    for code, label, emp_code, er_code in specs:
        branches.append({
            "code": code,
            "label": label,
            "employee_percent": float(param_number(params, emp_code)),
            "employer_percent": float(param_number(params, er_code)),
        })
    return branches


def efka_branches_from_params(
    params: dict[str, str],
    contract: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> list[dict[str, Any]]:
    branches = _efka_core_branches(params, EFKA_CORE_BEFORE_AUX)
    for fund_code in epikourikiki_codes_from_data(contract or {}):
        emp_code, er_code = supplementary_param_codes(fund_code)
        label = supplementary_fund_short_label(fund_code)
        emp_pct = param_number(params, emp_code)
        er_pct = param_number(params, er_code)
        if (
            warnings is not None
            and emp_pct == 0
            and er_pct == 0
            and fund_code not in {"001", "002"}
        ):
            warnings.append(
                f"Χωρίς ποσοστά για {label} ({fund_code}) — όρισέ τα στις παραμέτρους μισθοδοσίας"
            )
        branches.append({
            "code": supplementary_branch_code(fund_code),
            "label": label,
            "employee_percent": float(emp_pct),
            "employer_percent": float(er_pct),
        })
    branches.extend(_efka_core_branches(params, EFKA_CORE_AFTER_AUX))
    lump_emp = param_number(params, "efka_lump_employee_percent")
    lump_er = param_number(params, "efka_lump_employer_percent")
    if lump_emp > 0 or lump_er > 0:
        branches.append({
            "code": "lump",
            "label": "Εφάπαξ",
            "employee_percent": float(lump_emp),
            "employer_percent": float(lump_er),
        })
    kyria = normalize_kyria_asfalish((contract or {}).get("kyria_asfalish") or "")
    if warnings is not None and kyria not in {"", "001"}:
        warnings.append(
            f"Κύρια ασφάλιση {main_insurance_short_label(kyria)} — "
            "τα ποσοστά σύνταξης/υγείας είναι του κοινού e-ΕΦΚΑ"
        )
    return branches


def _efka_period_ceiling(row: dict[str, Any], params: dict[str, str] | None, period_type: str) -> Decimal:
    if params:
        ceiling = param_number(params, "efka_monthly_ceiling")
        factor_code = "month_factor_worker" if row.get("pay_base_hours") else "month_factor_employee"
        factor = param_number(params, factor_code)
    else:
        ceiling = _dec(row.get("efka_monthly_ceiling"))
        factor = _dec(row.get("month_factor"))
    if period_type != "month" and factor > 0:
        ceiling = ceiling / factor
    return money(ceiling)


def insurable_earnings_for_row(
    row: dict[str, Any],
    params: dict[str, str] | None = None,
    *,
    period_type: str = "month",
) -> Decimal:
    if row.get("efka_insurable_manual"):
        return money(row.get("efka_insurable"))
    insurable = money(row.get("period_salary"))
    exempt = efka_premium_exempt(params, row)
    for line in row.get("lines") or []:
        kind = str(line.get("line_kind") or "hour")
        if kind in {"allowance", "bonus"}:
            insurable += money(line.get("amount"))
            continue
        if kind != "hour":
            continue
        if exempt:
            if line.get("pay_hour"):
                insurable += money(_dec(line.get("hours")) * _dec(line.get("hourly")))
        else:
            insurable += money(line.get("amount"))
    ceiling = _efka_period_ceiling(row, params, period_type)
    if ceiling > 0 and insurable > ceiling:
        insurable = ceiling
    return money(insurable)


def apply_efka_to_row(
    row: dict[str, Any],
    params: dict[str, str] | None = None,
    *,
    period_type: str = "month",
) -> dict[str, Any]:
    if params:
        warns = row.get("warnings")
        if not isinstance(warns, list):
            warns = []
            row["warnings"] = warns
        branches = efka_branches_from_params(params, row, warnings=warns)
        factor_code = "month_factor_worker" if row.get("pay_base_hours") else "month_factor_employee"
        row["efka_branches"] = branches
        row["efka_premium_exempt"] = efka_premium_exempt(params)
        row["efka_monthly_ceiling"] = float(param_number(params, "efka_monthly_ceiling"))
        row["month_factor"] = float(param_number(params, factor_code))
    else:
        branches = list(row.get("efka_branches") or [])
    period_type = str(row.get("period_type") or period_type or "month")
    row["period_type"] = period_type
    insurable = insurable_earnings_for_row(row, params, period_type=period_type)
    employee_total = Decimal("0")
    employer_total = Decimal("0")
    computed: list[dict[str, Any]] = []
    for branch in branches:
        emp_pct = _dec(branch.get("employee_percent"))
        er_pct = _dec(branch.get("employer_percent"))
        emp_amt = money(insurable * emp_pct / Decimal(100))
        er_amt = money(insurable * er_pct / Decimal(100))
        employee_total += emp_amt
        employer_total += er_amt
        computed.append({
            "code": branch.get("code"),
            "label": branch.get("label"),
            "employee_percent": float(emp_pct),
            "employer_percent": float(er_pct),
            "employee_amount": float(emp_amt),
            "employer_amount": float(er_amt),
            "formula": (
                f"{_fmt_money(insurable)} € × {_fmt_factor(emp_pct)}% "
                f"({branch.get('label')}) = {_fmt_money(emp_amt)} €"
            ),
        })
    row["efka_branches"] = computed
    row["efka_insurable"] = float(insurable)
    row["efka_employee"] = float(money(employee_total))
    row["efka_employer"] = float(money(employer_total))
    row["after_efka"] = float(money(_dec(row.get("total")) - employee_total))
    return row


def _tax_child_key(children: int) -> str:
    return "4plus" if children >= 4 else str(max(0, children))


def tax_age_group_for_row(row: dict[str, Any], params: dict[str, str] | None) -> str:
    raw = str(row.get("tax_age_group") or "").strip()
    if raw in {"over_30", "age_26_30", "under_25"}:
        return raw
    if params:
        fallback = str(params.get("tax_default_age_group") or "over_30").strip()
        if fallback in {"over_30", "age_26_30", "under_25"}:
            return fallback
    return "over_30"


def tax_brackets_for(
    children: int,
    age_group: str,
    params: dict[str, str],
) -> list[dict[str, Any]]:
    key = _tax_child_key(children)
    b1 = param_number(params, f"tax_b1_percent_{key}")
    b2 = param_number(params, f"tax_b2_percent_{key}")
    b3 = param_number(params, "tax_b3_percent_0") - (
        param_number(params, "tax_b3_child_step_percent") * Decimal(max(0, children))
    )
    if b3 < 0:
        b3 = Decimal("0")
    if age_group == "under_25":
        b1 = min(b1, param_number(params, "tax_young25_b1_percent"))
        b2 = min(b2, param_number(params, "tax_young25_b2_percent"))
    elif age_group == "age_26_30":
        b1 = min(b1, param_number(params, "tax_young30_b1_percent"))
        b2 = min(b2, param_number(params, "tax_young30_b2_percent"))
    percents = (
        b1,
        b2,
        b3,
        param_number(params, "tax_b4_percent"),
        param_number(params, "tax_b5_percent"),
        param_number(params, "tax_b6_percent"),
    )
    uptos = (
        param_number(params, "tax_bracket_1_upto"),
        param_number(params, "tax_bracket_2_upto"),
        param_number(params, "tax_bracket_3_upto"),
        param_number(params, "tax_bracket_4_upto"),
        param_number(params, "tax_bracket_5_upto"),
        None,
    )
    return [
        {"upto": None if upto is None else float(upto), "percent": float(pct)}
        for upto, pct in zip(uptos, percents)
    ]


def tax_credit_annual(annual: Decimal, children: int, params: dict[str, str]) -> Decimal:
    if children <= 0:
        credit = param_number(params, "tax_credit_0")
    elif children >= 5:
        extra = param_number(params, "tax_credit_extra_per_child") * Decimal(children - 5)
        credit = param_number(params, "tax_credit_5") + extra
    else:
        credit = param_number(params, f"tax_credit_{children}")
    exempt_from = int(param_number(params, "tax_credit_taper_exempt_from_children"))
    taper_from = param_number(params, "tax_credit_taper_from")
    if children < exempt_from and annual > taper_from:
        step = param_number(params, "tax_credit_taper_step")
        amount = param_number(params, "tax_credit_taper_amount")
        if step > 0:
            steps = int((annual - taper_from) // step)
            credit -= amount * Decimal(steps)
    if credit < 0:
        return money(0)
    return money(credit)


def annual_income_tax(
    annual: Decimal,
    *,
    children: int,
    age_group: str,
    params: dict[str, str],
) -> dict[str, Any]:
    annual = money(annual)
    brackets = tax_brackets_for(children, age_group, params)
    remaining = annual
    previous_limit = Decimal("0")
    gross = Decimal("0")
    computed: list[dict[str, Any]] = []
    for bracket in brackets:
        upto = bracket.get("upto")
        pct = _dec(bracket.get("percent"))
        if remaining <= 0:
            slice_amt = Decimal("0")
        elif upto is None:
            slice_amt = remaining
        else:
            width = _dec(upto) - previous_limit
            if width < 0:
                width = Decimal("0")
            slice_amt = remaining if remaining < width else width
        tax_amt = money(slice_amt * pct / Decimal(100))
        gross += tax_amt
        computed.append({
            "upto": upto,
            "percent": float(pct),
            "slice": float(money(slice_amt)),
            "amount": float(tax_amt),
            "formula": (
                f"{_fmt_money(slice_amt)} € × {_fmt_factor(pct)}% = {_fmt_money(tax_amt)} €"
            ),
        })
        remaining = money(remaining - slice_amt)
        if upto is not None:
            previous_limit = _dec(upto)
    gross = money(gross)
    credit = tax_credit_annual(annual, children, params)
    if credit > gross:
        credit = gross
    tax = money(gross - credit)
    return {
        "annual": float(annual),
        "gross_tax": float(gross),
        "credit": float(credit),
        "tax": float(tax),
        "brackets": computed,
        "formula": (
            f"ετήσιο {_fmt_money(annual)} € → φόρος κλίμακας {_fmt_money(gross)} € "
            f"− μείωση άρθ. 16 {_fmt_money(credit)} € = {_fmt_money(tax)} €"
        ),
    }


def apply_fmy_to_row(
    row: dict[str, Any],
    params: dict[str, str] | None = None,
    *,
    period_type: str = "month",
) -> dict[str, Any]:
    period_type = str(row.get("period_type") or period_type or "month")
    row["period_type"] = period_type
    children = max(0, int(row.get("children_count") or 0))
    age_group = tax_age_group_for_row(row, params)
    row["tax_age_group"] = age_group
    if row.get("fmy_manual"):
        fmy = money(row.get("fmy"))
        row["net"] = float(money(_dec(row.get("after_efka")) - fmy))
        row["fmy"] = float(fmy)
        return row
    if not params:
        params = {}
    salaries = param_number(params, "fmy_annual_salaries")
    if salaries <= 0:
        salaries = Decimal("14")
    factor = _dec(row.get("month_factor"))
    if factor <= 0 and params:
        factor_code = "month_factor_worker" if row.get("pay_base_hours") else "month_factor_employee"
        factor = param_number(params, factor_code)
    if period_type == "month" or factor <= 0:
        annualize = salaries
    else:
        annualize = salaries * factor
    taxable = money(row.get("after_efka"))
    bonuses = money(row.get("bonuses_total"))
    total = money(row.get("total"))
    insurable = money(row.get("efka_insurable"))
    bonus_after = money(0)
    regular_after = taxable
    if bonuses > 0 and taxable > 0:
        if insurable > 0:
            bonus_efka = money(money(row.get("efka_employee")) * bonuses / insurable)
            bonus_after = money(bonuses - bonus_efka)
        elif total > 0:
            bonus_after = money(taxable * bonuses / total)
        if bonus_after > taxable:
            bonus_after = taxable
        regular_after = money(taxable - bonus_after)
    annual = money(regular_after * annualize)
    result = annual_income_tax(annual, children=children, age_group=age_group, params=params)
    fmy_regular = money(_dec(result["tax"]) / annualize) if annualize else money(0)
    fmy_bonus = money(0)
    if bonus_after > 0:
        with_bonus = annual_income_tax(
            money(annual + bonus_after), children=children, age_group=age_group, params=params,
        )
        fmy_bonus = money(_dec(with_bonus["tax"]) - _dec(result["tax"]))
        result = with_bonus
    fmy = money(fmy_regular + fmy_bonus)
    row["tax_annual"] = result["annual"]
    row["tax_gross_annual"] = result["gross_tax"]
    row["tax_credit_annual"] = result["credit"]
    row["tax_annual_amount"] = result["tax"]
    row["tax_brackets"] = result["brackets"]
    row["tax_regular_after"] = float(regular_after)
    row["tax_bonus_after"] = float(bonus_after)
    row["fmy_regular"] = float(fmy_regular)
    row["fmy_bonus"] = float(fmy_bonus)
    formula = (
        f"{result['formula']} · παρακράτηση τακτικών "
        f"{_fmt_money(fmy_regular)} €"
    )
    if bonus_after > 0:
        formula += (
            f" + ΦΜΥ δώρων/αδείας {_fmt_money(fmy_bonus)} € "
            f"(εφάπαξ {_fmt_money(bonus_after)} €, όχι × {_fmt_factor(annualize)})"
        )
    formula += f" = {_fmt_money(fmy)} €"
    row["tax_formula"] = formula
    row["fmy"] = float(fmy)
    row["net"] = float(money(taxable - fmy))
    return row


def apply_withholdings_to_row(
    row: dict[str, Any],
    params: dict[str, str] | None = None,
    *,
    period_type: str = "month",
) -> dict[str, Any]:
    return apply_fmy_to_row(
        apply_efka_to_row(row, params, period_type=period_type),
        params,
        period_type=period_type,
    )


def payroll_for_employee(
    *,
    employee: dict[str, Any],
    contract: dict[str, Any] | None,
    params: dict[str, str],
    period_type: str = "month",
    period_from: date | None = None,
    period_to: date | None = None,
    schedule_rows: list[dict[str, Any]] | None = None,
    salary_override: Decimal | None = None,
    include_bonuses: bool = True,
) -> dict[str, Any]:
    warnings: list[str] = []
    hourly, wage_warnings = hourly_from_contract(contract, params)
    warnings.extend(wage_warnings)
    legal = legal_hourly(contract, params)
    if hourly is None:
        return apply_withholdings_to_row({
            "employee_afm": employee.get("employee_afm"),
            "eponymo": employee.get("eponymo") or "",
            "onoma": employee.get("onoma") or "",
            "characterization": map_characterization((contract or {}).get("characterization")),
            "characterization_label": "Εργάτης" if _is_worker(contract) else "Υπάλληλος",
            "hourly_wage": None,
            "legal_hourly": float(legal) if legal is not None else None,
            "period_salary": 0.0,
            "base_pay": 0.0,
            "zone_premiums": 0.0,
            "extra_pay": 0.0,
            "allowances_total": 0.0,
            "allowance_base": 0.0,
            "bonuses_total": 0.0,
            "children_count": children_count_from_contract(contract),
            "marital_status": marital_code_from_contract(contract),
            "prior_service_years": float(prior_service_years_from_contract(contract)),
            "kyria_asfalish": normalize_kyria_asfalish((contract or {}).get("kyria_asfalish") or "") if (contract or {}).get("kyria_asfalish") else "",
            **auxiliary_fund_fields(contract),
            "total": 0.0,
            "pay_base_hours": _is_worker(contract),
            "period_type": period_type,
            "lines": [],
            "warnings": warnings,
        }, params, period_type=period_type)
    use_legal = str(params.get("zone_premium_base") or "legal").strip().lower() != "contractual"
    zone_hourly = legal if (use_legal and legal is not None) else hourly
    if zone_hourly is None:
        zone_hourly = hourly
    if hourly < zone_hourly:
        hourly = zone_hourly
        warnings.append("Το καταβαλλόμενο ωρομίσθιο ανυψώθηκε στο νόμιμο")

    pay_base_hours = _is_worker(contract)
    lines: list[dict[str, Any]] = []
    lines.extend(_breakdown_lines(
        employee.get("premium_minutes") or {
            "day": employee.get("day"),
            "night": employee.get("night"),
            "sunday_holiday": employee.get("sunday_holiday"),
            "night_sunday_holiday": employee.get("night_sunday_holiday"),
        },
        family_label="Βάση",
        family_percent=Decimal("0"),
        hourly=hourly,
        zone_hourly=zone_hourly,
        params=params,
        pay_hour=pay_base_hours,
    ))
    for field, percent_code, label in EXTRA_FAMILIES:
        lines.extend(_breakdown_lines(
            employee.get(field),
            family_label=label,
            family_percent=param_number(params, percent_code),
            hourly=hourly,
            zone_hourly=zone_hourly,
            params=params,
            pay_hour=True,
        ))

    full_period_salary = period_salary_amount(contract, params, period_type=period_type)
    period_salary = salary_override if salary_override is not None else period_salary_amount(
        contract, params, period_type=period_type, period_from=period_from, period_to=period_to,
        schedule_rows=schedule_rows,
    )
    salary_details = salary_period_details(contract, period_from, period_to, schedule_rows) if salary_override is None and period_type == "month" and not pay_base_hours else {}
    base_pay = money(sum(
        (Decimal(str(line["amount"])) for line in lines if line["family"] == "Βάση"),
        Decimal("0"),
    ))
    children = children_count_from_contract(contract)
    marital = marital_code_from_contract(contract)
    prior_years = prior_service_years_from_contract(contract)
    allowance_base = (period_salary if not pay_base_hours else base_pay)
    lines.extend(allowance_lines_for(
        base=allowance_base,
        children=children,
        marital_code=marital,
        prior_years=prior_years,
        params=params,
    ))
    allowances_now = money(sum(
        (Decimal(str(line["amount"])) for line in lines if _is_allowance_line(line)),
        Decimal("0"),
    ))
    lines.extend(seasonal_bonus_lines_for(
        contract=contract,
        params=params,
        period_type=period_type,
        period_from=period_from,
        period_to=period_to,
        hourly=hourly,
        period_salary=full_period_salary,
        allowances=money(sum((Decimal(str(line["amount"])) for line in allowance_lines_for(
            base=full_period_salary, children=children, marital_code=marital,
            prior_years=prior_years, params=params,
        )), Decimal(0))) if not pay_base_hours else allowances_now,
        warnings=warnings,
    ) if include_bonuses else [])
    if not contract:
        warnings.append("Δεν βρέθηκε τρέχουσα σύμβαση")
    return recalculate_employee_row({
        "employee_afm": employee.get("employee_afm"),
        "eponymo": employee.get("eponymo") or "",
        "onoma": employee.get("onoma") or "",
        "characterization": map_characterization((contract or {}).get("characterization")),
        "characterization_label": "Εργάτης" if pay_base_hours else "Υπάλληλος",
        "salary": (contract or {}).get("salary"),
        "hourly_wage": float(hourly),
        "legal_hourly": float(zone_hourly),
        "period_salary": float(period_salary),
        "salary_full_period": float(full_period_salary),
        **salary_details,
        "zone_premiums": float(base_pay) if not pay_base_hours else float(
            money(sum(
                (
                    Decimal(str(line["amount"]))
                    for line in lines
                    if line["family"] == "Βάση" and line["zone"] != "Ημέρας"
                ),
                Decimal("0"),
            ))
        ),
        "allowance_base": float(allowance_base),
        "children_count": children,
        "marital_status": marital,
        "prior_service_years": float(prior_years),
        "hire_date": str((contract or {}).get("hire_date") or "")[:10],
        "departure_date": str((contract or {}).get("departure_date") or "")[:10],
        "kyria_asfalish": (
            normalize_kyria_asfalish((contract or {}).get("kyria_asfalish") or "")
            if (contract or {}).get("kyria_asfalish")
            else ""
        ),
        **auxiliary_fund_fields(contract),
        "pay_base_hours": pay_base_hours,
        "period_type": period_type,
        "lines": lines,
        "warnings": warnings,
    }, params=params, period_type=period_type)


def build_payroll_report(
    timekeeping: dict[str, Any],
    contracts_by_afm: dict[str, dict[str, Any]],
    params: dict[str, str],
    *,
    period_type: str = "month",
    period_from: date | None = None,
    period_to: date | None = None,
    schedule_rows: list[dict[str, Any]] | None = None,
    contract_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    from app.payroll_contracts import contract_segments, segmented_payroll
    histories, days = {}, {}
    for row in contract_history or []:
        histories.setdefault(payroll_afm_key(row.get("employee_afm")), []).append(row)
    for row in timekeeping.get("days") or []:
        days.setdefault(payroll_afm_key(row.get("employee_afm")), []).append(row)
    schedules = {}
    for row in schedule_rows or []:
        schedules.setdefault(payroll_afm_key(row.get("employee_afm")), []).append(row)
    employees = []
    for item in timekeeping.get("employees") or []:
        afm = payroll_afm_key(item.get("employee_afm"))
        contract = contracts_by_afm.get(afm) or contracts_by_afm.get(str(item.get("employee_afm") or ""))
        try:
            segments = contract_segments(histories.get(afm), contract, period_from, period_to)
            employees.append(segmented_payroll(item, segments, days.get(afm), schedules.get(afm),
                params, period_type, period_from, period_to))
        except ValueError as ex:
            raise ValueError(f"{item.get('eponymo') or ''} {item.get('onoma') or ''} ({afm}): {ex}") from ex
    grand = money(sum((Decimal(str(row["total"])) for row in employees), Decimal("0")))
    grand_efka = money(sum((Decimal(str(row.get("efka_employee") or 0)) for row in employees), Decimal("0")))
    grand_after = money(sum((Decimal(str(row.get("after_efka") or 0)) for row in employees), Decimal("0")))
    grand_employer = money(sum((Decimal(str(row.get("efka_employer") or 0)) for row in employees), Decimal("0")))
    grand_fmy = money(sum((Decimal(str(row.get("fmy") or 0)) for row in employees), Decimal("0")))
    grand_net = money(sum((Decimal(str(row.get("net") or 0)) for row in employees), Decimal("0")))
    grand_bonuses = money(sum((Decimal(str(row.get("bonuses_total") or 0)) for row in employees), Decimal("0")))
    return {
        "calculation_version": "payroll-v8-contract-segments",
        "period_type": period_type,
        "period_from": period_from.isoformat() if period_from else None,
        "period_to": period_to.isoformat() if period_to else None,
        "parameters": dict(params),
        "employees": employees,
        "counts": {"employees": len(employees)},
        "grand_total": float(grand),
        "grand_efka_employee": float(grand_efka),
        "grand_after_efka": float(grand_after),
        "grand_efka_employer": float(grand_employer),
        "grand_fmy": float(grand_fmy),
        "grand_net": float(grand_net),
        "grand_bonuses": float(grand_bonuses),
    }


def _registry_digits(value: Any, max_len: int) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())[:max_len]


def insurance_days_from_timekeeping(
    timekeeping: dict[str, Any] | None,
    employee_afm: str,
) -> int:
    key = payroll_afm_key(employee_afm)
    if not key:
        return 0
    seen: set[str] = set()
    for day in (timekeeping or {}).get("days") or []:
        if payroll_afm_key(day.get("employee_afm")) != key:
            continue
        if int(day.get("recognized_work_minutes") or 0) <= 0:
            continue
        work_date = str(day.get("work_date") or "")[:10]
        if work_date:
            seen.add(work_date)
    return len(seen)


def build_apd_preview(
    row: dict[str, Any],
    *,
    store: dict[str, Any] | None = None,
    period_from: str | None = None,
    period_to: str | None = None,
) -> dict[str, Any]:
    store = store or {}
    ame = _registry_digits(row.get("employer_ame") or store.get("ame"), 20)
    amka = _registry_digits(row.get("amka"), 11)
    ama = _registry_digits(row.get("amika") or row.get("ama"), 20)
    gaps: list[str] = []
    if not ame:
        gaps.append("Λείπει ΑΜΕ εργοδότη — συμπληρώστε το στις Ρυθμίσεις καταστήματος.")
    if len(amka) != 11:
        gaps.append("Λείπει ΑΜΚΑ εργαζομένου — έρχεται από EX_BASE_05 στο συγχρονισμό.")
    if not ama:
        gaps.append("Λείπει ΑΜΑ (AmIka) εργαζομένου — έρχεται από EX_BASE_05 στο συγχρονισμό.")
    bonuses = money(row.get("bonuses_total"))
    insurable = money(row.get("efka_insurable"))
    regular = money(max(Decimal("0"), insurable - bonuses))
    packages: list[dict[str, Any]] = []
    days = int(row.get("insurance_days") or 0)
    if regular > 0:
        packages.append({
            "code": "regular",
            "label": "Τακτικές αποδοχές",
            "amount": float(regular),
            "insurance_days": days,
        })
    if bonuses > 0:
        packages.append({
            "code": "bonus",
            "label": "Δώρα / επίδομα αδείας",
            "amount": float(bonuses),
            "insurance_days": 0,
        })
    preview = {
        "ready": not gaps,
        "gaps": gaps,
        "note": "Προεπισκόπηση ΑΠΔ e-ΕΦΚΑ. Το XML είναι προσχέδιο από τη μισθοδοσία, όχι επίσημη υποβολή.",
        "employer_ame": ame,
        "employer_afm": str(store.get("employer_afm") or row.get("employer_afm") or ""),
        "employer_kad": str(store.get("kad_code") or row.get("employer_kad") or ""),
        "employee_afm": str(row.get("employee_afm") or ""),
        "amka": amka,
        "ama": ama,
        "eponymo": row.get("eponymo") or "",
        "onoma": row.get("onoma") or "",
        "kyria_asfalish": row.get("kyria_asfalish") or "001",
        "auxiliary_fund_code": row.get("epikourikiki_kod") or "001",
        "auxiliary_fund_label": row.get("auxiliary_fund_label") or "",
        "insurance_days": days,
        "insurable": float(insurable),
        "packages": packages,
        "efka_branches": list(row.get("efka_branches") or []),
        "efka_employee": float(money(row.get("efka_employee"))),
        "efka_employer": float(money(row.get("efka_employer"))),
        "period_from": period_from or str(row.get("period_from") or ""),
        "period_to": period_to or str(row.get("period_to") or ""),
        "hire_date": str(row.get("hire_date") or ""),
    }
    preview["xml"] = employee_apd_xml(preview)
    return preview


def attach_apd_identity(
    payroll: dict[str, Any],
    *,
    store: dict[str, Any] | None,
    employees_by_afm: dict[str, dict[str, Any]] | None = None,
    timekeeping: dict[str, Any] | None = None,
) -> dict[str, Any]:
    store = store or {}
    employees_by_afm = employees_by_afm or {}
    for row in payroll.get("employees") or []:
        emp = employees_by_afm.get(payroll_afm_key(row.get("employee_afm"))) or {}
        row["amka"] = str(emp.get("amka") or "")
        row["amika"] = str(emp.get("amika") or "")
        if emp.get("hire_date") and not row.get("hire_date"):
            row["hire_date"] = emp.get("hire_date")
        row["employer_ame"] = str(store.get("ame") or "")
        row["employer_kad"] = str(store.get("kad_code") or "")
        row["insurance_days"] = insurance_days_from_timekeeping(
            timekeeping, str(row.get("employee_afm") or "")
        )
        row["apd"] = build_apd_preview(
            row,
            store=store,
            period_from=str(payroll.get("period_from") or ""),
            period_to=str(payroll.get("period_to") or ""),
        )
    payroll["apd_xml"] = store_apd_xml(
        payroll.get("employees") or [],
        store=store,
        period_from=str(payroll.get("period_from") or ""),
        period_to=str(payroll.get("period_to") or ""),
    )
    return payroll


def _xml_pretty(root: Element) -> str:
    raw = tostring(root, encoding="utf-8")
    return parseString(raw).toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")


def _apd_employee_element(parent: Element, apd: dict[str, Any]) -> None:
    person = SubElement(parent, "Asfalismenos")
    person.set("AMKA", str(apd.get("amka") or ""))
    person.set("AMA", str(apd.get("ama") or ""))
    person.set("AFM", str(apd.get("employee_afm") or ""))
    SubElement(person, "Eponymo").text = str(apd.get("eponymo") or "")
    SubElement(person, "Onoma").text = str(apd.get("onoma") or "")
    if apd.get("hire_date"):
        SubElement(person, "HmProslipsis").text = str(apd.get("hire_date") or "")
    SubElement(person, "KyriaAsfalisi").text = str(apd.get("kyria_asfalish") or "001")
    SubElement(person, "Epikourikiki").text = str(
        apd.get("auxiliary_fund_code") or "001"
    )
    SubElement(person, "HmeresAsfalisis").text = str(int(apd.get("insurance_days") or 0))
    SubElement(person, "AsfalisteesApodoxes").text = f"{money(apd.get('insurable')):.2f}"
    eisfores = SubElement(person, "Eisfores")
    eisfores.set("asfalismenou", f"{money(apd.get('efka_employee')):.2f}")
    eisfores.set("ergodoti", f"{money(apd.get('efka_employer')):.2f}")
    for package in apd.get("packages") or []:
        pak = SubElement(person, "Paketo")
        pak.set("kod", str(package.get("code") or ""))
        pak.set("hmeres", str(int(package.get("insurance_days") or 0)))
        pak.set("apodoxes", f"{money(package.get('amount')):.2f}")
        pak.text = str(package.get("label") or "")
    for branch in apd.get("efka_branches") or []:
        klados = SubElement(person, "Klados")
        klados.set("kod", str(branch.get("code") or ""))
        klados.set("asfalismenou", f"{money(branch.get('employee_amount')):.2f}")
        klados.set("ergodoti", f"{money(branch.get('employer_amount')):.2f}")
        klados.text = str(branch.get("label") or "")


def employee_apd_xml(apd: dict[str, Any]) -> str:
    root = Element("APD")
    root.set("version", "preview")
    employer = SubElement(root, "Ergodotis")
    employer.set("AME", str(apd.get("employer_ame") or ""))
    employer.set("AFM", str(apd.get("employer_afm") or ""))
    employer.set("KAD", str(apd.get("employer_kad") or ""))
    period = SubElement(root, "Periodos")
    period.set("apo", str(apd.get("period_from") or ""))
    period.set("eos", str(apd.get("period_to") or ""))
    _apd_employee_element(root, apd)
    return _xml_pretty(root)


def store_apd_xml(
    employees: list[dict[str, Any]],
    *,
    store: dict[str, Any] | None = None,
    period_from: str = "",
    period_to: str = "",
) -> str:
    store = store or {}
    root = Element("APD")
    root.set("version", "preview")
    employer = SubElement(root, "Ergodotis")
    first = (employees[0].get("apd") if employees else None) or {}
    employer.set("AME", str(store.get("ame") or first.get("employer_ame") or ""))
    employer.set("AFM", str(store.get("employer_afm") or first.get("employer_afm") or ""))
    employer.set("KAD", str(store.get("kad_code") or first.get("employer_kad") or ""))
    period = SubElement(root, "Periodos")
    period.set("apo", period_from)
    period.set("eos", period_to)
    for row in employees:
        apd = row.get("apd") or {}
        _apd_employee_element(root, apd)
    return _xml_pretty(root)
