let reportDatePicker = null;
let leaveTypes = [];
let leaveModalRow = null;

document.addEventListener("DOMContentLoaded", () => {
  Office.setActiveNav("home");
  reportDatePicker = Office.createDatePicker({
    mountId: "homeDatePicker",
    mode: "single",
    quickPresets: ["today", "yesterday"],
    onApply: () => loadCardReport(),
  });
  document.getElementById("btnRefreshReport").onclick = () => loadCardReport();
  initLeaveModal();
  loadLeaveTypes();
  loadCardReport();
});

function reportDate() {
  const r = reportDatePicker ? reportDatePicker.getRange() : { start: "" };
  return r.start || "";
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
  const ref = reportDate();
  const leaveType = document.getElementById("leaveTypeValue")?.value || "";
  const comments = document.getElementById("leaveComments")?.value?.trim() || null;
  if (!ref || !leaveType) {
    Office.showMsg("leaveModalMsg", "Επιλέξτε ημερομηνία και τύπο άδειας.", false);
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
  const date = reportDate();
  if (!date) {
    return;
  }

  Office.showTableLoading(wrap, "Φόρτωση αναφοράς…");
  sumEl.innerHTML = "";
  meta.textContent = "";

  try {
    const activeRes = await fetch("/api/store/active");
    const activeData = await activeRes.json();
    if (!activeData.store) {
      wrap.innerHTML =
        `<p style="color:var(--muted);">${Office.icon("info-circle")}<span style="margin-left:0.35rem;">Επιλέξτε ενεργό κατάστημα από το sidebar για την αναφορά.</span></p>`;
      return;
    }
    await Office.loadActiveStore();

    const res = await fetch(`/api/dashboard/card-report?date=${encodeURIComponent(date)}`);
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
    renderTable(wrap, sortReportRows(data.rows || []), data.meta || {});
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
  return [...rows].sort((a, b) => {
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
  const a = (block.hour_from || "").trim() || "—";
  const b = (block.hour_to || "").trim() || "—";
  if (a === "—" && b === "—") return (block.shift_type || "").trim() || "—";
  return `${a} – ${b}`;
}

function fmtCard(card) {
  if (!card) return "—";
  const parts = [];
  if (card.has_check_in) parts.push(`Είσοδος ${card.check_in || "✓"}`);
  if (card.has_check_out) parts.push(`Έξοδος ${card.check_out || "✓"}`);
  return parts.length ? parts.join(" · ") : "—";
}

function buildActionCell(r) {
  const notes =
    (r.notes || []).length > 0
      ? `<ul class="report-notes">${r.notes
          .map((n) => `<li>${Office.escapeHtml(n)}</li>`)
          .join("")}</ul>`
      : "";
  let html = Office.escapeHtml(r.action || "—") + notes;
  if (r.leave_eligible) {
    html +=
      `<div><button type="button" class="btn btn-secondary btn-leave" data-leave-afm="${Office.escapeHtml(r.employee_afm || "")}">` +
      `${Office.icon("calendar-x")}<span>Άδεια</span></button></div>`;
  }
  return html;
}

function renderTable(wrap, rows, meta) {
  if (!meta.has_schedule && !meta.has_work_log) {
    wrap.innerHTML =
      `<p style="color:var(--muted);">${Office.icon("clipboard-data")}<span style="margin-left:0.35rem;">Δεν υπάρχουν δεδομένα για την ημέρα. Συγχρονίστε πρώτα το ψηφιακό ωράριο και την πραγματική απασχόληση.</span></p>`;
    return;
  }
  if (!rows.length) {
    wrap.innerHTML =
      `<p style="color:var(--muted);">Δεν βρέθηκαν εγγραφές εργαζομένων για την ημέρα.</p>`;
    return;
  }

  const t = document.createElement("table");
  t.className = "data report-table";
  const hr = document.createElement("tr");
  [
    "Κατάσταση",
    "ΑΦΜ",
    "Επώνυμο",
    "Όνομα",
    "Ευελ. (λεπτά)",
    "Ψηφ. ωράριο",
    "Πραγματική",
    "Δηλώσεις κάρτας",
    "Τι να γίνει",
  ].forEach((h) => {
    const th = document.createElement("th");
    th.textContent = h;
    hr.appendChild(th);
  });
  t.appendChild(hr);

  const rowByAfm = new Map(rows.map((r) => [r.employee_afm, r]));

  rows.forEach((r) => {
    const tr = document.createElement("tr");
    const badge = document.createElement("span");
    badge.className = `status-badge ${statusClass(r.status)}`;
    badge.textContent = r.status_label || r.status || "";

    const cells = [
      badge.outerHTML,
      r.employee_afm || "",
      r.eponymo || "",
      r.onoma || "",
      Office.formatFlexMinutes(r.flex_arrival_minutes),
      fmtHours(r.schedule),
      fmtHours(r.work_log),
      fmtCard(r.card),
      buildActionCell(r),
    ];
    const colClass = ["", "col-afm", "col-name", "col-name", "col-flex", "", "", "", "col-action"];
    cells.forEach((html, i) => {
      const td = document.createElement("td");
      if (colClass[i]) td.className = colClass[i];
      if (i === 0 || i === 8) td.innerHTML = html;
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
      const row = rowByAfm.get(afm);
      if (row) openLeaveModal(row);
    });
  });
}
