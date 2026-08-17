const EMP_MONTH_NAMES = ["Ιανουάριος", "Φεβρουάριος", "Μάρτιος", "Απρίλιος", "Μάιος", "Ιούνιος", "Ιούλιος", "Αύγουστος", "Σεπτέμβριος", "Οκτώβριος", "Νοέμβριος", "Δεκέμβριος"];
const EMP_DAY_NAMES = ["Κυρ", "Δευ", "Τρι", "Τετ", "Πεμ", "Παρ", "Σαβ"];
const apologisticToolbar = document.querySelector(".apologistic-toolbar");
const viewMode = apologisticToolbar?.dataset.viewMode || "week";
const isEmployeeMonthView = () => viewMode === "employee-month";
let periodMode = "week";
const isStoreMonthView = () => !isEmployeeMonthView() && periodMode === "month";
const isStoreRangeView = () => !isEmployeeMonthView() && periodMode === "range";
const monthPageQuery = new URLSearchParams(location.search);

let weekStart = previousMonday();
const latestCompletedWeekStart = new Date(weekStart);
let rangeStart = new Date(weekStart);
let rangeEnd = addDays(weekStart, 6);
let apologisticRangeDatePicker = null;
let monthStart = new Date(new Date().getFullYear(), new Date().getMonth(), 1);
let reportState = { rows: [], store: null, filter: "all", selectedDate: "", dates: [], employee: null };
let openExplanationId = null;
let openEmployeeAfm = null;
let proposalEditRow = null;
let submitModalState = null;
let acceptReviewPending = new Set();
let exchangePending = new Set();
const canSubmitErgani = apologisticToolbar?.dataset.canSubmit === "1";

document.addEventListener("DOMContentLoaded", async () => {
  Office.setActiveNav(isEmployeeMonthView() ? "employees" : "apologistic");
  if (isEmployeeMonthView()) {
    initEmployeeMonthNavigation();
  } else {
    initStorePeriodNavigation();
    document.getElementById("weekPrev").onclick = () => moveWeek(-7);
    document.getElementById("weekNext").onclick = () => moveWeek(7);
  }
  document.getElementById("apologisticAllDays")?.addEventListener("click", () => selectAllDays());
  initExplanationModal();
  initEmployeeModal();
  initProposalModal();
  initSubmitModal();
  initBulkWeekModal();
  initAcceptAllBar();
  window.addEventListener("scroll", () => {
    hideProposalHistoryOverlay();
    hideEmployeeWeekOverlay();
  }, true);
  window.addEventListener("resize", () => {
    hideProposalHistoryOverlay();
    hideEmployeeWeekOverlay();
  });
  document.addEventListener("click", (event) => {
    const unevenButton = event.target.closest(".apologistic-uneven-accept-btn");
    if (unevenButton) {
      event.stopPropagation();
      acceptUnevenDistribution(
        unevenButton.dataset.employeeAfm || "",
        unevenButton.dataset.groupId || "",
        unevenButton,
      );
      return;
    }
    const exchangeButton = event.target.closest(".apologistic-exchange-card");
    if (exchangeButton) {
      event.stopPropagation();
      applyExchange(
        exchangeButton.dataset.employeeAfm || "",
        exchangeButton.dataset.restWorkDate || "",
        exchangeButton.dataset.replacementWorkDate || "",
        exchangeButton,
      );
      return;
    }
    const acceptReviewButton = event.target.closest(".apologistic-accept-review-btn");
    if (acceptReviewButton) {
      event.stopPropagation();
      acceptReviewRow(acceptReviewButton.dataset.employeeAfm || "", acceptReviewButton.dataset.workDate || "", acceptReviewButton);
      return;
    }
    const exportButton = event.target.closest(".apologistic-export-btn");
    if (exportButton) {
      event.stopPropagation();
      downloadApologisticExcel(exportButton);
      return;
    }
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
    const scheduleSubmitButton = event.target.closest(".apologistic-submit-schedule-btn");
    if (scheduleSubmitButton) {
      event.stopPropagation();
      openSubmitModal("schedule", scheduleSubmitButton.dataset.employeeAfm || "", scheduleSubmitButton.dataset.workDate || "");
      return;
    }
    const overtimeSubmitButton = event.target.closest(".apologistic-submit-overtime-btn");
    if (overtimeSubmitButton) {
      event.stopPropagation();
      openSubmitModal("overtime", overtimeSubmitButton.dataset.employeeAfm || "", overtimeSubmitButton.dataset.workDate || "");
      return;
    }
    const button = event.target.closest(".apologistic-info-btn");
    if (!button) return;
    event.stopPropagation();
    openExplanation(button.dataset.explanationId || "");
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (!document.getElementById("apologisticBulkModal")?.classList.contains("hidden")) closeBulkWeekModal();
    else if (submitModalState) closeSubmitModal();
    else if (proposalEditRow) closeProposalEditor();
    else if (openEmployeeAfm) closeEmployeeDetail();
    else closeExplanation();
  });
  try {
    const active = await Office.fetchActiveStore();
    Office.applyActiveStoreChrome(active);
    if (isEmployeeMonthView() && !employeeMonthAfm()) {
      showError("Λείπει το ΑΦΜ εργαζομένου.");
      return;
    }
    await loadReport();
  } catch (e) { showError(e); }
});

function employeeMonthAfm() {
  return (monthPageQuery.get("afm") || reportState.employee?.afm || "").trim();
}

function employeeMonthName() {
  const employee = reportState.employee || {};
  const fromQuery = `${monthPageQuery.get("eponymo") || ""} ${monthPageQuery.get("onoma") || ""}`.trim();
  return `${employee.eponymo || ""} ${employee.onoma || ""}`.trim() || fromQuery || "Εργαζόμενος";
}

function initEmployeeMonthNavigation() {
  const select = document.getElementById("employeeMonthSelect");
  const now = new Date();
  if (select) {
    for (let offset = 0; offset < 60; offset += 1) {
      const d = new Date(now.getFullYear(), now.getMonth() - offset, 1);
      const option = document.createElement("option");
      option.value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
      option.textContent = `${EMP_MONTH_NAMES[d.getMonth()]} ${d.getFullYear()}`;
      select.appendChild(option);
    }
    select.onchange = (event) => {
      const [year, month] = event.target.value.split("-").map(Number);
      monthStart = new Date(year, month - 1, 1);
      loadReport();
    };
  }
  document.getElementById("monthPrev")?.addEventListener("click", () => changeEmployeeMonth(-1));
  document.getElementById("monthNext")?.addEventListener("click", () => changeEmployeeMonth(1));
}

function initStorePeriodNavigation() {
  const select = document.getElementById("apologisticMonthSelect");
  const now = new Date();
  if (select) {
    for (let offset = 0; offset < 60; offset += 1) {
      const d = new Date(now.getFullYear(), now.getMonth() - offset, 1);
      const option = document.createElement("option");
      option.value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
      option.textContent = `${EMP_MONTH_NAMES[d.getMonth()]} ${d.getFullYear()}`;
      select.appendChild(option);
    }
    select.addEventListener("change", () => {
      const [year, month] = select.value.split("-").map(Number);
      monthStart = new Date(year, month - 1, 1);
      loadReport();
    });
  }
  document.getElementById("apologisticModeMonth")?.addEventListener("click", () => switchStorePeriod("month"));
  document.getElementById("apologisticModeWeek")?.addEventListener("click", () => switchStorePeriod("week"));
  document.getElementById("apologisticModeRange")?.addEventListener("click", () => switchStorePeriod("range"));
  document.getElementById("apologisticMonthPrev")?.addEventListener("click", () => moveStoreMonth(-1));
  document.getElementById("apologisticMonthNext")?.addEventListener("click", () => moveStoreMonth(1));
  document.getElementById("apologisticRangeApply")?.addEventListener("click", applyStoreRange);
  apologisticRangeDatePicker = Office.createDatePicker({
    mountId: "apologisticRangeDatePicker",
    mode: "range",
    layout: "inline",
    autoApply: false,
    maxDate: iso(addDays(latestCompletedWeekStart, 6)),
    quickPresets: ["previousWeek", "previousMonth"],
  });
  apologisticRangeDatePicker?.setRange(iso(rangeStart), iso(rangeEnd));
  syncStorePeriodUi();
}

function switchStorePeriod(mode) {
  if (mode === periodMode) return;
  periodMode = mode;
  if (mode === "month") monthStart = new Date(weekStart.getFullYear(), weekStart.getMonth(), 1);
  resetPeriodResults();
  syncStorePeriodUi();
  loadReport();
}

function resetPeriodResults() {
  reportState = {
    rows: [], store: reportState.store, filter: "all", selectedDate: "", dates: [],
    employee: null, employeeCount: 0,
  };
  renderSummary({ days: [], employees: [] });
  syncDaySelectionUi();
}

function applyStoreRange() {
  const selectedRange = apologisticRangeDatePicker?.getRange() || {};
  const from = selectedRange.start || "";
  const to = selectedRange.end || "";
  if (!from || !to) return Office.showMsg("apologisticSubmitMsg", "Συμπληρώστε ημερομηνία από και έως.", false);
  rangeStart = new Date(`${from}T12:00:00`);
  rangeEnd = new Date(`${to}T12:00:00`);
  if (rangeEnd < rangeStart) return Office.showMsg("apologisticSubmitMsg", "Η ημερομηνία λήξης πρέπει να είναι μετά την έναρξη.", false);
  loadReport();
}

function moveStoreMonth(delta) {
  const candidate = new Date(monthStart.getFullYear(), monthStart.getMonth() + delta, 1);
  const current = new Date(new Date().getFullYear(), new Date().getMonth(), 1);
  if (candidate > current) return;
  monthStart = candidate;
  loadReport();
}

function syncStorePeriodUi() {
  const monthMode = isStoreMonthView();
  const rangeMode = isStoreRangeView();
  document.getElementById("apologisticModeMonth")?.classList.toggle("is-active", monthMode);
  document.getElementById("apologisticModeWeek")?.classList.toggle("is-active", !monthMode && !rangeMode);
  document.getElementById("apologisticModeRange")?.classList.toggle("is-active", rangeMode);
  document.getElementById("apologisticModeMonth")?.setAttribute("aria-selected", monthMode ? "true" : "false");
  document.getElementById("apologisticModeWeek")?.setAttribute("aria-selected", (!monthMode && !rangeMode) ? "true" : "false");
  document.getElementById("apologisticModeRange")?.setAttribute("aria-selected", rangeMode ? "true" : "false");
  document.getElementById("apologisticWeekControls")?.classList.toggle("hidden", monthMode || rangeMode);
  document.getElementById("apologisticDayTabs")?.classList.toggle("hidden", monthMode || rangeMode);
  document.getElementById("apologisticMonthControls")?.classList.toggle("hidden", !monthMode);
  document.getElementById("apologisticMonthWeeks")?.classList.toggle("hidden", !monthMode);
  document.getElementById("apologisticRangeControls")?.classList.toggle("hidden", !rangeMode);
  const select = document.getElementById("apologisticMonthSelect");
  if (select) select.value = `${monthStart.getFullYear()}-${String(monthStart.getMonth() + 1).padStart(2, "0")}`;
  const next = document.getElementById("apologisticMonthNext");
  if (next) next.disabled = monthStart.getFullYear() === new Date().getFullYear() && monthStart.getMonth() === new Date().getMonth();
  if (rangeMode) apologisticRangeDatePicker?.setRange(iso(rangeStart), iso(rangeEnd));
  const allButton = document.getElementById("apologisticAllDays");
  if (allButton) {
    const periodLabel = monthMode ? "του μήνα" : rangeMode ? "του διαστήματος" : "της εβδομάδας";
    allButton.title = `Εμφάνιση όλων των αποτελεσμάτων ${periodLabel}`;
  }
}

