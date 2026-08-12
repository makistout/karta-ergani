let weekStart = previousMonday();
const latestCompletedWeekStart = new Date(weekStart);
let reportState = { rows: [], store: null, filter: "all", selectedDate: "", dates: [] };
let openExplanationId = null;
let openEmployeeAfm = null;
let proposalEditRow = null;
let submitModalState = null;
const canSubmitErgani = document.querySelector(".apologistic-toolbar")?.dataset.canSubmit === "1";

document.addEventListener("DOMContentLoaded", async () => {
  Office.setActiveNav("apologistic");
  document.getElementById("weekPrev").onclick = () => moveWeek(-7);
  document.getElementById("weekNext").onclick = () => moveWeek(7);
  document.getElementById("apologisticAllDays")?.addEventListener("click", () => selectAllDays());
  initExplanationModal();
  initEmployeeModal();
  initProposalModal();
  initSubmitModal();
  window.addEventListener("scroll", () => {
    hideProposalHistoryOverlay();
    hideEmployeeWeekOverlay();
  }, true);
  window.addEventListener("resize", () => {
    hideProposalHistoryOverlay();
    hideEmployeeWeekOverlay();
  });
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
    if (submitModalState) closeSubmitModal();
    else if (proposalEditRow) closeProposalEditor();
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

function initSubmitModal() {
  const modal = document.getElementById("apologisticSubmitModal");
  if (!modal || modal.dataset.bound) return;
  modal.dataset.bound = "1";
  modal.querySelectorAll("[data-apologistic-submit-close]").forEach((el) => {
    el.addEventListener("click", closeSubmitModal);
  });
  document.getElementById("apologisticSubmitConfirm")?.addEventListener("click", confirmSubmitModal);
  document.getElementById("apologisticSubmitSegmentDate")?.addEventListener("change", () => {
    if (!submitModalState) return;
    renderSubmitPreviousBanner(
      submitModalState.row,
      submitModalState.kind,
      document.getElementById("apologisticSubmitSegmentDate")?.value || "",
    );
  });
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
  const list = rows || [];
  return {
    all: list.length,
    ok: list.filter((row) => row.status === "ok").length,
    change: list.filter((row) => row.status === "change").length,
    review: list.filter((row) => row.status === "review").length,
    submitted: countErganiSubmits(list),
  };
}

function refreshSummaryCounts() {
  renderSummary({
    employees: Array(reportState.employeeCount || 0).fill(null),
    days: reportState.rows,
    counts: computeReportCounts(reportState.rows),
  });
}

function isAllDaysSelected() {
  return !reportState.selectedDate;
}

function selectAllDays() {
  reportState.selectedDate = "";
  syncDaySelectionUi();
  renderVisibleRows();
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
    rows = rows.filter((row) => row.status === reportState.filter);
  }
  if (isAllDaysSelected()) {
    rows.sort((left, right) => {
      const dateCmp = String(left.work_date || "").localeCompare(String(right.work_date || ""), "el");
      if (dateCmp) return dateCmp;
      return String(left.eponymo || "").localeCompare(String(right.eponymo || ""), "el");
    });
  }
  return rows;
}

function reportPeriodLabel() {
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
  if (row.status !== "change") return false;
  if (scheduleLabelsMatch(row) && rowHasOvertime(row)) return false;
  return true;
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
  const overtime = row.ergani_submit?.overtime;
  if (!overtime) return null;
  for (const date of overtimeSegmentDates(row)) {
    if (overtime[date]?.protocol) return { ...overtime[date], segment_date: date };
  }
  return null;
}

function existingSubmitForKind(row, kind, segmentDate) {
  if (kind === "schedule") {
    const schedule = row.ergani_submit?.schedule;
    return schedule?.protocol ? schedule : null;
  }
  const seg = segmentDate || overtimeSegmentDates(row)[0] || row.work_date;
  const entry = row.ergani_submit?.overtime?.[seg];
  return entry?.protocol ? { ...entry, segment_date: seg } : null;
}

function formatSubmittedAt(value) {
  if (!value) return "—";
  const normalized = String(value).includes("T") ? String(value) : String(value).replace(" ", "T");
  const d = new Date(normalized);
  if (Number.isNaN(d.getTime())) return String(value).slice(0, 19).replace("T", " ");
  return d.toLocaleString("el-GR", { dateStyle: "short", timeStyle: "short" });
}

function renderSubmitPreviousBanner(row, kind, segmentDate) {
  const box = document.getElementById("apologisticSubmitPrevious");
  const confirmBtn = document.getElementById("apologisticSubmitConfirm");
  if (!box || !confirmBtn) return;
  const existing = existingSubmitForKind(row, kind, segmentDate);
  if (!existing?.protocol) {
    box.classList.add("hidden");
    box.innerHTML = "";
    confirmBtn.innerHTML = '<i class="bi bi-send" aria-hidden="true"></i> Υποβολή';
    return;
  }
  const doc = kind === "schedule" ? "WTODailyA" : "WTOOvA";
  const lines = [
    `Έχετε ήδη καταχωρήσει ${doc} για αυτή την ημέρα.`,
    `Πρωτόκολλο: ${existing.protocol}`,
    `Ημερομηνία/ώρα υποβολής: ${formatSubmittedAt(existing.submitted_at || existing.submit_date)}`,
  ];
  if (kind === "schedule" && existing.proposed_at_submit) {
    lines.push(`Ωράριο που στάλθηκε: ${existing.proposed_at_submit}`);
    if (existing.matches_proposal === false) {
      lines.push("Η τρέχουσα πρόταση διαφέρει — η επαναποστολή θα στείλει το νέο ωράριο.");
    }
  }
  if (kind === "overtime" && existing.segment_date) {
    lines.push(`Ημέρα υπερωρίας: ${existing.segment_date}`);
  }
  lines.push("Θέλετε να το υποβάλετε ξανά;");
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
  submitModalState = { kind, row };
  errorBox.textContent = "";
  const employeeName = `${row.eponymo || ""} ${row.onoma || ""}`.trim();
  meta.textContent = `${employeeName} · ${row.work_date}`;

  if (kind === "schedule") {
    title.textContent = "Υποβολή απολογιστικής μεταβολής";
    detail.innerHTML = `Έγγραφο: <strong>WTODailyA</strong><br>Πρόταση: <strong>${attr(compactScheduleLabel(row.proposed))}</strong>`;
    segmentWrap.classList.add("hidden");
    segmentSelect.innerHTML = "";
  } else {
    title.textContent = "Υποβολή απολογιστικής υπερωρίας";
    const dates = overtimeSegmentDates(row);
    segmentSelect.innerHTML = dates.map((date) => {
      const segments = overtimeSegmentsForDate(row, date);
      const label = segments.map((segment) => `${segment.from}–${segment.to}`).join(", ");
      return `<option value="${attr(date)}">${attr(date)} · ${attr(label)}</option>`;
    }).join("");
    if (dates.length > 1) {
      segmentWrap.classList.remove("hidden");
      detail.innerHTML = `Έγγραφο: <strong>WTOOvA</strong><br>Η υπερωρία απλώνεται σε περισσότερες από μία ημέρες — επιλέξτε ημέρα υποβολής.`;
    } else {
      segmentWrap.classList.add("hidden");
      const onlyDate = dates[0] || row.work_date;
      const label = overtimeSegmentsForDate(row, onlyDate).map((segment) => `${segment.from}–${segment.to}`).join(", ");
      detail.innerHTML = `Έγγραφο: <strong>WTOOvA</strong><br>Διάστημα: <strong>${attr(label || "—")}</strong>`;
    }
  }
  const segmentDate = kind === "overtime"
    ? (segmentSelect.value || overtimeSegmentDates(row)[0] || row.work_date)
    : "";
  renderSubmitPreviousBanner(row, kind, segmentDate);
  modal.classList.remove("hidden");
}

async function confirmSubmitModal() {
  const state = submitModalState;
  const btn = document.getElementById("apologisticSubmitConfirm");
  const errorBox = document.getElementById("apologisticSubmitError");
  if (!state || !btn) return;

  const { kind, row } = state;
  const body = {
    week_from: iso(weekStart),
    work_date: row.work_date,
    employee_afm: row.employee_afm,
    use_snapshot: true,
  };
  if (kind === "overtime") {
    const segmentDate = document.getElementById("apologisticSubmitSegmentDate")?.value || overtimeSegmentDates(row)[0] || "";
    if (segmentDate) body.segment_date = segmentDate;
  }

  const url = kind === "schedule" ? "/api/apologistic/submit-schedule" : "/api/apologistic/submit-overtime";
  Office.setButtonLoading(btn, true);
  errorBox.textContent = "";
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.success) {
      errorBox.innerHTML = Office.formatMultilineHtml(
        data.error || data.data?.message || data.data?.Message || `Αποτυχία υποβολής (HTTP ${res.status})`,
      );
      return;
    }
    mergeErganiSubmit(row, data.ergani_submit);
    if (kind === "schedule" && !data.ergani_submit?.schedule) {
      mergeErganiSubmit(row, {
        schedule: {
          protocol: data.protocol || null,
          ergani_submission_id: data.ergani_submission_id || null,
          submit_date: data.submit_date || null,
          submitted_at: new Date().toISOString(),
          proposed_at_submit: row.proposed,
          matches_proposal: true,
        },
      });
    } else if (kind === "overtime" && !data.ergani_submit?.overtime) {
      const segmentDate = body.segment_date || overtimeSegmentDates(row)[0] || row.work_date;
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
    closeSubmitModal();
    refreshSummaryCounts();
    renderVisibleRows();
    const proto = data.protocol ? ` · πρωτ. ${data.protocol}` : "";
    showSubmitToast(
      kind === "schedule"
        ? `Η απολογιστική μεταβολή ωραρίου υποβλήθηκε${proto}.`
        : `Η απολογιστική υπερωρία υποβλήθηκε${proto}.`,
      true,
    );
  } catch (error) {
    errorBox.innerHTML = Office.formatMultilineHtml(error.message || error);
  } finally {
    Office.setButtonLoading(btn, false);
  }
}

