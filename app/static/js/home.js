let reportDatePicker = null;
let leaveTypes = [];
let leaveModalRow = null;
let wtoDailyModalRow = null;

document.addEventListener("DOMContentLoaded", () => {
  Office.setActiveNav("home");
  reportDatePicker = Office.createDatePicker({
    mountId: "homeDatePicker",
    mode: "range",
    autoApply: true,
    onApply: () => loadCardReport(),
    quickPresets: ["yesterday", "today", "tomorrow", "dayAfterTomorrow"],
    quickLabels: {
      tomorrow: "Αύριο",
      dayAfterTomorrow: "Μεθαύριο",
    },
  });
  document.getElementById("btnRefreshReport").onclick = () => loadCardReport();
  initLeaveModal();
  initWtoDailyModal();
  loadLeaveTypes();
  loadCardReport();
});

function reportRange() {
  return reportDatePicker ? reportDatePicker.getRange() : { start: "", end: "" };
}

function reportDate() {
  return reportRange().start || "";
}

function reportQueryString() {
  const { start, end } = reportRange();
  if (!start) return "";
  if (!end || start === end) return `date=${encodeURIComponent(start)}`;
  return `from=${encodeURIComponent(start)}&to=${encodeURIComponent(end)}`;
}

function isMultiDayReport(data) {
  const dates = data?.work_dates;
  return Array.isArray(dates) && dates.length > 1;
}

function leaveTypeLabel(type) {
  if (!type) return "—";
  return `${type.code} — ${type.label}`;
}

function renderLeaveTypeList() {
  const list = document.getElementById("leaveTypeList");
  if (!list) return;
  list.innerHTML = leaveTypes
    .map(
      (t) =>
        `<li role="option" data-code="${Office.escapeHtml(t.code)}" tabindex="-1">` +
        `<span class="leave-type-code">${Office.escapeHtml(t.code)}</span>` +
        `<span>${Office.escapeHtml(t.label)}</span></li>`
    )
    .join("");
  list.querySelectorAll("li").forEach((li) => {
    li.addEventListener("click", () => selectLeaveType(li.dataset.code || ""));
  });
}

function setLeaveTypeOpen(open) {
  const list = document.getElementById("leaveTypeList");
  const trigger = document.getElementById("leaveTypeTrigger");
  if (!list || !trigger) return;
  list.classList.toggle("show", open);
  trigger.setAttribute("aria-expanded", open ? "true" : "false");
}

function selectLeaveType(code) {
  const hidden = document.getElementById("leaveTypeValue");
  const trigger = document.getElementById("leaveTypeTrigger");
  const list = document.getElementById("leaveTypeList");
  const type = leaveTypes.find((t) => t.code === code) || leaveTypes[0];
  if (!hidden || !trigger || !type) return;
  hidden.value = type.code;
  trigger.textContent = leaveTypeLabel(type);
  list?.querySelectorAll("li").forEach((li) => {
    li.classList.toggle("selected", li.dataset.code === type.code);
  });
  setLeaveTypeOpen(false);
}

async function loadLeaveTypes() {
  try {
    const res = await fetch("/api/leave/types");
    const data = await res.json();
    leaveTypes = data.types || [];
    renderLeaveTypeList();
    if (leaveTypes.length) selectLeaveType(leaveTypes[0].code);
  } catch {
    leaveTypes = [];
  }
}

function initLeaveModal() {
  const modal = document.getElementById("leaveModal");
  if (!modal) return;
  modal.querySelectorAll("[data-leave-close]").forEach((el) => {
    el.addEventListener("click", closeLeaveModal);
  });
  document.getElementById("btnLeaveCancel")?.addEventListener("click", closeLeaveModal);
  document.getElementById("btnLeaveSubmit")?.addEventListener("click", submitLeave);
  document.getElementById("leaveTypeTrigger")?.addEventListener("click", (e) => {
    e.stopPropagation();
    const list = document.getElementById("leaveTypeList");
    setLeaveTypeOpen(!list?.classList.contains("show"));
  });
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".leave-type-picker")) setLeaveTypeOpen(false);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (modal.classList.contains("hidden")) return;
    const list = document.getElementById("leaveTypeList");
    if (list?.classList.contains("show")) {
      e.preventDefault();
      setLeaveTypeOpen(false);
      return;
    }
    e.preventDefault();
    closeLeaveModal();
  });
}

