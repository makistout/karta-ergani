let weekStart = previousMonday();
const latestCompletedWeekStart = new Date(weekStart);
let reportState = { rows: [], store: null, filter: "all", selectedDate: "", dates: [] };
let openExplanationId = null;
let openEmployeeAfm = null;
let proposalEditRow = null;

document.addEventListener("DOMContentLoaded", async () => {
  Office.setActiveNav("apologistic");
  document.getElementById("weekPrev").onclick = () => moveWeek(-7);
  document.getElementById("weekNext").onclick = () => moveWeek(7);
  initExplanationModal();
  initEmployeeModal();
  initProposalModal();
  document.addEventListener("click", (event) => {
    const proposalButton = event.target.closest(".apologistic-proposal-btn");
    if (proposalButton) {
      event.stopPropagation();
      editProposal(proposalButton.dataset.employeeAfm || "", proposalButton.dataset.workDate || "");
      return;
    }
    const employeeButton = event.target.closest(".apologistic-employee-btn");
    if (employeeButton) {
      event.stopPropagation();
      openEmployeeDetail(employeeButton.dataset.employeeAfm || "");
      return;
    }
    const button = event.target.closest(".apologistic-info-btn");
    if (!button) return;
    event.stopPropagation();
    openExplanation(button.dataset.explanationId || "");
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (proposalEditRow) closeProposalEditor();
    else if (openEmployeeAfm) closeEmployeeDetail();
    else closeExplanation();
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

function initEmployeeModal() {
  const modal = document.getElementById("apologisticEmployeeModal");
  if (!modal || modal.dataset.bound) return;
  modal.dataset.bound = "1";
  modal.querySelectorAll("[data-apologistic-employee-close]").forEach((el) => {
    el.addEventListener("click", closeEmployeeDetail);
  });
}

function initProposalModal() {
  const modal = document.getElementById("apologisticProposalModal");
  const form = document.getElementById("apologisticProposalForm");
  if (!modal || !form || modal.dataset.bound) return;
  modal.dataset.bound = "1";
  modal.querySelectorAll("[data-apologistic-proposal-close]").forEach((el) => el.addEventListener("click", closeProposalEditor));
  modal.querySelectorAll(".input-time-24").forEach((input) => {
    input.addEventListener("input", () => { input.value = Office.formatHourMinuteInput(input.value || ""); });
    input.addEventListener("blur", () => {
      const normalized = Office.normalizeHourMinute(input.value || "");
      if (normalized) input.value = normalized;
    });
  });
  form.addEventListener("submit", saveProposalEditor);
}

const employeeContractFields = [
  ["employer_afm", "ΑΦΜ εργοδότη"], ["branch_aa", "Παράρτημα"], ["employee_afm", "ΑΦΜ εργαζομένου"],
  ["eponymo", "Επώνυμο"], ["onoma", "Όνομα"], ["specialty", "Ειδικότητα"],
  ["characterization", "Χαρακτηρισμός"], ["step92", "ΣΤΕΠ 92"],
  ["weekly_work_days", "Ημέρες εβδομαδιαίας απασχόλησης"], ["prior_service", "Προϋπηρεσία"],
  ["employment_relation", "Σχέση απασχόλησης"], ["fixed_term_from", "Ορισμένου χρόνου από"],
  ["fixed_term_to", "Ορισμένου χρόνου έως"], ["regime", "Καθεστώς"],
  ["weekly_hours", "Ώρες εβδομαδιαίως"], ["salary", "Αποδοχές"], ["hourly_wage", "Ωρομίσθιο"],
  ["total_weekly_hours", "Συνολικές ώρες εβδομαδιαίως"],
  ["fulltime_contract_weekly_hours", "Συμβατικές ώρες πλήρους απασχόλησης"],
  ["break_minutes", "Διάλειμμα (λεπτά)"], ["break_in_work", "Διάλειμμα εντός ωραρίου"],
  ["flex_arrival_minutes", "Ευέλικτη προσέλευση (λεπτά)"],
  ["ergani_updated_at", "Ημ/νία τελευταίας ενημέρωσης Ergani"], ["synced_at", "Τελευταίος συγχρονισμός"],
  ["source", "Πηγή"],
];

function employeeContractValue(key, value) {
  if (value == null || value === "") return "—";
  if (key === "break_in_work") return value === 1 || value === true || value === "1" ? "Ναι" : "Όχι";
  if (key === "flex_arrival_minutes" && Office.formatFlexMinutes) return Office.formatFlexMinutes(value);
  if (key === "synced_at") return String(value).replace("T", " ").slice(0, 19);
  return String(value);
}

function employeeContractTable(row) {
  return `<table class="data employee-contract-fields-table"><thead><tr><th>Πεδίο</th><th>Τιμή</th></tr></thead><tbody>` +
    employeeContractFields.map(([key, label]) => `<tr><td class="employee-contract-field-label">${attr(label)}</td><td>${attr(employeeContractValue(key, row?.[key]))}</td></tr>`).join("") +
    `</tbody></table>`;
}

async function openEmployeeDetail(afm) {
  const cleanAfm = String(afm || "").replace(/\D/g, "");
  const modal = document.getElementById("apologisticEmployeeModal");
  const title = document.getElementById("apologisticEmployeeModalTitle");
  const meta = document.getElementById("apologisticEmployeeModalMeta");
  const body = document.getElementById("apologisticEmployeeModalBody");
  if (!cleanAfm || !modal || !title || !meta || !body) return;
  closeExplanation();
  openEmployeeAfm = cleanAfm;
  title.textContent = "Στοιχεία εργαζομένου";
  meta.textContent = `ΑΦΜ ${cleanAfm}`;
  body.innerHTML = `<p class="apologistic-employee-loading"><i class="bi bi-hourglass-split"></i> Φόρτωση…</p>`;
  modal.classList.remove("hidden");
  try {
    const res = await fetch(`/api/employees/contract/history?employee_afm=${encodeURIComponent(cleanAfm)}`, {cache:"no-store"});
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
    body.innerHTML = `<section><h3>Τρέχουσα κατάσταση</h3>${employeeContractTable(current)}</section>` +
      (previous.length ? `<details class="apologistic-employee-history"><summary>Προηγούμενες εκδόσεις (${previous.length})</summary>` +
        previous.map((row) => `<details><summary>${attr(employeeContractValue("synced_at", row.synced_at))} · ${attr(employeeContractValue("specialty", row.specialty))}</summary>${employeeContractTable(row)}</details>`).join("") +
        `</details>` : "");
  } catch (error) {
    if (openEmployeeAfm === cleanAfm) body.innerHTML = `<p style="color:var(--err);">${attr(error)}</p>`;
  }
}

function closeEmployeeDetail() {
  const modal = document.getElementById("apologisticEmployeeModal");
  const body = document.getElementById("apologisticEmployeeModalBody");
  openEmployeeAfm = null;
  modal?.classList.add("hidden");
  if (body) body.innerHTML = "";
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
function syncWeekNavigation() {
  const next = document.getElementById("weekNext");
  if (!next) return;
  const disabled = iso(weekStart) >= iso(latestCompletedWeekStart);
  next.disabled = disabled;
  next.setAttribute("aria-disabled", disabled ? "true" : "false");
  next.title = disabled ? "Η τρέχουσα και οι επόμενες εβδομάδες δεν έχουν ακόμη απολογιστικά δεδομένα" : "Επόμενη ολοκληρωμένη εβδομάδα";
}
function moveWeek(days) {
  const candidate = addDays(weekStart, days);
  if (candidate > latestCompletedWeekStart) return;
  weekStart = candidate;
  syncWeekNavigation();
  loadReport();
}
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
function statusShortLabel(status) { return status === "ok" ? "Σ" : status === "change" ? "Μ" : "Ε"; }
function rowExplanationId(row) { return `${row.employee_afm}-${String(row.work_date || "").replace(/\//g, "")}`; }

function proposalHistory(row) {
  const history = Array.isArray(row.proposal_history) ? row.proposal_history : [];
  if (!history.length) return `<div class="apologistic-proposal-history-empty">Δεν έχει γίνει χειροκίνητη αλλαγή.</div>`;
  return history.map((item) => {
    const when = item.changed_at ? new Date(item.changed_at).toLocaleString("el-GR") : "—";
    return `<div class="apologistic-proposal-history-item"><strong>${attr(item.new_value || "—")}</strong>` +
      `<span>${attr(item.old_value || "—")} → ${attr(item.new_value || "—")}</span>` +
      `<small>${attr(when)}${item.changed_by ? ` · ${attr(item.changed_by)}` : ""}</small></div>`;
  }).join("");
}

async function editProposal(employeeAfm, workDate) {
  const row = reportState.rows.find((item) => item.employee_afm === employeeAfm && item.work_date === workDate);
  if (!row) return;
  const match = String(row.proposed || "").match(/(\d{2}:\d{2})\s*[–-]\s*(\d{2}:\d{2})/);
  proposalEditRow = row;
  document.getElementById("apologisticProposalModalMeta").textContent = `${row.eponymo || ""} ${row.onoma || ""} · ${row.work_date}`;
  document.getElementById("apologisticProposalFrom").value = match?.[1] || "";
  document.getElementById("apologisticProposalTo").value = match?.[2] || "";
  document.getElementById("apologisticProposalError").textContent = "";
  document.getElementById("apologisticProposalModal").classList.remove("hidden");
  setTimeout(() => document.getElementById("apologisticProposalFrom")?.focus(), 0);
}

function closeProposalEditor() {
  proposalEditRow = null;
  document.getElementById("apologisticProposalModal")?.classList.add("hidden");
  const error = document.getElementById("apologisticProposalError");
  if (error) error.textContent = "";
}

async function saveProposalEditor(event) {
  event.preventDefault();
  const row = proposalEditRow;
  if (!row) return;
  const from = Office.normalizeHourMinute(document.getElementById("apologisticProposalFrom").value || "");
  const to = Office.normalizeHourMinute(document.getElementById("apologisticProposalTo").value || "");
  const errorBox = document.getElementById("apologisticProposalError");
  if (!from || !to) {
    errorBox.textContent = "Συμπληρώστε έγκυρες ώρες σε μορφή ΩΩ:ΛΛ.";
    return;
  }
  const requested = `${from}–${to}`;
  if (requested === row.proposed) { closeProposalEditor(); return; }
  try {
    const res = await fetch("/api/apologistic/proposal", {
      method: "PUT", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({week_from: iso(weekStart), employee_afm: row.employee_afm, work_date: row.work_date, proposed: requested}),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    row.proposed = data.proposed;
    row.proposal_history = data.history || [];
    closeProposalEditor();
    renderVisibleRows();
  } catch (error) {
    errorBox.textContent = String(error.message || error);
  }
}

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

  if (Array.isArray(row.weekly_punch_details) && row.weekly_punch_details.length) {
    body.innerHTML = weeklyNonWorkExplanation(row);
  } else {
    const lines = Array.isArray(row.status_explanation) ? row.status_explanation : [row.reason || ""];
    body.innerHTML = `<ul class="apologistic-info-list">${lines.map((line) => `<li>${attr(line)}</li>`).join("")}</ul>`;
  }

  modal.classList.remove("hidden");
  document.querySelectorAll(`.apologistic-info-btn[data-explanation-id="${id}"]`).forEach((button) => {
    button.setAttribute("aria-expanded", "true");
  });
}

function weeklyNonWorkExplanation(row) {
  const currentPunches = String(row.punch_recorded || "—").split("\n").filter(Boolean);
  const weeklyDays = row.weekly_punch_details || [];
  const candidates = row.replacement_candidates || [];
  const ignoredPrefixes = [
    "Αποτέλεσμα:", "Χτύπημα σε ", "Καταγεγραμμένα χτυπήματα", "  · ",
    "Εβδομαδιαίος έλεγχος:", "Η τρέχουσα σύμβαση προβλέπει",
    "Αναλυτικές ημέρες και χτυπήματα", "Οι ημέρες με κάρτα καλύπτουν",
    "Δηλωμένες ημέρες εργασίας χωρίς χτύπημα", "Δεν βρέθηκε δηλωμένη ημέρα",
  ];
  const notes = (row.status_explanation || []).filter((line) =>
    line && !ignoredPrefixes.some((prefix) => String(line).startsWith(prefix))
  );
  const dayRows = weeklyDays.map((item) => {
    const current = item.work_date === row.work_date;
    return `<div class="apologistic-analysis-day${current ? " is-current" : ""}">` +
      `<span>${attr(item.work_date)}${current ? " <em>τρέχουσα</em>" : ""}</span>` +
      `<strong>${attr((item.punches || []).join(" · ") || "—")}</strong></div>`;
  }).join("");
  const candidateRows = candidates.length
    ? candidates.map((item) => `<div class="apologistic-analysis-candidate"><span>${attr(item.work_date)}</span><strong>${attr(item.declared)}</strong></div>`).join("")
    : `<p class="apologistic-analysis-empty">Δεν βρέθηκε δηλωμένη ημέρα εργασίας χωρίς χτύπημα.</p>`;
  return `<div class="apologistic-analysis-grid">` +
    `<section class="apologistic-analysis-card"><h3><i class="bi bi-calendar-event"></i> Τρέχουσα ημέρα</h3>` +
      `<dl><div><dt>Κατάσταση</dt><dd>${attr(row.day_state || "—")}</dd></div>` +
      `<div><dt>Χτύπημα${currentPunches.length > 1 ? "τα" : ""}</dt><dd>${currentPunches.map(attr).join(" · ")}</dd></div>` +
      `<div><dt>Πρόταση</dt><dd>${attr(row.proposed || "—")}</dd></div></dl></section>` +
    `<section class="apologistic-analysis-card"><h3><i class="bi bi-calendar-week"></i> Έλεγχος εβδομάδας</h3>` +
      `<div class="apologistic-analysis-metrics"><div><strong>${attr(row.weekly_punch_days ?? weeklyDays.length)}</strong><span>ημέρες με κάρτα</span></div>` +
      `<div><strong>${attr(row.contract_required_days ?? "—")}</strong><span>ημέρες σύμβασης</span></div></div>` +
      `<div class="apologistic-analysis-days">${dayRows}</div></section>` +
    `<section class="apologistic-analysis-card"><h3><i class="bi bi-arrow-left-right"></i> Υποψήφιες ημέρες αντικατάστασης</h3>${candidateRows}</section>` +
    (notes.length ? `<section class="apologistic-analysis-card"><h3><i class="bi bi-info-circle"></i> Παρατηρήσεις</h3><ul>${notes.map((line) => `<li>${attr(line)}</li>`).join("")}</ul></section>` : "") +
    `<section class="apologistic-analysis-conclusion apologistic-analysis-conclusion--${attr(row.status)}">` +
      `<div><span>Συμπέρασμα</span><strong>${attr(row.reason || "—")}</strong></div>` +
      `<span class="status-badge apologistic-status--${attr(row.status)}">${attr(statusLabel(row.status))}</span></section>` +
    `</div>`;
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
function overtimeCell(row) {
  const segments = row.overtime_segments || [];
  if (!segments.length) return "—";
  return segments.map((segment) => `${attr(segment.from)}–${attr(segment.to)}`).join("<br>");
}

async function loadReport() {
  const wrap = document.getElementById("apologisticWrap");
  const end = addDays(weekStart, 6);
  document.getElementById("weekLabel").textContent = `${weekStart.toLocaleDateString("el-GR")} – ${end.toLocaleDateString("el-GR")}`;
  syncWeekNavigation();
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
  html += `<table class="data apologistic-table"><thead><tr><th>Εργαζόμενος</th><th>Κατάσταση</th><th>Δηλωμένο</th><th>Χτύπημα</th><th>Δηλωμένες ώρες</th><th>Πραγματικές ώρες</th><th>Διαφ. έναρξης</th><th>Διαφ. λήξης</th><th>Μικτή διαφορά</th><th>Διάλ. εκτός</th><th>Καθαρή διαφορά</th><th>Υπερωρίες</th><th>Πρόταση</th><th>Αποτέλεσμα</th></tr></thead><tbody>`;
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
      ...(row.overtime_segments || []).map((segment) => `Υποβολή ${segment.date}: ${segment.from}–${segment.to}`),
      ...(row.corrected_extra_punches || []).map((item) => `Λανθασμένο πρόσθετο χτύπημα: κλείσιμο ${item.corrected}`),
      row.undeclared_extra_minutes ? `Πρόσθετος χρόνος χωρίς δήλωση υπερωρίας: ${mins(row.undeclared_extra_minutes)}` : "",
      row.unlawful_overtime_minutes ? `Πέρα από το ημερήσιο όριο 4 ωρών: ${mins(row.unlawful_overtime_minutes)}` : "",
      row.night_minutes ? `Νυχτερινά: ${mins(row.night_minutes)}` : "",
      row.classification_warning || "",
    ].filter(Boolean).join(" · ");
    html += `<tr class="apologistic-row--${row.status}">` +
      `<td title="${attr(`ΑΦΜ: ${row.employee_afm} · Κλικ για στοιχεία σύμβασης`)}"><button type="button" class="apologistic-employee-btn" data-employee-afm="${attr(row.employee_afm)}">${attr(`${row.eponymo || ""} ${row.onoma || ""}`.trim())}</button></td>` +
      `<td title="${attr(contractTip)}">${attr(compactDayState(row.day_state))}</td>` +
      `<td title="${attr(declaredTip)}">${attr(compactScheduleLabel(row.declared))}</td>` +
      `<td class="apologistic-punch-cell" title="${attr(punchTip)}">${formatPunchCell(punchRecorded)}${row.overnight ? "*" : ""}</td>` +
      `<td title="Δηλωμένη διάρκεια">${mins(row.declared_minutes)}</td><td title="Πραγματική διάρκεια${row.actual && row.actual !== punchRecorded ? ` (τεκμαίρεται: ${row.actual})` : ""}">${mins(row.actual_minutes)}</td>` +
      `<td title="Διαφορά πραγματικής από δηλωμένη έναρξη" class="${diffClass(row.start_difference_minutes)}">${signedMins(row.start_difference_minutes)}</td>` +
      `<td title="Διαφορά πραγματικής από δηλωμένη λήξη" class="${diffClass(row.end_difference_minutes)}">${signedMins(row.end_difference_minutes)}</td>` +
      `<td title="Πραγματική μείον δηλωμένη διάρκεια" class="${diffClass(row.gross_difference_minutes)}">${signedMins(row.gross_difference_minutes)}</td>` +
      `<td title="${attr(breakTip)}">${row.outside_break_minutes ? mins(row.outside_break_minutes) : "—"}</td>` +
      `<td title="${attr(netDetails)}" class="${diffClass(row.net_difference_minutes)}"><strong>${signedMins(row.net_difference_minutes)}</strong></td>` +
      `<td title="${attr((row.overtime_segments || []).map((segment) => `${segment.date}: ${segment.from}–${segment.to} (${mins(segment.minutes)})`).join(" · ") || "Δεν προκύπτει υπερωρία")}" class="${row.overtime_minutes ? "time-diff--plus" : ""}"><strong>${overtimeCell(row)}</strong></td>` +
      `<td class="apologistic-proposal-cell"><div class="apologistic-proposal-wrap">` +
      `<button type="button" class="apologistic-proposal-btn" data-employee-afm="${attr(row.employee_afm)}" data-work-date="${attr(row.work_date)}" title="Κλικ για αλλαγή προτεινόμενου ωραρίου"><strong>${attr(compactScheduleLabel(row.proposed))}</strong></button>` +
      `<div class="apologistic-proposal-history"><b>Ιστορικό πρότασης</b>${proposalHistory(row)}</div></div></td>` +
      `<td class="apologistic-result-cell" title="${attr(statusLabel(row.status))}"><span class="status-badge apologistic-status--${row.status}">${statusShortLabel(row.status)}</span>` +
      `<button type="button" class="apologistic-info-btn" data-explanation-id="${attr(explanationId)}" aria-expanded="false" aria-label="Λεπτομέρειες αποτελέσματος"><i class="bi bi-info-circle" aria-hidden="true"></i></button></td></tr>`;
    if ((row.replacement_candidates || []).length) {
      html += `<tr class="apologistic-replacement-row"><td colspan="14"><div class="apologistic-replacement-options">` +
        `<span><i class="bi bi-arrow-left-right" aria-hidden="true"></i> Υποψήφιες ημέρες αντικατάστασης:</span>` +
        row.replacement_candidates.map((item) => `<strong>${attr(item.work_date)} · ${attr(item.declared)}</strong>`).join("") +
        `</div></td></tr>`;
    }
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