function renderStoreMonthWeeks(weeks) {
  const mount = document.getElementById("apologisticMonthWeeks");
  if (!mount) return;
  mount.innerHTML = (weeks || []).map((week, index) => {
    const from = new Date(`${week.visible_from || week.from}T12:00:00`);
    const to = new Date(`${week.visible_to || week.to}T12:00:00`);
    return `<button type="button" class="apologistic-month-week" data-week-from="${attr(week.from)}" ${week.available ? "" : "disabled"}>` +
      `Εβδ. ${index + 1} · ${from.toLocaleDateString("el-GR", { day: "2-digit", month: "2-digit" })}–${to.toLocaleDateString("el-GR", { day: "2-digit", month: "2-digit" })}</button>`;
  }).join("");
  mount.querySelectorAll("[data-week-from]").forEach((button) => button.addEventListener("click", () => {
    weekStart = new Date(`${button.dataset.weekFrom}T12:00:00`);
    periodMode = "week";
    syncStorePeriodUi();
    loadReport();
  }));
}

function changeEmployeeMonth(delta) {
  const candidate = new Date(monthStart.getFullYear(), monthStart.getMonth() + delta, 1);
  const current = new Date(new Date().getFullYear(), new Date().getMonth(), 1);
  if (candidate > current) return;
  monthStart = candidate;
  loadReport();
}

function syncEmployeeMonthNavigation() {
  const select = document.getElementById("employeeMonthSelect");
  const next = document.getElementById("monthNext");
  const key = `${monthStart.getFullYear()}-${String(monthStart.getMonth() + 1).padStart(2, "0")}`;
  if (select) select.value = key;
  if (next) next.disabled = select ? select.selectedIndex === 0 : false;
}

function isRowFinalized(row) {
  return row?.finalized !== false && Boolean(row?.status);
}

function actionableReportRows(rows) {
  return (rows || []).filter(isRowFinalized);
}

function weekFromForRow(row) {
  const raw = String(row?.week_from || "").trim();
  if (raw) return raw.slice(0, 10);
  return iso(weekStart);
}

function pendingRowLabel(row) {
  if (row?.source === "future") return "Μελλοντική";
  if (row?.source === "live_preview") {
    const statusLabels = { ok: "Σύμφωνο", change: "Μεταβολή", review: "Έλεγχος" };
    return `Προσωρινό · ${statusLabels[row.status] || "στοιχεία"}`;
  }
  return "Δεν έχει υπολογιστεί";
}

function weekdayLabelForDate(workDate) {
  const parts = String(workDate || "").split("/").map(Number);
  if (parts.length !== 3) return "—";
  const date = new Date(parts[2], parts[1] - 1, parts[0]);
  return EMP_DAY_NAMES[date.getDay()] || "—";
}

function bulkPeriodLabel() {
  if (isEmployeeMonthView() || isStoreMonthView()) return "Μαζική Καταχώρηση μήνα";
  return isStoreRangeView() ? "Μαζική Καταχώρηση διαστήματος" : "Μαζική Καταχώρηση εβδομάδας";
}

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
  form.querySelectorAll('input[name="apologisticProposalType"]').forEach((input) => {
    input.addEventListener("change", syncProposalTypeUi);
  });
  form.querySelectorAll(".apologistic-proposal-type-option").forEach((option) => {
    option.addEventListener("click", (event) => {
      if (event.target.closest(".field-input, .input-time-24")) return;
      const radio = option.querySelector('input[name="apologisticProposalType"]');
      if (!radio || radio.checked) return;
      radio.checked = true;
      radio.dispatchEvent(new Event("change", { bubbles: true }));
    });
  });
  form.addEventListener("submit", saveProposalEditor);
}

function selectedProposalType() {
  return document.querySelector('input[name="apologisticProposalType"]:checked')?.value || "work";
}

function setProposalType(type) {
  const target = String(type || "work");
  document.querySelectorAll('input[name="apologisticProposalType"]').forEach((input) => {
    input.checked = input.value === target;
  });
  syncProposalTypeUi();
}

function syncProposalTypeUi() {
  const type = selectedProposalType();
  const workWrap = document.getElementById("apologisticProposalTimeWrap");
  const teleWrap = document.getElementById("apologisticProposalTeleTimeWrap");
  const workFrom = document.getElementById("apologisticProposalFrom");
  const workTo = document.getElementById("apologisticProposalTo");
  const workFrom2 = document.getElementById("apologisticProposalFrom2");
  const workTo2 = document.getElementById("apologisticProposalTo2");
  const teleFrom = document.getElementById("apologisticProposalTeleFrom");
  const teleTo = document.getElementById("apologisticProposalTeleTo");
  const workEnabled = type === "work";
  const teleEnabled = type === "telework";
  if (workWrap) workWrap.classList.toggle("is-disabled", !workEnabled);
  if (teleWrap) teleWrap.classList.toggle("is-disabled", !teleEnabled);
  if (workFrom) workFrom.disabled = !workEnabled;
  if (workTo) workTo.disabled = !workEnabled;
  if (workFrom2) workFrom2.disabled = !workEnabled;
  if (workTo2) workTo2.disabled = !workEnabled;
  if (teleFrom) teleFrom.disabled = !teleEnabled;
  if (teleTo) teleTo.disabled = !teleEnabled;
  document.querySelectorAll(".apologistic-proposal-type-option").forEach((label) => {
    const input = label.querySelector('input[name="apologisticProposalType"]');
    const selected = Boolean(input?.checked);
    label.classList.toggle("is-selected", selected);
    label.classList.toggle("is-disabled", !selected);
  });
}

function parseWorkTimeSlots(raw) {
  return String(raw || "").split(" · ").map((part) => part.trim()).filter(Boolean).map((part) => {
    const match = part.match(/(\d{2}:\d{2})\s*[–-]\s*(\d{2}:\d{2})/);
    return match ? { from: match[1], to: match[2] } : null;
  }).filter(Boolean);
}

function detectProposalType(proposed) {
  const raw = String(proposed || "").trim();
  const upper = raw.toLocaleUpperCase("el-GR");
  const emptyWork = { type: "work", from: "", to: "", from2: "", to2: "" };
  if (!raw) return emptyWork;
  if (upper.includes("ΑΝΑΠΑΥΣ") || upper.includes("ΡΕΠΟ")) return { type: "rest", from: "", to: "" };
  if (upper.includes("ΜΗ ΕΡΓΑΣΙΑ")) return { type: "non_work", from: "", to: "" };
  const tele = raw.match(/ΤΗΛΕΡΓΑΣΙΑ\s+(\d{2}:\d{2})\s*[–-]\s*(\d{2}:\d{2})/i);
  if (tele || upper.startsWith("ΤΗΛ")) {
    return { type: "telework", from: tele?.[1] || "", to: tele?.[2] || "" };
  }
  const slots = parseWorkTimeSlots(raw);
  if (!slots.length) return emptyWork;
  return {
    type: "work",
    from: slots[0].from || "",
    to: slots[0].to || "",
    from2: slots[1]?.from || "",
    to2: slots[1]?.to || "",
  };
}

function buildProposedValueFromEditor() {
  const type = selectedProposalType();
  if (type === "rest") return "ΑΝΑΠΑΥΣΗ/ΡΕΠΟ";
  if (type === "non_work") return "ΜΗ ΕΡΓΑΣΙΑ";
  if (type === "telework") {
    const from = Office.normalizeHourMinute(document.getElementById("apologisticProposalTeleFrom")?.value || "");
    const to = Office.normalizeHourMinute(document.getElementById("apologisticProposalTeleTo")?.value || "");
    if (!from || !to) return { error: "Συμπληρώστε έγκυρες ώρες σε μορφή ΩΩ:ΛΛ." };
    return `ΤΗΛΕΡΓΑΣΙΑ ${from}–${to}`;
  }
  const from = Office.normalizeHourMinute(document.getElementById("apologisticProposalFrom")?.value || "");
  const to = Office.normalizeHourMinute(document.getElementById("apologisticProposalTo")?.value || "");
  const from2 = Office.normalizeHourMinute(document.getElementById("apologisticProposalFrom2")?.value || "");
  const to2 = Office.normalizeHourMinute(document.getElementById("apologisticProposalTo2")?.value || "");
  if (!from || !to) return { error: "Συμπληρώστε έγκυρες ώρες σε μορφή ΩΩ:ΛΛ." };
  if ((from2 && !to2) || (!from2 && to2)) {
    return { error: "Συμπληρώστε και τα δύο πεδία του 2ου τμήματος ή αφήστε τα κενά." };
  }
  const primary = `${from}–${to}`;
  return from2 && to2 ? `${primary} · ${from2}–${to2}` : primary;
}

function initSubmitModal() {
  const modal = document.getElementById("apologisticSubmitModal");
  if (!modal || modal.dataset.bound) return;
  modal.dataset.bound = "1";
  modal.querySelectorAll("[data-apologistic-submit-close]").forEach((el) => {
    el.addEventListener("click", closeSubmitModal);
  });
  document.getElementById("apologisticSubmitConfirm")?.addEventListener("click", confirmSubmitModal);
}

function findReportRow(employeeAfm, workDate) {
  return reportState.rows.find((item) => item.employee_afm === employeeAfm && item.work_date === workDate) || null;
}

function rowHasOvertime(row) {
  return Boolean((row.overtime_segments || []).length || (row.overtime_minutes || 0) > 0);
}

function overtimeSegmentDates(row) {
  const segments = row.overtime_segments || [];
  if (!segments.length) return row.work_date ? [row.work_date] : [];
  return [...new Set(segments.map((segment) => String(segment.date || row.work_date || "").trim()).filter(Boolean))].sort();
}

function overtimeSegmentsForDate(row, segmentDate) {
  const segments = row.overtime_segments || [];
  if (!segments.length) {
    if (row.overtime_from && row.overtime_to) {
      return [{ date: row.work_date, from: row.overtime_from, to: row.overtime_to }];
    }
    return [];
  }
  return segments.filter((segment) => String(segment.date || row.work_date || "").trim() === segmentDate);
}

function formatOvertimeSegmentLines(row) {
  return overtimeSegmentDates(row).map((date) => {
    const segments = overtimeSegmentsForDate(row, date);
    const label = segments.map((segment) => `${segment.from}–${segment.to}`).join(", ");
    return `${date} · ${label || "—"}`;
  });
}

function pendingOvertimeSegmentDates(row) {
  return overtimeSegmentDates(row).filter((date) => !overtimeSegmentAlreadySubmitted(row, date));
}

function allOvertimeSegmentsSubmitted(row) {
  const dates = overtimeSegmentDates(row);
  return dates.length > 0 && dates.every((date) => overtimeSegmentAlreadySubmitted(row, date));
}

function overtimeDatesToSubmit(row) {
  const pending = pendingOvertimeSegmentDates(row);
  if (pending.length) return pending;
  if (allOvertimeSegmentsSubmitted(row)) return overtimeSegmentDates(row);
  return overtimeSegmentDates(row);
}

function rowHasAnyErganiSubmit(row) {
  if (String(row.ergani_submit?.schedule?.protocol || "").trim()) return true;
  return Object.values(row.ergani_submit?.overtime || {}).some(
    (entry) => String(entry?.protocol || "").trim(),
  );
}

function countErganiSubmits(rows) {
  let total = 0;
  for (const row of rows || []) {
    if (String(row.ergani_submit?.schedule?.protocol || "").trim()) total += 1;
    for (const entry of Object.values(row.ergani_submit?.overtime || {})) {
      if (String(entry?.protocol || "").trim()) total += 1;
    }
  }
  return total;
}

function computeReportCounts(rows) {
  const list = actionableReportRows(rows);
  return {
    all: list.length,
    ok: list.filter((row) => row.status === "ok").length,
    change: list.filter((row) => row.status === "change").length,
    review: list.filter((row) => row.status === "review").length,
    submitted: countErganiSubmits(list),
  };
}

function weekHasReviewRows(rows) {
  return actionableReportRows(rows).some((row) => row.status === "review");
}

function refreshSummaryCounts() {
  renderSummary({
    employees: Array(reportState.employeeCount || 0).fill(null),
    days: reportState.rows,
    counts: computeReportCounts(reportState.rows),
  });
}

function isAllDaysSelected() {
  return isEmployeeMonthView() || isStoreMonthView() || isStoreRangeView() || !reportState.selectedDate;
}

