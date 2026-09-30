const qs = new URLSearchParams(location.search);
const weekFrom = qs.get("week_from") || "";
const year = qs.get("year") || "";
const month = qs.get("month") || "";
let timekeepingData = null;
let payrollData = null;
let payrollOriginal = null;
let payrollModalIndex = null;

function esc(value) { return Office.escapeHtml(String(value ?? "")); }
function duration(minutes) {
  const value = Math.max(0, Number(minutes || 0));
  return new Intl.NumberFormat("el-GR", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(value / 60);
}
function displayDate(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value || ""));
  return match ? `${match[3]}/${match[2]}/${match[1]}` : String(value || "");
}
function money(value) {
  return new Intl.NumberFormat("el-GR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(value || 0));
}
function parseNum(value) {
  const text = String(value ?? "").trim().replace(/\s/g, "").replace(",", ".");
  if (!text) return 0;
  const n = Number(text);
  return Number.isFinite(n) ? n : 0;
}
function round2(value) {
  return Math.round((Number(value) + Number.EPSILON) * 100) / 100;
}
function fmtFactor(value) {
  return new Intl.NumberFormat("el-GR", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(Number(value || 0));
}
function fmtHours(value) {
  return new Intl.NumberFormat("el-GR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(value || 0));
}
function employeeName(row) {
  return `${row?.eponymo || ""} ${row?.onoma || ""}`.trim() || "—";
}
function canViewPayroll() {
  return Boolean(document.getElementById("payrollEmbed"));
}

document.addEventListener("DOMContentLoaded", async () => {
  Office.setActiveNav("apologistic");
  document.getElementById("timekeepingBack").href = buildBackHref();
  document.getElementById("timekeepingExport").addEventListener("click", () => downloadExcel("summary"));
  document.getElementById("timekeepingDetailedExport").addEventListener("click", () => downloadExcel("detailed"));
  bindPayrollModal();
  bindApdModal();
  bindEmployeeDetailModal();
  document.getElementById("payrollExport")?.addEventListener("click", downloadPayrollExcel);
  document.getElementById("payrollApdXml")?.addEventListener("click", downloadPayrollApdXml);
  try {
    const active = await Office.fetchActiveStore();
    Office.applyActiveStoreChrome(active);
    if (!isWeekMode() && !isMonthMode()) {
      throw new Error("Λείπει έγκυρη εβδομάδα ή μήνας ωρομέτρησης.");
    }
    await loadTimekeeping();
  } catch (error) {
    document.getElementById("timekeepingWrap").innerHTML = `<p style="color:var(--err);">${esc(error.message || error)}</p>`;
  }
});

function isWeekMode() {
  return /^\d{4}-\d{2}-\d{2}$/.test(weekFrom);
}

function isMonthMode() {
  const y = Number(year || 0);
  const m = Number(month || 0);
  return Number.isInteger(y) && y >= 2000 && Number.isInteger(m) && m >= 1 && m <= 12;
}

function periodPayload() {
  if (isMonthMode()) return { year: Number(year), month: Number(month) };
  return { week_from: weekFrom };
}

function buildBackHref() {
  const params = new URLSearchParams();
  const mode = String(qs.get("origin_mode") || "").trim();
  if (mode) params.set("mode", mode);
  const originWeekFrom = String(qs.get("origin_week_from") || "").trim();
  if (originWeekFrom) params.set("week_from", originWeekFrom);
  const originYear = String(qs.get("origin_year") || "").trim();
  const originMonth = String(qs.get("origin_month") || "").trim();
  if (originYear) params.set("year", originYear);
  if (originMonth) params.set("month", originMonth);
  const originFrom = String(qs.get("origin_from") || "").trim();
  const originTo = String(qs.get("origin_to") || "").trim();
  if (originFrom) params.set("from", originFrom);
  if (originTo) params.set("to", originTo);
  const originFilter = String(qs.get("origin_filter") || "").trim();
  if (originFilter) params.set("filter", originFilter);
  const originSelectedDate = String(qs.get("origin_selected_date") || "").trim();
  if (originSelectedDate) params.set("selected_date", originSelectedDate);
  return `/ui/apologistic${params.toString() ? `?${params.toString()}` : ""}`;
}

function problemWeekHref(weekFrom) {
  const params = new URLSearchParams();
  params.set("mode", "week");
  params.set("week_from", String(weekFrom || ""));
  params.set("filter", "review");
  return `/ui/apologistic?${params.toString()}`;
}

function renderProblemWeeksError(message, problemWeeks) {
  const rows = Array.isArray(problemWeeks) ? problemWeeks : [];
  const links = rows.length
    ? `<div class="timekeeping-problem-weeks">` +
      rows.map((week) =>
        `<a class="btn btn-secondary timekeeping-problem-link" href="${esc(problemWeekHref(week.week_from))}">` +
        `${esc(week.label || `${displayDate(week.week_from)}–${displayDate(week.week_to)}`)}` +
        `</a>`
      ).join("") +
      `</div>`
    : "";
  document.getElementById("timekeepingWrap").innerHTML =
    `<div class="timekeeping-problem-box">` +
    `<p class="timekeeping-problem-text">${esc(message)}</p>` +
    (rows.length ? `<p class="timekeeping-problem-hint">Προβληματικές εβδομάδες:</p>${links}` : "") +
    `</div>`;
}

async function loadTimekeeping() {
  const res = await fetch("/api/apologistic/timekeeping/preview", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(periodPayload()),
  });
  const data = await Office.parseJson(res);
  if (!res.ok) {
    if (Array.isArray(data.problem_weeks) && data.problem_weeks.length) {
      renderProblemWeeksError(data.error || `HTTP ${res.status}`, data.problem_weeks);
      return;
    }
    throw new Error(data.error || `HTTP ${res.status}`);
  }
  timekeepingData = data;
  if (data.period_type === "month") {
    document.getElementById("timekeepingMeta").textContent =
      `${data.store?.name || "Κατάστημα"} · ${displayDate(data.period_from)} – ${displayDate(data.period_to)} · ${data.calculation_version}`;
  } else {
    document.getElementById("timekeepingMeta").textContent =
      `${data.store?.name || "Κατάστημα"} · ${displayDate(data.week_from)} – ${displayDate(data.week_to)} · ${data.calculation_version}`;
  }
  document.getElementById("timekeepingSummary").innerHTML =
    `<div class="card apologistic-kpi"><span>Εργαζόμενοι</span><strong>${data.counts?.employees || 0}</strong></div>` +
    `<div class="card apologistic-kpi"><span>Ημέρες</span><strong>${data.counts?.days || 0}</strong></div>` +
    `<div class="card apologistic-kpi apologistic-kpi--ok"><span>Κατάσταση</span><strong>Σ / Μ</strong></div>`;
  renderHours(data.employees || [], { collapsed: canViewPayroll() });
  if (canViewPayroll()) await loadPayroll();
}

function renderHours(rows, { collapsed } = { collapsed: false }) {
  const zones = [
    ["day", "Ημέρας"], ["night", "Νύχτας"],
    ["sunday_holiday", "Κυρ/Αργίας"],
    ["night_sunday_holiday", "Νύχτας/Κυρ-Αργίας"],
  ];
  const families = [
    ["overwork_breakdown", "Υπερεργασία 20%"],
    ["partial_additional_12_breakdown", "Μερική 12%"],
    ["overtime_40_breakdown", "Υπερωρία 40%"],
    ["overtime_60_breakdown", "Υπερωρία 60%"],
    ["overtime_120_breakdown", "Κατ’ εξαίρεση"],
    ["sixth_day_breakdown", "6η ημέρα 30%"],
    ["sixth_day_above_48_breakdown", "6η ημέρα άνω των 48 ωρών"],
    ["exception_sixth_day_above_48_breakdown", "Κατ’ εξαίρεση 6η ημέρα άνω των 48 ωρών"],
  ];
  const familyHeaders = families.map(([, label]) =>
    `<th colspan="4">${esc(label)}</th>`
  ).join("");
  const zoneHeaders = zones.map(([, label]) => `<th>${esc(label)}</th>`).join("");
  const detailHeaders = `<th>Βάση (ώρες)</th>${zoneHeaders}${families.map(() => zoneHeaders).join("")}`;
  const breakdownCells = (row, field) => zones.map(([key]) =>
    `<td>${duration(row[field]?.[key])}</td>`
  ).join("");
  const table =
    `<div class="timekeeping-hours-scroll"><table class="data apologistic-timekeeping-table"><thead>` +
    `<tr><th rowspan="2" class="work-log-action-cell" aria-label="Στοιχεία σύμβασης"></th>` +
    `<th rowspan="2">Εργαζόμενος</th><th colspan="5">Αναγνωρισμένη βάση</th>${familyHeaders}</tr>` +
    `<tr>${detailHeaders}</tr></thead><tbody>${rows.map((row) => `<tr>` +
      `<td class="work-log-action-cell">${employeeDetailButton(row)}</td>` +
      `<td><div class="payroll-list-name"><span>${esc(`${row.eponymo || ""} ${row.onoma || ""}`.trim() || "—")}</span></div><small>${esc(row.employee_afm)}</small></td>` +
      `<td>${duration(row.recognized_work_minutes)}</td><td>${duration(row.day)}</td>` +
      `<td>${duration(row.night)}</td><td>${duration(row.sunday_holiday)}</td>` +
      `<td>${duration(row.night_sunday_holiday)}</td>` +
      families.map(([field]) => breakdownCells(row, field)).join("") + `</tr>`
    ).join("")}</tbody></table></div>`;
  const wrap = document.getElementById("timekeepingWrap");
  if (collapsed) {
    wrap.innerHTML =
      `<details class="timekeeping-hours-details"><summary>Ανάλυση ωρών ωρομέτρησης</summary>${table}</details>`;
  } else {
    wrap.innerHTML = table;
  }
}

function lineAmount(line) {
  if (line.line_kind === "bonus") return round2(parseNum(line.hourly));
  if (line.line_kind === "allowance") {
    return round2(parseNum(line.hourly) * parseNum(line.family_percent) / 100);
  }
  const hours = parseNum(line.hours);
  if (hours <= 0) return 0;
  const hourPay = line.pay_hour
    ? parseNum(line.hourly) * (1 + parseNum(line.family_percent) / 100)
    : 0;
  const zonePay = parseNum(line.zone_hourly) * (parseNum(line.zone_percent) / 100);
  return round2(hours * (hourPay + zonePay));
}

function lineFormula(line) {
  const amount = money(line.amount);
  const family = line.family || "";
  if (line.line_kind === "bonus") {
    return line.formula || `${family} = ${amount} €`;
  }
  if (line.line_kind === "allowance") {
    return `${money(line.hourly)} € × ${fmtFactor(line.family_percent)}% (${family}) = ${amount} €`;
  }
  const hours = fmtHours(parseNum(line.hours));
  const zone = line.zone || "";
  if (!line.pay_hour && parseNum(line.zone_percent) <= 0) {
    return `${hours} ώρες ${family} ${zone}: ήδη μέσα στον μηνιαίο μισθό, χωρίς επιπλέον ευρώ.`;
  }
  if (!line.pay_hour) {
    return `${hours} ώρες × ${money(line.zone_hourly)} € × ${fmtFactor(line.zone_percent)}% (${zone}) = ${amount} €`;
  }
  const familyFactor = 1 + parseNum(line.family_percent) / 100;
  if (parseNum(line.zone_percent) <= 0) {
    const extra = parseNum(line.family_percent)
      ? ` (${family} ${fmtFactor(line.family_percent)}%)`
      : "";
    return `${hours} ώρες × ${money(line.hourly)} € × ${fmtFactor(familyFactor)}${extra} = ${amount} €`;
  }
  return `${hours} ώρες × (${money(line.hourly)} € × ${fmtFactor(familyFactor)} + ${money(line.zone_hourly)} € × ${fmtFactor(line.zone_percent)}%) = ${amount} €`;
}

function applyEmployee(row) {
  const lines = Array.isArray(row.lines) ? row.lines : [];
  for (const line of lines) {
    line.amount = lineAmount(line);
    line.formula = lineFormula(line);
  }
  row.base_pay = round2(lines.filter((line) => line.family === "Βάση" && line.line_kind === "hour").reduce((sum, line) => sum + Number(line.amount || 0), 0));
  row.extra_pay = round2(lines.filter((line) => line.family !== "Βάση" && line.line_kind === "hour").reduce((sum, line) => sum + Number(line.amount || 0), 0));
  row.allowances_total = round2(lines.filter((line) => line.line_kind === "allowance").reduce((sum, line) => sum + Number(line.amount || 0), 0));
  row.bonuses_total = round2(lines.filter((line) => line.line_kind === "bonus").reduce((sum, line) => sum + Number(line.amount || 0), 0));
  row.total = round2(parseNum(row.period_salary) + row.base_pay + row.extra_pay + row.allowances_total + row.bonuses_total);
  applyEfka(row);
  applyFmy(row);
  return row;
}

function payrollParams() {
  return payrollData?.parameters || {};
}

const TAX_PARAM_DEFAULTS = {
  tax_bracket_1_upto: 10000,
  tax_bracket_2_upto: 20000,
  tax_bracket_3_upto: 30000,
  tax_bracket_4_upto: 40000,
  tax_bracket_5_upto: 60000,
  tax_b1_percent_0: 9,
  tax_b1_percent_1: 9,
  tax_b1_percent_2: 9,
  tax_b1_percent_3: 9,
  tax_b1_percent_4plus: 0,
  tax_b2_percent_0: 20,
  tax_b2_percent_1: 18,
  tax_b2_percent_2: 16,
  tax_b2_percent_3: 9,
  tax_b2_percent_4plus: 0,
  tax_b3_percent_0: 26,
  tax_b3_child_step_percent: 2,
  tax_b4_percent: 34,
  tax_b5_percent: 39,
  tax_b6_percent: 44,
  tax_young25_b1_percent: 0,
  tax_young25_b2_percent: 0,
  tax_young30_b1_percent: 9,
  tax_young30_b2_percent: 9,
  tax_credit_0: 777,
  tax_credit_1: 900,
  tax_credit_2: 1120,
  tax_credit_3: 1340,
  tax_credit_4: 1580,
  tax_credit_5: 1780,
  tax_credit_extra_per_child: 220,
  tax_credit_taper_from: 12000,
  tax_credit_taper_amount: 20,
  tax_credit_taper_step: 1000,
  tax_credit_taper_exempt_from_children: 5,
  fmy_annual_salaries: 14,
};

function taxParamNum(code) {
  const raw = payrollParams()[code];
  if (raw == null || String(raw).trim() === "") {
    return Number(TAX_PARAM_DEFAULTS[code] ?? 0);
  }
  return parseNum(raw);
}

function efkaParamPercent(code) {
  return parseNum(payrollParams()[code]);
}

const AUX_FUND_SHORT = {
  "001": "ΕΤΕΑΕΠ",
  "002": "ΤΕΚΑ",
  "003": "ΕΤΕΑΠΕΠ",
  "004": "ΤΕΑΥΦΕ",
  "005": "ΤΕΑΥΕΤ",
  "006": "ΤΕΑ-ΕΑΠΑΕ",
  "007": "ΕΔΟΕΑΠ",
  "008": "ΜΤΠΥ",
  "009": "ΜΤΠΥ ΤτΕ",
  "010": "ΚΕΑΝ",
};

function normalizeAuxFundCode(value) {
  const text = String(value || "").trim().toUpperCase();
  const match = text.match(/^(\d{1,10})/);
  if (match && match[1] !== "0") {
    const padded = match[1].length <= 3 ? match[1].padStart(3, "0") : match[1];
    if (AUX_FUND_SHORT[padded]) return padded;
  }
  if (text.includes("ΤΕΚΑ")) return "002";
  return "001";
}

function auxiliaryParamCodes(fundCode) {
  if (fundCode === "002") return ["efka_teka_employee_percent", "efka_teka_employer_percent"];
  if (fundCode !== "001") {
    return [`efka_aux_${fundCode}_employee_percent`, `efka_aux_${fundCode}_employer_percent`];
  }
  return ["efka_auxiliary_employee_percent", "efka_auxiliary_employer_percent"];
}

function defaultEfkaBranches(row) {
  const fundCode = normalizeAuxFundCode(row && row.epikourikiki_kod);
  const [empCode, erCode] = auxiliaryParamCodes(fundCode);
  const auxCode = fundCode === "001" ? "auxiliary" : (fundCode === "002" ? "teka" : `aux_${fundCode}`);
  const branches = [
    { code: "pension", label: "Κύρια σύνταξη", employee_percent: efkaParamPercent("efka_pension_employee_percent"), employer_percent: efkaParamPercent("efka_pension_employer_percent") },
    { code: "health_kind", label: "Υγεία σε είδος", employee_percent: efkaParamPercent("efka_health_kind_employee_percent"), employer_percent: efkaParamPercent("efka_health_kind_employer_percent") },
    { code: "health_cash", label: "Υγεία σε χρήμα", employee_percent: efkaParamPercent("efka_health_cash_employee_percent"), employer_percent: efkaParamPercent("efka_health_cash_employer_percent") },
    { code: auxCode, label: AUX_FUND_SHORT[fundCode] || fundCode, employee_percent: efkaParamPercent(empCode), employer_percent: efkaParamPercent(erCode) },
    { code: "dypa", label: "ΔΥΠΑ συνεισπραττόμενες", employee_percent: efkaParamPercent("efka_dypa_employee_percent"), employer_percent: efkaParamPercent("efka_dypa_employer_percent") },
    { code: "heavy", label: "Βαρέα και ανθυγιεινά", employee_percent: efkaParamPercent("efka_heavy_employee_percent"), employer_percent: efkaParamPercent("efka_heavy_employer_percent") },
  ];
  const lumpEmp = efkaParamPercent("efka_lump_employee_percent");
  const lumpEr = efkaParamPercent("efka_lump_employer_percent");
  if (lumpEmp || lumpEr) {
    branches.push({ code: "lump", label: "Εφάπαξ", employee_percent: lumpEmp, employer_percent: lumpEr });
  }
  return branches;
}

function applyEfka(row) {
  const params = payrollParams();
  const exempt = row.efka_premium_exempt !== undefined
    ? Boolean(row.efka_premium_exempt)
    : !["όχι", "no", "0", "false"].includes(String(params.efka_premium_exempt || "ναι").toLowerCase());
  row.efka_premium_exempt = exempt;
  if (!Array.isArray(row.efka_branches) || !row.efka_branches.length) {
    row.efka_branches = defaultEfkaBranches(row);
  }
  let insurable = parseNum(row.period_salary);
  if (!row.efka_insurable_manual) {
    for (const line of row.lines || []) {
      if (line.line_kind === "allowance" || line.line_kind === "bonus") {
        insurable += parseNum(line.amount);
      } else if (line.line_kind !== "efka") {
        if (exempt) {
          if (line.pay_hour) insurable += round2(parseNum(line.hours) * parseNum(line.hourly));
        } else {
          insurable += parseNum(line.amount);
        }
      }
    }
    let ceiling = parseNum(row.efka_monthly_ceiling);
    if (!ceiling) ceiling = parseNum(params.efka_monthly_ceiling);
    const periodType = row.period_type || payrollData?.period_type || "month";
    if (periodType !== "month") {
      const factor = parseNum(row.month_factor) || parseNum(row.pay_base_hours ? params.month_factor_worker : params.month_factor_employee) || 4.166;
      if (factor > 0) ceiling = round2(ceiling / factor);
    }
    if (ceiling > 0 && insurable > ceiling) insurable = ceiling;
    row.efka_insurable = round2(insurable);
  }
  insurable = parseNum(row.efka_insurable);
  let employeeTotal = 0;
  let employerTotal = 0;
  row.efka_branches = row.efka_branches.map((branch) => {
    const employeeAmount = round2(insurable * parseNum(branch.employee_percent) / 100);
    const employerAmount = round2(insurable * parseNum(branch.employer_percent) / 100);
    employeeTotal += employeeAmount;
    employerTotal += employerAmount;
    return {
      ...branch,
      employee_amount: employeeAmount,
      employer_amount: employerAmount,
      formula: `${money(insurable)} € × ${fmtFactor(branch.employee_percent)}% (${branch.label || ""}) = ${money(employeeAmount)} €`,
    };
  });
  row.efka_employee = round2(employeeTotal);
  row.efka_employer = round2(employerTotal);
  row.after_efka = round2(parseNum(row.total) - employeeTotal);
}

function taxChildKey(children) {
  const n = Math.max(0, Math.floor(parseNum(children)));
  return n >= 4 ? "4plus" : String(n);
}

function taxAgeGroup(row) {
  const raw = String(row.tax_age_group || "").trim();
  if (["over_30", "age_26_30", "under_25"].includes(raw)) return raw;
  const fallback = String(payrollParams().tax_default_age_group || "over_30").trim();
  return ["over_30", "age_26_30", "under_25"].includes(fallback) ? fallback : "over_30";
}

function taxBracketsFor(children, ageGroup) {
  const key = taxChildKey(children);
  let b1 = taxParamNum(`tax_b1_percent_${key}`);
  let b2 = taxParamNum(`tax_b2_percent_${key}`);
  let b3 = taxParamNum("tax_b3_percent_0") - taxParamNum("tax_b3_child_step_percent") * Math.max(0, Math.floor(parseNum(children)));
  if (b3 < 0) b3 = 0;
  if (ageGroup === "under_25") {
    b1 = Math.min(b1, taxParamNum("tax_young25_b1_percent"));
    b2 = Math.min(b2, taxParamNum("tax_young25_b2_percent"));
  } else if (ageGroup === "age_26_30") {
    b1 = Math.min(b1, taxParamNum("tax_young30_b1_percent"));
    b2 = Math.min(b2, taxParamNum("tax_young30_b2_percent"));
  }
  return [
    { upto: taxParamNum("tax_bracket_1_upto"), percent: b1 },
    { upto: taxParamNum("tax_bracket_2_upto"), percent: b2 },
    { upto: taxParamNum("tax_bracket_3_upto"), percent: b3 },
    { upto: taxParamNum("tax_bracket_4_upto"), percent: taxParamNum("tax_b4_percent") },
    { upto: taxParamNum("tax_bracket_5_upto"), percent: taxParamNum("tax_b5_percent") },
    { upto: null, percent: taxParamNum("tax_b6_percent") },
  ];
}

function taxCreditAnnual(annual, children) {
  const n = Math.max(0, Math.floor(parseNum(children)));
  let credit = 0;
  if (n <= 0) credit = taxParamNum("tax_credit_0");
  else if (n >= 5) credit = taxParamNum("tax_credit_5") + taxParamNum("tax_credit_extra_per_child") * (n - 5);
  else credit = taxParamNum(`tax_credit_${n}`);
  const exemptFrom = taxParamNum("tax_credit_taper_exempt_from_children") || 5;
  const taperFrom = taxParamNum("tax_credit_taper_from");
  if (n < exemptFrom && annual > taperFrom) {
    const step = taxParamNum("tax_credit_taper_step");
    const amount = taxParamNum("tax_credit_taper_amount");
    if (step > 0) credit -= amount * Math.floor((annual - taperFrom) / step);
  }
  return round2(Math.max(0, credit));
}

function annualIncomeTaxResult(annual, children, ageGroup) {
  const brackets = taxBracketsFor(children, ageGroup);
  let remaining = annual;
  let previousLimit = 0;
  let gross = 0;
  const computed = brackets.map((bracket) => {
    const upto = bracket.upto;
    let slice = 0;
    if (remaining > 0) {
      if (upto == null) slice = remaining;
      else {
        const width = Math.max(0, parseNum(upto) - previousLimit);
        slice = remaining < width ? remaining : width;
      }
    }
    slice = round2(slice);
    const amount = round2(slice * parseNum(bracket.percent) / 100);
    gross = round2(gross + amount);
    remaining = round2(remaining - slice);
    if (upto != null) previousLimit = parseNum(upto);
    return {
      ...bracket,
      slice,
      amount,
      formula: `${money(slice)} € × ${fmtFactor(bracket.percent)}% = ${money(amount)} €`,
    };
  });
  let credit = taxCreditAnnual(annual, children);
  if (credit > gross) credit = gross;
  return { annual, gross, credit, tax: round2(gross - credit), brackets: computed };
}

function applyFmy(row) {
  const params = payrollParams();
  const children = Math.max(0, Math.floor(parseNum(row.children_count)));
  const ageGroup = taxAgeGroup(row);
  row.tax_age_group = ageGroup;
  if (row.fmy_manual) {
    row.net = round2(parseNum(row.after_efka) - parseNum(row.fmy));
    row.tax_formula = `Χειροκίνητη παρακράτηση: ${money(row.fmy)} €`;
    return;
  }
  let salaries = taxParamNum("fmy_annual_salaries");
  if (salaries <= 0) salaries = 14;
  let factor = parseNum(row.month_factor);
  if (!factor) factor = parseNum(row.pay_base_hours ? params.month_factor_worker : params.month_factor_employee);
  const periodType = row.period_type || payrollData?.period_type || "month";
  const annualize = periodType === "month" || factor <= 0 ? salaries : salaries * factor;
  const taxable = parseNum(row.after_efka);
  const bonuses = parseNum(row.bonuses_total);
  const total = parseNum(row.total);
  const insurable = parseNum(row.efka_insurable);
  let bonusAfter = 0;
  let regularAfter = taxable;
  if (bonuses > 0 && taxable > 0) {
    if (insurable > 0) {
      bonusAfter = round2(bonuses - parseNum(row.efka_employee) * bonuses / insurable);
    } else if (total > 0) {
      bonusAfter = round2(taxable * bonuses / total);
    }
    if (bonusAfter > taxable) bonusAfter = taxable;
    regularAfter = round2(taxable - bonusAfter);
  }
  const annual = round2(regularAfter * annualize);
  let result = annualIncomeTaxResult(annual, children, ageGroup);
  const fmyRegular = annualize ? round2(result.tax / annualize) : 0;
  let fmyBonus = 0;
  if (bonusAfter > 0) {
    const withBonus = annualIncomeTaxResult(round2(annual + bonusAfter), children, ageGroup);
    fmyBonus = round2(withBonus.tax - result.tax);
    result = withBonus;
  }
  const fmy = round2(fmyRegular + fmyBonus);
  row.tax_annual = result.annual;
  row.tax_gross_annual = result.gross;
  row.tax_credit_annual = result.credit;
  row.tax_annual_amount = result.tax;
  row.tax_brackets = result.brackets;
  row.tax_regular_after = regularAfter;
  row.tax_bonus_after = bonusAfter;
  row.fmy_regular = fmyRegular;
  row.fmy_bonus = fmyBonus;
  let formula = `ετήσιο ${money(annual)} € → φόρος κλίμακας ${money(result.gross)} € − μείωση άρθ. 16 ${money(result.credit)} € = ${money(result.tax)} € · παρακράτηση τακτικών ${money(fmyRegular)} €`;
  if (bonusAfter > 0) {
    formula += ` + ΦΜΥ δώρων/αδείας ${money(fmyBonus)} € (εφάπαξ ${money(bonusAfter)} €, όχι × ${fmtFactor(annualize)})`;
  }
  formula += ` = ${money(fmy)} €`;
  row.tax_formula = formula;
  row.fmy = fmy;
  row.net = round2(taxable - fmy);
}

function childAllowancePercent(count) {
  const params = payrollParams();
  const n = Math.max(0, Math.floor(parseNum(count)));
  if (n <= 0) return 0;
  if (n >= 5) return parseNum(params.child_allowance_5plus_percent);
  return parseNum(params[`child_allowance_${n}_percent`]);
}

function marriageAllowancePercent(code) {
  const params = payrollParams();
  const codes = String(params.marriage_marital_codes || "")
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
  return codes.includes(String(code || "").trim()) ? parseNum(params.marriage_percent) : 0;
}

function seniorityAllowancePercent(years) {
  const params = payrollParams();
  const stepYears = parseNum(params.seniority_years_per_step);
  const perStep = parseNum(params.seniority_percent_per_step);
  const maxSteps = parseNum(params.seniority_max_steps);
  const value = parseNum(years);
  if (stepYears <= 0 || perStep <= 0 || value <= 0) return 0;
  let steps = Math.floor(value / stepYears);
  if (maxSteps > 0) steps = Math.min(steps, Math.floor(maxSteps));
  return steps > 0 ? round2(perStep * steps) : 0;
}

function findAllowanceLine(row, family) {
  return (row.lines || []).find((line) => line.line_kind === "allowance" && line.family === family);
}

function refreshAllowancePercents(row) {
  const marriage = findAllowanceLine(row, "Επίδομα γάμου");
  if (marriage) marriage.family_percent = marriageAllowancePercent(row.marital_status);
  const children = findAllowanceLine(row, "Επίδομα τέκνων");
  if (children) children.family_percent = childAllowancePercent(row.children_count);
  const seniority = findAllowanceLine(row, "Επίδομα προϋπηρεσίας");
  if (seniority) seniority.family_percent = seniorityAllowancePercent(row.prior_service_years);
}

function setAllowanceBase(row, value) {
  row.allowance_base = value;
  for (const line of row.lines || []) {
    if (line.line_kind === "allowance") line.hourly = value;
  }
}

function payrollGrandTotal() {
  const rows = payrollData?.employees || [];
  return round2(rows.reduce((sum, row) => sum + Number(row.total || 0), 0));
}

function payrollGrandFmy() {
  const rows = payrollData?.employees || [];
  return round2(rows.reduce((sum, row) => sum + Number(row.fmy || 0), 0));
}

function payrollGrandNet() {
  const rows = payrollData?.employees || [];
  return round2(rows.reduce((sum, row) => sum + Number(row.net || 0), 0));
}

function payrollGrandBonuses() {
  const rows = payrollData?.employees || [];
  return round2(rows.reduce((sum, row) => sum + Number(row.bonuses_total || 0), 0));
}

function payrollGrandEfka() {
  const rows = payrollData?.employees || [];
  return round2(rows.reduce((sum, row) => sum + Number(row.efka_employee || 0), 0));
}

async function loadPayroll() {
  const embed = document.getElementById("payrollEmbed");
  const wrap = document.getElementById("payrollWrap");
  if (!embed || !wrap) return;
  wrap.innerHTML = `<p class="payroll-embed-loading"><i class="bi bi-hourglass-split"></i> Υπολογισμός μεικτών…</p>`;
  embed.classList.remove("hidden");
  try {
    const res = await fetch("/api/payroll/calculate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(periodPayload()),
    });
    const data = await Office.parseJson(res);
    if (!res.ok) {
      wrap.innerHTML = `<p class="payroll-warn">${esc(data.error || `HTTP ${res.status}`)}</p>`;
      return;
    }
    payrollData = data;
    payrollOriginal = JSON.parse(JSON.stringify(data));
    (payrollData.employees || []).forEach(applyEmployee);
    renderPayroll();
  } catch (error) {
    wrap.innerHTML = `<p class="payroll-warn">${esc(error.message || error)}</p>`;
  }
}

function renderPayroll() {
  const embed = document.getElementById("payrollEmbed");
  const wrap = document.getElementById("payrollWrap");
  const totalEl = document.getElementById("payrollGrandTotal");
  if (!embed || !wrap) return;
  const rows = payrollData?.employees || [];
  const grand = payrollGrandTotal();
  const efkaTotal = payrollGrandEfka();
  const fmyTotal = payrollGrandFmy();
  const netTotal = payrollGrandNet();
  const bonusTotal = payrollGrandBonuses();
  if (totalEl) totalEl.textContent = `${money(grand)} €`;
  const summary = document.getElementById("timekeepingSummary");
  if (summary && !summary.querySelector("[data-payroll-kpi]")) {
    summary.insertAdjacentHTML(
      "beforeend",
      `<div class="card apologistic-kpi" data-payroll-kpi><span>Μεικτά</span><strong id="payrollKpiTotal">${money(grand)} €</strong></div>` +
      `<div class="card apologistic-kpi" data-payroll-kpi-bonus><span>Δώρα / άδεια</span><strong id="payrollKpiBonus">${money(bonusTotal)} €</strong></div>` +
      `<div class="card apologistic-kpi" data-payroll-kpi-efka><span>ΕΦΚΑ</span><strong id="payrollKpiEfka">${money(efkaTotal)} €</strong></div>` +
      `<div class="card apologistic-kpi" data-payroll-kpi-fmy><span>ΦΜΥ</span><strong id="payrollKpiFmy">${money(fmyTotal)} €</strong></div>` +
      `<div class="card apologistic-kpi" data-payroll-kpi-net><span>Καθαρά</span><strong id="payrollKpiNet">${money(netTotal)} €</strong></div>`
    );
  } else {
    const kpi = document.getElementById("payrollKpiTotal");
    if (kpi) kpi.textContent = `${money(grand)} €`;
    const kpiBonus = document.getElementById("payrollKpiBonus");
    if (kpiBonus) kpiBonus.textContent = `${money(bonusTotal)} €`;
    const kpiEfka = document.getElementById("payrollKpiEfka");
    if (kpiEfka) kpiEfka.textContent = `${money(efkaTotal)} €`;
    const kpiFmy = document.getElementById("payrollKpiFmy");
    if (kpiFmy) kpiFmy.textContent = `${money(fmyTotal)} €`;
    const kpiNet = document.getElementById("payrollKpiNet");
    if (kpiNet) kpiNet.textContent = `${money(netTotal)} €`;
  }
  if (!rows.length) {
    wrap.innerHTML = `<p class="payroll-embed-note">Δεν υπάρχουν εργαζόμενοι στην ωρομέτρηση.</p>`;
    return;
  }
  wrap.innerHTML =
    `<table class="data payroll-list-table"><thead><tr>` +
    `<th class="work-log-action-cell" aria-label="Στοιχεία σύμβασης"></th>` +
    `<th>Εργαζόμενος</th><th>ΑΦΜ</th><th class="payroll-money">Μισθός περιόδου</th>` +
    `<th class="payroll-money">Προσαυξήσεις</th><th class="payroll-money">Επιδόματα</th>` +
    `<th class="payroll-money">Δώρα / άδεια</th>` +
    `<th class="payroll-money">Μεικτά</th><th class="payroll-money">ΕΦΚΑ</th>` +
    `<th class="payroll-money">Επικουρική</th>` +
    `<th class="payroll-money">ΦΜΥ</th><th class="payroll-money">Καθαρά</th><th class="payroll-list-info"></th>` +
    `</tr></thead><tbody>` +
    rows.map((row, index) => {
      const extras = round2(Number(row.base_pay || 0) + Number(row.extra_pay || 0));
      const warn = (row.warnings || []).length
        ? `<p class="payroll-warn-inline">${esc(row.warnings.join(" · "))}</p>`
        : "";
      const fund = fundListLabel(row);
      const kindBits = [row.characterization_label || "", fund].filter(Boolean).join(" · ");
      const aux = auxiliaryBranch(row);
      const apdMissing = row.apd && row.apd.ready ? "" : " payroll-apd-missing";
      return `<tr>` +
        `<td class="work-log-action-cell">${employeeDetailButton(row)}</td>` +
        `<td><div class="payroll-list-name"><span>${esc(employeeName(row))}</span></div>` +
        `<small class="payroll-list-kind">${esc(kindBits)}</small>${warn}</td>` +
        `<td class="payroll-list-afm">${esc(row.employee_afm || "")}</td>` +
        `<td class="payroll-money">${money(row.period_salary)}</td>` +
        `<td class="payroll-money">${money(extras)}</td>` +
        `<td class="payroll-money">${money(row.allowances_total)}</td>` +
        `<td class="payroll-money">${money(row.bonuses_total)}</td>` +
        `<td class="payroll-money"><strong>${money(row.total)}</strong></td>` +
        `<td class="payroll-money">${money(row.efka_employee)}</td>` +
        `<td class="payroll-money">${money(aux?.employee_amount)}</td>` +
        `<td class="payroll-money">${money(row.fmy)}</td>` +
        `<td class="payroll-money"><strong>${money(row.net)}</strong></td>` +
        `<td class="payroll-list-info">` +
        `<button type="button" class="apologistic-info-btn payroll-info-btn" data-payroll-index="${index}" aria-label="Πώς υπολογίστηκε">` +
        `<i class="bi bi-info-circle" aria-hidden="true"></i></button>` +
        `<button type="button" class="apologistic-info-btn payroll-apd-btn${apdMissing}" data-apd-index="${index}" title="Προεπισκόπηση ΑΠΔ" aria-label="Προεπισκόπηση ΑΠΔ">` +
        `<i class="bi bi-file-earmark-text" aria-hidden="true"></i></button></td>` +
        `</tr>`;
    }).join("") +
    `</tbody></table>`;
}

function employeeDetailButton(row) {
  const afm = String((row && row.employee_afm) || "").replace(/\D/g, "");
  if (!afm) return "";
  const name = employeeName(row);
  return (
    `<button type="button" class="employees-action-btn employees-action-button payroll-employee-btn" ` +
    `data-employee-afm="${esc(afm)}" title="Στοιχεία σύμβασης Ergani" ` +
    `aria-label="Στοιχεία σύμβασης — ${esc(name)}">` +
    `<i class="bi bi-info-circle" aria-hidden="true"></i></button>`
  );
}

function auxiliaryBranch(row) {
  const branches = Array.isArray(row?.efka_branches) ? row.efka_branches : [];
  return branches.find((branch) => {
    const code = String(branch.code || "");
    return code === "teka" || code === "auxiliary" || code.startsWith("aux_");
  }) || null;
}

function fundListLabel(row) {
  const label = row.auxiliary_fund_label || AUX_FUND_SHORT[normalizeAuxFundCode(row.epikourikiki_kod)] || "ΕΤΕΑΕΠ";
  const branch = auxiliaryBranch(row);
  if (!branch) return label;
  return `${label} ${fmtFactor(branch.employee_percent)}%+${fmtFactor(branch.employer_percent)}%`;
}

function employeeFundLabel(row) {
  const raw = row && row.epikourikiki_kod;
  if (raw == null || String(raw).trim() === "") {
    return "ΕΤΕΑΕΠ (προεπιλογή)";
  }
  const code = normalizeAuxFundCode(raw);
  return `${AUX_FUND_SHORT[code] || code} (${code})`;
}

const EMPLOYEE_CONTRACT_FIELDS = [
  ["employer_afm", "ΑΦΜ εργοδότη"],
  ["branch_aa", "Παράρτημα"],
  ["employee_afm", "ΑΦΜ εργαζομένου"],
  ["eponymo", "Επώνυμο"],
  ["onoma", "Όνομα"],
  ["hire_date", "Ημερομηνία πρόσληψης"],
  ["specialty", "Ειδικότητα"],
  ["characterization", "Χαρακτηρισμός"],
  ["kyria_asfalish", "Κύρια ασφάλιση"],
  ["epikourikiki_kod", "Επικουρική ασφάλιση"],
  ["step92", "ΣΤΕΠ 92"],
  ["weekly_work_days", "Ημέρες εβδομαδιαίας απασχόλησης"],
  ["prior_service", "Προϋπηρεσία"],
  ["arithmos_teknon", "Αριθμός τέκνων"],
  ["marital_status", "Οικογενειακή κατάσταση"],
  ["employment_relation", "Σχέση απασχόλησης"],
  ["fixed_term_from", "Ορισμένου χρόνου από"],
  ["fixed_term_to", "Ορισμένου χρόνου έως"],
  ["regime", "Καθεστώς"],
  ["weekly_hours", "Ώρες εβδομαδιαίως"],
  ["salary", "Αποδοχές"],
  ["hourly_wage", "Ωρομίσθιο"],
  ["total_weekly_hours", "Συνολικές ώρες εβδομαδιαίως"],
  ["fulltime_contract_weekly_hours", "Συμβατικές ώρες πλήρους απασχόλησης"],
  ["break_minutes", "Διάλειμμα (λεπτά)"],
  ["break_in_work", "Διάλειμμα εντός ωραρίου"],
  ["flex_arrival_minutes", "Ευέλικτη προσέλευση (λεπτά)"],
  ["ergani_updated_at", "Ημ/νία τελευταίας ενημέρωσης Ergani"],
  ["last_checked_at", "Τελευταίος επιτυχής έλεγχος"],
  ["synced_at", "Αποθήκευση έκδοσης"],
  ["source", "Πηγή"],
];

function employeeContractValue(key, value) {
  if (value == null || value === "") return "—";
  if (key === "break_in_work") {
    if (value === 1 || value === true || value === "1") return "Ναι";
    if (value === 0 || value === false || value === "0") return "Όχι";
  }
  if (key === "flex_arrival_minutes" && Office.formatFlexMinutes) {
    return Office.formatFlexMinutes(value);
  }
  if (key === "hire_date") {
    const shown = displayDate(value);
    return shown ? `${shown} (Ergani)` : "—";
  }
  if (key === "epikourikiki_kod") {
    const code = normalizeAuxFundCode(value);
    return `${code} — ${AUX_FUND_SHORT[code] || code}`;
  }
  if (key === "kyria_asfalish") {
    const code = String(value || "").replace(/\D/g, "").padStart(3, "0").slice(-3);
    const labels = { "001": "e-ΕΦΚΑ", "002": "ΝΑΤ", "003": "ΤτΕ" };
    return labels[code] ? `${code} — ${labels[code]}` : String(value);
  }
  if (key === "synced_at" || key === "last_checked_at") {
    return String(value).replace("T", " ").slice(0, 19);
  }
  return String(value);
}

function employeeContractTable(row) {
  return `<table class="data employee-contract-fields-table"><thead><tr><th>Πεδίο</th><th>Τιμή</th></tr></thead><tbody>` +
    EMPLOYEE_CONTRACT_FIELDS.map(([key, label]) =>
      `<tr><td class="employee-contract-field-label">${esc(label)}</td><td>${esc(employeeContractValue(key, row?.[key]))}</td></tr>`
    ).join("") +
    `</tbody></table>`;
}

let openEmployeeAfm = null;

function bindEmployeeDetailModal() {
  const modal = document.getElementById("apologisticEmployeeModal");
  if (!modal || modal.dataset.bound === "1") return;
  modal.dataset.bound = "1";
  modal.querySelectorAll("[data-apologistic-employee-close]").forEach((el) => {
    el.addEventListener("click", closeEmployeeDetailModal);
  });
  document.getElementById("payrollWrap")?.addEventListener("click", onEmployeeDetailClick);
  document.getElementById("timekeepingWrap")?.addEventListener("click", onEmployeeDetailClick);
}

function onEmployeeDetailClick(event) {
  const button = event.target.closest(".payroll-employee-btn[data-employee-afm]");
  if (!button) return;
  event.preventDefault();
  event.stopPropagation();
  openEmployeeDetailModal(button.getAttribute("data-employee-afm"));
}

async function openEmployeeDetailModal(afm) {
  const cleanAfm = String(afm || "").replace(/\D/g, "");
  const modal = document.getElementById("apologisticEmployeeModal");
  const title = document.getElementById("apologisticEmployeeModalTitle");
  const meta = document.getElementById("apologisticEmployeeModalMeta");
  const body = document.getElementById("apologisticEmployeeModalBody");
  const pageLink = document.getElementById("apologisticEmployeePageLink");
  if (!cleanAfm || !modal || !title || !meta || !body) return;
  openEmployeeAfm = cleanAfm;
  title.textContent = "Στοιχεία εργαζομένου";
  meta.textContent = `ΑΦΜ ${cleanAfm}`;
  if (pageLink) {
    pageLink.href = `/ui/employees/detail?afm=${encodeURIComponent(cleanAfm)}`;
    pageLink.classList.remove("hidden");
  }
  body.innerHTML = `<p class="apologistic-employee-loading"><i class="bi bi-hourglass-split"></i> Φόρτωση…</p>`;
  modal.classList.remove("hidden");
  try {
    const res = await fetch(
      `/api/employees/contract/history?employee_afm=${encodeURIComponent(cleanAfm)}`,
      { cache: "no-store" }
    );
    const data = await res.json().catch(() => ({}));
    if (openEmployeeAfm !== cleanAfm) return;
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    const rows = data.contracts || [];
    title.textContent = data.employee_name || `ΑΦΜ ${cleanAfm}`;
    meta.textContent = `ΑΦΜ ${cleanAfm}${data.store ? ` · ${data.store.name || ""} · παράρτημα ${data.store.branch_aa ?? "0"}` : ""}`;
    if (!rows.length) {
      body.innerHTML = `<p style="color:var(--muted);">Δεν υπάρχουν στοιχεία σύμβασης.</p>`;
      return;
    }
    const current = rows.find((row) => row.is_current === true || row.is_current === 1 || row.is_current === "1") || rows[0];
    const previous = rows.filter((row) => row !== current);
    const fund = employeeFundLabel(current);
    const mainRaw = String(current.kyria_asfalish || "").trim();
    const mainCode = mainRaw.replace(/\D/g, "").padStart(3, "0").slice(-3);
    const mainLabels = { "001": "e-ΕΦΚΑ", "002": "ΝΑΤ", "003": "ΤτΕ" };
    const main = mainLabels[mainCode] ? `${mainLabels[mainCode]} (${mainCode})` : (mainRaw || "e-ΕΦΚΑ");
    const hire = current.hire_date ? displayDate(current.hire_date) : "";
    const pay = (payrollData?.employees || []).find(
      (item) => String(item.employee_afm || "").replace(/\D/g, "") === cleanAfm
    );
    const aux = auxiliaryBranch(pay);
    const amountBit = aux
      ? ` · ασφαλισμένος ${fmtFactor(aux.employee_percent)}% = ${money(aux.employee_amount)} €` +
        ` · εργοδότης ${fmtFactor(aux.employer_percent)}% = ${money(aux.employer_amount)} €`
      : "";
    body.innerHTML =
      `<p class="payroll-employee-fund"><strong>Επικουρική / ΤΕΚΑ:</strong> ${esc(fund)}` +
      `${esc(amountBit)}` +
      ` · <strong>Κύρια:</strong> ${esc(main)}` +
      (hire ? ` · <strong>Πρόσληψη:</strong> ${esc(hire)}` : "") +
      `</p>` +
      `<section><h3>Τρέχουσα κατάσταση</h3>${employeeContractTable(current)}</section>` +
      (previous.length
        ? `<details class="apologistic-employee-history"><summary>Προηγούμενες εκδόσεις (${previous.length})</summary>` +
          previous.map((row) =>
            `<details><summary>${esc(employeeContractValue("synced_at", row.synced_at))} · ${esc(employeeContractValue("specialty", row.specialty))}</summary>${employeeContractTable(row)}</details>`
          ).join("") +
          `</details>`
        : "");
  } catch (error) {
    if (openEmployeeAfm === cleanAfm) {
      body.innerHTML = `<p style="color:var(--err);">${esc(error.message || error)}</p>`;
    }
  }
}

function closeEmployeeDetailModal() {
  const modal = document.getElementById("apologisticEmployeeModal");
  const body = document.getElementById("apologisticEmployeeModalBody");
  openEmployeeAfm = null;
  modal?.classList.add("hidden");
  if (body) body.innerHTML = "";
}

function bindPayrollModal() {
  const modal = document.getElementById("payrollInfoModal");
  if (!modal) return;
  modal.querySelectorAll("[data-payroll-info-close]").forEach((el) => {
    el.addEventListener("click", closePayrollModal);
  });
  document.getElementById("payrollInfoReset")?.addEventListener("click", resetPayrollModal);
  document.getElementById("payrollWrap")?.addEventListener("click", (event) => {
    const apdButton = event.target.closest("[data-apd-index]");
    if (apdButton) {
      openApdModal(Number(apdButton.getAttribute("data-apd-index")));
      return;
    }
    const button = event.target.closest("[data-payroll-index]");
    if (!button) return;
    openPayrollModal(Number(button.getAttribute("data-payroll-index")));
  });
  document.getElementById("payrollInfoModalBody")?.addEventListener("input", onPayrollModalInput);
  document.getElementById("payrollInfoModalBody")?.addEventListener("change", onPayrollModalInput);
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    const employeeModal = document.getElementById("apologisticEmployeeModal");
    if (employeeModal && !employeeModal.classList.contains("hidden")) {
      closeEmployeeDetailModal();
      return;
    }
    const apdModal = document.getElementById("payrollApdModal");
    if (apdModal && !apdModal.classList.contains("hidden")) {
      closeApdModal();
      return;
    }
    const open = document.getElementById("payrollInfoModal");
    if (open && !open.classList.contains("hidden")) closePayrollModal();
  });
}

