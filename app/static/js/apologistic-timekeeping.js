const qs = new URLSearchParams(location.search);
const weekFrom = qs.get("week_from") || "";
const year = qs.get("year") || "";
const month = qs.get("month") || "";
let timekeepingData = null;

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

document.addEventListener("DOMContentLoaded", async () => {
  Office.setActiveNav("apologistic");
  document.getElementById("timekeepingBack").href = buildBackHref();
  document.getElementById("timekeepingExport").addEventListener("click", () => downloadExcel("summary"));
  document.getElementById("timekeepingDetailedExport").addEventListener("click", () => downloadExcel("detailed"));
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
  renderRows(data.employees || []);
}

function renderRows(rows) {
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
  ];
  const familyHeaders = families.map(([, label]) =>
    `<th colspan="4">${esc(label)}</th>`
  ).join("");
  const zoneHeaders = zones.map(([, label]) => `<th>${esc(label)}</th>`).join("");
  const detailHeaders = `<th>Βάση (ώρες)</th>${zoneHeaders}${families.map(() => zoneHeaders).join("")}`;
  const breakdownCells = (row, field) => zones.map(([key]) =>
    `<td>${duration(row[field]?.[key])}</td>`
  ).join("");
  document.getElementById("timekeepingWrap").innerHTML =
    `<table class="data apologistic-timekeeping-table"><thead>` +
    `<tr><th rowspan="2">Εργαζόμενος</th><th colspan="5">Αναγνωρισμένη βάση</th>${familyHeaders}</tr>` +
    `<tr>${detailHeaders}</tr></thead><tbody>${rows.map((row) => `<tr>` +
      `<td>${esc(`${row.eponymo || ""} ${row.onoma || ""}`.trim())}<br><small>${esc(row.employee_afm)}</small></td>` +
      `<td>${duration(row.recognized_work_minutes)}</td><td>${duration(row.day)}</td>` +
      `<td>${duration(row.night)}</td><td>${duration(row.sunday_holiday)}</td>` +
      `<td>${duration(row.night_sunday_holiday)}</td>` +
      families.map(([field]) => breakdownCells(row, field)).join("") + `</tr>`
    ).join("")}</tbody></table>`;
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