function selectAllDays() {
  reportState.selectedDate = "";
  reportState.filter = "all";
  syncDaySelectionUi();
  renderVisibleRows();
  syncFilterButtons();
  updateBulkWeekBar();
  updateAcceptAllBar();
}

function syncDaySelectionUi() {
  const allBtn = document.getElementById("apologisticAllDays");
  if (allBtn) {
    const active = isAllDaysSelected();
    allBtn.classList.toggle("is-active", active);
    allBtn.setAttribute("aria-pressed", active ? "true" : "false");
  }
  document.querySelectorAll(".apologistic-day-tab").forEach((button) => {
    const active = button.dataset.workDate === reportState.selectedDate;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
}

function visibleReportRows() {
  let rows = isAllDaysSelected()
    ? reportState.rows.slice()
    : reportState.rows.filter((row) => row.work_date === reportState.selectedDate);
  if (reportState.filter === "submitted") {
    rows = rows.filter(rowHasAnyErganiSubmit);
  } else if (reportState.filter !== "all") {
    rows = rows.filter((row) => isRowFinalized(row) && row.status === reportState.filter);
  } else if (!isEmployeeMonthView()) {
    rows = rows.filter(isRowFinalized);
  }
  if (isAllDaysSelected()) {
    rows.sort((left, right) => {
      const dateCmp = String(left.work_date || "").localeCompare(String(right.work_date || ""), "el");
      if (dateCmp) return dateCmp;
      if (isEmployeeMonthView()) return 0;
      return String(left.eponymo || "").localeCompare(String(right.eponymo || ""), "el");
    });
  }
  return rows;
}

function reportPeriodLabel() {
  if (isEmployeeMonthView()) {
    if (!isAllDaysSelected()) return reportState.selectedDate;
    return `${EMP_MONTH_NAMES[monthStart.getMonth()]} ${monthStart.getFullYear()} · όλος ο μήνας`;
  }
  if (isStoreMonthView()) return `${EMP_MONTH_NAMES[monthStart.getMonth()]} ${monthStart.getFullYear()} · όλος ο μήνας`;
  if (isStoreRangeView()) return `${rangeStart.toLocaleDateString("el-GR")}–${rangeEnd.toLocaleDateString("el-GR")}`;
  if (!isAllDaysSelected()) return reportState.selectedDate;
  const dates = reportState.dates || [];
  if (!dates.length) return "όλη η εβδομάδα";
  const start = dates[0].slice(0, 5);
  const end = dates[dates.length - 1].slice(0, 5);
  return `${start}–${end} · όλη η εβδομάδα`;
}

function scheduleLabelsMatch(row) {
  const declared = String(row.declared || "").trim();
  const proposed = String(row.proposed || "").trim();
  return Boolean(declared && proposed && declared === proposed);
}

function canSubmitScheduleRow(row) {
  if (!isRowFinalized(row) || row.status !== "change") return false;
  if (scheduleLabelsMatch(row) && rowHasOvertime(row)) return false;
  return true;
}

function scheduleAlreadySubmitted(row) {
  return Boolean(String(row.ergani_submit?.schedule?.protocol || "").trim());
}

function overtimeSegmentAlreadySubmitted(row, segmentDate) {
  const seg = String(segmentDate || "").trim();
  return Boolean(String(row.ergani_submit?.overtime?.[seg]?.protocol || "").trim());
}

function collectBulkWeekPendingItems(rows) {
  const items = [];
  for (const row of actionableReportRows(rows)) {
    if (row.status === "review") continue;
    const name = `${row.eponymo || ""} ${row.onoma || ""}`.trim() || row.employee_afm || "—";
    if (canSubmitScheduleRow(row) && !scheduleAlreadySubmitted(row)) {
      items.push({
        kind: "schedule",
        document: "WTODailyA",
        employee_afm: row.employee_afm,
        employee_name: name,
        work_date: row.work_date,
        declared: row.declared,
        detail: compactScheduleLabel(row.proposed),
        detail_label: "Πρόταση ωραρίου",
        segment_date: null,
      });
    }
    if (!rowHasOvertime(row)) continue;
    for (const segmentDate of overtimeSegmentDates(row)) {
      if (overtimeSegmentAlreadySubmitted(row, segmentDate)) continue;
      const segments = overtimeSegmentsForDate(row, segmentDate);
      const label = segments.map((segment) => `${segment.from}–${segment.to}`).join(" · ") || "—";
      items.push({
        kind: "overtime",
        document: "WTOOvA",
        employee_afm: row.employee_afm,
        employee_name: name,
        work_date: row.work_date,
        declared: row.declared,
        detail: label,
        detail_label: `Υπερωρία${segmentDate && segmentDate !== row.work_date ? ` · υποβολή ${segmentDate}` : ""}`,
        segment_date: segmentDate,
      });
    }
  }
  items.sort((left, right) => {
    const dateCmp = String(left.work_date || "").localeCompare(String(right.work_date || ""), "el");
    if (dateCmp) return dateCmp;
    const nameCmp = String(left.employee_name || "").localeCompare(String(right.employee_name || ""), "el");
    if (nameCmp) return nameCmp;
    return String(left.document).localeCompare(String(right.document));
  });
  return items;
}

function bulkWeekEligible(rows) {
  const actionable = actionableReportRows(rows);
  const counts = computeReportCounts(rows);
  if (!canSubmitErgani || weekHasReviewRows(rows) || (counts.change || 0) <= 0) {
    return { eligible: false, items: [], counts };
  }
  const items = collectBulkWeekPendingItems(actionable);
  return { eligible: items.length > 0, items, counts };
}

function updateAcceptAllBar() {
  const bar = document.getElementById("apologisticAcceptAllBar");
  const btn = document.getElementById("apologisticAcceptAllBtn");
  const hint = document.getElementById("apologisticAcceptAllHint");
  if (!bar || !btn) return;
  const reviewRows = visibleReportRows().filter((row) => row.status === "review");
  const visible = reportState.filter === "review" && reviewRows.length > 0;
  if (!visible) {
    bar.classList.add("hidden");
    btn.hidden = true;
    if (hint) hint.textContent = "";
    return;
  }
  bar.classList.remove("hidden");
  btn.hidden = false;
  if (hint) {
    const exchangeCount = reviewRows.filter((row) => (row.exchange_options || []).length).length;
    hint.textContent =
      `${reviewRows.length} εγγραφές · έγκριση πρότασης και μετάβαση σε Μ* (Μεταβολή)` +
      (exchangeCount ? ` · ${exchangeCount} με αυτόματη επιλογή ανταλλαγής` : "") +
      (isAllDaysSelected() ? "" : ` · ${reportPeriodLabel()}`);
  }
}

function initAcceptAllBar() {
  const btn = document.getElementById("apologisticAcceptAllBtn");
  if (!btn || btn.dataset.bound) return;
  btn.dataset.bound = "1";
  btn.addEventListener("click", acceptAllReview);
}

async function acceptAllReview() {
  const btn = document.getElementById("apologisticAcceptAllBtn");
  const reviewRows = visibleReportRows().filter((row) => row.status === "review");
  if (!reviewRows.length) {
    updateAcceptAllBar();
    return;
  }
  const exchangeRows = reviewRows.filter((row) => (row.exchange_options || []).length);
  const ordinaryRows = reviewRows.filter((row) => !(row.exchange_options || []).length);
  const groups = new Map();
  for (const row of ordinaryRows) {
    const weekFrom = weekFromForRow(row);
    if (!groups.has(weekFrom)) groups.set(weekFrom, []);
    groups.get(weekFrom).push({
      employee_afm: row.employee_afm,
      work_date: row.work_date,
    });
  }
  if (btn) Office.setButtonLoading(btn, true);
  try {
    let changedTotal = 0;
    let unresolvedExchangeTotal = 0;
    const changedKeys = new Set();
    const usedReplacementDays = new Set();
    const randomizedExchangeRows = exchangeRows
      .map((row) => ({ row, order: Math.random() }))
      .sort((left, right) =>
        (left.row.exchange_options || []).length - (right.row.exchange_options || []).length
        || left.order - right.order
      )
      .map((item) => item.row);
    for (const row of randomizedExchangeRows) {
      const available = (row.exchange_options || []).filter((option) =>
        !usedReplacementDays.has(`${row.employee_afm}|${option.replacement_work_date}`)
      );
      const candidates = available
        .map((option) => ({ option, order: Math.random() }))
        .sort((left, right) => left.order - right.order)
        .map((item) => item.option);
      let applied = false;
      for (const option of candidates) {
        const result = await submitExchangeChoice(row, option.replacement_work_date);
        if (!result.ok) continue;
        usedReplacementDays.add(`${row.employee_afm}|${option.replacement_work_date}`);
        changedTotal += Number((result.data.rows || []).length || 2);
        mergeExchangeRows(result.data.rows || []);
        applied = true;
        break;
      }
      if (!applied) unresolvedExchangeTotal += 1;
    }
    for (const [weekFrom, items] of groups.entries()) {
      const res = await fetch("/api/apologistic/accept-all-review", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ week_from: weekFrom, items }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
      changedTotal += Number(data.changed || items.length);
      for (const item of items) changedKeys.add(`${item.employee_afm}|${item.work_date}`);
    }
    for (const row of reportState.rows) {
      if (!changedKeys.has(`${row.employee_afm}|${row.work_date}`)) continue;
      row.status = "change";
      row.change_from_review = true;
      row.reason = "Εγκρίθηκε η πρόταση — μετατράπηκε από Έλεγχο σε Μεταβολή";
    }
    refreshSummaryCounts();
    renderVisibleRows();
    Office.showMsg(
      "apologisticSubmitMsg",
      `Εγκρίθηκαν ${changedTotal} εγγραφές προς μεταβολή (Μ*).` +
        (unresolvedExchangeTotal
          ? ` ${unresolvedExchangeTotal} ανταλλαγές δεν βρήκαν διαθέσιμο ζεύγος και παρέμειναν σε Έλεγχο.`
          : ""),
      changedTotal > 0,
    );
  } catch (error) {
    Office.showMsg("apologisticSubmitMsg", error.message || String(error), false);
  } finally {
    if (btn) Office.setButtonLoading(btn, false);
  }
}

function updateBulkWeekBar() {
  const bar = document.getElementById("apologisticBulkBar");
  const btn = document.getElementById("apologisticBulkWeekBtn");
  const hint = document.getElementById("apologisticBulkHint");
  if (!bar || !btn) return;
  const { eligible, items, counts } = bulkWeekEligible(reportState.rows);
  if (!eligible) {
    bar.classList.add("hidden");
    btn.hidden = true;
    if (hint) hint.textContent = "";
    return;
  }
  const scheduleCount = items.filter((item) => item.kind === "schedule").length;
  const overtimeCount = items.filter((item) => item.kind === "overtime").length;
  bar.classList.remove("hidden");
  btn.hidden = false;
  const bulkLabel = document.getElementById("apologisticBulkBtnLabel");
  if (bulkLabel) bulkLabel.textContent = bulkPeriodLabel();
  if (hint) {
    hint.textContent =
      `Έλεγχος: 0 · Μεταβολές: ${counts.change} · Εκκρεμείς υποβολές: ${items.length}` +
      ` (WTODailyA ${scheduleCount}, WTOOvA ${overtimeCount}) · προεπισκόπηση χωρίς αποστολή`;
  }
}

function closeBulkWeekModal() {
  document.getElementById("apologisticBulkModal")?.classList.add("hidden");
}

function openBulkWeekPreview() {
  const modal = document.getElementById("apologisticBulkModal");
  const meta = document.getElementById("apologisticBulkModalMeta");
  const body = document.getElementById("apologisticBulkModalBody");
  if (!modal || !body) return;
  const { eligible, items } = bulkWeekEligible(reportState.rows);
  if (!eligible) {
    Office.showMsg("apologisticSubmitMsg", "Δεν υπάρχουν εκκρεμείς μεταβολές/υπερωρίες για μαζική καταχώρηση.", false);
    updateBulkWeekBar();
    return;
  }
  closeSubmitModal();
  closeExplanation();
  const scheduleCount = items.filter((item) => item.kind === "schedule").length;
  const overtimeCount = items.filter((item) => item.kind === "overtime").length;
  const weekLabel = reportPeriodLabel();
  if (meta) {
    meta.textContent =
      `${reportState.store?.name || "Κατάστημα"} · ${weekLabel} · ` +
      `${items.length} υποβολές (${scheduleCount} WTODailyA, ${overtimeCount} WTOOvA)`;
  }
  body.innerHTML =
    `<p class="apologistic-bulk-summary">Θα στέλνονταν στο Ergani οι παρακάτω καταχωρήσεις. Όσες έχουν ήδη σταλεί μεμονωμένα εξαιρούνται.</p>` +
    `<table class="apologistic-bulk-table"><thead><tr>` +
    `<th>Έγγραφο</th><th>Εργαζόμενος</th><th>Ημέρα</th><th>Λεπτομέρειες</th>` +
    `</tr></thead><tbody>` +
    items.map((item) => {
      const docClass = item.kind === "schedule" ? "apologistic-bulk-doc--schedule" : "apologistic-bulk-doc--overtime";
      const icon = item.kind === "schedule" ? "bi-calendar-check" : "bi-clock-history";
      return `<tr>` +
        `<td><span class="apologistic-bulk-doc ${docClass}"><i class="bi ${icon}" aria-hidden="true"></i>${attr(item.document)}</span></td>` +
        `<td title="${attr(`ΑΦΜ ${item.employee_afm || ""}`)}">${attr(item.employee_name)}<br><small style="color:var(--muted)">${attr(item.employee_afm || "")}</small></td>` +
        `<td>${attr(item.work_date || "—")}</td>` +
        `<td><strong>${attr(item.detail_label)}:</strong> ${attr(item.detail)}` +
        (item.declared ? `<br><small style="color:var(--muted)">Δηλωμένο: ${attr(compactScheduleLabel(item.declared))}</small>` : "") +
        `</td></tr>`;
    }).join("") +
    `</tbody></table>`;
  modal.classList.remove("hidden");
}

function initBulkWeekModal() {
  const modal = document.getElementById("apologisticBulkModal");
  if (!modal || modal.dataset.bound) return;
  modal.dataset.bound = "1";
  modal.querySelectorAll("[data-apologistic-bulk-close]").forEach((el) => {
    el.addEventListener("click", closeBulkWeekModal);
  });
  document.getElementById("apologisticBulkWeekBtn")?.addEventListener("click", openBulkWeekPreview);
}

function mergeErganiSubmit(row, fragment) {
  if (!fragment || typeof fragment !== "object") return;
  if (!row.ergani_submit) row.ergani_submit = {};
  if (fragment.schedule) row.ergani_submit.schedule = fragment.schedule;
  if (fragment.overtime) {
    if (!row.ergani_submit.overtime) row.ergani_submit.overtime = {};
    Object.assign(row.ergani_submit.overtime, fragment.overtime);
  }
}

function refreshScheduleSubmitMatch(row) {
  const schedule = row.ergani_submit?.schedule;
  if (!schedule?.proposed_at_submit) return;
  schedule.matches_proposal = String(schedule.proposed_at_submit).trim() === String(row.proposed || "").trim();
}

function overtimeSubmitForRow(row) {
  if (!allOvertimeSegmentsSubmitted(row)) return null;
  const overtime = row.ergani_submit?.overtime || {};
  const dates = overtimeSegmentDates(row);
  const protocols = dates.map((date) => String(overtime[date]?.protocol || "").trim()).filter(Boolean);
  if (!protocols.length) return null;
  return {
    protocol: protocols.join(", "),
    segment_date: dates.join(", "),
    submitted_at: dates.map((date) => overtime[date]?.submitted_at).filter(Boolean).sort().pop() || null,
    submit_date: dates.map((date) => overtime[date]?.submit_date).filter(Boolean).sort().pop() || null,
  };
}

function existingSubmitForKind(row, kind) {
  if (kind === "schedule") {
    const schedule = row.ergani_submit?.schedule;
    return schedule?.protocol ? schedule : null;
  }
  const dates = overtimeSegmentDates(row);
  const entries = dates
    .map((date) => ({ date, entry: row.ergani_submit?.overtime?.[date] }))
    .filter(({ entry }) => String(entry?.protocol || "").trim());
  if (!entries.length) return null;
  return { entries, allSubmitted: entries.length === dates.length };
}

function formatSubmittedAt(value) {
  if (!value) return "—";
  const normalized = String(value).includes("T") ? String(value) : String(value).replace(" ", "T");
  const d = new Date(normalized);
  if (Number.isNaN(d.getTime())) return String(value).slice(0, 19).replace("T", " ");
  return d.toLocaleString("el-GR", { dateStyle: "short", timeStyle: "short" });
}

function renderSubmitPreviousBanner(row, kind) {
  const box = document.getElementById("apologisticSubmitPrevious");
  const confirmBtn = document.getElementById("apologisticSubmitConfirm");
  if (!box || !confirmBtn) return;
  const existing = existingSubmitForKind(row, kind);
  if (!existing) {
    box.classList.add("hidden");
    box.innerHTML = "";
    confirmBtn.innerHTML = '<i class="bi bi-send" aria-hidden="true"></i> Υποβολή';
    return;
  }
  const doc = kind === "schedule" ? "WTODailyA" : "WTOOvA";
  const lines = [];
  if (kind === "schedule") {
    lines.push(
      `Έχετε ήδη καταχωρήσει ${doc} για αυτή την ημέρα.`,
      `Πρωτόκολλο: ${existing.protocol}`,
      `Ημερομηνία/ώρα υποβολής: ${formatSubmittedAt(existing.submitted_at || existing.submit_date)}`,
    );
    if (existing.proposed_at_submit) {
      lines.push(`Ωράριο που στάλθηκε: ${existing.proposed_at_submit}`);
      if (existing.matches_proposal === false) {
        lines.push("Η τρέχουσα πρόταση διαφέρει — η επαναποστολή θα στείλει το νέο ωράριο.");
      }
    }
    lines.push("Θέλετε να το υποβάλετε ξανά;");
  } else {
    for (const { date, entry } of existing.entries) {
      lines.push(
        `${date}: πρωτ. ${entry.protocol} · ${formatSubmittedAt(entry.submitted_at || entry.submit_date)}`,
      );
    }
    const pending = pendingOvertimeSegmentDates(row);
    if (pending.length) {
      lines.push(`Θα υποβληθούν επίσης: ${pending.join(", ")}`);
      confirmBtn.innerHTML = '<i class="bi bi-send" aria-hidden="true"></i> Υποβολή';
    } else {
      lines.push("Θέλετε να τα υποβάλετε ξανά;");
      confirmBtn.innerHTML = '<i class="bi bi-arrow-repeat" aria-hidden="true"></i> Υποβολή ξανά';
    }
    box.innerHTML =
      `<strong><i class="bi bi-check2-circle" aria-hidden="true"></i> Υπάρχει καταχωρημένη υποβολή</strong>` +
      `<p>${lines.map((line) => attr(line)).join("<br>")}</p>`;
    box.classList.remove("hidden");
    return;
  }
  box.innerHTML =
    `<strong><i class="bi bi-check2-circle" aria-hidden="true"></i> Υπάρχει καταχωρημένη υποβολή</strong>` +
    `<p>${lines.map((line) => attr(line)).join("<br>")}</p>`;
  box.classList.remove("hidden");
  confirmBtn.innerHTML = '<i class="bi bi-arrow-repeat" aria-hidden="true"></i> Υποβολή ξανά';
}

function showSubmitToast(text, ok) {
  Office.showMsg("apologisticSubmitMsg", text, ok);
}

function closeSubmitModal() {
  submitModalState = null;
  document.getElementById("apologisticSubmitModal")?.classList.add("hidden");
  const error = document.getElementById("apologisticSubmitError");
  if (error) error.textContent = "";
  const previous = document.getElementById("apologisticSubmitPrevious");
  if (previous) {
    previous.classList.add("hidden");
    previous.innerHTML = "";
  }
  const confirmBtn = document.getElementById("apologisticSubmitConfirm");
  if (confirmBtn) confirmBtn.innerHTML = '<i class="bi bi-send" aria-hidden="true"></i> Υποβολή';
}

function openSubmitModal(kind, employeeAfm, workDate) {
  if (!canSubmitErgani) return;
  const row = findReportRow(employeeAfm, workDate);
  const modal = document.getElementById("apologisticSubmitModal");
  const title = document.getElementById("apologisticSubmitModalTitle");
  const meta = document.getElementById("apologisticSubmitModalMeta");
  const detail = document.getElementById("apologisticSubmitModalDetail");
  const segmentWrap = document.getElementById("apologisticSubmitSegmentWrap");
  const segmentSelect = document.getElementById("apologisticSubmitSegmentDate");
  const errorBox = document.getElementById("apologisticSubmitError");
  if (!row || !modal || !title || !meta || !detail || !segmentWrap || !segmentSelect) return;

  closeExplanation();
  const pairedRow = kind === "schedule" && row.exchange_pair?.paired_work_date
    ? findReportRow(row.employee_afm, row.exchange_pair.paired_work_date)
    : null;
  const pairRows = pairedRow ? [row, pairedRow] : [row];
  submitModalState = { kind, row, pairRows };
  errorBox.textContent = "";
  const employeeName = `${row.eponymo || ""} ${row.onoma || ""}`.trim();
  meta.textContent = `${employeeName} · ${row.work_date}`;

  if (kind === "schedule") {
    title.textContent = "Υποβολή απολογιστικής μεταβολής";
    detail.innerHTML = pairRows.length === 2
      ? `Έγγραφο: <strong>2 × WTODailyA</strong><br>` + pairRows.map((item) =>
          `<strong>${attr(item.work_date)}</strong>: ${attr(compactScheduleLabel(item.proposed))}`
        ).join("<br>")
      : `Έγγραφο: <strong>WTODailyA</strong><br>Πρόταση: <strong>${attr(compactScheduleLabel(row.proposed))}</strong>`;
    segmentWrap.classList.add("hidden");
    segmentSelect.innerHTML = "";
  } else {
    title.textContent = "Υποβολή απολογιστικής υπερωρίας";
    segmentWrap.classList.add("hidden");
    segmentSelect.innerHTML = "";
    const lines = formatOvertimeSegmentLines(row);
    detail.innerHTML =
      `Έγγραφο: <strong>WTOOvA</strong><br>` +
      `Διαστήματα:<br><strong>${lines.map((line) => attr(line)).join("<br>")}</strong>`;
  }
  renderSubmitPreviousBanner(row, kind);
  modal.classList.remove("hidden");
}

async function confirmSubmitModal() {
  const state = submitModalState;
  const btn = document.getElementById("apologisticSubmitConfirm");
  const errorBox = document.getElementById("apologisticSubmitError");
  if (!state || !btn) return;

  const { kind, row } = state;
  const baseBody = {
    week_from: weekFromForRow(row),
    work_date: row.work_date,
    employee_afm: row.employee_afm,
    use_snapshot: true,
  };
  const url = kind === "schedule" ? "/api/apologistic/submit-schedule" : "/api/apologistic/submit-overtime";
  Office.setButtonLoading(btn, true);
  errorBox.textContent = "";
  try {
    if (kind === "schedule") {
      const scheduleRows = state.pairRows || [row];
      const pendingRows = scheduleRows.filter((item) =>
        !scheduleAlreadySubmitted(item) || item.ergani_submit?.schedule?.matches_proposal === false
      );
      const protocols = [];
      for (const scheduleRow of pendingRows) {
        const submitBody = {
          week_from: weekFromForRow(scheduleRow),
          work_date: scheduleRow.work_date,
          employee_afm: scheduleRow.employee_afm,
          use_snapshot: true,
        };
        const res = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(submitBody),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok || !data.success) {
          throw new Error(
            `${scheduleRow.work_date}: ` +
            (data.error || data.data?.message || data.data?.Message || `Αποτυχία υποβολής (HTTP ${res.status})`),
          );
        }
        mergeErganiSubmit(scheduleRow, data.ergani_submit);
        if (!data.ergani_submit?.schedule) {
          mergeErganiSubmit(scheduleRow, {
            schedule: {
              protocol: data.protocol || null,
              ergani_submission_id: data.ergani_submission_id || null,
              submit_date: data.submit_date || null,
              submitted_at: new Date().toISOString(),
              proposed_at_submit: scheduleRow.proposed,
              matches_proposal: true,
            },
          });
        }
        if (data.protocol) protocols.push(String(data.protocol));
      }
      closeSubmitModal();
      refreshSummaryCounts();
      renderVisibleRows();
      const proto = protocols.length ? ` · πρωτ. ${protocols.join(", ")}` : "";
      const label = scheduleRows.length === 2 ? "Οι δύο μεταβολές της ανταλλαγής υποβλήθηκαν" : "Η απολογιστική μεταβολή ωραρίου υποβλήθηκε";
      showSubmitToast(`${label}${proto}.`, true);
      return;
    }

    const segmentDates = overtimeDatesToSubmit(row);
    if (!segmentDates.length) {
      errorBox.textContent = "Δεν προκύπτει υπερωρία για υποβολή.";
      return;
    }
    const protocols = [];
    for (const segmentDate of segmentDates) {
      let submitBody = { ...baseBody, segment_date: segmentDate };
      let res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(submitBody),
      });
      let data = await res.json().catch(() => ({}));
      if (res.status === 409 && data.requires_confirmation) {
        const proceed = window.confirm(`${data.error}\n\nΘέλετε να συνεχίσετε την υποβολή;`);
        if (!proceed) return;
        submitBody = { ...submitBody, confirm_annual_limit: true };
        res = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(submitBody),
        });
        data = await res.json().catch(() => ({}));
      }
      if (!res.ok || !data.success) {
        const prefix = segmentDates.length > 1
          ? `Αποτυχία για ${segmentDate}${protocols.length ? ` (${protocols.length}/${segmentDates.length} υποβλήθηκαν)` : ""}: `
          : "";
        errorBox.innerHTML = Office.formatMultilineHtml(
          prefix + (data.error || data.data?.message || data.data?.Message || `Αποτυχία υποβολής (HTTP ${res.status})`),
        );
        if (protocols.length) {
          refreshSummaryCounts();
          renderVisibleRows();
        }
        return;
      }
      mergeErganiSubmit(row, data.ergani_submit);
      if (!data.ergani_submit?.overtime) {
        mergeErganiSubmit(row, {
          overtime: {
            [segmentDate]: {
              protocol: data.protocol || null,
              ergani_submission_id: data.ergani_submission_id || null,
              submit_date: data.submit_date || null,
              submitted_at: new Date().toISOString(),
              segment_date: segmentDate,
            },
          },
        });
      }
      if (data.protocol) protocols.push(String(data.protocol));
    }
    closeSubmitModal();
    refreshSummaryCounts();
    renderVisibleRows();
    const proto = protocols.length ? ` · πρωτ. ${protocols.join(", ")}` : "";
    const countLabel = segmentDates.length > 1 ? ` (${segmentDates.length} ημέρες)` : "";
    showSubmitToast(`Η απολογιστική υπερωρία υποβλήθηκε${countLabel}${proto}.`, true);
  } catch (error) {
    errorBox.innerHTML = Office.formatMultilineHtml(error.message || error);
  } finally {
    Office.setButtonLoading(btn, false);
  }
}