function initWtoDailyModal() {
  const modal = document.getElementById("wtoDailyModal");
  if (!modal) return;
  document.getElementById("btnWtoDailyAddInterval")?.addEventListener("click", () => {
    addWtoDailyIntervalRow({ hour_from: "", hour_to: "" });
  });
  modal.querySelectorAll("[data-wto-daily-close]").forEach((el) => {
    el.addEventListener("click", closeWtoDailyModal);
  });
  document.getElementById("btnWtoDailyCancel")?.addEventListener("click", closeWtoDailyModal);
  document.getElementById("btnWtoDailySubmit")?.addEventListener("click", submitWtoDaily);
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (modal.classList.contains("hidden")) return;
    e.preventDefault();
    closeWtoDailyModal();
  });
}

function hmToTimeInput(hm) {
  return Office.normalizeHourMinute(hm);
}

function timeInputToHm(value) {
  return Office.normalizeHourMinute(value);
}

function normalizeScheduleIntervals(value) {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => ({
      hour_from: hmToTimeInput(item?.hour_from || ""),
      hour_to: hmToTimeInput(item?.hour_to || ""),
    }))
    .filter((item) => item.hour_from || item.hour_to);
}

function wtoDailyProposalForRow(row) {
  const proposal = row.wto_daily || {};
  if (proposal.hour_from || proposal.hour_to || proposal.note || proposal.schedule_type) {
    if (!proposal.intervals) {
      proposal.intervals = normalizeScheduleIntervals([
        { hour_from: proposal.hour_from, hour_to: proposal.hour_to },
      ]);
    }
    return proposal;
  }
  const sched = row.schedule || {};
  const intervals = normalizeScheduleIntervals(sched.intervals);
  return {
    schedule_type: "ΕΡΓ",
    hour_from: intervals[0]?.hour_from || sched.hour_from || "",
    hour_to: intervals[intervals.length - 1]?.hour_to || sched.hour_to || "",
    intervals: intervals.length
      ? intervals
      : normalizeScheduleIntervals([{ hour_from: sched.hour_from, hour_to: sched.hour_to }]),
    note: "Τρέχον ψηφιακό ωράριο για την ημέρα.",
  };
}

function addWtoDailyIntervalRow(interval = {}) {
  const wrap = document.getElementById("wtoDailyIntervals");
  if (!wrap) return;
  const row = document.createElement("div");
  row.className = "wto-daily-hours-row";
  row.innerHTML =
    `<div><label class="field-label">Ώρα από</label>` +
    `<input type="text" class="field-input input-time-24 wto-daily-hour-from" inputmode="numeric" placeholder="09:30" maxlength="5" autocomplete="off"></div>` +
    `<div><label class="field-label">Ώρα έως</label>` +
    `<input type="text" class="field-input input-time-24 wto-daily-hour-to" inputmode="numeric" placeholder="17:00" maxlength="5" autocomplete="off"></div>` +
    `<button type="button" class="btn btn-secondary wto-daily-interval-remove" title="Αφαίρεση διαστήματος" aria-label="Αφαίρεση διαστήματος">` +
    `${Office.icon("x-lg")}</button>`;
  wrap.appendChild(row);
  const fromEl = row.querySelector(".wto-daily-hour-from");
  const toEl = row.querySelector(".wto-daily-hour-to");
  if (fromEl) fromEl.value = hmToTimeInput(interval.hour_from);
  if (toEl) toEl.value = hmToTimeInput(interval.hour_to);
  row.querySelector(".wto-daily-interval-remove")?.addEventListener("click", () => {
    if (wrap.querySelectorAll(".wto-daily-hours-row").length <= 1) {
      if (fromEl) fromEl.value = "";
      if (toEl) toEl.value = "";
      return;
    }
    row.remove();
  });
  Office.bindHourMinuteElement(fromEl);
  Office.bindHourMinuteElement(toEl);
}

function setWtoDailyIntervals(intervals, isRest) {
  const wrap = document.getElementById("wtoDailyIntervals");
  if (!wrap) return;
  wrap.innerHTML = "";
  if (isRest) return;
  const rows = normalizeScheduleIntervals(intervals).length
    ? normalizeScheduleIntervals(intervals)
    : [{ hour_from: "", hour_to: "" }];
  rows.forEach((item) => addWtoDailyIntervalRow(item));
}

function collectWtoDailyIntervals() {
  return [...document.querySelectorAll("#wtoDailyIntervals .wto-daily-hours-row")]
    .map((row) => ({
      hour_from: timeInputToHm(row.querySelector(".wto-daily-hour-from")?.value),
      hour_to: timeInputToHm(row.querySelector(".wto-daily-hour-to")?.value),
    }))
    .filter((item) => item.hour_from || item.hour_to);
}