function closePayrollModal() {
  const modal = document.getElementById("payrollInfoModal");
  if (modal) modal.classList.add("hidden");
  payrollModalIndex = null;
}

function resetPayrollModal() {
  if (payrollModalIndex == null || !payrollOriginal) return;
  const original = payrollOriginal.employees?.[payrollModalIndex];
  if (!original || !payrollData?.employees) return;
  payrollData.employees[payrollModalIndex] = applyEmployee(JSON.parse(JSON.stringify(original)));
  renderPayroll();
  fillPayrollModal(payrollData.employees[payrollModalIndex]);
}

function openPayrollModal(index) {
  const row = payrollData?.employees?.[index];
  if (!row) return;
  payrollModalIndex = index;
  fillPayrollModal(row);
  document.getElementById("payrollInfoModal")?.classList.remove("hidden");
}

function fillPayrollModal(row) {
  const segments = row.contract_segments || [];
  document.getElementById("payrollInfoModalTitle").textContent = employeeName(row);
  document.getElementById("payrollInfoModalSub").textContent =
    `${row.characterization_label || ""} · ΑΦΜ ${row.employee_afm || ""}`;
  const method = row.pay_base_hours
    ? "Εργάτης: πληρώνονται και οι ώρες βάσης. Νύχτα/Κυριακή πάνω στο νόμιμο. Τα έξτρα πάνω στο καταβαλλόμενο. Επιδόματα = βάση × %. Δώρα/άδεια στον μήνα καταβολής (παράμετροι). ΕΦΚΑ επί ασφαλιστέων. ΦΜΥ: τακτικά × 14, δώρα εφάπαξ."
    : "Υπάλληλος: ο μηνιαίος καλύπτει τις ώρες βάσης ημέρας. Νύχτα/Κυριακή πάνω στο νόμιμο. Τα έξτρα πάνω στο καταβαλλόμενο. Επιδόματα = βάση × %. Δώρα/άδεια στον μήνα καταβολής (παράμετροι). ΕΦΚΑ επί ασφαλιστέων. ΦΜΥ: τακτικά × 14, δώρα εφάπαξ.";
  const hourLines = (Array.isArray(row.lines) ? row.lines : [])
    .map((line, lineIndex) => ({ line, lineIndex }))
    .filter(({ line }) => line.line_kind === "hour" || !line.line_kind);
  const allowanceLines = (Array.isArray(row.lines) ? row.lines : [])
    .map((line, lineIndex) => ({ line, lineIndex }))
    .filter(({ line }) => line.line_kind === "allowance");
  const bonusLines = (Array.isArray(row.lines) ? row.lines : [])
    .map((line, lineIndex) => ({ line, lineIndex }))
    .filter(({ line }) => line.line_kind === "bonus");
  const lineRows = hourLines.length
    ? hourLines.map(({ line, lineIndex }) =>
        `<tr>` +
        `<td>${esc(line.family)}<br><small>${esc(line.contract_segment || "")}</small></td><td>${esc(line.zone)}</td>` +
        `<td><input class="field-input payroll-modal-num" data-line="${lineIndex}" data-field="hours" value="${esc(String(line.hours ?? 0).replace(".", ","))}"></td>` +
        `<td><input class="field-input payroll-modal-num" data-line="${lineIndex}" data-field="family_percent" value="${esc(String(line.family_percent ?? 0).replace(".", ","))}"></td>` +
        `<td><input class="field-input payroll-modal-num" data-line="${lineIndex}" data-field="zone_percent" value="${esc(String(line.zone_percent ?? 0).replace(".", ","))}"></td>` +
        `<td class="payroll-formula" data-formula="${lineIndex}">${esc(line.formula || "")}</td>` +
        `<td class="payroll-money" data-amount="${lineIndex}">${money(line.amount)}</td>` +
        `</tr>`
      ).join("")
    : `<tr><td colspan="7" class="payroll-embed-note">Δεν υπάρχουν ώρες προς πληρωμή· μένει ο μισθός περιόδου και τα επιδόματα (αν υπάρχουν).</td></tr>`;
  const marital = String(row.marital_status ?? "");
  const maritalOptions = [
    ["", "—"],
    ["0", "0 άγαμος/η"],
    ["1", "1 έγγαμος/η"],
    ["2", "2 διαζευγμένος/η"],
    ["3", "3 χήρος/α"],
  ].map(([value, label]) =>
    `<option value="${esc(value)}" ${value === marital ? "selected" : ""}>${esc(label)}</option>`
  ).join("");
  const allowanceRows = allowanceLines.length
    ? allowanceLines.map(({ line, lineIndex }) =>
        `<tr>` +
        `<td>${esc(line.family)}<br><small>${esc(line.contract_segment || "")}</small></td>` +
        `<td><input class="field-input payroll-modal-num" data-line="${lineIndex}" data-field="family_percent" value="${esc(String(line.family_percent ?? 0).replace(".", ","))}"></td>` +
        `<td class="payroll-formula" data-formula="${lineIndex}">${esc(line.formula || "")}</td>` +
        `<td class="payroll-money" data-amount="${lineIndex}">${money(line.amount)}</td>` +
        `</tr>`
      ).join("")
    : `<tr><td colspan="4" class="payroll-embed-note">Δεν υπάρχουν γραμμές επιδομάτων.</td></tr>`;
  const bonusRows = bonusLines.length
    ? bonusLines.map(({ line, lineIndex }) =>
        `<tr>` +
        `<td>${esc(line.family)}</td>` +
        `<td><input class="field-input payroll-modal-num" data-line="${lineIndex}" data-field="hourly" value="${esc(String(line.hourly ?? 0).replace(".", ","))}"></td>` +
        `<td class="payroll-formula" data-formula="${lineIndex}">${esc(line.formula || "")}</td>` +
        `<td class="payroll-money" data-amount="${lineIndex}">${money(line.amount)}</td>` +
        `</tr>`
      ).join("")
    : `<tr><td colspan="4" class="payroll-embed-note">Δεν υπάρχουν δώρα/επίδομα αδείας σε αυτόν τον μήνα (βλ. μήνες καταβολής στις παραμέτρους).</td></tr>`;
  const efkaRows = (Array.isArray(row.efka_branches) ? row.efka_branches : []).map((branch, branchIndex) => {
    const code = String(branch.code || "");
    const isAux = code === "teka" || code === "auxiliary" || code.startsWith("aux_");
    return `<tr${isAux ? " class=\"payroll-efka-aux-row\"" : ""}>` +
    `<td>${esc(branch.label || "")}</td>` +
    `<td><input class="field-input payroll-modal-num" data-efka="${branchIndex}" data-field="employee_percent" value="${esc(String(branch.employee_percent ?? 0).replace(".", ","))}"></td>` +
    `<td class="payroll-formula" data-efka-formula="${branchIndex}">${esc(branch.formula || "")}</td>` +
    `<td class="payroll-money" data-efka-emp="${branchIndex}">${money(branch.employee_amount)}</td>` +
    `<td><input class="field-input payroll-modal-num" data-efka="${branchIndex}" data-field="employer_percent" value="${esc(String(branch.employer_percent ?? 0).replace(".", ","))}"></td>` +
    `<td class="payroll-money" data-efka-er="${branchIndex}">${money(branch.employer_amount)}</td>` +
    `</tr>`;
  }).join("") || `<tr><td colspan="6" class="payroll-embed-note">Λείπουν οι συντελεστές ΕΦΚΑ από τις παραμέτρους.</td></tr>`;
  const aux = auxiliaryBranch(row);
  const ageGroup = String(row.tax_age_group || "over_30");
  const ageOptions = [
    ["over_30", "Άνω των 30"],
    ["age_26_30", "26–30 ετών"],
    ["under_25", "Έως 25 ετών"],
  ].map(([value, label]) =>
    `<option value="${esc(value)}" ${value === ageGroup ? "selected" : ""}>${esc(label)}</option>`
  ).join("");
  const taxRows = (Array.isArray(row.tax_brackets) ? row.tax_brackets : []).map((bracket, taxIndex) =>
    `<tr>` +
    `<td>${bracket.upto == null ? "Υπερβάλλον" : `Έως ${money(bracket.upto)}`}</td>` +
    `<td>${esc(String(bracket.percent ?? 0).replace(".", ","))}%</td>` +
    `<td class="payroll-formula">${esc(bracket.formula || "")}</td>` +
    `<td class="payroll-money">${money(bracket.amount)}</td>` +
    `</tr>`
  ).join("") || `<tr><td colspan="4" class="payroll-embed-note">Λείπει η κλίμακα ΦΜΥ από τις παραμέτρους.</td></tr>`;
  document.getElementById("payrollInfoModalBody").innerHTML =
    `<p class="payroll-modal-method">${esc(method)}</p>` +
    (segments.length ? `<h3>Διαστήματα συμβάσεων</h3><p>Ο μισθός επιμερίζεται με τις δηλωμένες ώρες κάθε διαστήματος προς τις συμβατικές εβδομαδιαίες ώρες. Οι συντελεστές κάθε γραμμής διατηρούνται ανά σύμβαση.</p>` +
      `<table class="data"><thead><tr><th>Από – έως</th><th>Μηνιαίος μισθός σύμβασης</th><th>Ώρες/εβδομάδα</th><th>Μερίδιο</th><th>Μισθός διαστήματος</th></tr></thead><tbody>` +
      segments.map(s => `<tr><td>${esc(s.from)} – ${esc(s.to)}</td><td>${esc(s.salary ?? "")}</td><td>${esc(s.weekly_hours ?? "")}</td><td>${money(s.salary_share * 100)}%</td><td>${money(s.period_salary)} €</td></tr>`).join("") + `</tbody></table>` : "") +
    (row.salary_payable_days != null ? `<p class="payroll-embed-note">${esc(row.salary_days_basis || "")} · Μονάδες μισθού /25, όχι ημέρες ασφάλισης. Οι ημέρες χωρίς αποδοχές αφαιρούνται μόνο με ρητή καταχώριση.</p>` +
    `<div class="payroll-modal-meta"><label><span>Ημέρες μισθοδοσίας (έως 25)</span><input class="field-input payroll-modal-num" data-emp="salary_payable_days" value="${esc(row.salary_payable_days)}"></label>` +
    `<label><span>Χωρίς αποδοχές (μονάδες /25)</span><input class="field-input payroll-modal-num" data-emp="salary_unpaid_days" value="${esc(row.salary_unpaid_days || 0)}"></label></div>` : "") +
    `<div class="payroll-modal-meta">` +
    `<label><span>Μισθός περιόδου (€)</span><input class="field-input payroll-modal-num" data-emp="period_salary" value="${esc(String(row.period_salary ?? 0).replace(".", ","))}"></label>` +
    `<label><span>Καταβαλλόμενο ωρομίσθιο (€)</span><input class="field-input payroll-modal-num" data-emp="hourly_wage" value="${esc(String(row.hourly_wage ?? 0).replace(".", ","))}"></label>` +
    `<label><span>Νόμιμο ωρομίσθιο ζώνης (€)</span><input class="field-input payroll-modal-num" data-emp="legal_hourly" value="${esc(String(row.legal_hourly ?? 0).replace(".", ","))}"></label>` +
    `</div>` +
    `<div class="payroll-modal-table-wrap"><table class="data payroll-modal-table"><thead><tr>` +
    `<th>Οικογένεια</th><th>Ζώνη</th><th>Ώρες</th><th>% οικογένειας</th><th>% ζώνης</th><th>Υπολογισμός</th><th>Ποσό</th>` +
    `</tr></thead><tbody>${lineRows}</tbody></table></div>` +
    `<h3 class="payroll-allowance-title">Επιδόματα ΕΓΣΣΕ</h3>` +
    `<div class="payroll-modal-meta payroll-modal-meta-4">` +
    `<label><span>Τέκνα</span><input class="field-input payroll-modal-num" data-emp="children_count" value="${esc(String(row.children_count ?? 0))}"></label>` +
    `<label><span>Οικογενειακή κατάσταση</span><select class="input-select payroll-modal-num" data-emp="marital_status">${maritalOptions}</select></label>` +
    `<label><span>Έτη προϋπηρεσίας</span><input class="field-input payroll-modal-num" data-emp="prior_service_years" value="${esc(String(row.prior_service_years ?? 0).replace(".", ","))}"></label>` +
    `<label><span>Βάση επιδομάτων (€)</span><input class="field-input payroll-modal-num" data-emp="allowance_base" value="${esc(String(row.allowance_base ?? 0).replace(".", ","))}"></label>` +
    `</div>` +
    `<div class="payroll-modal-table-wrap"><table class="data payroll-modal-table"><thead><tr>` +
    `<th>Επίδομα</th><th>%</th><th>Υπολογισμός</th><th>Ποσό</th>` +
    `</tr></thead><tbody>${allowanceRows}</tbody></table></div>` +
    `<h3 class="payroll-allowance-title">Δώρα / επίδομα αδείας</h3>` +
    `<div class="payroll-modal-table-wrap"><table class="data payroll-modal-table"><thead><tr>` +
    `<th>Γραμμή</th><th>Ποσό (€)</th><th>Υπολογισμός</th><th>Πληρωτέο</th>` +
    `</tr></thead><tbody>${bonusRows}</tbody></table></div>` +
    `<h3 class="payroll-allowance-title">Εισφορές ΕΦΚΑ</h3>` +
    `<div class="payroll-modal-meta">` +
    `<label><span>Ασφαλιστέες αποδοχές (€)</span><input class="field-input payroll-modal-num" data-emp="efka_insurable" value="${esc(String(row.efka_insurable ?? 0).replace(".", ","))}"></label>` +
    `<label><span>Κύρια ασφάλιση</span><input class="field-input" value="${esc(row.kyria_asfalish || "001")}" disabled></label>` +
    `<label><span>Επικουρική / ΤΕΚΑ</span><input class="field-input" value="${esc((row.auxiliary_fund_label || AUX_FUND_SHORT[normalizeAuxFundCode(row.epikourikiki_kod)] || "ΕΤΕΑΕΠ") + " (" + normalizeAuxFundCode(row.epikourikiki_kod) + ")")}" disabled></label>` +
    `</div>` +
    `<div class="payroll-modal-meta">` +
    `<label><span>${esc((aux && aux.label) || "Επικουρική")} ασφαλισμένου (€)</span><input class="field-input" value="${esc(money(aux?.employee_amount))} (${esc(fmtFactor(aux?.employee_percent || 0))}%)" disabled></label>` +
    `<label><span>${esc((aux && aux.label) || "Επικουρική")} εργοδότη (€)</span><input class="field-input" value="${esc(money(aux?.employer_amount))} (${esc(fmtFactor(aux?.employer_percent || 0))}%)" disabled></label>` +
    `</div>` +
    `<div class="payroll-modal-meta">` +
    `<label><span>Κράτηση ασφαλισμένου (€)</span><input class="field-input payroll-modal-num" id="payrollModalEfkaEmployee" value="${esc(String(row.efka_employee ?? 0).replace(".", ","))}" disabled></label>` +
    `<label><span>Εισφορά εργοδότη (€)</span><input class="field-input payroll-modal-num" id="payrollModalEfkaEmployer" value="${esc(String(row.efka_employer ?? 0).replace(".", ","))}" disabled></label>` +
    `</div>` +
    `<div class="payroll-modal-table-wrap"><table class="data payroll-modal-table"><thead><tr>` +
    `<th>Κλάδος</th><th>% ασφαλισμένου</th><th>Υπολογισμός</th><th>Κράτηση</th><th>% εργοδότη</th><th>Εργοδότης</th>` +
    `</tr></thead><tbody>${efkaRows}</tbody></table></div>` +
    `<h3 class="payroll-allowance-title">ΦΜΥ / φόρος εισοδήματος</h3>` +
    `<div class="payroll-modal-meta payroll-modal-meta-4">` +
    `<label><span>Ηλικιακή ομάδα</span><select class="input-select payroll-modal-num" data-emp="tax_age_group">${ageOptions}</select></label>` +
    `<label><span>Ετήσιο φορολογητέο (€)</span><input class="field-input payroll-modal-num" id="payrollModalTaxAnnual" value="${esc(String(row.tax_annual ?? 0).replace(".", ","))}" disabled></label>` +
    `<label><span>Μείωση άρθ. 16 (€)</span><input class="field-input payroll-modal-num" id="payrollModalTaxCredit" value="${esc(String(row.tax_credit_annual ?? 0).replace(".", ","))}" disabled></label>` +
    `<label><span>ΦΜΥ περιόδου (€)</span><input class="field-input payroll-modal-num" data-emp="fmy" value="${esc(String(row.fmy ?? 0).replace(".", ","))}"></label>` +
    `</div>` +
    `<p class="payroll-embed-note" id="payrollModalTaxFormula">${esc(row.tax_formula || "")}</p>` +
    `<div class="payroll-modal-table-wrap"><table class="data payroll-modal-table"><thead><tr>` +
    `<th>Κλιμάκιο</th><th>%</th><th>Υπολογισμός</th><th>Φόρος</th>` +
    `</tr></thead><tbody>${taxRows}</tbody></table></div>` +
    `<div class="payroll-modal-total"><span>Σύνολο μεικτών</span><strong id="payrollModalTotal">${money(row.total)} €</strong></div>` +
    `<div class="payroll-modal-total"><span>Δώρα / άδεια</span><strong id="payrollModalBonuses">${money(row.bonuses_total)} €</strong></div>` +
    `<div class="payroll-modal-total"><span>Μετά ΕΦΚΑ</span><strong id="payrollModalAfterEfka">${money(row.after_efka)} €</strong></div>` +
    `<div class="payroll-modal-total"><span>ΦΜΥ περιόδου</span><strong id="payrollModalFmy">${money(row.fmy)} €</strong></div>` +
    `<div class="payroll-modal-total"><span>Καθαρά πληρωτέα</span><strong id="payrollModalNet">${money(row.net)} €</strong></div>`;
  if (segments.length) {
    for (const field of ["period_salary", "hourly_wage", "legal_hourly", "allowance_base", "children_count", "marital_status", "prior_service_years"]) {
      const input = document.querySelector(`[data-emp="${field}"]`);
      if (input) input.disabled = true;
    }
  }
}

