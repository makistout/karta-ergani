let weekStart = previousMonday();
let reportState = { rows: [], store: null, filter: "all", selectedDate: "", dates: [] };

document.addEventListener("DOMContentLoaded", async () => {
  Office.setActiveNav("apologistic");
  document.getElementById("weekPrev").onclick = () => moveWeek(-7);
  document.getElementById("weekNext").onclick = () => moveWeek(7);
  document.getElementById("weekDefault").onclick = () => { weekStart = previousMonday(); loadReport(); };
  try {
    const active = await Office.fetchActiveStore();
    Office.applyActiveStoreChrome(active);
    await loadReport();
  } catch (e) { showError(e); }
});

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
    const contractTip = `${row.day_state} · ${row.contract_kind}${row.weekly_days ? ` · ${row.weekly_days}ήμερο` : ""}`;
    const declaredTip = `Δηλωμένο: ${row.declared} · Ευέλικτη προσέλευση: ${row.flex_minutes || 0} λεπτά`;
    const punchTip = `${row.actual} · ${row.punch_completeness} · ${row.data_source}` +
      (row.punch_count > 1 ? ` · ${row.punch_count} εγγραφές, αντιστοιχίστηκαν ανά δηλωμένο τμήμα` : "") +
      (row.orphan_punch_count ? ` · ${row.orphan_punch_count} ορφανές εγγραφές` : "");
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
    const resultTip = [row.reason, `Βεβαιότητα: ${row.confidence}`,
      row.proposal_basis ? `Βάση πρότασης: ${row.proposal_basis}` : "",
      row.requires_confirmation ? "Χρειάζεται επιβεβαίωση" : ""].filter(Boolean).join(" · ");
    html += `<tr class="apologistic-row--${row.status}">` +
      `<td title="${attr(`ΑΦΜ: ${row.employee_afm}`)}"><strong>${attr(`${row.eponymo || ""} ${row.onoma || ""}`.trim())}</strong></td>` +
      `<td title="${attr(contractTip)}">${attr(compactDayState(row.day_state))}</td>` +
      `<td title="${attr(declaredTip)}">${attr(compactScheduleLabel(row.declared))}</td>` +
      `<td title="${attr(punchTip)}">${attr(row.actual)}${row.overnight ? "*" : ""}</td>` +
      `<td title="Δηλωμένη διάρκεια">${mins(row.declared_minutes)}</td><td title="Πραγματική διάρκεια">${mins(row.actual_minutes)}</td>` +
      `<td title="Διαφορά πραγματικής από δηλωμένη έναρξη" class="${diffClass(row.start_difference_minutes)}">${signedMins(row.start_difference_minutes)}</td>` +
      `<td title="Διαφορά πραγματικής από δηλωμένη λήξη" class="${diffClass(row.end_difference_minutes)}">${signedMins(row.end_difference_minutes)}</td>` +
      `<td title="Πραγματική μείον δηλωμένη διάρκεια" class="${diffClass(row.gross_difference_minutes)}">${signedMins(row.gross_difference_minutes)}</td>` +
      `<td title="${attr(breakTip)}">${row.outside_break_minutes ? mins(row.outside_break_minutes) : "—"}</td>` +
      `<td title="${attr(netDetails)}" class="${diffClass(row.net_difference_minutes)}"><strong>${signedMins(row.net_difference_minutes)}</strong></td>` +
      `<td title="${attr(`Προτεινόμενο απολογιστικό: ${row.proposed} · ${row.proposal_basis || ""}`)}"><strong>${attr(compactScheduleLabel(row.proposed))}</strong></td>` +
      `<td title="${attr(resultTip)}"><span class="status-badge apologistic-status--${row.status}">${statusLabel(row.status)}</span></td></tr>`;
  }
  wrap.innerHTML = html + `</tbody></table>`;
}