function openWtoDailyModal(row, opts = {}) {
  wtoDailyModalRow = { ...row, _wtoRestMode: opts.mode === "rest" };
  const modal = document.getElementById("wtoDailyModal");
  const title = document.getElementById("wtoDailyModalTitle");
  const sub = document.getElementById("wtoDailyModalEmployee");
  const hint = document.getElementById("wtoDailyModalHint");
  const msg = document.getElementById("wtoDailyModalMsg");
  const proposal = wtoDailyProposalForRow(row);
  const isRest = opts.mode === "rest";
  if (!modal || !sub) return;
  sub.textContent =
    `${row.eponymo || ""} ${row.onoma || ""}`.trim() + ` · ΑΦΜ ${row.employee_afm || ""}`;
  if (title) {
    title.textContent = isRest
      ? "Δήλωση ρεπό (WTODaily)"
      : "Τροποποίηση ωραρίου (WTODaily)";
  }
  if (hint) {
    hint.textContent = isRest
      ? "Δήλωση ρεπό/ανάπαυσης (τύπος ΑΝ) για την ημέρα."
      : proposal.note || row.action || "";
  }
  const hoursRow = document.getElementById("wtoDailyHoursRow");
  if (hoursRow) hoursRow.classList.toggle("hidden", isRest);
  const typeEl = document.getElementById("wtoDailyScheduleType");
  setWtoDailyIntervals(proposal.intervals, isRest);
  if (typeEl) typeEl.value = isRest ? "ΑΝ" : proposal.schedule_type || "ΕΡΓ";
  const comments = document.getElementById("wtoDailyComments");
  if (comments) comments.value = "";
  if (msg) {
    msg.className = "msg";
    msg.textContent = "";
  }
  modal.classList.remove("hidden");
}

function openWtoRestModal(row) {
  openWtoDailyModal(row, { mode: "rest" });
}

function closeWtoDailyModal() {
  const modal = document.getElementById("wtoDailyModal");
  const title = document.getElementById("wtoDailyModalTitle");
  const hoursRow = document.getElementById("wtoDailyHoursRow");
  if (title) title.textContent = "Τροποποίηση ωραρίου (WTODaily)";
  if (hoursRow) hoursRow.classList.remove("hidden");
  modal?.classList.add("hidden");
  wtoDailyModalRow = null;
}

async function submitWtoDaily() {
  if (!wtoDailyModalRow) return;
  const btn = document.getElementById("btnWtoDailySubmit");
  const ref =
    Office.parseDateGr(wtoDailyModalRow.work_date || "") || reportDate();
  const scheduleType = document.getElementById("wtoDailyScheduleType")?.value || "ΕΡΓ";
  const comments = document.getElementById("wtoDailyComments")?.value?.trim() || null;
  const isRest =
    Boolean(wtoDailyModalRow._wtoRestMode) || scheduleType === "ΑΝ" || scheduleType === "AN";
  const intervals = isRest ? [] : collectWtoDailyIntervals();
  const incomplete = intervals.some((item) => !item.hour_from || !item.hour_to);
  if (!ref || (!intervals.length && !isRest) || incomplete) {
    Office.showMsg(
      "wtoDailyModalMsg",
      isRest
        ? "Συμπληρώστε ημερομηνία."
        : "Συμπληρώστε ημερομηνία και ώρα από/έως για κάθε διάστημα.",
      false
    );
    return;
  }
  Office.setButtonLoading(btn, true);
  Office.showLoading("wtoDailyModalMsg", "Αποστολή WTODaily στο Ergani…");
  try {
    const res = await fetch("/api/wto-daily/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        employee_afm: wtoDailyModalRow.employee_afm,
        eponymo: wtoDailyModalRow.eponymo,
        onoma: wtoDailyModalRow.onoma,
        reference_date: ref,
        schedule_type: scheduleType,
        hour_from: isRest ? null : intervals[0].hour_from,
        hour_to: isRest ? null : intervals[intervals.length - 1].hour_to,
        intervals: isRest ? null : intervals,
        comments,
        kind: wtoDailyModalRow.wto_daily?.kind || null,
      }),
    });
    const data = await Office.parseJson(res);
    if (!res.ok || !data.success) {
      Office.showMsg(
        "wtoDailyModalMsg",
        data.error || data.data?.message || data.data?.Message || "Αποτυχία υποβολής",
        false
      );
      return;
    }
    closeWtoDailyModal();
    const proto = data.protocol ? ` · ${data.protocol}` : "";
    Office.showMsg(
      "wtoDailyMsg",
      `Ωράριο υποβλήθηκε επιτυχώς${proto}. Η τοπική εικόνα ενημερώθηκε.`,
      true
    );
    await loadCardReport();
  } catch (e) {
    Office.showMsg("wtoDailyModalMsg", String(e), false);
  } finally {
    Office.setButtonLoading(btn, false);
  }
}