function onPayrollModalInput(event) {
  const input = event.target.closest(".payroll-modal-num");
  if (!input || payrollModalIndex == null) return;
  const row = payrollData?.employees?.[payrollModalIndex];
  if (!row) return;
  const empField = input.getAttribute("data-emp");
  if (row.contract_segments?.length && ["period_salary", "hourly_wage", "legal_hourly", "allowance_base", "children_count", "marital_status", "prior_service_years"].includes(empField)) return;
  const lineIndex = input.getAttribute("data-line");
  const value = parseNum(input.value);
  if (empField === "salary_payable_days" || empField === "salary_unpaid_days") {
    row[empField] = Math.max(0, Math.min(25, value));
    row.salary_unpaid_days = Math.min(row.salary_unpaid_days || 0, row.salary_payable_days);
    row.period_salary = round2(parseNum(row.salary_full_period) * (row.salary_payable_days - row.salary_unpaid_days) / 25);
    setAllowanceBase(row, row.period_salary);
    const salaryInput = document.querySelector('[data-emp="period_salary"]');
    if (salaryInput) salaryInput.value = String(row.period_salary).replace(".", ",");
    const unpaidInput = document.querySelector('[data-emp="salary_unpaid_days"]');
    if (unpaidInput) unpaidInput.value = String(row.salary_unpaid_days).replace(".", ",");
  } else if (empField === "period_salary") {
    row.period_salary = value;
    if (!row.pay_base_hours) setAllowanceBase(row, value);
  } else if (empField === "hourly_wage") {
    row.hourly_wage = value;
    for (const line of row.lines || []) {
      if (line.line_kind === "hour") line.hourly = value;
    }
  } else if (empField === "legal_hourly") {
    row.legal_hourly = value;
    for (const line of row.lines || []) {
      if (line.line_kind === "hour") line.zone_hourly = value;
    }
  } else if (empField === "children_count") {
    row.children_count = Math.max(0, Math.floor(value));
    refreshAllowancePercents(row);
  } else if (empField === "marital_status") {
    row.marital_status = String(input.value || "").trim();
    refreshAllowancePercents(row);
  } else if (empField === "prior_service_years") {
    row.prior_service_years = value;
    refreshAllowancePercents(row);
  } else if (empField === "allowance_base") {
    setAllowanceBase(row, value);
  } else if (empField === "efka_insurable") {
    row.efka_insurable = value;
    row.efka_insurable_manual = true;
  } else if (empField === "tax_age_group") {
    row.tax_age_group = String(input.value || "").trim() || "over_30";
  } else if (empField === "fmy") {
    row.fmy = value;
    row.fmy_manual = true;
  } else if (input.getAttribute("data-efka") != null) {
    const branch = row.efka_branches?.[Number(input.getAttribute("data-efka"))];
    const field = input.getAttribute("data-field");
    if (branch && field) branch[field] = value;
  } else if (lineIndex != null) {
    const line = row.lines?.[Number(lineIndex)];
    const field = input.getAttribute("data-field");
    if (line && field) {
      line[field] = value;
      if (line.line_kind === "bonus") line.formula = `Χειροκίνητη διόρθωση: ${money(line.hourly)} €`;
    }
  }
  if (empField && empField !== "efka_insurable") {
    row.efka_insurable_manual = false;
  }
  if (empField && empField !== "fmy") {
    row.fmy_manual = false;
  }
  if (input.getAttribute("data-efka") != null) {
    row.fmy_manual = false;
  }
  if (lineIndex != null) {
    row.efka_insurable_manual = false;
    row.fmy_manual = false;
  }
  applyEmployee(row);
  (row.lines || []).forEach((line, idx) => {
    const formulaEl = document.querySelector(`[data-formula="${idx}"]`);
    const amountEl = document.querySelector(`[data-amount="${idx}"]`);
    if (formulaEl) formulaEl.textContent = line.formula || "";
    if (amountEl) amountEl.textContent = money(line.amount);
  });
  const percentInputs = document.querySelectorAll("[data-line][data-field='family_percent']");
  percentInputs.forEach((el) => {
    const idx = Number(el.getAttribute("data-line"));
    const line = row.lines?.[idx];
    if (line && line.line_kind === "allowance" && document.activeElement !== el) {
      el.value = String(line.family_percent ?? 0).replace(".", ",");
    }
  });
  const totalEl = document.getElementById("payrollModalTotal");
  if (totalEl) totalEl.textContent = `${money(row.total)} €`;
  const bonusEl = document.getElementById("payrollModalBonuses");
  if (bonusEl) bonusEl.textContent = `${money(row.bonuses_total)} €`;
  const afterEl = document.getElementById("payrollModalAfterEfka");
  if (afterEl) afterEl.textContent = `${money(row.after_efka)} €`;
  const empEl = document.getElementById("payrollModalEfkaEmployee");
  if (empEl) empEl.value = String(row.efka_employee ?? 0).replace(".", ",");
  const erEl = document.getElementById("payrollModalEfkaEmployer");
  if (erEl) erEl.value = String(row.efka_employer ?? 0).replace(".", ",");
  const insurableEl = document.querySelector("[data-emp='efka_insurable']");
  if (insurableEl && document.activeElement !== insurableEl) {
    insurableEl.value = String(row.efka_insurable ?? 0).replace(".", ",");
  }
  (row.efka_branches || []).forEach((branch, idx) => {
    const formulaEl = document.querySelector(`[data-efka-formula="${idx}"]`);
    const empAmt = document.querySelector(`[data-efka-emp="${idx}"]`);
    const erAmt = document.querySelector(`[data-efka-er="${idx}"]`);
    if (formulaEl) formulaEl.textContent = branch.formula || "";
    if (empAmt) empAmt.textContent = money(branch.employee_amount);
    if (erAmt) erAmt.textContent = money(branch.employer_amount);
  });
  const fmyTotalEl = document.getElementById("payrollModalFmy");
  if (fmyTotalEl) fmyTotalEl.textContent = `${money(row.fmy)} €`;
  const netEl = document.getElementById("payrollModalNet");
  if (netEl) netEl.textContent = `${money(row.net)} €`;
  const fmyInput = document.querySelector("[data-emp='fmy']");
  if (fmyInput && document.activeElement !== fmyInput) {
    fmyInput.value = String(row.fmy ?? 0).replace(".", ",");
  }
  const annualEl = document.getElementById("payrollModalTaxAnnual");
  if (annualEl) annualEl.value = String(row.tax_annual ?? 0).replace(".", ",");
  const creditEl = document.getElementById("payrollModalTaxCredit");
  if (creditEl) creditEl.value = String(row.tax_credit_annual ?? 0).replace(".", ",");
  const taxFormulaEl = document.getElementById("payrollModalTaxFormula");
  if (taxFormulaEl) taxFormulaEl.textContent = row.tax_formula || "";
  if (empField === "children_count" || empField === "tax_age_group") {
    fillPayrollModal(row);
  }
  renderPayroll();
}