function renderErganiActions(row) {
  if (!canSubmitErgani || !isRowFinalized(row) || row.status === "review") return "—";
  const actions = [];
  const schedule = row.ergani_submit?.schedule;
  if (canSubmitScheduleRow(row)) {
    const done = schedule?.protocol;
    const stale = Boolean(done && schedule.matches_proposal === false);
    const stateClass = done ? (stale ? " is-stale" : " is-done") : "";
    actions.push(
      `<button type="button" class="apologistic-ergani-btn apologistic-submit-schedule-btn${stateClass}" ` +
      `data-employee-afm="${attr(row.employee_afm)}" data-work-date="${attr(row.work_date)}" ` +
      `title="${attr(done ? (stale ? `Υποβλήθηκε WTODailyA · ${schedule.protocol} · η πρόταση άλλαξε — κλικ για επαναποστολή` : `Υποβλήθηκε WTODailyA · ${schedule.protocol} · ${formatSubmittedAt(schedule.submitted_at || schedule.submit_date)}`) : "Υποβολή απολογιστικής μεταβολής (WTODailyA)")}">` +
      `<i class="bi ${done && !stale ? "bi-check2-circle" : stale ? "bi-arrow-repeat" : "bi-calendar-check"}" aria-hidden="true"></i></button>`,
    );
  }
  if (rowHasOvertime(row)) {
    const submitted = overtimeSubmitForRow(row);
    const pendingCount = pendingOvertimeSegmentDates(row).length;
    const done = Boolean(submitted);
    const partial = !done && pendingCount < overtimeSegmentDates(row).length;
    actions.push(
      `<button type="button" class="apologistic-ergani-btn apologistic-submit-overtime-btn${done ? " is-done" : partial ? " is-partial" : ""}" ` +
      `data-employee-afm="${attr(row.employee_afm)}" data-work-date="${attr(row.work_date)}" ` +
      `title="${attr(done ? `Υποβλήθηκε WTOOvA · ${submitted.protocol}${submitted.segment_date ? ` · ${submitted.segment_date}` : ""} · ${formatSubmittedAt(submitted.submitted_at || submitted.submit_date)}` : partial ? `Μερική υποβολή WTOOvA · απομένουν ${pendingCount} ημέρες` : "Υποβολή απολογιστικής υπερωρίας (WTOOvA)")}">` +
      `<i class="bi ${done ? "bi-check2-circle" : partial ? "bi-clock-history" : "bi-clock-history"}" aria-hidden="true"></i></button>`,
    );
  }
  if (!actions.length) return "—";
  return `<div class="apologistic-ergani-actions">${actions.join("")}</div>`;
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
function changeFromReview(row) {
  return Boolean(row?.change_from_review);
}

function statusLabel(status, row) {
  if (status === "ok") return "Σύμφωνο";
  if (status === "change") return changeFromReview(row) ? "Μεταβολή (από Έλεγχο)" : "Μεταβολή";
  return "Έλεγχος";
}

function statusShortLabel(status, row) {
  if (status === "ok") return "Σ";
  if (status === "change") return changeFromReview(row) ? "Μ*" : "Μ";
  return "Ε";
}

function renderResultBadge(row) {
  const title = statusLabel(row.status, row);
  if (row.status === "review") {
    const unevenGroup = row.uneven_distribution_group;
    if (unevenGroup?.group_id) {
      return `<button type="button" class="status-badge apologistic-status--review apologistic-uneven-accept-btn" ` +
        `data-employee-afm="${attr(row.employee_afm)}" data-group-id="${attr(unevenGroup.group_id)}" ` +
        `title="Έγκριση ολόκληρης της ομάδας ανισομερούς κατανομής">${statusShortLabel(row.status, row)}</button>`;
    }
    if ((row.exchange_options || []).length) {
      return `<span class="status-badge apologistic-status--review" title="Επιλέξτε πρώτα μία από τις διαθέσιμες ανταλλαγές">${statusShortLabel(row.status, row)}</span>`;
    }
    const key = `${row.employee_afm}|${row.work_date}`;
    const pending = acceptReviewPending.has(key);
    return `<button type="button" class="status-badge apologistic-status--review apologistic-accept-review-btn${pending ? " is-pending" : ""}" ` +
      `data-employee-afm="${attr(row.employee_afm)}" data-work-date="${attr(row.work_date)}" ` +
      `title="${attr(pending ? "Αποθήκευση…" : "Κλικ: OK με την πρόταση")}"${pending ? " disabled" : ""}>${statusShortLabel(row.status, row)}</button>`;
  }
  return `<span class="status-badge apologistic-status--${row.status}">${statusShortLabel(row.status, row)}</span>`;
}

async function acceptUnevenDistribution(employeeAfm, groupId, button) {
  const rows = reportState.rows.filter((row) =>
    row.employee_afm === employeeAfm && row.uneven_distribution_group?.group_id === groupId
  );
  if (!rows.length || rows.some((row) => row.status !== "review")) return;
  if (button) button.disabled = true;
  try {
    const res = await fetch("/api/apologistic/uneven-distribution/accept", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ week_from: weekFromForRow(rows[0]), employee_afm: employeeAfm, group_id: groupId }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    for (const updated of data.days || []) {
      const row = reportState.rows.find((item) =>
        item.employee_afm === updated.employee_afm && item.work_date === updated.work_date
      );
      if (row) Object.assign(row, updated);
    }
    refreshSummaryCounts();
    renderVisibleRows();
    Office.showMsg("apologisticSubmitMsg", `Εγκρίθηκαν ${data.changed || 0} ημέρες της ανισομερούς κατανομής.`, true);
  } catch (error) {
    Office.showMsg("apologisticSubmitMsg", error.message || String(error), false);
  } finally {
    if (button) button.disabled = false;
  }
}

async function acceptReviewRow(employeeAfm, workDate, button) {
  const key = `${employeeAfm}|${workDate}`;
  if (acceptReviewPending.has(key)) return;
  const row = reportState.rows.find((item) => item.employee_afm === employeeAfm && item.work_date === workDate);
  if (!row || row.status !== "review") return;
  acceptReviewPending.add(key);
  if (button) {
    button.disabled = true;
    button.classList.add("is-pending");
    button.title = "Αποθήκευση…";
  }
  try {
    const res = await fetch("/api/apologistic/accept-review", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ week_from: weekFromForRow(row), employee_afm: employeeAfm, work_date: workDate }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    row.status = data.status || "change";
    row.change_from_review = Boolean(data.change_from_review);
    if (data.reason) row.reason = data.reason;
    refreshSummaryCounts();
    renderVisibleRows();
  } catch (error) {
    Office.showMsg("apologisticSubmitMsg", error.message || String(error), false);
  } finally {
    acceptReviewPending.delete(key);
  }
}

async function submitExchangeChoice(row, replacementWorkDate) {
  try {
    const res = await fetch("/api/apologistic/exchange", {
      method: "PUT",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        week_from: weekFromForRow(row),
        employee_afm: row.employee_afm,
        rest_work_date: row.work_date,
        replacement_work_date: replacementWorkDate,
      }),
    });
    const data = await res.json().catch(() => ({}));
    return { ok: res.ok, data, error: data.error || `HTTP ${res.status}` };
  } catch (error) {
    return { ok: false, data: {}, error: error.message || String(error) };
  }
}