function openLeaveModal(row) {
  leaveModalRow = row;
  const modal = document.getElementById("leaveModal");
  const sub = document.getElementById("leaveModalEmployee");
  const msg = document.getElementById("leaveModalMsg");
  if (!modal || !sub) return;
  sub.textContent = `${row.eponymo || ""} ${row.onoma || ""}`.trim() + ` · ΑΦΜ ${row.employee_afm || ""}`;
  const comments = document.getElementById("leaveComments");
  if (comments) comments.value = "";
  if (msg) {
    msg.className = "msg";
    msg.textContent = "";
  }
  if (leaveTypes.length) selectLeaveType(leaveTypes[0].code);
  setLeaveTypeOpen(false);
  modal.classList.remove("hidden");
}

function closeLeaveModal() {
  setLeaveTypeOpen(false);
  document.getElementById("leaveModal")?.classList.add("hidden");
  leaveModalRow = null;
}

async function submitLeave() {
  if (!leaveModalRow) return;
  const btn = document.getElementById("btnLeaveSubmit");
  const ref =
    Office.parseDateGr(leaveModalRow.work_date || "") || reportDate();
  const leaveType = document.getElementById("leaveTypeValue")?.value || "";
  const comments = document.getElementById("leaveComments")?.value?.trim() || null;
  if (!ref || !leaveType) {
    Office.showMsg("leaveModalMsg", "Επιλέξτε περίοδο και τύπο άδειας.", false);
    return;
  }
  Office.setButtonLoading(btn, true);
  Office.showLoading("leaveModalMsg", "Αποστολή WTOLeave στο Ergani…");
  try {
    const res = await fetch("/api/leave/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        employee_afm: leaveModalRow.employee_afm,
        eponymo: leaveModalRow.eponymo,
        onoma: leaveModalRow.onoma,
        reference_date: ref,
        leave_type: leaveType,
        comments,
      }),
    });
    const data = await Office.parseJson(res);
    if (!res.ok || !data.success) {
      Office.showMsg(
        "leaveModalMsg",
        data.error || data.data?.message || data.data?.Message || "Αποτυχία υποβολής",
        false
      );
      return;
    }
    closeLeaveModal();
    const proto = data.protocol ? ` · ${data.protocol}` : "";
    Office.showMsg("leaveMsg", `Άδεια υποβλήθηκε επιτυχώς${proto}`, true);
    await loadCardReport();
  } catch (e) {
    Office.showMsg("leaveModalMsg", String(e), false);
  } finally {
    Office.setButtonLoading(btn, false);
  }
}

async function loadCardReport() {
  const wrap = document.getElementById("cardReportWrap");
  const meta = document.getElementById("cardReportMeta");
  const sumEl = document.getElementById("cardReportSummary");
  const qs = reportQueryString();
  if (!qs) {
    return;
  }

  Office.showTableLoading(wrap, "Φόρτωση αναφοράς…");
  sumEl.innerHTML = "";
  meta.textContent = "";

  try {
    const activeRes = await fetch("/api/store/active");
    let activeData = {};
    try {
      activeData = await activeRes.json();
    } catch {
      throw new Error(`Σφάλμα διακομιστή (HTTP ${activeRes.status}). Δοκιμάστε επανεκκίνηση του site.`);
    }
    if (!activeRes.ok) {
      throw new Error(activeData.error || `HTTP ${activeRes.status}`);
    }
    if (!activeData.store) {
      const syncMeta = document.getElementById("homeWorkLogSyncMeta");
      if (syncMeta) syncMeta.innerHTML = "";
      wrap.innerHTML =
        `<p style="color:var(--muted);">${Office.icon("info-circle")}<span style="margin-left:0.35rem;">Επιλέξτε ενεργό κατάστημα από το sidebar για την αναφορά.</span></p>`;
      return;
    }
    await Office.loadActiveStore();
    await Office.refreshActiveStoreSyncMeta("homeWorkLogSyncMeta", "worklog");

    const res = await fetch(`/api/dashboard/card-report?${qs}`);
    let data = {};
    try {
      data = await res.json();
    } catch {
      wrap.innerHTML = `<p style="color:var(--err);">Σφάλμα διακομιστή (HTTP ${res.status}).</p>`;
      return;
    }
    if (!res.ok) {
      wrap.innerHTML = `<p style="color:var(--err);">${Office.escapeHtml(data.error || "Σφάλμα")}</p>`;
      return;
    }

    renderSummary(sumEl, data.summary || {}, data.meta || {}, data.store, data.work_date);
    renderTable(
      wrap,
      sortReportRows(data.rows || []),
      data.meta || {},
      isMultiDayReport(data)
    );
  } catch (e) {
    wrap.innerHTML = `<p style="color:var(--err);">${Office.escapeHtml(String(e))}</p>`;
  }
}

