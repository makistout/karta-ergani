let weekStart = previousMonday();
let reportState = { rows: [], store: null, filter: "all", selectedDate: "", dates: [] };
let openExplanationId = null;

document.addEventListener("DOMContentLoaded", async () => {
  Office.setActiveNav("apologistic");
  document.getElementById("weekPrev").onclick = () => moveWeek(-7);
  document.getElementById("weekNext").onclick = () => moveWeek(7);
  initExplanationModal();
  document.addEventListener("click", (event) => {
    const button = event.target.closest(".apologistic-info-btn");
    if (!button) return;
    event.stopPropagation();
    openExplanation(button.dataset.explanationId || "");
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeExplanation();
  });
  try {
    const active = await Office.fetchActiveStore();
    Office.applyActiveStoreChrome(active);
    await loadReport();
  } catch (e) { showError(e); }
});

function initExplanationModal() {
  const modal = document.getElementById("apologisticInfoModal");
  if (!modal || modal.dataset.bound) return;
  modal.dataset.bound = "1";
  modal.querySelectorAll("[data-apologistic-info-close]").forEach((el) => {
    el.addEventListener("click", closeExplanation);
  });
}

function previousMonday() {
  const now = new Date();
  const day = (now.getDay() + 6) % 7;
  const monday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - day - 7);
  monday.setHours(12, 0, 0, 0);
  return monday;
}
function iso(d) { return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`; }
function addDays(d, n) { const x = new Date(d); x.setDate(x.getDate() + n); return x; }
function moveWeek(days) { weekStart = addDays(weekStart, days); loadReport(); }
function mins(value) {
  if (value == null) return "—";
  const h = Math.floor(value / 60), m = value % 60;
  return `${h}:${String(m).padStart(2, "0")}`;
}
function signedMins(value) {
  if (value == null) return "—";
  if (value === 0) return "0:00";
  return `${value > 0 ? "+" : "−"}${mins(Math.abs(value))}`;
}
function diffClass(value) { return value > 0 ? "time-diff--plus" : value < 0 ? "time-diff--minus" : ""; }
function attr(value) { return Office.escapeHtml(String(value ?? "")); }
function statusLabel(status) { return status === "ok" ? "Σύμφωνο" : status === "change" ? "Μεταβολή" : "Έλεγχος"; }
function rowExplanationId(row) { return `${row.employee_afm}-${String(row.work_date || "").replace(/\//g, "")}`; }

function findExplanationRow(id) {
  return reportState.rows.find((row) => rowExplanationId(row) === id) || null;
}

function closeExplanation() {
  openExplanationId = null;
  document.getElementById("apologisticInfoModal")?.classList.add("hidden");
  document.querySelectorAll(".apologistic-info-btn[aria-expanded='true']").forEach((button) => {
    button.setAttribute("aria-expanded", "false");
  });
}

function openExplanation(id) {
  if (!id) return;
  const row = findExplanationRow(id);
  const modal = document.getElementById("apologisticInfoModal");
  const title = document.getElementById("apologisticInfoModalTitle");
  const sub = document.getElementById("apologisticInfoModalSub");
  const body = document.getElementById("apologisticInfoModalBody");
  if (!row || !modal || !title || !sub || !body) return;

  openExplanationId = id;
  document.querySelectorAll(".apologistic-info-btn[aria-expanded='true']").forEach((button) => {
    button.setAttribute("aria-expanded", "false");
  });

  const employeeName = `${row.eponymo || ""} ${row.onoma || ""}`.trim();
  title.textContent = "Ανάλυση αποτελέσματος";
  sub.innerHTML = `<strong>${attr(employeeName)}</strong> · ${attr(row.work_date || "")} · ` +
    `<span class="status-badge apologistic-status--${attr(row.status)}">${attr(statusLabel(row.status))}</span>`;

  const lines = Array.isArray(row.status_explanation) ? row.status_explanation : [row.reason || ""];
  body.innerHTML = `<ul class="apologistic-info-list">${lines.map((line) => `<li>${attr(line)}</li>`).join("")}</ul>`;

  modal.classList.remove("hidden");
  document.querySelectorAll(`.apologistic-info-btn[data-explanation-id="${id}"]`).forEach((button) => {
    button.setAttribute("aria-expanded", "true");
  });
}

function formatPunchPart(value, title) {
  if ((value || "").trim()) return attr(value.trim());
  return `<span class="report-missing-time" title="${attr(title)}">${Office.icon("clock")}</span>`;
}

function formatPunchLine(line) {
  const raw = String(line || "").trim();
  if (!raw || raw === "—") return "—";
  const dashIdx = raw.indexOf("–");
  if (dashIdx === -1) return attr(raw);
  const start = raw.slice(0, dashIdx).trim();
  const end = raw.slice(dashIdx + 1).trim();
  if (!start && !end) return "—";
  return `${formatPunchPart(start, "Λείπει ώρα εισόδου")}–${formatPunchPart(end, "Λείπει ώρα εξόδου")}`;
}

function formatPunchCell(value) {
  const raw = String(value || "").trim();
  if (!raw || raw === "—") return "—";
  return raw.split("\n").map((line) => formatPunchLine(line)).join("<br>");
}

function compactScheduleLabel(value) {
  const raw = String(value || "").trim();
  const upper = raw.toLocaleUpperCase("el-GR");
  if (!raw) return "—";
  if (upper.includes("ΚΑΝΟΝΙΚ") && upper.includes("ΑΔΕΙΑ")) return "Κανονική άδεια";
  if (upper.includes("ΑΔΕΙΑ")) {
    const match = raw.match(/^(.{0,60}?άδεια)/i);
    return match ? match[1].trim() : "Άδεια";
  }
  if (upper.includes("ΑΝΑΠΑΥΣ") || upper.includes("ΡΕΠΟ")) return "ΑΝΑΠΑΥΣΗ/ΡΕΠΟ";
  if (upper.includes("ΜΗ ΕΡΓΑΣΙΑ")) return "ΜΗ ΕΡΓΑΣΙΑ";
  if (upper.includes("ΑΡΓΙΑ")) return "ΑΡΓΙΑ";
  return raw;
}
function compactDayState(value) {
  return ({"Εργασία":"Εργ.", "Ρεπό":"Ρεπό", "Μη εργασία":"Μη εργ.", "Τηλεργασία":"Τηλεργ.", "Άδεια":"Άδεια", "Αργία":"Αργία"})[value] || "Χωρίς";
}

async function loadReport() {
  const wrap = document.getElementById("apologisticWrap");
  const end = addDays(weekStart, 6);
  document.getElementById("weekLabel").textContent = `${weekStart.toLocaleDateString("el-GR")} – ${end.toLocaleDateString("el-GR")}`;
  Office.showTableLoading(wrap);
  closeExplanation();
  const res = await fetch(`/api/apologistic/week?from=${iso(weekStart)}&to=${iso(end)}`);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) return showError(data.error || `HTTP ${res.status}`);
  reportState = {
    rows: data.days || [], store: data.store, filter: "all",
    dates: data.work_dates || [], selectedDate: (data.work_dates || [])[0] || "",
  };
  renderSummary(data);
  renderDayTabs();
  renderVisibleRows();
  document.getElementById("apologisticNotice").textContent = data.legal_notice || "";
}
function showError(error) {
  document.getElementById("apologisticWrap").innerHTML = `<p style="color:var(--err);">${Office.escapeHtml(String(error))}</p>`;
}
function renderSummary(data) {
  const counts = data.counts || {};
  document.getElementById("apologisticSummary").innerHTML =
    `<div class="card apologistic-kpi"><span>Εργαζόμενοι</span><strong>${(data.employees || []).length}</strong></div>` +
    `<button type="button" class="card apologistic-kpi apologistic-kpi--filter" data-report-filter="all" title="Εμφάνιση όλων των αποτελεσμάτων"><span>Αποτελέσματα</span><strong>${counts.all || 0}</strong></button>` +
    `<button type="button" class="card apologistic-kpi apologistic-kpi--ok apologistic-kpi--filter" data-report-filter="ok" title="Εμφάνιση μόνο των σύμφωνων εγγραφών"><span>Σύμφωνο</span><strong>${counts.ok || 0}</strong></button>` +
    `<button type="button" class="card apologistic-kpi apologistic-kpi--change apologistic-kpi--filter" data-report-filter="change" title="Εμφάνιση μόνο των μεταβολών"><span>Μεταβολές</span><strong>${counts.change || 0}</strong></button>` +
    `<button type="button" class="card apologistic-kpi apologistic-kpi--review apologistic-kpi--filter" data-report-filter="review" title="Εμφάνιση μόνο των εγγραφών για έλεγχο"><span>Για έλεγχο</span><strong>${counts.review || 0}</strong></button>`;
  document.querySelectorAll("[data-report-filter]").forEach((button) => {
    button.addEventListener("click", () => applyReportFilter(button.dataset.reportFilter || "all"));
  });
  syncFilterButtons();
}
function applyReportFilter(requested) {
  reportState.filter = requested !== "all" && reportState.filter === requested ? "all" : requested;
  renderVisibleRows();
  syncFilterButtons();
}
function syncFilterButtons() {
  document.querySelectorAll("[data-report-filter]").forEach((button) => {
    const active = button.dataset.reportFilter === reportState.filter;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
}
function renderDayTabs() {
  const mount = document.getElementById("apologisticDayTabs");
  const weekdayNames = ["Δευτέρα", "Τρίτη", "Τετάρτη", "Πέμπτη", "Παρασκευή", "Σάββατο", "Κυριακή"];
  mount.innerHTML = reportState.dates.map((date, index) => {
    const count = reportState.rows.filter((row) => row.work_date === date).length;
    return `<button type="button" class="apologistic-day-tab${date === reportState.selectedDate ? " is-active" : ""}" ` +
      `data-work-date="${attr(date)}" aria-pressed="${date === reportState.selectedDate ? "true" : "false"}">` +
      `<span>${weekdayNames[index] || "Ημέρα"}</span><strong>${attr(date.slice(0, 5))}</strong><small>${count}</small></button>`;
  }).join("");
  mount.querySelectorAll("[data-work-date]").forEach((button) => {
    button.addEventListener("click", () => {
      reportState.selectedDate = button.dataset.workDate || "";
      renderDayTabs();
      renderVisibleRows();
    });
  });
}
function renderVisibleRows() {
  let rows = reportState.rows.filter((row) => row.work_date === reportState.selectedDate);
  if (reportState.filter !== "all") rows = rows.filter((row) => row.status === reportState.filter);
  renderRows(rows, reportState.store);
}
function renderRows(rows, store) {
  const wrap = document.getElementById("apologisticWrap");
  if (!rows.length) {
    const suffix = reportState.filter === "all" ? "" : " με το ενεργό φίλτρο";
    wrap.innerHTML = `<p style="color:var(--muted);">Δεν υπάρχουν αποτελέσματα για ${attr(reportState.selectedDate)}${suffix}.</p>`;
    return;
  }
  const filterLabel = reportState.filter === "ok" ? " · φίλτρο: Σύμφωνο" : reportState.filter === "change" ? " · φίλτρο: Μεταβολές" : reportState.filter === "review" ? " · φίλτρο: Για έλεγχο" : "";
  let html = `<p class="table-meta"><i class="bi bi-shop-window"></i> <strong>${Office.escapeHtml(store?.name || "")}</strong> · ${attr(reportState.selectedDate)} · ${rows.length} εργαζόμενοι${filterLabel}</p>`;
  html += `<table class="data apologistic-table"><thead><tr><th>Εργαζόμενος</th><th>Κατάσταση</th><th>Δηλωμένο</th><th>Χτύπημα</th><th>Δηλωμένες ώρες</th><th>Πραγματικές ώρες</th><th>Διαφ. έναρξης</th><th>Διαφ. λήξης</th><th>Μικτή διαφορά</th><th>Διάλειμμα εκτός</th><th>Καθαρή διαφορά</th><th>Πρόταση</th><th>Αποτέλεσμα</th></tr></thead><tbody>`;
  for (const row of rows) {
    const punchRecorded = row.punch_recorded ?? row.actual ?? "—";
    const explanationId = rowExplanationId(row);
    const contractTip = `${row.day_state} · ${row.contract_kind}${row.weekly_days ? ` · ${row.weekly_days}ήμερο` : ""}`;
    const declaredTip = `Δηλωμένο: ${row.declared} · Ευέλικτη προσέλευση: ${row.flex_minutes || 0} λεπτά`;
    const punchTip = [
      `Καταγεγραμμένα: ${punchRecorded}`,
      row.actual && row.actual !== punchRecorded ? `Για υπολογισμό (τεκμαίρεται): ${row.actual}` : "",
      row.punch_completeness,
      row.data_source,
      row.punch_count > 1 ? `${row.punch_count} εγγραφές στην κάρτα` : "",
      row.orphan_punch_count ? `${row.orphan_punch_count} μη αντιστοιχισμένες` : "",
    ].filter(Boolean).join(" · ");
    const breakTip = row.break_minutes
      ? `Δηλωμένο διάλειμμα: ${mins(row.break_minutes)} · Εκτός ωραρίου που αφαιρέθηκε: ${mins(row.outside_break_minutes)}`
      : "Δεν υπάρχει δηλωμένο διάλειμμα";
    const netDetails = [
      `Καθαρή διαφορά: ${signedMins(row.net_difference_minutes)}`,
      row.overwork_minutes ? `Υπερεργασία: ${mins(row.overwork_minutes)}` : "",
      row.overtime_minutes ? `Υπερωρία: ${mins(row.overtime_minutes)}${row.overtime_from && row.overtime_to ? ` (${row.overtime_from}–${row.overtime_to})` : ""}` : "",
      row.undeclared_extra_minutes ? `Πρόσθετος χρόνος χωρίς δήλωση υπερωρίας: ${mins(row.undeclared_extra_minutes)}` : "",
      row.unlawful_overtime_minutes ? `Πέρα από το ημερήσιο όριο 4 ωρών: ${mins(row.unlawful_overtime_minutes)}` : "",
      row.night_minutes ? `Νυχτερινά: ${mins(row.night_minutes)}` : "",
      row.classification_warning || "",
    ].filter(Boolean).join(" · ");
    html += `<tr class="apologistic-row--${row.status}">` +
      `<td title="${attr(`ΑΦΜ: ${row.employee_afm}`)}"><strong>${attr(`${row.eponymo || ""} ${row.onoma || ""}`.trim())}</strong></td>` +
      `<td title="${attr(contractTip)}">${attr(compactDayState(row.day_state))}</td>` +
      `<td title="${attr(declaredTip)}">${attr(compactScheduleLabel(row.declared))}</td>` +
      `<td class="apologistic-punch-cell" title="${attr(punchTip)}">${formatPunchCell(punchRecorded)}${row.overnight ? "*" : ""}</td>` +
      `<td title="Δηλωμένη διάρκεια">${mins(row.declared_minutes)}</td><td title="Πραγματική διάρκεια${row.actual && row.actual !== punchRecorded ? ` (τεκμαίρεται: ${row.actual})` : ""}">${mins(row.actual_minutes)}</td>` +
      `<td title="Διαφορά πραγματικής από δηλωμένη έναρξη" class="${diffClass(row.start_difference_minutes)}">${signedMins(row.start_difference_minutes)}</td>` +
      `<td title="Διαφορά πραγματικής από δηλωμένη λήξη" class="${diffClass(row.end_difference_minutes)}">${signedMins(row.end_difference_minutes)}</td>` +
      `<td title="Πραγματική μείον δηλωμένη διάρκεια" class="${diffClass(row.gross_difference_minutes)}">${signedMins(row.gross_difference_minutes)}</td>` +
      `<td title="${attr(breakTip)}">${row.outside_break_minutes ? mins(row.outside_break_minutes) : "—"}</td>` +
      `<td title="${attr(netDetails)}" class="${diffClass(row.net_difference_minutes)}"><strong>${signedMins(row.net_difference_minutes)}</strong></td>` +
      `<td title="${attr(`Προτεινόμενο απολογιστικό: ${row.proposed} · ${row.proposal_basis || ""}`)}"><strong>${attr(compactScheduleLabel(row.proposed))}</strong></td>` +
      `<td class="apologistic-result-cell"><span class="status-badge apologistic-status--${row.status}">${statusLabel(row.status)}</span>` +
      `<button type="button" class="apologistic-info-btn" data-explanation-id="${attr(explanationId)}" aria-expanded="false" aria-label="Λεπτομέρειες αποτελέσματος"><i class="bi bi-info-circle" aria-hidden="true"></i></button></td></tr>`;
  }
  wrap.innerHTML = html + `</tbody></table>`;
  if (openExplanationId) {
    const modal = document.getElementById("apologisticInfoModal");
    if (findExplanationRow(openExplanationId) && modal && !modal.classList.contains("hidden")) {
      openExplanation(openExplanationId);
    } else {
      closeExplanation();
    }
  }
}