function mergeExchangeRows(rows) {
  for (const updated of rows || []) {
    const row = reportState.rows.find((item) =>
      item.employee_afm === updated.employee_afm && item.work_date === updated.work_date
    );
    if (row) Object.assign(row, updated);
  }
}

async function applyExchange(employeeAfm, restWorkDate, replacementWorkDate, button) {
  const key = `${employeeAfm}|${restWorkDate}|${replacementWorkDate}`;
  if (exchangePending.has(key)) return;
  const source = reportState.rows.find((row) =>
    row.employee_afm === employeeAfm && row.work_date === restWorkDate
  );
  if (!source) return;
  exchangePending.add(key);
  if (button) {
    button.disabled = true;
    button.classList.add("is-pending");
  }
  try {
    const alternatives = (source.exchange_options || []).filter((option) =>
      option.replacement_work_date !== replacementWorkDate
    );
    const candidates = [replacementWorkDate, ...alternatives.map((option) => option.replacement_work_date)];
    let applied = null;
    let lastError = "Δεν βρέθηκε διαθέσιμη ημέρα ανταλλαγής";
    for (const candidate of candidates) {
      const result = await submitExchangeChoice(source, candidate);
      if (!result.ok) {
        lastError = result.error;
        continue;
      }
      applied = { replacementWorkDate: candidate, data: result.data };
      break;
    }
    if (!applied) throw new Error(`${lastError}. Η γραμμή παρέμεινε σε Έλεγχο.`);
    mergeExchangeRows(applied.data.rows || []);
    refreshSummaryCounts();
    renderVisibleRows();
    Office.showMsg(
      "apologisticSubmitMsg",
      `Η ανταλλαγή ${restWorkDate} ↔ ${applied.replacementWorkDate} αποθηκεύτηκε ως δύο μεταβολές (Μ*).`,
      true,
    );
  } catch (error) {
    Office.showMsg("apologisticSubmitMsg", error.message || String(error), false);
  } finally {
    exchangePending.delete(key);
  }
}
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