function renderSummary(el, summary, meta, store, workDate) {
  if (!el) return;
  const chips = [
    { key: "needs_checkin", label: "Είσοδος", cls: "status-warn" },
    { key: "needs_checkout", label: "Έξοδος", cls: "status-warn" },
    { key: "at_work", label: "Σε εργασία", cls: "status-info" },
    { key: "late_arrival", label: "Καθυστέρηση", cls: "status-err" },
    { key: "completed", label: "Ολοκληρωμένοι", cls: "status-ok" },
    { key: "rest", label: "Ρεπό/ανάπαυση", cls: "status-muted" },
    { key: "absent", label: "Χωρίς άφιξη", cls: "status-err" },
  ];
  const parts = chips
    .filter((c) => (summary[c.key] || 0) > 0)
    .map(
      (c) =>
        `<span class="report-chip ${c.cls}">${Office.escapeHtml(c.label)}: <strong>${summary[c.key]}</strong></span>`
    );
  const storeLine = store
    ? `<span class="report-meta-line">${Office.icon("shop-window")} <strong>${Office.escapeHtml(store.name)}</strong> · ${Office.escapeHtml(workDate || "")}</span>`
    : "";
  const dataLine = meta.has_schedule || meta.has_work_log
    ? `<span class="report-meta-line">${Office.icon("database")} Ωράριο: ${meta.schedule_count || 0} · Πραγματική: ${meta.work_log_count || 0} · Δηλώσεις κάρτας: ${meta.card_event_count || 0}</span>`
    : `<span class="report-meta-line" style="color:var(--err);">${Office.icon("exclamation-triangle")} Δεν υπάρχουν συγχρονισμένα δεδομένα — συγχρονίστε <a href="/ui/schedule">ωράριο</a> και <a href="/ui/work-log">πραγματική απασχόληση</a>.</span>`;
  el.innerHTML = `${storeLine}${dataLine}<div class="report-chips">${parts.join("")}</div>`;
}

function statusClass(status) {
  const map = {
    needs_checkin: "status-warn",
    needs_checkout: "status-warn",
    at_work: "status-info",
    late_arrival: "status-err",
    absent: "status-err",
    completed: "status-ok",
    rest: "status-muted",
    pending: "status-muted",
    unscheduled_work: "status-warn",
    no_schedule: "status-muted",
  };
  return map[status] || "status-muted";
}

const REPORT_STATUS_ORDER = {
  at_work: 0,
  needs_checkout: 1,
  completed: 2,
  late_arrival: 3,
  needs_checkin: 4,
  unscheduled_work: 5,
  absent: 6,
  pending: 7,
  no_schedule: 8,
  rest: 9,
};

function scheduleShowsBlank(schedule) {
  if (!schedule) return true;
  const hf = (schedule.hour_from || "").trim();
  const ht = (schedule.hour_to || "").trim();
  if (hf || ht) return false;
  return !(schedule.shift_type || "").trim();
}

function sortReportRows(rows) {
  const dayKey = (s) => Office.parseDateGr(s || "") || s || "";
  return [...rows].sort((a, b) => {
    const da = dayKey(a.work_date);
    const db = dayKey(b.work_date);
    if (da && db && da !== db) return da.localeCompare(db);
    const blankA = scheduleShowsBlank(a.schedule) ? 1 : 0;
    const blankB = scheduleShowsBlank(b.schedule) ? 1 : 0;
    if (blankA !== blankB) return blankA - blankB;
    const stA = REPORT_STATUS_ORDER[a.status] ?? 99;
    const stB = REPORT_STATUS_ORDER[b.status] ?? 99;
    if (stA !== stB) return stA - stB;
    const epA = (a.eponymo || "").toUpperCase();
    const epB = (b.eponymo || "").toUpperCase();
    if (epA !== epB) return epA.localeCompare(epB, "el");
    return (a.employee_afm || "").localeCompare(b.employee_afm || "", "el");
  });
}