function bindApdModal() {
  const modal = document.getElementById("payrollApdModal");
  if (!modal) return;
  modal.querySelectorAll("[data-payroll-apd-close]").forEach((el) => {
    el.addEventListener("click", closeApdModal);
  });
}

function closeApdModal() {
  const modal = document.getElementById("payrollApdModal");
  if (modal) modal.classList.add("hidden");
}

function apdValue(value) {
  const text = String(value || "").trim();
  return text || "—";
}

async function openApdModal(index) {
  try {
    await refreshPayrollApd();
  } catch (error) {
    Office.showMsg("timekeepingMsg", error.message || String(error), false);
    return;
  }
  const row = payrollData?.employees?.[index];
  if (!row) return;
  const apd = row.apd || {};
  document.getElementById("payrollApdModalTitle").textContent = `ΑΠΔ — ${employeeName(row)}`;
  document.getElementById("payrollApdModalSub").textContent = apd.note || "Προεπισκόπηση στοιχείων ΑΠΔ";
  const gaps = Array.isArray(apd.gaps) ? apd.gaps : [];
  const packages = Array.isArray(apd.packages) ? apd.packages : [];
  const branches = Array.isArray(apd.efka_branches) ? apd.efka_branches : (row.efka_branches || []);
  const gapHtml = gaps.length
    ? `<ul class="payroll-apd-gaps">${gaps.map((item) => `<li>${esc(item)}</li>`).join("")}</ul>`
    : `<p class="payroll-apd-ready">Τα βασικά στοιχεία ΑΠΔ είναι συμπληρωμένα.</p>`;
  const packageHtml = packages.length
    ? `<table class="data payroll-modal-table"><thead><tr><th>Πακέτο</th><th>Ημέρες</th><th>Ποσό</th></tr></thead><tbody>` +
      packages.map((item) =>
        `<tr><td>${esc(item.label || "")}</td><td>${esc(String(item.insurance_days ?? "—"))}</td>` +
        `<td class="payroll-money">${money(item.amount)} €</td></tr>`
      ).join("") +
      `</tbody></table>`
    : "";
  const branchHtml = branches.length
    ? `<table class="data payroll-modal-table"><thead><tr><th>Κλάδος</th><th>Ασφαλισμένου</th><th>Εργοδότη</th></tr></thead><tbody>` +
      branches.map((branch) =>
        `<tr><td>${esc(branch.label || branch.code || "")}</td>` +
        `<td class="payroll-money">${money(branch.employee_amount)} €</td>` +
        `<td class="payroll-money">${money(branch.employer_amount)} €</td></tr>`
      ).join("") +
      `</tbody></table>`
    : "";
  document.getElementById("payrollApdModalBody").innerHTML =
    gapHtml +
    `<dl class="payroll-apd-kv">` +
    `<div><dt>ΑΜΕ εργοδότη</dt><dd>${esc(apdValue(apd.employer_ame))}</dd></div>` +
    `<div><dt>ΑΦΜ εργοδότη</dt><dd>${esc(apdValue(apd.employer_afm))}</dd></div>` +
    `<div><dt>ΚΑΔ</dt><dd>${esc(apdValue(apd.employer_kad))}</dd></div>` +
    `<div><dt>ΑΦΜ εργαζομένου</dt><dd>${esc(apdValue(apd.employee_afm || row.employee_afm))}</dd></div>` +
    `<div><dt>ΑΜΚΑ</dt><dd>${esc(apdValue(apd.amka))}</dd></div>` +
    `<div><dt>ΑΜΑ</dt><dd>${esc(apdValue(apd.ama))}</dd></div>` +
    `<div><dt>Ημ. πρόσληψης</dt><dd>${esc(apdValue(displayDate(apd.hire_date || row.hire_date)))}</dd></div>` +
    `<div><dt>Κύρια ασφάλιση</dt><dd>${esc(apdValue(apd.kyria_asfalish))}</dd></div>` +
    `<div><dt>Επικουρική</dt><dd>${esc(apdValue(apd.auxiliary_fund_label || apd.auxiliary_fund_code))}</dd></div>` +
    `<div><dt>Ημέρες ασφάλισης</dt><dd>${esc(String(apd.insurance_days ?? 0))}</dd></div>` +
    `<div><dt>Ασφαλιστέες αποδοχές</dt><dd>${money(apd.insurable)} €</dd></div>` +
    `<div><dt>ΕΦΚΑ ασφαλισμένου</dt><dd>${money(apd.efka_employee)} €</dd></div>` +
    `<div><dt>ΕΦΚΑ εργοδότη</dt><dd>${money(apd.efka_employer)} €</dd></div>` +
    `</dl>` +
    packageHtml +
    branchHtml +
    `<div class="payroll-apd-xml"><label for="payrollApdXmlText">XML e-ΕΦΚΑ</label>` +
    `<textarea id="payrollApdXmlText" readonly>${esc(apd.xml || "")}</textarea></div>`;
  document.getElementById("payrollApdModal")?.classList.remove("hidden");
}