function hideProposalHistoryOverlay() {
  document.getElementById("apologisticProposalHistoryOverlay")?.remove();
}

function hideEmployeeWeekOverlay() {
  document.getElementById("apologisticEmployeeWeekOverlay")?.remove();
}

function positionApologisticHoverOverlay(overlay, anchor) {
  const anchorRect = anchor.getBoundingClientRect();
  const overlayRect = overlay.getBoundingClientRect();
  const gap = 8;
  const left = Math.max(gap, Math.min(
    window.innerWidth - overlayRect.width - gap,
    anchorRect.left,
  ));
  const fitsBelow = anchorRect.bottom + gap + overlayRect.height <= window.innerHeight;
  const top = fitsBelow
    ? anchorRect.bottom + gap
    : Math.max(gap, anchorRect.top - overlayRect.height - gap);
  overlay.style.left = `${left}px`;
  overlay.style.top = `${top}px`;
}

function employeeWeekHistoryHtml(employeeAfm, highlightWorkDate) {
  const rows = reportState.rows
    .filter((item) => item.employee_afm === employeeAfm)
    .sort((left, right) => String(left.work_date || "").localeCompare(String(right.work_date || ""), "el"));
  if (!rows.length) {
    return `<div class="apologistic-employee-week-empty">Δεν βρέθηκαν ημέρες για αυτή την εβδομάδα.</div>`;
  }
  const name = `${rows[0].eponymo || ""} ${rows[0].onoma || ""}`.trim();
  const body = rows.map((item) => {
    const punch = item.punch_recorded ?? item.actual ?? "—";
    const current = highlightWorkDate && item.work_date === highlightWorkDate;
    return `<tr class="${current ? "is-current" : ""}">` +
      `<td>${attr(String(item.work_date || "").slice(0, 5))}</td>` +
      `<td>${attr(compactDayState(item.day_state))}</td>` +
      `<td>${attr(compactScheduleLabel(item.declared))}</td>` +
      `<td class="apologistic-week-punch">${formatPunchCell(punch)}${item.overnight ? "*" : ""}</td>` +
      `<td><span class="status-badge apologistic-status--${attr(item.status)}">${statusShortLabel(item.status, item)}</span></td>` +
      `</tr>`;
  }).join("");
  return `<b>Εβδομάδα · ${attr(name)}</b>` +
    `<table class="apologistic-employee-week-table"><thead><tr>` +
    `<th>Ημέρα</th><th>Κατά.</th><th>Δηλωμένο</th><th>Χτύπημα</th><th>Αποτ.</th>` +
    `</tr></thead><tbody>${body}</tbody></table>`;
}

function showEmployeeWeekOverlay(anchor, employeeAfm, workDate) {
  hideEmployeeWeekOverlay();
  hideProposalHistoryOverlay();
  if (!employeeAfm) return;
  const overlay = document.createElement("div");
  overlay.id = "apologisticEmployeeWeekOverlay";
  overlay.className = "apologistic-employee-week-overlay";
  overlay.innerHTML = employeeWeekHistoryHtml(employeeAfm, workDate);
  document.body.appendChild(overlay);
  positionApologisticHoverOverlay(overlay, anchor);
}

function showProposalHistoryOverlay(anchor) {
  hideProposalHistoryOverlay();
  hideEmployeeWeekOverlay();
  const source = anchor.querySelector(".apologistic-proposal-history");
  if (!source) return;
  const overlay = document.createElement("div");
  overlay.id = "apologisticProposalHistoryOverlay";
  overlay.className = "apologistic-proposal-history-overlay";
  overlay.innerHTML = source.innerHTML;
  document.body.appendChild(overlay);
  positionApologisticHoverOverlay(overlay, anchor);
}

function bindProposalHistoryOverlays() {
  document.querySelectorAll(".apologistic-proposal-wrap").forEach((wrap) => {
    wrap.addEventListener("mouseenter", () => showProposalHistoryOverlay(wrap));
    wrap.addEventListener("mouseleave", hideProposalHistoryOverlay);
    wrap.addEventListener("focusin", () => showProposalHistoryOverlay(wrap));
    wrap.addEventListener("focusout", hideProposalHistoryOverlay);
  });
}

function bindEmployeeWeekOverlays() {
  document.querySelectorAll(".apologistic-employee-wrap").forEach((wrap) => {
    const afm = wrap.dataset.employeeAfm || "";
    const workDate = wrap.dataset.workDate || "";
    wrap.addEventListener("mouseenter", () => showEmployeeWeekOverlay(wrap, afm, workDate));
    wrap.addEventListener("mouseleave", hideEmployeeWeekOverlay);
    wrap.addEventListener("focusin", () => showEmployeeWeekOverlay(wrap, afm, workDate));
    wrap.addEventListener("focusout", hideEmployeeWeekOverlay);
  });
}