function fmtHours(block) {
  if (!block) return "—";
  const intervals = normalizeScheduleIntervals(block.intervals);
  if (intervals.length > 1) {
    return intervals.map((item) => `${item.hour_from || "—"} – ${item.hour_to || "—"}`).join(" / ");
  }
  const a = (block.hour_from || "").trim() || "—";
  const b = (block.hour_to || "").trim() || "—";
  if (a === "—" && b === "—") return (block.shift_type || "").trim() || "—";
  return `${a} – ${b}`;
}

function fmtHoursPart(value, title) {
  if ((value || "").trim()) return Office.escapeHtml(value.trim());
  return (
    `<span class="report-missing-time" title="${Office.escapeHtml(title)}">` +
    `${Office.icon("clock")}</span>`
  );
}

function fmtWorkLogHtml(block) {
  if (!block) return "—";
  const hf = (block.hour_from || "").trim();
  const ht = (block.hour_to || "").trim();
  if (!hf && !ht) {
    const st = (block.shift_type || "").trim();
    return st ? Office.escapeHtml(st) : "—";
  }
  return `${fmtHoursPart(block.hour_from, "Λείπει ώρα εισόδου")} – ${fmtHoursPart(block.hour_to, "Λείπει ώρα εξόδου")}`;
}

function buildCardLinkCell(r) {
  if (!Office.shouldShowWorkCardLink(r)) return "";
  const afm = (r.employee_afm || "").trim();
  const dateIso = Office.erganiDateToIso(r.work_date) || "";
  const name = `${r.eponymo || ""} ${r.onoma || ""}`.trim();
  const opts = Office.workCardUrlOptsFromRow(r);
  const url = Office.workCardUrl(afm, dateIso, name, opts);
  const cls = opts.retro
    ? "work-log-card-link work-log-card-link--required"
    : "work-log-card-link";
  return (
    `<a href="${Office.escapeHtml(url)}" class="${cls}" ` +
    `title="Ψηφιακή κάρτα" aria-label="Ψηφιακή κάρτα — ${Office.escapeHtml(name || afm)}">` +
    `${Office.icon("credit-card-2-front")}</a>`
  );
}

function buildTodayNotifyButton(r) {
  const kind = (r.today_notify_kind || "").trim();
  if (!kind) return "";
  const snoozed = Boolean(r.today_notify_snoozed);
  const label = Office.todayNotifyLabel(kind, r.notify_grace_minutes);
  const cls =
    "work-log-notify-btn work-log-notify-btn--today" +
    (snoozed ? " work-log-notify-btn--snoozed" : "");
  const title = snoozed
    ? "Όλοι οι λήπτες σε αναβολή (snooze)"
    : `Ειδοποίηση σήμερα — ${label}`;
  return (
    `<button type="button" class="${cls}" ` +
    `data-today-notify-afm="${Office.escapeHtml(r.employee_afm || "")}" ` +
    `data-today-notify-date="${Office.escapeHtml(r.work_date || "")}" ` +
    `data-today-notify-kind="${Office.escapeHtml(kind)}" ` +
    `${snoozed ? "disabled " : ""}` +
    `title="${Office.escapeHtml(title)}" ` +
    `aria-label="${Office.escapeHtml(title)}">` +
    `${Office.icon("bell")}</button>`
  );
}

function minutesFromHm(hm) {
  const norm = Office.normalizeHourMinute(hm || "");
  if (!norm) return null;
  const [h, m] = norm.split(":").map((x) => parseInt(x, 10));
  if (!Number.isFinite(h) || !Number.isFinite(m)) return null;
  return h * 60 + m;
}

function rowHasWorkSignal(row) {
  return Boolean(
    row.work_log?.hour_from ||
      row.work_log?.hour_to ||
      row.card?.has_check_in ||
      row.card?.has_check_out
  );
}

function scheduleIsRestLike(schedule) {
  const shiftType = String(schedule?.shift_type || "").trim().toUpperCase();
  return Boolean(
    shiftType &&
      (/^(ΑΝ|AN|Ρ)$/.test(shiftType) ||
        /ΑΝΑΠΑΥΣ|ΡΕΠΟ|REPO|ΜΗ\s*ΕΡΓΑΣΙΑ|ΑΔΕΙΑ|ΑΡΓΙΑ/.test(shiftType))
  );
}

function rowWorkDateIso(row) {
  return (
    Office.workDateToIso?.(row.work_date) ||
    Office.parseDateGr(row.work_date || "") ||
    String(row.work_date || "").slice(0, 10)
  );
}

function isEditableWorkDate(row) {
  const workDate = rowWorkDateIso(row);
  return Boolean(workDate && workDate >= Office.todayIsoLocal());
}