function renderErganiActions(row) {
  if (!canSubmitErgani) return "";
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
    const done = submitted?.protocol;
    actions.push(
      `<button type="button" class="apologistic-ergani-btn apologistic-submit-overtime-btn${done ? " is-done" : ""}" ` +
      `data-employee-afm="${attr(row.employee_afm)}" data-work-date="${attr(row.work_date)}" ` +
      `title="${attr(done ? `Υποβλήθηκε WTOOvA · ${submitted.protocol}${submitted.segment_date ? ` · ${submitted.segment_date}` : ""} · ${formatSubmittedAt(submitted.submitted_at || submitted.submit_date)}` : "Υποβολή απολογιστικής υπερωρίας (WTOOvA)")}">` +
      `<i class="bi ${done ? "bi-check2-circle" : "bi-clock-history"}" aria-hidden="true"></i></button>`,
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
      `<td><span class="status-badge apologistic-status--${attr(item.status)}">${statusShortLabel(item.status)}</span></td>` +
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
    refreshScheduleSubmitMatch(row);
    closeProposalEditor();
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
    dates: data.work_dates || [], selectedDate: "",
    employeeCount: (data.employees || []).length,
  };
  renderSummary(data);
  renderDayTabs();
  syncDaySelectionUi();
  renderVisibleRows();
  document.getElementById("apologisticNotice").textContent = data.legal_notice || "";
}
function showError(error) {
  document.getElementById("apologisticWrap").innerHTML = `<p style="color:var(--err);">${Office.formatMultilineHtml(String(error))}</p>`;
}
function renderSummary(data) {
  const rows = data.days || reportState.rows || [];
  const counts = {
    ...(data.counts || {}),
    submitted: computeReportCounts(rows).submitted,
  };
  document.getElementById("apologisticSummary").innerHTML =
    `<div class="card apologistic-kpi"><span>Εργαζόμενοι</span><strong>${(data.employees || []).length}</strong></div>` +
    `<button type="button" class="card apologistic-kpi apologistic-kpi--filter" data-report-filter="all" title="Εμφάνιση όλων των αποτελεσμάτων"><span>Αποτελέσματα</span><strong>${counts.all || 0}</strong></button>` +
    `<button type="button" class="card apologistic-kpi apologistic-kpi--ok apologistic-kpi--filter" data-report-filter="ok" title="Εμφάνιση μόνο των σύμφωνων εγγραφών"><span>Σύμφωνο</span><strong>${counts.ok || 0}</strong></button>` +
    `<button type="button" class="card apologistic-kpi apologistic-kpi--change apologistic-kpi--filter" data-report-filter="change" title="Εμφάνιση μόνο των μεταβολών"><span>Μεταβολές</span><strong>${counts.change || 0}</strong></button>` +
    `<button type="button" class="card apologistic-kpi apologistic-kpi--review apologistic-kpi--filter" data-report-filter="review" title="Εμφάνιση μόνο των εγγραφών για έλεγχο"><span>Για έλεγχο</span><strong>${counts.review || 0}</strong></button>` +
    `<button type="button" class="card apologistic-kpi apologistic-kpi--submitted apologistic-kpi--filter" data-report-filter="submitted" title="Εμφάνιση γραμμών με υποβληθείσα απολογιστική μεταβολή ή υπερωρία (WTODailyA / WTOOvA)"><span>Υποβεβλημένες</span><strong>${counts.submitted || 0}</strong></button>`;
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
    return;
  }
  const filterLabel =
    reportState.filter === "ok" ? " · φίλτρο: Σύμφωνο"
    : reportState.filter === "change" ? " · φίλτρο: Μεταβολές"
    : reportState.filter === "review" ? " · φίλτρο: Για έλεγχο"
    : reportState.filter === "submitted" ? " · φίλτρο: Υποβεβλημένες"
    : "";
  const countLabel = isAllDaysSelected() ? `${rows.length} αποτελέσματα` : `${rows.length} εργαζόμενοι`;
  const showDateColumn = isAllDaysSelected();
  const erganiHeader = canSubmitErgani ? `<th>Ergani</th>` : "";
  let html = `<p class="table-meta"><i class="bi bi-shop-window"></i> <strong>${Office.escapeHtml(store?.name || "")}</strong> · ${attr(reportPeriodLabel())} · ${countLabel}${filterLabel}</p>`;
  html += `<table class="data apologistic-table${canSubmitErgani ? " apologistic-table--ergani" : ""}${showDateColumn ? " apologistic-table--all-days" : ""}"><thead><tr>${showDateColumn ? "<th>Ημέρα</th>" : ""}<th>Εργαζόμενος</th><th>Κατάσταση</th><th>Δηλωμένο</th><th>Χτύπημα</th><th>Δηλωμένες ώρες</th><th>Πραγματικές ώρες</th><th>Διαφ. έναρξης</th><th>Διαφ. λήξης</th><th>Μικτή διαφορά</th><th>Διάλ. εκτός</th><th>Καθαρή διαφορά</th><th class="apologistic-overtime-head">Υπερωρίες</th><th>Πρόταση</th><th>Αποτέλεσμα</th>${erganiHeader}</tr></thead><tbody>`;
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
      (showDateColumn ? `<td title="${attr(row.work_date || "")}">${attr(String(row.work_date || "").slice(0, 5))}</td>` : "") +
      `<td title="${attr(`ΑΦΜ: ${row.employee_afm} · Κλικ για στοιχεία σύμβασης · Πέρασμα για εβδομαδιαίο ιστορικό`)}">` +
      `<div class="apologistic-employee-wrap" data-employee-afm="${attr(row.employee_afm)}" data-work-date="${attr(row.work_date)}">` +
      `<button type="button" class="apologistic-employee-btn" data-employee-afm="${attr(row.employee_afm)}">${attr(`${row.eponymo || ""} ${row.onoma || ""}`.trim())}</button>` +
      ((row.incoming_rest_obligations || []).length
        ? `<span class="apologistic-rest-due" title="${attr((row.incoming_rest_obligations || []).map((item) => `Οφείλεται ρεπό από Κυριακή ${item.source_work_date} · ${mins(item.source_actual_minutes)} εργασία`).join(" · "))}"><i class="bi bi-calendar2-check" aria-hidden="true"></i> Οφείλεται ρεπό</span>`
        : "") +
      `</div></td>` +
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
      `<td class="apologistic-result-cell" title="${attr(statusLabel(row.status))}"><span class="status-badge apologistic-status--${row.status}">${statusShortLabel(row.status)}</span>` +
      `<button type="button" class="apologistic-info-btn" data-explanation-id="${attr(explanationId)}" aria-expanded="false" aria-label="Λεπτομέρειες αποτελέσματος"><i class="bi bi-info-circle" aria-hidden="true"></i></button></td>` +
      (canSubmitErgani ? `<td class="apologistic-ergani-cell">${renderErganiActions(row)}</td>` : "") +
      `</tr>`;
    if ((row.exchange_options || []).length) {
      html += `<tr class="apologistic-replacement-row"><td colspan="${(canSubmitErgani ? 15 : 14) + (showDateColumn ? 1 : 0)}"><div class="apologistic-replacement-options">` +
        `<span class="apologistic-exchange-title"><i class="bi bi-arrow-left-right" aria-hidden="true"></i> Επιλογές ανταλλαγής</span>` +
        row.exchange_options.map((item) => `<div class="apologistic-exchange-card">` +
          `<div class="apologistic-exchange-side apologistic-exchange-side--source"><small>Ωράριο χωρίς χτύπημα</small><strong>${attr(item.replacement_work_date)}</strong><span>${attr(item.replacement_declared)}</span></div>` +
          `<div class="apologistic-exchange-arrow"><i class="bi bi-arrow-left-right" aria-hidden="true"></i><small>${mins(item.contract_duration_minutes)}</small></div>` +
          `<div class="apologistic-exchange-side apologistic-exchange-side--target"><small>Χτύπημα σε ${attr(row.day_state)}</small><strong>${attr(item.rest_work_date)}</strong><span>${attr(item.rest_punch)} → <b>${attr(item.proposed)}</b></span></div>` +
        `</div>`).join("") +
        `</div></td></tr>`;
    }
  }
  wrap.innerHTML = html + `</tbody></table>`;
  bindProposalHistoryOverlays();
  bindEmployeeWeekOverlays();
  if (openExplanationId) {
    const modal = document.getElementById("apologisticInfoModal");
    if (findExplanationRow(openExplanationId) && modal && !modal.classList.contains("hidden")) {
      openExplanation(openExplanationId);
    } else {
      closeExplanation();
    }
  }
}