async function editProposal(employeeAfm, workDate) {
  const row = reportState.rows.find((item) => item.employee_afm === employeeAfm && item.work_date === workDate);
  if (!row) return;
  const detected = detectProposalType(row.proposed);
  proposalEditRow = row;
  document.getElementById("apologisticProposalModalMeta").textContent = `${row.eponymo || ""} ${row.onoma || ""} · ${row.work_date}`;
  document.getElementById("apologisticProposalFrom").value = detected.type === "work" ? (detected.from || "") : "";
  document.getElementById("apologisticProposalTo").value = detected.type === "work" ? (detected.to || "") : "";
  const workFrom2 = document.getElementById("apologisticProposalFrom2");
  const workTo2 = document.getElementById("apologisticProposalTo2");
  if (workFrom2) workFrom2.value = detected.type === "work" ? (detected.from2 || "") : "";
  if (workTo2) workTo2.value = detected.type === "work" ? (detected.to2 || "") : "";
  const teleFrom = document.getElementById("apologisticProposalTeleFrom");
  const teleTo = document.getElementById("apologisticProposalTeleTo");
  if (teleFrom) teleFrom.value = detected.type === "telework" ? (detected.from || "") : "";
  if (teleTo) teleTo.value = detected.type === "telework" ? (detected.to || "") : "";
  document.getElementById("apologisticProposalError").textContent = "";
  setProposalType(detected.type);
  document.getElementById("apologisticProposalModal").classList.remove("hidden");
  setTimeout(() => {
    if (detected.type === "work") document.getElementById("apologisticProposalFrom")?.focus();
    else if (detected.type === "telework") document.getElementById("apologisticProposalTeleFrom")?.focus();
  }, 0);
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
  const errorBox = document.getElementById("apologisticProposalError");
  const built = buildProposedValueFromEditor();
  if (built && typeof built === "object" && built.error) {
    errorBox.textContent = built.error;
    return;
  }
  const requested = String(built || "").trim();
  if (!requested) {
    errorBox.textContent = "Επιλέξτε τύπο πρότασης.";
    return;
  }
  if (requested === row.proposed) { closeProposalEditor(); return; }
  try {
    const res = await fetch("/api/apologistic/proposal", {
      method: "PUT", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({week_from: weekFromForRow(row), employee_afm: row.employee_afm, work_date: row.work_date, proposed: requested}),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    row.proposed = data.proposed;
    row.proposal_history = data.history || [];
    if (data.status) row.status = data.status;
    if (data.reason) row.reason = data.reason;
    if (data.status_changed) row.change_from_review = false;
    else if ("change_from_review" in data) row.change_from_review = Boolean(data.change_from_review);
    refreshScheduleSubmitMatch(row);
    closeProposalEditor();
    refreshSummaryCounts();
    renderVisibleRows();
  } catch (error) {
    errorBox.innerHTML = Office.formatMultilineHtml(error.message || error);
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
    `<span class="status-badge apologistic-status--${attr(row.status)}">${attr(statusLabel(row.status, row))}</span>`;

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
      `<span class="status-badge apologistic-status--${attr(row.status)}">${attr(statusLabel(row.status, row))}</span></section>` +
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

function formatPunchPlain(value) {
  const raw = String(value || "").trim();
  if (!raw || raw === "—") return "—";
  return raw.split("\n").map((line) => formatPunchLine(line)).join(" · ");
}

function overtimePlain(row) {
  const segments = row.overtime_segments || [];
  if (!segments.length) return "—";
  return segments.map((segment) => `${segment.from || ""}–${segment.to || ""}`).join(" · ");
}

function apologisticExportFilterLabel() {
  if (reportState.filter === "ok") return "φίλτρο: Σύμφωνο";
  if (reportState.filter === "change") return "φίλτρο: Μεταβολές";
  if (reportState.filter === "review") return "φίλτρο: Για έλεγχο";
  if (reportState.filter === "submitted") return "φίλτρο: Υποβεβλημένες";
  return "";
}

function buildApologisticExportHeaders(showDateColumn) {
  const headers = [];
  if (showDateColumn) headers.push("Ημέρα");
  headers.push(
    "Εργαζόμενος",
    "Κατάσταση",
    "Δηλωμένο",
    "Χτύπημα",
    "Δηλωμένες ώρες",
    "Πραγματικές ώρες",
    "Διαφ. έναρξης",
    "Διαφ. λήξης",
    "Μικτή διαφορά",
    "Διάλ. εκτός",
    "Καθαρή διαφορά",
    "Υπερωρίες",
    "Πρόταση",
  );
  return headers;
}

function buildApologisticExportRow(row, showDateColumn) {
  const punchRecorded = row.punch_recorded ?? row.actual ?? "—";
  const cells = [];
  if (showDateColumn) cells.push(String(row.work_date || ""));
  cells.push(
    `${row.eponymo || ""} ${row.onoma || ""}`.trim(),
    compactDayState(row.day_state),
    compactScheduleLabel(row.declared),
    `${formatPunchPlain(punchRecorded)}${row.overnight ? "*" : ""}`,
    mins(row.declared_minutes),
    mins(row.actual_minutes),
    signedMins(row.start_difference_minutes),
    signedMins(row.end_difference_minutes),
    signedMins(row.gross_difference_minutes),
    row.outside_break_minutes ? mins(row.outside_break_minutes) : "—",
    signedMins(row.net_difference_minutes),
    overtimePlain(row),
    compactScheduleLabel(row.proposed),
  );
  return cells;
}

function escapeExcelXml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function excelXmlRow(cells) {
  const body = cells.map((cell) =>
    `<Cell><Data ss:Type="String">${escapeExcelXml(cell)}</Data></Cell>`,
  ).join("");
  return `<Row>${body}</Row>`;
}

function buildApologisticExcelBlob(metaLine, headers, rows) {
  const tableRows = [
    excelXmlRow([metaLine]),
    excelXmlRow(headers),
    ...rows.map((row) => excelXmlRow(row)),
  ].join("");
  const xml =
    '<?xml version="1.0"?><?mso-application progid="Excel.Sheet"?>' +
    '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" ' +
    'xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">' +
    '<Worksheet ss:Name="Απολογιστικό"><Table>' +
    tableRows +
    "</Table></Worksheet></Workbook>";
  return new Blob([`\uFEFF${xml}`], { type: "application/vnd.ms-excel;charset=utf-8" });
}

function downloadApologisticExcel(button) {
  const rows = visibleReportRows();
  if (!rows.length) {
    Office.showMsg("apologisticSubmitMsg", "Δεν υπάρχουν αποτελέσματα για εξαγωγή.", false);
    return;
  }
  const showDateColumn = isAllDaysSelected();
  const filterLabel = apologisticExportFilterLabel();
  const countLabel = isAllDaysSelected() ? `${rows.length} αποτελέσματα` : `${rows.length} εργαζόμενοι`;
  const metaParts = [
    reportState.store?.name || "",
    `${reportPeriodLabel()} · ${countLabel}`,
    filterLabel,
  ].filter(Boolean);
  const headers = buildApologisticExportHeaders(showDateColumn);
  const dataRows = rows.map((row) => buildApologisticExportRow(row, showDateColumn));
  const filename = isEmployeeMonthView()
    ? `monthly_${employeeMonthAfm()}_${monthStart.getFullYear()}${String(monthStart.getMonth() + 1).padStart(2, "0")}.xls`
    : isStoreMonthView()
      ? `apologistic_month_${monthStart.getFullYear()}${String(monthStart.getMonth() + 1).padStart(2, "0")}.xls`
      : isStoreRangeView()
        ? `apologistic_${iso(rangeStart).replace(/-/g, "")}_${iso(rangeEnd).replace(/-/g, "")}.xls`
        : `apologistic_${iso(weekStart).replace(/-/g, "")}.xls`;
  if (button) Office.setButtonLoading(button, true);
  try {
    const blob = buildApologisticExcelBlob(metaParts.join(" · "), headers, dataRows);
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    Office.showMsg("apologisticSubmitMsg", `Κατέβηκε Excel (${rows.length} γραμμές).`, true);
  } catch (error) {
    Office.showMsg("apologisticSubmitMsg", error.message || String(error), false);
  } finally {
    if (button) Office.setButtonLoading(button, false);
  }
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
  if (upper.includes("ΤΗΛΕΡΓΑΣ") || upper.startsWith("ΤΗΛ ")) {
    const match = raw.match(/(\d{2}:\d{2})\s*[–-]\s*(\d{2}:\d{2})/);
    return match ? `Τηλεργ. ${match[1]}–${match[2]}` : "Τηλεργασία";
  }
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
  if (isEmployeeMonthView()) return loadEmployeeMonthReport();
  if (isStoreMonthView()) return loadStoreMonthReport();
  if (isStoreRangeView()) return loadStoreRangeReport();
  return loadWeekReport();
}

async function loadStoreRangeReport() {
  const wrap = document.getElementById("apologisticWrap");
  syncStorePeriodUi();
  closeBulkWeekModal();
  Office.showTableLoading(wrap);
  closeExplanation();
  const qs = new URLSearchParams({ from: iso(rangeStart), to: iso(rangeEnd) });
  const res = await fetch(`/api/apologistic/range?${qs}`, { cache: "no-store" });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) return showError(data.error || `HTTP ${res.status}`);
  reportState = {
    rows: data.days || [], store: data.store, filter: "all", dates: data.work_dates || [],
    selectedDate: "", employeeCount: (data.employees || []).length, employee: null,
  };
  renderSummary(data);
  renderVisibleRows();
  document.getElementById("apologisticNotice").textContent = data.legal_notice || "";
}

async function loadStoreMonthReport() {
  const wrap = document.getElementById("apologisticWrap");
  syncStorePeriodUi();
  closeBulkWeekModal();
  Office.showTableLoading(wrap);
  closeExplanation();
  const qs = new URLSearchParams({ year: String(monthStart.getFullYear()), month: String(monthStart.getMonth() + 1) });
  const res = await fetch(`/api/apologistic/month?${qs}`, { cache: "no-store" });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) return showError(data.error || `HTTP ${res.status}`);
  const monthFrom = new Date(monthStart.getFullYear(), monthStart.getMonth(), 1);
  const monthTo = new Date(monthStart.getFullYear(), monthStart.getMonth() + 1, 0);
  const days = (data.days || []).filter((row) => {
    const parts = String(row.work_date || "").split("/").map(Number);
    if (parts.length !== 3 || parts.some((part) => !Number.isFinite(part))) return false;
    const workDate = new Date(parts[2], parts[1] - 1, parts[0]);
    return workDate >= monthFrom && workDate <= monthTo;
  });
  reportState = {
    rows: days, store: data.store, filter: "all",
    dates: (data.work_dates || []).filter((value) => days.some((row) => row.work_date === value)),
    selectedDate: "", employeeCount: (data.employees || []).length, employee: null,
  };
  renderStoreMonthWeeks(data.weeks || []);
  renderSummary({ ...data, days });
  renderVisibleRows();
  document.getElementById("apologisticNotice").textContent = data.legal_notice || "";
}

async function loadWeekReport() {
  const wrap = document.getElementById("apologisticWrap");
  const end = addDays(weekStart, 6);
  document.getElementById("weekLabel").textContent = `${weekStart.toLocaleDateString("el-GR")} – ${end.toLocaleDateString("el-GR")}`;
  syncWeekNavigation();
  closeBulkWeekModal();
  document.getElementById("apologisticBulkBar")?.classList.add("hidden");
  document.getElementById("apologisticBulkWeekBtn")?.setAttribute("hidden", "");
  Office.showTableLoading(wrap);
  closeExplanation();
  const res = await fetch(`/api/apologistic/week?from=${iso(weekStart)}&to=${iso(end)}`);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) return showError(data.error || `HTTP ${res.status}`);
  reportState = {
    rows: data.days || [], store: data.store, filter: "all",
    dates: data.work_dates || [], selectedDate: "",
    employeeCount: (data.employees || []).length,
    employee: null,
  };
  renderSummary(data);
  if (!isEmployeeMonthView()) {
    renderDayTabs();
    syncDaySelectionUi();
  } else {
    reportState.selectedDate = "";
  }
  renderVisibleRows();
  document.getElementById("apologisticNotice").textContent = data.legal_notice || "";
}

async function loadEmployeeMonthReport() {
  const wrap = document.getElementById("apologisticWrap");
  syncEmployeeMonthNavigation();
  closeBulkWeekModal();
  document.getElementById("apologisticBulkBar")?.classList.add("hidden");
  document.getElementById("apologisticBulkWeekBtn")?.setAttribute("hidden", "");
  Office.showTableLoading(wrap);
  closeExplanation();
  const qs = new URLSearchParams({
    afm: employeeMonthAfm(),
    year: String(monthStart.getFullYear()),
    month: String(monthStart.getMonth() + 1),
  });
  const res = await fetch(`/api/employees/monthly-overview?${qs}`, { cache: "no-store" });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) return showError(data.error || `HTTP ${res.status}`);
  const days = data.days || [];
  reportState = {
    rows: days,
    store: data.store,
    filter: "all",
    dates: days.map((row) => row.work_date),
    selectedDate: "",
    employee: data.employee || null,
    employeeCount: 1,
  };
  const desc = document.getElementById("employeeMonthDesc");
  if (desc) {
    desc.textContent = `${employeeMonthName()} · ΑΦΜ ${employeeMonthAfm()} · ${data.store?.name || ""}`;
  }
  renderSummary({ days, employees: [data.employee].filter(Boolean) });
  reportState.selectedDate = "";
  renderVisibleRows();
  document.getElementById("apologisticNotice").textContent = data.legal_notice || "";
}
function showError(error) {
  document.getElementById("apologisticWrap").innerHTML = `<p style="color:var(--err);">${Office.formatMultilineHtml(String(error))}</p>`;
}
function renderSummary(data) {
  const rows = data.days || reportState.rows || [];
  const counts = computeReportCounts(rows);
  if (isEmployeeMonthView()) {
    document.getElementById("apologisticSummary").innerHTML =
      `<div class="card apologistic-kpi"><span>Ημέρες μήνα</span><strong>${reportState.dates.length}</strong></div>` +
      `<button type="button" class="card apologistic-kpi apologistic-kpi--filter" data-report-filter="all" title="Όλες οι ημέρες του μήνα"><span>Υπολογισμένες</span><strong>${counts.all || 0}</strong></button>` +
      `<button type="button" class="card apologistic-kpi apologistic-kpi--ok apologistic-kpi--filter" data-report-filter="ok" title="Μόνο σύμφωνες ημέρες"><span>Σύμφωνο</span><strong>${counts.ok || 0}</strong></button>` +
      `<button type="button" class="card apologistic-kpi apologistic-kpi--change apologistic-kpi--filter" data-report-filter="change" title="Μόνο μεταβολές"><span>Μεταβολές</span><strong>${counts.change || 0}</strong></button>` +
      `<button type="button" class="card apologistic-kpi apologistic-kpi--review apologistic-kpi--filter" data-report-filter="review" title="Μόνο για έλεγχο"><span>Για έλεγχο</span><strong>${counts.review || 0}</strong></button>` +
      `<button type="button" class="card apologistic-kpi apologistic-kpi--submitted apologistic-kpi--filter" data-report-filter="submitted" title="Ημέρες με υποβολή Ergani"><span>Υποβεβλημένες</span><strong>${counts.submitted || 0}</strong></button>`;
  } else {
    document.getElementById("apologisticSummary").innerHTML =
      `<div class="card apologistic-kpi"><span>Εργαζόμενοι</span><strong>${(data.employees || []).length}</strong></div>` +
      `<button type="button" class="card apologistic-kpi apologistic-kpi--filter" data-report-filter="all" title="Εμφάνιση όλων των αποτελεσμάτων"><span>Αποτελέσματα</span><strong>${counts.all || 0}</strong></button>` +
      `<button type="button" class="card apologistic-kpi apologistic-kpi--ok apologistic-kpi--filter" data-report-filter="ok" title="Εμφάνιση μόνο των σύμφωνων εγγραφών"><span>Σύμφωνο</span><strong>${counts.ok || 0}</strong></button>` +
      `<button type="button" class="card apologistic-kpi apologistic-kpi--change apologistic-kpi--filter" data-report-filter="change" title="Εμφάνιση μόνο των μεταβολών"><span>Μεταβολές</span><strong>${counts.change || 0}</strong></button>` +
      `<button type="button" class="card apologistic-kpi apologistic-kpi--review apologistic-kpi--filter" data-report-filter="review" title="Εμφάνιση μόνο των εγγραφών για έλεγχο"><span>Για έλεγχο</span><strong>${counts.review || 0}</strong></button>` +
      `<button type="button" class="card apologistic-kpi apologistic-kpi--submitted apologistic-kpi--filter" data-report-filter="submitted" title="Εμφάνιση γραμμών με υποβληθείσα απολογιστική μεταβολή ή υπερωρία (WTODailyA / WTOOvA)"><span>Υποβεβλημένες</span><strong>${counts.submitted || 0}</strong></button>`;
  }
  document.querySelectorAll("[data-report-filter]").forEach((button) => {
    button.addEventListener("click", () => applyReportFilter(button.dataset.reportFilter || "all"));
  });
  syncFilterButtons();
  updateBulkWeekBar();
  updateAcceptAllBar();
}
function applyReportFilter(requested) {
  reportState.filter = requested !== "all" && reportState.filter === requested ? "all" : requested;
  renderVisibleRows();
  syncFilterButtons();
  updateBulkWeekBar();
  updateAcceptAllBar();
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
  if (!mount) return;
  if (isEmployeeMonthView()) {
    mount.innerHTML = reportState.dates.map((date) => {
      const finalized = reportState.rows.some((row) => row.work_date === date && isRowFinalized(row));
      return `<button type="button" class="apologistic-day-tab${date === reportState.selectedDate ? " is-active" : ""}${finalized ? "" : " is-empty"}" ` +
        `data-work-date="${attr(date)}" aria-pressed="${date === reportState.selectedDate ? "true" : "false"}">` +
        `<span>${weekdayLabelForDate(date)}</span><strong>${attr(date.slice(0, 5))}</strong></button>`;
    }).join("");
  } else {
    const weekdayNames = ["Δευτέρα", "Τρίτη", "Τετάρτη", "Πέμπτη", "Παρασκευή", "Σάββατο", "Κυριακή"];
    mount.innerHTML = reportState.dates.map((date, index) => {
      const count = reportState.rows.filter((row) => row.work_date === date).length;
      return `<button type="button" class="apologistic-day-tab${date === reportState.selectedDate ? " is-active" : ""}" ` +
        `data-work-date="${attr(date)}" aria-pressed="${date === reportState.selectedDate ? "true" : "false"}">` +
        `<span>${weekdayNames[index] || "Ημέρα"}</span><strong>${attr(date.slice(0, 5))}</strong><small>${count}</small></button>`;
    }).join("");
  }
  mount.querySelectorAll("[data-work-date]").forEach((button) => {
    button.addEventListener("click", () => {
      reportState.selectedDate = button.dataset.workDate || "";
      syncDaySelectionUi();
      renderVisibleRows();
    });
  });
  syncDaySelectionUi();
}
function renderVisibleRows() {
  renderRows(visibleReportRows(), reportState.store);
}
function renderRows(rows, store) {
  hideProposalHistoryOverlay();
  const wrap = document.getElementById("apologisticWrap");
  if (!rows.length) {
    const suffix = reportState.filter === "all" ? "" : " με το ενεργό φίλτρο";
    wrap.innerHTML = `<p style="color:var(--muted);">Δεν υπάρχουν αποτελέσματα για ${attr(reportPeriodLabel())}${suffix}.</p>`;
    updateBulkWeekBar();
    updateAcceptAllBar();
    return;
  }
  const filterLabel =
    reportState.filter === "ok" ? " · φίλτρο: Σύμφωνο"
    : reportState.filter === "change" ? " · φίλτρο: Μεταβολές"
    : reportState.filter === "review" ? " · φίλτρο: Για έλεγχο"
    : reportState.filter === "submitted" ? " · φίλτρο: Υποβεβλημένες"
    : "";
  const countLabel = isEmployeeMonthView()
    ? (isAllDaysSelected() ? `${rows.length} ημέρες` : "1 ημέρα")
    : (isAllDaysSelected() ? `${rows.length} αποτελέσματα` : `${rows.length} εργαζόμενοι`);
  const showDateColumn = isEmployeeMonthView() || isAllDaysSelected();
  const hideEmployeeColumn = isEmployeeMonthView();
  const erganiHeader = canSubmitErgani ? `<th>Ergani</th>` : "";
  const baseCols = canSubmitErgani ? 15 : 14;
  const tableCols = baseCols + (showDateColumn ? 1 : 0) - (hideEmployeeColumn ? 1 : 0);
  let html = `<div class="apologistic-table-meta">` +
    `<p class="table-meta"><i class="bi bi-${isEmployeeMonthView() ? "person" : "shop-window"}"></i> ` +
    `<strong>${Office.escapeHtml(isEmployeeMonthView() ? employeeMonthName() : (store?.name || ""))}</strong>` +
    `${isEmployeeMonthView() ? ` · ΑΦΜ ${attr(employeeMonthAfm())}` : ""}` +
    ` · ${attr(reportPeriodLabel())} · ${countLabel}${filterLabel}</p>` +
    `<button type="button" class="btn btn-secondary btn-icon apologistic-export-btn" title="Εξαγωγή Excel (ορατά αποτελέσματα)" aria-label="Εξαγωγή Excel">` +
    `<i class="bi bi-file-earmark-excel" aria-hidden="true"></i></button></div>`;
  html += `<table class="data apologistic-table${canSubmitErgani ? " apologistic-table--ergani" : ""}${showDateColumn ? " apologistic-table--all-days" : ""}"><thead><tr>` +
    `${showDateColumn ? "<th>Ημέρα</th>" : ""}` +
    `${hideEmployeeColumn ? "" : "<th>Εργαζόμενος</th>"}` +
    `<th>Κατάσταση</th><th>Δηλωμένο</th><th>Χτύπημα</th><th>Δηλωμένες ώρες</th><th>Πραγματικές ώρες</th><th>Διαφ. έναρξης</th><th>Διαφ. λήξης</th><th>Μικτή διαφορά</th><th>Διάλ. εκτός</th><th>Καθαρή διαφορά</th><th class="apologistic-overtime-head">Υπερωρίες</th><th>Πρόταση</th><th>Αποτέλεσμα</th>${erganiHeader}</tr></thead><tbody>`;
  for (const row of rows) {
    if (isEmployeeMonthView() && !isRowFinalized(row)) {
      html += `<tr class="apologistic-row--pending${row.source === "future" ? " employee-month-future" : ""}">` +
        `<td title="${attr(row.work_date || "")}"><strong>${attr(weekdayLabelForDate(row.work_date))}</strong> ${attr(row.work_date || "")}</td>` +
        `<td colspan="${tableCols - 1}" class="employee-month-pending-label">${attr(pendingRowLabel(row))}</td></tr>`;
      continue;
    }
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
      (showDateColumn
        ? `<td title="${attr(row.work_date || "")}"><strong>${attr(isEmployeeMonthView() ? weekdayLabelForDate(row.work_date) : String(row.work_date || "").slice(0, 5))}</strong>${isEmployeeMonthView() ? ` ${attr(row.work_date || "")}` : ""}</td>`
        : "") +
      (hideEmployeeColumn ? "" :
        `<td title="${attr(`ΑΦΜ: ${row.employee_afm} · Κλικ για στοιχεία σύμβασης · Πέρασμα για εβδομαδιαίο ιστορικό`)}">` +
        `<div class="apologistic-employee-wrap" data-employee-afm="${attr(row.employee_afm)}" data-work-date="${attr(row.work_date)}">` +
        `<button type="button" class="apologistic-employee-btn" data-employee-afm="${attr(row.employee_afm)}">${attr(`${row.eponymo || ""} ${row.onoma || ""}`.trim())}</button>` +
        ((row.incoming_rest_obligations || []).length
          ? `<span class="apologistic-rest-due" title="${attr((row.incoming_rest_obligations || []).map((item) => `Οφείλεται ρεπό από Κυριακή ${item.source_work_date} · ${mins(item.source_actual_minutes)} εργασία`).join(" · "))}"><i class="bi bi-calendar2-check" aria-hidden="true"></i> Οφείλεται ρεπό</span>`
          : "") +
        `</div></td>`) +
      `<td title="${attr(contractTip)}">${attr(compactDayState(row.day_state))}</td>` +
      `<td title="${attr(declaredTip)}">${attr(compactScheduleLabel(row.declared))}</td>` +
      `<td class="apologistic-punch-cell" title="${attr(punchTip)}">${formatPunchCell(punchRecorded)}${row.overnight ? "*" : ""}</td>` +
      `<td title="Δηλωμένη διάρκεια">${mins(row.declared_minutes)}</td><td title="Πραγματική διάρκεια${row.actual && row.actual !== punchRecorded ? ` (τεκμαίρεται: ${row.actual})` : ""}">${mins(row.actual_minutes)}</td>` +
      `<td title="Διαφορά πραγματικής από δηλωμένη έναρξη" class="${diffClass(row.start_difference_minutes)}">${signedMins(row.start_difference_minutes)}</td>` +
      `<td title="Διαφορά πραγματικής από δηλωμένη λήξη" class="${diffClass(row.end_difference_minutes)}">${signedMins(row.end_difference_minutes)}</td>` +
      `<td title="Πραγματική μείον δηλωμένη διάρκεια" class="${diffClass(row.gross_difference_minutes)}">${signedMins(row.gross_difference_minutes)}</td>` +
      `<td title="${attr(breakTip)}">${row.outside_break_minutes ? mins(row.outside_break_minutes) : "—"}</td>` +
      `<td title="${attr(netDetails)}" class="${diffClass(row.net_difference_minutes)}"><strong>${signedMins(row.net_difference_minutes)}</strong></td>` +
      `<td title="${attr((row.overtime_segments || []).map((segment) => `${segment.date}: ${segment.from}–${segment.to} (${mins(segment.minutes)})`).join(" · ") || "Δεν προκύπτει υπερωρία")}" class="apologistic-overtime-cell${row.overtime_minutes ? " time-diff--plus" : ""}">${overtimeCell(row)}</td>` +
      `<td class="apologistic-proposal-cell"><div class="apologistic-proposal-wrap">` +
      `<button type="button" class="apologistic-proposal-btn" data-employee-afm="${attr(row.employee_afm)}" data-work-date="${attr(row.work_date)}" title="Κλικ για αλλαγή προτεινόμενου ωραρίου"><strong>${attr(compactScheduleLabel(row.proposed))}</strong></button>` +
      `<div class="apologistic-proposal-history"><b>Ιστορικό πρότασης</b>${proposalHistory(row)}</div></div></td>` +
      `<td class="apologistic-result-cell" title="${attr(statusLabel(row.status, row))}">${renderResultBadge(row)}` +
      `<button type="button" class="apologistic-info-btn" data-explanation-id="${attr(explanationId)}" aria-expanded="false" aria-label="Λεπτομέρειες αποτελέσματος"><i class="bi bi-info-circle" aria-hidden="true"></i></button></td>` +
      (canSubmitErgani ? `<td class="apologistic-ergani-cell">${renderErganiActions(row)}</td>` : "") +
      `</tr>`;
    if ((row.exchange_options || []).length) {
      html += `<tr class="apologistic-replacement-row"><td colspan="${tableCols}"><div class="apologistic-replacement-options">` +
        `<span class="apologistic-exchange-title"><i class="bi bi-arrow-left-right" aria-hidden="true"></i> Επιλογές ανταλλαγής</span>` +
        row.exchange_options.map((item) => `<button type="button" class="apologistic-exchange-card" ` +
          `data-employee-afm="${attr(row.employee_afm)}" data-rest-work-date="${attr(item.rest_work_date)}" ` +
          `data-replacement-work-date="${attr(item.replacement_work_date)}" title="Εφαρμογή ανταλλαγής και δημιουργία δύο μεταβολών Μ*">` +
          `<div class="apologistic-exchange-side apologistic-exchange-side--source"><small>Ωράριο χωρίς χτύπημα</small><strong>${attr(item.replacement_work_date)}</strong><span>${attr(item.replacement_declared)}</span></div>` +
          `<div class="apologistic-exchange-arrow"><i class="bi bi-arrow-left-right" aria-hidden="true"></i><small>${mins(item.contract_duration_minutes)}</small></div>` +
          `<div class="apologistic-exchange-side apologistic-exchange-side--target"><small>Χτύπημα σε ${attr(row.day_state)}</small><strong>${attr(item.rest_work_date)}</strong><span>${attr(item.rest_punch)} → <b>${attr(item.proposed)}</b></span></div>` +
        `</button>`).join("") +
        `</div></td></tr>`;
    }
    const uneven = row.uneven_distribution_group;
    if (uneven?.group_id && uneven.role === "target") {
      html += `<tr class="apologistic-replacement-row"><td colspan="${tableCols}"><div class="apologistic-replacement-options">` +
        `<span class="apologistic-exchange-title"><i class="bi bi-distribute-horizontal" aria-hidden="true"></i> Ανισομερής κατανομή · 40:00 → 40:00</span>` +
        (uneven.members || []).map((item) =>
          `<div class="apologistic-uneven-member"><div class="apologistic-exchange-side"><small>${item.role === "target" ? "Συμπλήρωση" : "Αφαίρεση"}</small>` +
          `<strong>${attr(item.work_date)}</strong><span>${attr(item.declared)} → <b>${attr(item.proposed)}</b> (${signedMins(item.delta_minutes)})</span></div></div>`
        ).join("") +
        `<button type="button" class="btn primary apologistic-uneven-accept-btn" data-employee-afm="${attr(row.employee_afm)}" data-group-id="${attr(uneven.group_id)}">Έγκριση ολόκληρης ομάδας</button>` +
        `</div></td></tr>`;
    }
  }
  wrap.innerHTML = html + `</tbody></table>`;
  bindProposalHistoryOverlays();
  bindEmployeeWeekOverlays();
  updateBulkWeekBar();
  updateAcceptAllBar();
  if (openExplanationId) {
    const modal = document.getElementById("apologisticInfoModal");
    if (findExplanationRow(openExplanationId) && modal && !modal.classList.contains("hidden")) {
      openExplanation(openExplanationId);
    } else {
      closeExplanation();
    }
  }
}