function restDayAlwaysShowActions(row) {
  // Ρεπό αλλά έχει ήδη χτύπημα/πραγματική → μόνο έξοδος, όχι αλλαγή/ρεπό/άδεια.
  if (rowHasWorkSignal(row)) return false;
  return Boolean(
    row.rest_day_actions_always ||
      (isEditableWorkDate(row) && scheduleIsRestLike(row.schedule))
  );
}

function canDeclareRestBeforeShift(row) {
  const workDate = rowWorkDateIso(row);
  if (!workDate) return false;
  if (workDate < Office.todayIsoLocal()) return false;
  if (rowHasWorkSignal(row)) return false;
  const sched = row.schedule || {};
  if (scheduleIsRestLike(sched)) return false;
  const startMin = minutesFromHm(sched.hour_from);
  if (startMin == null) return false;
  if (workDate > Office.todayIsoLocal()) return true;
  const now = new Date();
  const nowMin = now.getHours() * 60 + now.getMinutes();
  return nowMin < startMin;
}

function canChangeScheduleBeforeShift(row) {
  return canDeclareRestBeforeShift(row);
}

function buildActionCell(r) {
  const notes =
    (r.notes || []).length > 0
      ? `<ul class="report-notes">${r.notes
          .map((n) => `<li>${Office.escapeHtml(n)}</li>`)
          .join("")}</ul>`
      : "";
  let html = Office.escapeHtml(r.action || "—") + notes;
  const notifyBase = String(r.today_notify_kind || "").trim().split("@", 1)[0];
  if (notifyBase === "exit_needs_correction") {
    const notifyRow = {
      ...r,
      hour_from: r.work_log?.hour_from || r.hour_from || "",
      hour_to: r.work_log?.hour_to || r.hour_to || "",
    };
    const entry = Office.escapeHtml(notifyRow.hour_from || "—");
    const wrongExit = Office.escapeHtml(notifyRow.hour_to || "—");
    const expectedExit = Office.escapeHtml(
      Office.expectedExitTimeForRow(notifyRow) || "—"
    );
    html =
      `<div class="report-correction-box">` +
      `<div class="report-correction-title">${Office.icon("exclamation-triangle")} Χρειάζεται διόρθωση εξόδου</div>` +
      `<div class="report-correction-body">Υπάρχει έξοδος <strong>${wrongExit}</strong> πριν από την είσοδο <strong>${entry}</strong>. ` +
      `Στείλτε διορθωτική έξοδο περίπου στις <strong>${expectedExit}</strong> (είσοδος + διάρκεια ωραρίου).</div>` +
      `</div>` +
      html;
  }
  const restDayAlways = restDayAlwaysShowActions(r);
  const beforeShift = canDeclareRestBeforeShift(r);
  const wtoKind = String(r.wto_daily?.kind || "");
  // Χωρίς ωράριο (κενή/ανύπαρκτη εγγραφή): κουμπί WTODaily χωρίς απαίτηση «πριν την έναρξη».
  const noScheduleChange =
    Boolean(r.wto_daily_eligible) &&
    (r.status === "no_schedule" || wtoKind === "no_schedule") &&
    isEditableWorkDate(r) &&
    !rowHasWorkSignal(r);
  const scheduleChangeEligible =
    restDayAlways ||
    noScheduleChange ||
    (r.wto_daily_eligible && beforeShift) ||
    canChangeScheduleBeforeShift(r);
  if (scheduleChangeEligible) {
    html +=
      `<div><button type="button" class="btn btn-secondary btn-wto-daily" data-wto-daily-afm="${Office.escapeHtml(r.employee_afm || "")}" data-wto-daily-date="${Office.escapeHtml(r.work_date || "")}">` +
      `${Office.icon("calendar-week")}<span>Αλλαγή ωραρίου</span></button></div>`;
  }
  const restEligible = restDayAlways || beforeShift;
  const leaveEligible = restDayAlways || (beforeShift && Boolean(r.leave_eligible));
  if (restEligible || leaveEligible || r.today_notify_kind) {
    html += `<div class="report-action-btns">`;
    html += buildTodayNotifyButton(r);
    if (restEligible) {
      html +=
        `<button type="button" class="btn btn-secondary btn-rest" data-wto-rest-afm="${Office.escapeHtml(r.employee_afm || "")}" data-wto-rest-date="${Office.escapeHtml(r.work_date || "")}">` +
        `${Office.icon("calendar-minus")}<span>Ρεπό</span></button>`;
    }
    if (leaveEligible) {
      html +=
        `<button type="button" class="btn btn-secondary btn-leave" data-leave-afm="${Office.escapeHtml(r.employee_afm || "")}" data-leave-date="${Office.escapeHtml(r.work_date || "")}">` +
        `${Office.icon("calendar-x")}<span>Άδεια</span></button>`;
    }
    html += `</div>`;
  }
  return html;
}