async function downloadExcel(kind) {
  const detailed = kind === "detailed";
  const button = document.getElementById(detailed ? "timekeepingDetailedExport" : "timekeepingExport");
  Office.setButtonLoading(button, true);
  try {
    const res = await fetch(detailed
      ? "/api/apologistic/timekeeping/export-detailed"
      : "/api/apologistic/timekeeping/export", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(periodPayload()),
    });
    if (!res.ok) {
      const data = await Office.parseJson(res);
      throw new Error(data.error || `HTTP ${res.status}`);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    const prefix = detailed ? "orometrisi_analysis" : "orometrisi";
    link.download = isMonthMode()
      ? `${prefix}_month_${String(year)}${String(month).padStart(2, "0")}.xlsx`
      : `${prefix}_${weekFrom.replaceAll("-", "")}.xlsx`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (error) {
    Office.showMsg("timekeepingMsg", error.message || String(error), false);
  } finally {
    Office.setButtonLoading(button, false);
  }
}

async function downloadPayrollExcel() {
  const button = document.getElementById("payrollExport");
  Office.setButtonLoading(button, true);
  try {
    const res = await fetch("/api/payroll/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payrollExportPayload()),
    });
    if (!res.ok) {
      const data = await Office.parseJson(res);
      throw new Error(data.error || `HTTP ${res.status}`);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = isMonthMode()
      ? `misthodosia_month_${String(year)}${String(month).padStart(2, "0")}.xlsx`
      : `misthodosia_${weekFrom.replaceAll("-", "")}.xlsx`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (error) {
    Office.showMsg("timekeepingMsg", error.message || String(error), false);
  } finally {
    Office.setButtonLoading(button, false);
  }
}

async function downloadPayrollApdXml() {
  try {
    await refreshPayrollApd();
  } catch (error) {
    Office.showMsg("timekeepingMsg", error.message || String(error), false);
    return;
  }
  const xml = payrollData?.apd_xml || "";
  if (!xml) {
    Office.showMsg("timekeepingMsg", "Δεν υπάρχει XML ΑΠΔ. Ανανεώστε την ωρομέτρηση.", false);
    return;
  }
  const blob = new Blob([xml], { type: "application/xml;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = isMonthMode()
    ? `apd_efka_month_${String(year)}${String(month).padStart(2, "0")}.xml`
    : `apd_efka_${weekFrom.replaceAll("-", "")}.xml`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

// Export the current edits; the server retains identity and recomputes totals.
function payrollExportPayload() {
  if (!payrollData || !payrollOriginal) throw new Error("Ανανεώστε πρώτα τη μισθοδοσία.");
  return { ...periodPayload(), store_id: payrollData.store?.id, adjustments: payrollData.employees || [] };
}

async function refreshPayrollApd() {
  const current = payrollData;
  const payload = payrollExportPayload();
  const edits = JSON.stringify(payload.adjustments);
  const res = await fetch("/api/payroll/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...payload, format: "apd-preview" }),
  });
  const data = await Office.parseJson(res);
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  if (current !== payrollData || edits !== JSON.stringify(payrollData.employees)) {
    throw new Error("Οι τιμές άλλαξαν κατά την εξαγωγή. Δοκιμάστε ξανά.");
  }
  for (const row of payrollData.employees) {
    row.apd = data.employees.find((item) => item.employee_afm === row.employee_afm)?.apd;
  }
  payrollData.apd_xml = data.apd_xml;
}