function renderTable(wrap, rows, meta, multiDay) {
  if (!meta.has_schedule && !meta.has_work_log) {
    wrap.innerHTML =
      `<p style="color:var(--muted);">${Office.icon("clipboard-data")}<span style="margin-left:0.35rem;">Δεν υπάρχουν δεδομένα για την περίοδο. Συγχρονίστε πρώτα το ψηφιακό ωράριο και την πραγματική απασχόληση.</span></p>`;
    return;
  }
  if (!rows.length) {
    wrap.innerHTML =
      `<p style="color:var(--muted);">Δεν βρέθηκαν εγγραφές εργαζομένων για την περίοδο.</p>`;
    return;
  }

  const t = document.createElement("table");
  t.className = "data report-table";
  const hr = document.createElement("tr");
  const headers = [
    "Κατάσταση",
    "Επώνυμο",
    "Όνομα",
  ];
  if (multiDay) headers.push("Ημερομηνία");
  headers.push(
    "Ευελ. (λεπτά)",
    "Ψηφ. ωράριο",
    "Πραγματική",
    "Κάρτα",
    "Τι να γίνει"
  );
  headers.forEach((h) => {
    const th = document.createElement("th");
    th.textContent = h;
    hr.appendChild(th);
  });
  t.appendChild(hr);

  const rowByKey = new Map(
    rows.map((r) => [`${r.employee_afm}|${r.work_date || ""}`, r])
  );

  rows.forEach((r) => {
    const tr = document.createElement("tr");
    const badge = document.createElement("span");
    badge.className = `status-badge ${statusClass(r.status)}`;
    badge.textContent = r.status_label || r.status || "";

    const cells = [
      badge.outerHTML,
      r.eponymo || "",
      r.onoma || "",
    ];
    if (multiDay) cells.push(r.work_date || "");
    cells.push(
      Office.formatFlexMinutes(r.flex_arrival_minutes),
      fmtHours(r.schedule),
      fmtWorkLogHtml(r.work_log),
      buildCardLinkCell(r),
      buildActionCell(r)
    );
    const colClass = ["", "col-name", "col-name"];
    if (multiDay) colClass.push("");
    colClass.push("col-flex", "col-hours", "col-hours", "work-log-action-cell", "col-action");
    const htmlColumns = new Set([0, cells.length - 3, cells.length - 2, cells.length - 1]);
    cells.forEach((html, i) => {
      const td = document.createElement("td");
      if (colClass[i]) td.className = colClass[i];
      if (htmlColumns.has(i)) td.innerHTML = html;
      else td.textContent = html;
      tr.appendChild(td);
    });
    t.appendChild(tr);
  });

  wrap.innerHTML = "";
  wrap.appendChild(t);

  wrap.querySelectorAll("[data-leave-afm]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const afm = btn.getAttribute("data-leave-afm");
      const wd = btn.getAttribute("data-leave-date") || "";
      const row = rowByKey.get(`${afm}|${wd}`);
      if (row) openLeaveModal(row);
    });
  });

  wrap.querySelectorAll("[data-today-notify-afm]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (btn.disabled) return;
      const afm = btn.getAttribute("data-today-notify-afm");
      const wd = btn.getAttribute("data-today-notify-date") || "";
      const kind = btn.getAttribute("data-today-notify-kind") || "";
      const row = rowByKey.get(`${afm}|${wd}`);
      if (!row) return;
      Office.sendTodayPunchNotify(
        row,
        { kind, label: Office.todayNotifyLabel(kind, row.notify_grace_minutes) },
        btn,
        "cardReportNotifyMsg"
      );
    });
  });

  wrap.querySelectorAll("[data-wto-rest-afm]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const afm = btn.getAttribute("data-wto-rest-afm");
      const wd = btn.getAttribute("data-wto-rest-date") || "";
      const row = rowByKey.get(`${afm}|${wd}`);
      if (row) openWtoRestModal(row);
    });
  });

  wrap.querySelectorAll("[data-wto-daily-afm]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const afm = btn.getAttribute("data-wto-daily-afm");
      const wd = btn.getAttribute("data-wto-daily-date") || "";
      const row = rowByKey.get(`${afm}|${wd}`);
      if (row) openWtoDailyModal(row);
    });
  });
}
