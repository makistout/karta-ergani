let scheduleListDateIso = "";
let scheduleListDatePicker = null;
let currentRange = { start: "", end: "" };
let tableState = { rows: [], page: 1, count: 0, store: null, range: null, workDates: [] };
let initialAutoSyncDone = false;
let scheduleImportBatchId = null;
let scheduleDayFormState = { dateIso: "", rows: [], preview: null };
let scheduleDayFormDatePicker = null;

document.addEventListener("DOMContentLoaded", async () => {
  Office.setActiveNav("schedule");
  Office.initWorkLogHistoryModal();
  scheduleListDateIso = Office.todayIsoLocal();
  if (document.getElementById("scheduleListDatePicker")) {
    scheduleListDatePicker = Office.createDatePicker({
      mountId: "scheduleListDatePicker",
      mode: "single",
      autoApply: true,
      quickPresets: ["yesterday", "today", "tomorrow", "dayAfterTomorrow"],
      quickLabels: {
        tomorrow: "Αύριο",
        dayAfterTomorrow: "Μεθαύριο",
      },
      onApply: ({ start }) => {
        if (!start) return;
        scheduleListDateIso = start;
        void loadSchedule();
      },
    });
    scheduleListDatePicker.setRange(scheduleListDateIso, scheduleListDateIso);
  }
  const btnSync = document.getElementById("btnSyncSchedule");
  if (btnSync) btnSync.onclick = () => runSync();
  initScheduleImportUi();
  initScheduleTemplateDownload();
  initScheduleDayFormUi();

  const activeData = await Office.fetchActiveStore();
  Office.applyActiveStoreChrome(activeData);
  await loadSchedule(activeData);

  if (btnSync) {
    void maybeAutoSyncSchedule(activeData).then(async (synced) => {
      if (synced) {
        await loadSchedule(await Office.fetchActiveStore({ refresh: true }));
      }
    });
  }
});

function getRange() {
  const d = scheduleListDateIso || Office.todayIsoLocal();
  currentRange = { start: d, end: d };
  return currentRange;
}

function listQuery(r) {
  return `date=${encodeURIComponent(r.start)}`;
}

function scheduleHasHours(row) {
  const hf = (row.hour_from || "").trim();
  const ht = (row.hour_to || "").trim();
  return Boolean(hf || ht);
}

function erganiDateSortKey(wd) {
  const parts = (wd || "").trim().split("/");
  if (parts.length === 3) {
    const d = parseInt(parts[0], 10);
    const m = parseInt(parts[1], 10);
    let y = parseInt(parts[2], 10);
    if (y < 100) y += 2000;
    if (!Number.isNaN(d) && !Number.isNaN(m) && !Number.isNaN(y)) {
      return y * 10000 + m * 100 + d;
    }
  }
  return 99999999;
}

function sortScheduleRows(rows) {
  const shiftKey = (row) => {
    const st = (row.shift_type || "").trim().toUpperCase();
    return st ? `0:${st}` : "1:";
  };
  return [...rows].sort((a, b) => {
    const dateCmp = erganiDateSortKey(a.work_date) - erganiDateSortKey(b.work_date);
    if (dateCmp !== 0) return dateCmp;
    const ha = scheduleHasHours(a);
    const hb = scheduleHasHours(b);
    if (ha !== hb) return ha ? -1 : 1;
    if (ha) {
      const ta = (a.hour_from || "").trim() || "99:99";
      const tb = (b.hour_from || "").trim() || "99:99";
      if (ta !== tb) return ta.localeCompare(tb);
    } else {
      const cmp = shiftKey(a).localeCompare(shiftKey(b), "el");
      if (cmp !== 0) return cmp;
    }
    const epA = (a.eponymo || "").toUpperCase();
    const epB = (b.eponymo || "").toUpperCase();
    if (epA !== epB) return epA.localeCompare(epB, "el");
    return (a.employee_afm || "").localeCompare(b.employee_afm || "", "el");
  });
}

async function loadSchedule(cachedActive) {
  const wrap = document.getElementById("scheduleWrap");
  const btn = document.getElementById("btnSyncSchedule");
  const r = getRange();
  if (!r.start) {
    return;
  }
  Office.showTableLoading(wrap);
  try {
    const activeData = cachedActive || (await Office.fetchActiveStore());
    if (!activeData.store) {
      if (btn) btn.disabled = true;
      wrap.innerHTML =
        `<p style="color:var(--muted);">${Office.icon("info-circle")}<span style="margin-left:0.35rem;">Επιλέξτε ενεργό κατάστημα (sidebar).</span></p>`;
      return;
    }
    if (btn) btn.disabled = false;
    const res = await fetch(`/api/schedule/list?${listQuery(r)}`);
    let data = {};
    try {
      data = await res.json();
    } catch {
      wrap.innerHTML = `<p style="color:var(--err);">Σφάλμα διακομιστή (HTTP ${res.status}).</p>`;
      return;
    }
    if (!res.ok) {
      wrap.innerHTML = `<p style="color:var(--err);">${Office.escapeHtml(data.error || "Σφάλμα")}</p>`;
      if (data.db_setup) {
        wrap.innerHTML += `<p style="font-size:0.85rem;color:var(--muted);margin-top:0.5rem;">${Office.escapeHtml(data.db_setup)}</p>`;
      }
      return;
    }
    renderTable(
      sortScheduleRows(data.schedule || []),
      data.count || 0,
      data.store,
      r,
      data.work_dates
    );
    Office.updateSyncMetaLine("scheduleSyncMeta", activeData.store, "schedule");
  } catch (e) {
    wrap.innerHTML = `<p style="color:var(--err);">${Office.escapeHtml(String(e))}</p>`;
  }
}

function renderTable(rows, count, store, range, workDates) {
  tableState = { rows, page: 1, count, store, range, workDates: workDates || [] };
  renderTablePage();
}

function renderTablePage() {
  const wrap = document.getElementById("scheduleWrap");
  const { rows, store, range } = tableState;
  if (!rows.length) {
    wrap.innerHTML =
      `<p style="color:var(--muted);">${Office.icon("calendar-x")}<span style="margin-left:0.35rem;">Δεν υπάρχουν εγγραφές για την ημέρα ${Office.escapeHtml(Office.formatDateGr(range.start) || "")}.</span></p>`;
    return;
  }

  const pg = Office.paginateSlice(rows, tableState.page);
  tableState.page = pg.page;

  const storeLine = store
    ? `<p class="table-meta">${Office.icon("shop-window")} <strong>${Office.escapeHtml(store.name)}</strong></p>`
    : "";
  const dateGr = Office.formatDateGr(range.start) || range.start;
  const rangeLine = `<p class="table-meta">${rows.length} εγγραφές · ${Office.escapeHtml(dateGr)}</p>`;

  const t = document.createElement("table");
  t.className = "data";
  const headers = ["ΑΦΜ", "", "Επώνυμο", "Όνομα", "Ευελ. (λεπτά)", "Από", "Έως", "Τύπος", "Διάλειμμα"];
  const hr = document.createElement("tr");
  headers.forEach((h) => {
    const th = document.createElement("th");
    if (h === "") {
      th.className = "col-history";
      th.setAttribute("aria-label", "Ιστορικό");
    } else {
      th.textContent = h;
    }
    hr.appendChild(th);
  });
  t.appendChild(hr);

  pg.items.forEach((row) => {
    const tr = document.createElement("tr");
    const tdAfm = document.createElement("td");
    tdAfm.innerHTML = `<strong>${Office.escapeHtml(row.employee_afm || "")}</strong>`;
    tr.appendChild(tdAfm);
    tr.appendChild(Office.createWorkLogHistoryCell(row));

    const cells = [row.eponymo || "", row.onoma || ""];
    cells.push(
      Office.formatFlexMinutes(row.flex_arrival_minutes),
      row.hour_from || "",
      row.hour_to || "",
      row.shift_type || "",
      row.break_minutes != null ? String(row.break_minutes) : ""
    );
    cells.forEach((txt, i) => {
      const td = document.createElement("td");
      if (i === 0) {
        td.innerHTML = `<strong>${Office.escapeHtml(txt)}</strong>`;
      } else {
        td.textContent = txt;
      }
      tr.appendChild(td);
    });
    t.appendChild(tr);
  });

  wrap.innerHTML = storeLine + rangeLine;
  wrap.appendChild(t);
  if (pg.totalPages > 1) {
    wrap.appendChild(
      Office.buildTablePager(pg.page, pg.totalPages, pg.total, (p) => {
        tableState.page = p;
        renderTablePage();
      })
    );
  }
}

async function maybeAutoSyncSchedule(activeData) {
  if (initialAutoSyncDone) return false;
  initialAutoSyncDone = true;
  try {
    const data = activeData || (await Office.fetchActiveStore());
    if (!data.store) return false;
    if (!Office.scheduleNeedsAutoSync(data.store.schedule_last_sync_at)) return false;
    return await runSync({ date: Office.todayIsoLocal() }, { auto: true });
  } catch {
    return false;
  }
}

async function runSync(bodyOverride, opts = {}) {
  const { auto = false } = opts;
  const r = getRange();
  const body = bodyOverride || { date: r.start };
  if (!auto) {
    Office.beginSyncPanel("scheduleWrap", "schedMsg");
  } else {
    Office.showMsg(
      "schedMsg",
      "Αυτόματος συγχρονισμός ωραρίου για σήμερα…",
      true
    );
  }
  try {
    const payload = await Office.runPortalSync({
      url: "/api/schedule/sync",
      body,
      msgId: "schedMsg",
      btnId: "btnSyncSchedule",
      startMessage: auto
        ? "Αυτόματος συγχρονισμός ωραρίου (σήμερα)"
        : "Συγχρονισμός ψηφιακού ωραρίου",
    });
    const result = Office.buildSyncResultMessage(payload, Office.portalHostFromSync);
    if (!auto) {
      Office.endSyncPanel("scheduleWrap", "schedMsg");
    }
    if (result.ok) {
      await Office.recordStoreSync("schedule");
      const fresh = await Office.fetchActiveStore({ refresh: true });
      Office.applyActiveStoreChrome(fresh);
      await loadSchedule(fresh);
    }
    Office.showMsg(
      "schedMsg",
      auto
        ? result.ok
          ? `Αυτόματος συγχρονισμός: ${result.text}`
          : result.text
        : result.text,
      result.ok
    );
    return result.ok;
  } catch (e) {
    if (!auto) {
      Office.endSyncPanel("scheduleWrap", "schedMsg");
    }
    Office.showMsg("schedMsg", String(e), false);
    return false;
  }
}

function initScheduleTemplateDownload() {
  const menu = document.querySelector(".schedule-download-menu");
  if (!menu) return;
  menu.querySelectorAll("[data-schedule-template]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const week = String(btn.getAttribute("data-schedule-template") || "current");
      menu.open = false;
      void downloadScheduleTemplate(week);
    });
  });
  document.addEventListener("click", (event) => {
    if (!menu.open) return;
    if (!menu.contains(event.target)) menu.open = false;
  });
}

async function downloadScheduleTemplate(week) {
  Office.showMsg("schedMsg", "Δημιουργία Excel…", true);
  try {
    const res = await fetch(`/api/schedule/import/template?week=${encodeURIComponent(week)}`, {
      credentials: "same-origin",
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      Office.showMsg("schedMsg", data.error || `Σφάλμα HTTP ${res.status}`, false);
      return;
    }
    const blob = await res.blob();
    let filename = "weekly_schedule.xlsx";
    const cd = res.headers.get("Content-Disposition") || "";
    const match = /filename\*=UTF-8''([^;]+)|filename="([^"]+)"/i.exec(cd);
    if (match) {
      filename = decodeURIComponent(match[1] || match[2] || filename);
    }
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    const label = week === "next" ? "επόμενη" : "τρέχουσα";
    Office.showMsg("schedMsg", `Κατέβηκε template (${label} εβδομάδα)`, true);
  } catch (e) {
    Office.showMsg("schedMsg", String(e), false);
  }
}

function initScheduleImportUi() {
  const fileInput = document.getElementById("scheduleImportFile");
  const btnConfirm = document.getElementById("btnScheduleImportConfirm");
  const btnCancel = document.getElementById("btnScheduleImportCancel");
  if (fileInput) {
    fileInput.addEventListener("change", () => {
      const file = fileInput.files && fileInput.files[0];
      fileInput.value = "";
      if (file) void uploadScheduleImport(file);
    });
  }
  if (btnConfirm) {
    btnConfirm.addEventListener("click", () => {
      if (scheduleImportBatchId) void confirmScheduleImport(scheduleImportBatchId);
    });
  }
  if (btnCancel) {
    btnCancel.addEventListener("click", () => {
      if (scheduleImportBatchId) void cancelScheduleImport(scheduleImportBatchId);
      else hideScheduleImportPanel();
    });
  }
}

function hideScheduleImportPanel() {
  scheduleImportBatchId = null;
  const panel = document.getElementById("scheduleImportPanel");
  if (panel) panel.classList.add("hidden");
  const btnConfirm = document.getElementById("btnScheduleImportConfirm");
  if (btnConfirm) btnConfirm.disabled = true;
}

function changeKindLabel(kind) {
  const map = {
    new: "Νέο",
    update: "Αλλαγή",
    same: "Ίδιο",
    skip: "Χωρίς αλλαγή",
    error: "Σφάλμα",
  };
  return map[kind] || kind || "—";
}

function changeKindClass(kind) {
  const map = {
    new: "status-info",
    update: "status-warn",
    same: "status-muted",
    skip: "status-muted",
    error: "status-err",
  };
  return map[kind] || "status-muted";
}

function formatImportRowNote(row) {
  const errs = (row.validation_errors || []).join(" · ");
  if (errs) return { text: errs, tone: "error" };
  if (String(row.import_action || "") === "absent") {
    const status = String(row.apply_status || "").trim().toLowerCase();
    if (!status || status === "pending") {
      return { text: "Λείπει από Excel → χωρίς εργασία", tone: "none" };
    }
  }
  const status = String(row.apply_status || "").trim().toLowerCase();
  const msg = String(row.apply_message || "").trim();
  if (!status || status === "pending") return { text: "", tone: "none" };
  if (status === "success") {
    return { text: msg || "Εφαρμόστηκε στο Ergani", tone: "success" };
  }
  if (status === "failed") {
    return { text: msg || "Αποτυχία αποστολής", tone: "error" };
  }
  return { text: msg || status, tone: "error" };
}

function scrollToScheduleImportMsg() {
  const msg = document.getElementById("schedMsg");
  if (msg) {
    msg.scrollIntoView({ behavior: "smooth", block: "center" });
    return;
  }
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function scheduleImportResultMessage(data) {
  const applied = data.applied || 0;
  const failed = data.failed || 0;
  const parts = [];
  if (data.success) {
    parts.push(`Εφαρμόστηκαν ${applied} αλλαγές στο Ergani`);
  } else if (applied || failed) {
    parts.push(`Ολοκληρώθηκε με σφάλματα — επιτυχία: ${applied}, αποτυχία: ${failed}`);
  }
  const sync = data.schedule_sync;
  if (sync?.attempted) {
    if (sync.success) {
      parts.push(`Συγχρονίστηκε ψηφ. ωράριο ${sync.from} έως ${sync.to}`);
    } else {
      parts.push(`Συγχρονισμός ωραρίου: ${sync.detail || "αποτυχία"}`);
    }
  }
  return parts.join(" · ");
}

async function afterScheduleImportConfirm(data) {
  if (data.schedule_sync?.success) {
    await Office.recordStoreSync("schedule");
  }
  const fresh = await Office.fetchActiveStore({ refresh: true });
  Office.applyActiveStoreChrome(fresh);
  await loadSchedule(fresh);
}

function renderScheduleImportPreview(preview, fileErrors) {
  const panel = document.getElementById("scheduleImportPanel");
  const metaEl = document.getElementById("scheduleImportMeta");
  const summaryEl = document.getElementById("scheduleImportSummary");
  const wrap = document.getElementById("scheduleImportWrap");
  const btnConfirm = document.getElementById("btnScheduleImportConfirm");
  if (!panel || !wrap || !summaryEl || !metaEl) return;

  closeScheduleDayForm();

  const batch = preview?.batch || {};
  const rows = preview?.rows || [];
  const summary = preview?.summary || {};
  scheduleImportBatchId = batch.id || null;

  const fileName = Office.escapeHtml(batch.original_filename || "Excel");
  const week = Office.escapeHtml(batch.week_label || "");
  metaEl.innerHTML = `${Office.icon("file-earmark-excel")} <strong>${fileName}</strong>${week ? ` · ${week}` : ""}`;

  const chips = [
    ["apply", "Προς εφαρμογή", "status-warn"],
    ["update", "Αλλαγές", "status-warn"],
    ["new", "Νέες", "status-info"],
    ["same", "Ίδιες", "status-muted"],
    ["skip", "Χωρίς αλλαγή", "status-muted"],
    ["absent", "Λείπουν από Excel", "status-warn"],
    ["error", "Σφάλματα", "status-err"],
  ];
  summaryEl.innerHTML =
    `<div class="report-chips">${chips
      .filter(([key]) => (summary[key] || 0) > 0)
      .map(
        ([key, label, cls]) =>
          `<span class="report-chip ${cls}">${Office.escapeHtml(label)}: <strong>${summary[key]}</strong></span>`
      )
      .join("")}</div>` +
    (fileErrors?.length
      ? `<ul class="report-notes">${fileErrors
          .map((e) => `<li>${Office.escapeHtml(e)}</li>`)
          .join("")}</ul>`
      : "");

  const visibleRows = [...rows]
    .filter((r) => r.change_kind !== "skip")
    .sort((a, b) => {
      const dateCmp = erganiDateSortKey(a.work_date) - erganiDateSortKey(b.work_date);
      if (dateCmp !== 0) return dateCmp;
      const ep = String(a.eponymo || "").localeCompare(String(b.eponymo || ""), "el");
      if (ep !== 0) return ep;
      const on = String(a.onoma || "").localeCompare(String(b.onoma || ""), "el");
      if (on !== 0) return on;
      return String(a.employee_afm || "").localeCompare(String(b.employee_afm || ""), "el");
    });
  if (!visibleRows.length) {
    wrap.innerHTML =
      `<p style="color:var(--muted);">${Office.icon("info-circle")} Δεν βρέθηκαν αλλαγές στο αρχείο.</p>`;
  } else {
    const t = document.createElement("table");
    t.className = "data schedule-import-table";
    const headers = [
      "Ημερομηνία",
      "Επώνυμο",
      "Όνομα",
      "ΑΦΜ",
      "Κατάσταση",
      "Τρέχον",
      "Νέο",
      "Σημειώσεις",
    ];
    const hr = document.createElement("tr");
    headers.forEach((h) => {
      const th = document.createElement("th");
      th.textContent = h;
      hr.appendChild(th);
    });
    t.appendChild(hr);
    visibleRows.forEach((row) => {
      const tr = document.createElement("tr");
      const badge = document.createElement("span");
      badge.className = `status-badge ${changeKindClass(row.change_kind)}`;
      badge.textContent = changeKindLabel(row.change_kind);
      const note = formatImportRowNote(row);
      const cells = [
        row.work_date || "",
        row.eponymo || "",
        row.onoma || "",
        row.employee_afm || "",
        badge.outerHTML,
        row.current_label || "—",
        row.proposed_label || "—",
        note.text,
      ];
      cells.forEach((html, i) => {
        const td = document.createElement("td");
        if (i === 4) td.innerHTML = html;
        else if (i >= 7) {
          if (!note.text) td.innerHTML = "";
          else {
            const noteCls =
              note.tone === "success"
                ? "schedule-import-note schedule-import-note--ok"
                : "schedule-import-note schedule-import-note--err";
            td.innerHTML = `<span class="${noteCls}">${Office.escapeHtml(note.text)}</span>`;
          }
        } else td.textContent = html;
        tr.appendChild(td);
      });
      t.appendChild(tr);
    });
    wrap.innerHTML = "";
    wrap.appendChild(t);
  }

  if (btnConfirm) btnConfirm.disabled = !(summary.apply > 0);
  panel.classList.remove("hidden");
  panel.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function uploadScheduleImport(file) {
  Office.showMsg("schedMsg", `Ανάγνωση ${file.name}…`, true);
  const form = new FormData();
  form.append("file", file);
  try {
    const res = await fetch("/api/schedule/import/upload", {
      method: "POST",
      credentials: "same-origin",
      body: form,
    });
    const data = await Office.parseJson(res);
    if (!res.ok || !data.success) {
      Office.showMsg("schedMsg", data.error || "Αποτυχία ανάγνωσης Excel", false);
      return;
    }
    renderScheduleImportPreview(data.preview, data.file_errors || []);
    Office.showMsg(
      "schedMsg",
      `Φορτώθηκε προεπισκόπηση — ${data.preview?.summary?.apply || 0} αλλαγές προς εφαρμογή`,
      true
    );
  } catch (e) {
    Office.showMsg("schedMsg", String(e), false);
  }
}

async function confirmScheduleImport(batchId) {
  const btnConfirm = document.getElementById("btnScheduleImportConfirm");
  if (btnConfirm) btnConfirm.disabled = true;
  scrollToScheduleImportMsg();
  Office.showLoading("schedMsg", "Εφαρμογή προς Ergani και συγχρονισμός ωραρίου…");
  try {
    const res = await fetch(`/api/schedule/import/confirm/${batchId}`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
    });
    const data = await Office.parseJson(res);
    const resultMsg = scheduleImportResultMessage(data);
    if (!res.ok || !data.success) {
      Office.showMsg("schedMsg", data.error || resultMsg || "Αποτυχία εφαρμογής", false);
      scrollToScheduleImportMsg();
      const previewRes = await fetch(`/api/schedule/import/preview/${batchId}`);
      const previewData = await Office.parseJson(previewRes);
      if (previewRes.ok) renderScheduleImportPreview(previewData, []);
      await afterScheduleImportConfirm(data);
      return;
    }
    Office.showMsg("schedMsg", resultMsg || `Εφαρμόστηκαν ${data.applied || 0} αλλαγές στο Ergani`, true);
    scrollToScheduleImportMsg();
    hideScheduleImportPanel();
    await afterScheduleImportConfirm(data);
  } catch (e) {
    Office.showMsg("schedMsg", String(e), false);
    if (btnConfirm) btnConfirm.disabled = false;
  }
}

async function cancelScheduleImport(batchId) {
  try {
    await fetch(`/api/schedule/import/cancel/${batchId}`, {
      method: "POST",
      credentials: "same-origin",
    });
  } catch {
    /* ignore */
  }
  hideScheduleImportPanel();
  Office.showMsg("schedMsg", "Ακυρώθηκε η εισαγωγή Excel", true);
}

function initScheduleDayFormUi() {
  const panel = document.getElementById("scheduleDayFormPanel");
  if (!panel) return;

  const dateMount = document.getElementById("scheduleDayFormDatePicker");
  if (dateMount) {
    scheduleDayFormDatePicker = Office.createDatePicker({
      mountId: "scheduleDayFormDatePicker",
      mode: "single",
      layout: "inline",
      quickPresets: ["yesterday", "today", "tomorrow", "dayAfterTomorrow"],
      autoApply: true,
      onApply: ({ start }) => {
        if (start) void loadScheduleDayFormData(start);
      },
    });
  }

  const btnCancel = document.getElementById("btnScheduleDayFormCancel");
  if (btnCancel) btnCancel.addEventListener("click", () => closeScheduleDayForm());

  const btnOpen = document.getElementById("btnScheduleDayForm");
  if (btnOpen) btnOpen.addEventListener("click", () => beginScheduleDayForm());

  const btnPreview = document.getElementById("btnScheduleDayFormPreview");
  if (btnPreview) btnPreview.addEventListener("click", () => void previewScheduleDayForm());

  const btnSubmit = document.getElementById("btnScheduleDayFormSubmit");
  if (btnSubmit) btnSubmit.addEventListener("click", () => void submitScheduleDayForm());
}

function resetScheduleDayFormContent() {
  scheduleDayFormState = { dateIso: "", rows: [], preview: null };
  const wrap = document.getElementById("scheduleDayFormWrap");
  const actions = document.getElementById("scheduleDayFormActions");
  const previewEl = document.getElementById("scheduleDayFormPreview");
  const btnSubmit = document.getElementById("btnScheduleDayFormSubmit");
  const metaEl = document.getElementById("scheduleDayFormMeta");

  if (metaEl) metaEl.textContent = "Επιλέξτε ημερομηνία.";
  if (wrap) {
    wrap.classList.add("schedule-day-form-wrap--pending");
    wrap.innerHTML =
      `<p class="schedule-day-form-pick-hint" style="color:var(--muted);">${Office.icon("calendar3")} Επιλέξτε ημερομηνία για να εμφανιστεί η λίστα εργαζομένων.</p>`;
  }
  if (actions) actions.classList.add("hidden");
  if (previewEl) {
    previewEl.classList.add("hidden");
    previewEl.innerHTML = "";
  }
  if (btnSubmit) btnSubmit.disabled = true;
  showScheduleDayFormMsg("", true);
}

function beginScheduleDayForm() {
  const panel = document.getElementById("scheduleDayFormPanel");
  if (!panel) return;

  hideScheduleImportPanel();
  resetScheduleDayFormContent();
  panel.classList.remove("hidden");
  panel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function closeScheduleDayForm() {
  const panel = document.getElementById("scheduleDayFormPanel");
  if (panel) panel.classList.add("hidden");
  resetScheduleDayFormContent();
}

function showScheduleDayFormMsg(text, ok) {
  Office.showMsg("scheduleDayFormMsg", text, ok);
}

function collectScheduleDayFormRows() {
  const wrap = document.getElementById("scheduleDayFormWrap");
  if (!wrap) return [];
  return [...wrap.querySelectorAll("tr[data-afm]")].map((tr) => {
    const energia = tr.querySelector(".schedule-day-form-energia")?.value || "";
    const hf1 = tr.querySelector('[data-field="hour_from_1"]')?.value || "";
    const ht1 = tr.querySelector('[data-field="hour_to_1"]')?.value || "";
    const hf2 = tr.querySelector('[data-field="hour_from_2"]')?.value || "";
    const ht2 = tr.querySelector('[data-field="hour_to_2"]')?.value || "";
    return {
      employee_afm: tr.dataset.afm || "",
      eponymo: tr.dataset.eponymo || "",
      onoma: tr.dataset.onoma || "",
      energia,
      hour_from_1: Office.normalizeHourMinute(hf1),
      hour_to_1: Office.normalizeHourMinute(ht1),
      hour_from_2: Office.normalizeHourMinute(hf2),
      hour_to_2: Office.normalizeHourMinute(ht2),
    };
  });
}

function syncDayFormRowHours(tr) {
  const energia = (tr.querySelector(".schedule-day-form-energia")?.value || "").toUpperCase();
  const isRepo = energia === "REPO";
  tr.querySelectorAll(".schedule-day-form-hours input").forEach((input) => {
    input.disabled = isRepo;
    if (isRepo) input.value = "";
  });
}

function renderScheduleDayFormTable(payload) {
  const wrap = document.getElementById("scheduleDayFormWrap");
  const btnSubmit = document.getElementById("btnScheduleDayFormSubmit");
  if (!wrap) return;

  const rows = payload.rows || [];
  if (!rows.length) {
    wrap.innerHTML =
      `<p style="color:var(--muted);">${Office.icon("info-circle")} Δεν βρέθηκαν εργαζόμενοι για το κατάστημα.</p>`;
    if (btnSubmit) btnSubmit.disabled = true;
    return;
  }

  const t = document.createElement("table");
  t.className = "data schedule-day-form-table";
  const headers = ["Επώνυμο", "Όνομα", "Τρέχον", "Ενέργεια", "Ωράριο (1)", "Ωράριο (2)"];
  const hr = document.createElement("tr");
  headers.forEach((h) => {
    const th = document.createElement("th");
    th.textContent = h;
    hr.appendChild(th);
  });
  t.appendChild(hr);

  rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.dataset.afm = row.employee_afm || "";
    tr.dataset.eponymo = row.eponymo || "";
    tr.dataset.onoma = row.onoma || "";

    const tdName = document.createElement("td");
    tdName.className = "col-name";
    tdName.innerHTML = `<strong>${Office.escapeHtml(row.eponymo || "")}</strong>`;
    tr.appendChild(tdName);

    const tdOnoma = document.createElement("td");
    tdOnoma.textContent = row.onoma || "";
    tr.appendChild(tdOnoma);

    const tdCurrent = document.createElement("td");
    tdCurrent.className = "col-current";
    tdCurrent.textContent = row.current_label || "—";
    tr.appendChild(tdCurrent);

    const tdEnergia = document.createElement("td");
    const sel = document.createElement("select");
    sel.className = "schedule-day-form-energia";
    sel.innerHTML =
      `<option value="">— χωρίς αλλαγή —</option>` +
      `<option value="WORK">Εργασία</option>` +
      `<option value="REPO">Ρεπό / Ανάπαυση</option>`;
    sel.value = row.energia || "";
    sel.addEventListener("change", () => {
      syncDayFormRowHours(tr);
      scheduleDayFormState.preview = null;
      const previewEl = document.getElementById("scheduleDayFormPreview");
      if (previewEl) {
        previewEl.classList.add("hidden");
        previewEl.innerHTML = "";
      }
      if (btnSubmit) btnSubmit.disabled = true;
    });
    tdEnergia.appendChild(sel);
    tr.appendChild(tdEnergia);

    function hoursCell(hfKey, htKey, label) {
      const td = document.createElement("td");
      const box = document.createElement("div");
      box.className = "schedule-day-form-hours";
      box.innerHTML =
        `<div><span class="schedule-day-form-hours-label">Από</span>` +
        `<input type="text" data-field="${hfKey}" class="input-time-24" inputmode="numeric" placeholder="09:00" maxlength="5" autocomplete="off"></div>` +
        `<div><span class="schedule-day-form-hours-label">Έως</span>` +
        `<input type="text" data-field="${htKey}" class="input-time-24" inputmode="numeric" placeholder="17:00" maxlength="5" autocomplete="off"></div>`;
      const hf = box.querySelector(`[data-field="${hfKey}"]`);
      const ht = box.querySelector(`[data-field="${htKey}"]`);
      if (hf) {
        hf.value = Office.normalizeHourMinute(row[hfKey] || "");
        Office.bindHourMinuteElement(hf);
        hf.addEventListener("input", () => {
          if (!sel.value && (hf.value || ht?.value)) sel.value = "WORK";
          syncDayFormRowHours(tr);
        });
      }
      if (ht) {
        ht.value = Office.normalizeHourMinute(row[htKey] || "");
        Office.bindHourMinuteElement(ht);
        ht.addEventListener("input", () => {
          if (!sel.value && (hf?.value || ht.value)) sel.value = "WORK";
          syncDayFormRowHours(tr);
        });
      }
      td.appendChild(box);
      return td;
    }

    tr.appendChild(hoursCell("hour_from_1", "hour_to_1", "1"));
    tr.appendChild(hoursCell("hour_from_2", "hour_to_2", "2"));
    syncDayFormRowHours(tr);
    t.appendChild(tr);
  });

  wrap.innerHTML = "";
  wrap.appendChild(t);
  if (btnSubmit) btnSubmit.disabled = true;
}

function renderScheduleDayFormPreview(preview) {
  const previewEl = document.getElementById("scheduleDayFormPreview");
  const btnSubmit = document.getElementById("btnScheduleDayFormSubmit");
  if (!previewEl) return;

  const summary = preview?.summary || {};
  const rows = (preview?.rows || []).filter((r) => r.change_kind !== "skip");
  const chips = [
    ["apply", "Προς αποστολή", "status-warn"],
    ["update", "Αλλαγές", "status-warn"],
    ["new", "Νέες", "status-info"],
    ["same", "Ίδιες", "status-muted"],
    ["error", "Σφάλματα", "status-err"],
  ];

  let html =
    `<div class="report-chips">${chips
      .filter(([key]) => (summary[key] || 0) > 0)
      .map(
        ([key, label, cls]) =>
          `<span class="report-chip ${cls}">${Office.escapeHtml(label)}: <strong>${summary[key]}</strong></span>`
      )
      .join("")}</div>`;

  if (rows.length) {
    html += `<table class="data schedule-import-table"><thead><tr>` +
      `<th>Επώνυμο</th><th>Κατάσταση</th><th>Τρέχον</th><th>Νέο</th><th>Σημειώσεις</th></tr></thead><tbody>`;
    rows.forEach((row) => {
      const note = formatImportRowNote(row);
      const noteHtml = note.text
        ? `<span class="schedule-import-note schedule-import-note--${note.tone === "error" ? "err" : note.tone === "success" ? "ok" : ""}">${Office.escapeHtml(note.text)}</span>`
        : "";
      html +=
        `<tr><td>${Office.escapeHtml(row.eponymo || "")}</td>` +
        `<td><span class="status-badge ${changeKindClass(row.change_kind)}">${Office.escapeHtml(changeKindLabel(row.change_kind))}</span></td>` +
        `<td>${Office.escapeHtml(row.current_label || "—")}</td>` +
        `<td>${Office.escapeHtml(row.proposed_label || "—")}</td>` +
        `<td>${noteHtml}</td></tr>`;
    });
    html += `</tbody></table>`;
  } else {
    html += `<p style="color:var(--muted);margin:0.5rem 0 0;">Δεν υπάρχουν αλλαγές προς αποστολή.</p>`;
  }

  previewEl.innerHTML = html;
  previewEl.classList.remove("hidden");
  if (btnSubmit) btnSubmit.disabled = !(summary.apply > 0);
}

async function loadScheduleDayFormData(dateIso) {
  const panel = document.getElementById("scheduleDayFormPanel");
  const metaEl = document.getElementById("scheduleDayFormMeta");
  const wrap = document.getElementById("scheduleDayFormWrap");
  const actions = document.getElementById("scheduleDayFormActions");
  if (!panel || !wrap) return;

  const iso = String(dateIso || "").slice(0, 10);
  if (!iso) return;

  scheduleDayFormState = { dateIso: iso, rows: [], preview: null };
  const previewEl = document.getElementById("scheduleDayFormPreview");
  if (previewEl) {
    previewEl.classList.add("hidden");
    previewEl.innerHTML = "";
  }
  const btnSubmit = document.getElementById("btnScheduleDayFormSubmit");
  if (btnSubmit) btnSubmit.disabled = true;
  if (actions) actions.classList.remove("hidden");

  const dateGr = Office.formatDateGr ? Office.formatDateGr(iso) : iso;
  if (metaEl) {
    metaEl.textContent = `Ημερομηνία: ${dateGr} — συμπληρώστε ενέργεια και ωράριο ανά εργαζόμενο.`;
  }
  wrap.classList.remove("schedule-day-form-wrap--pending");
  wrap.innerHTML = `<p style="color:var(--muted);">${Office.icon("hourglass-split")} Φόρτωση…</p>`;
  showScheduleDayFormMsg("", true);
  panel.classList.remove("hidden");

  try {
    const res = await fetch(`/api/schedule/day-form?date=${encodeURIComponent(iso)}`, {
      credentials: "same-origin",
    });
    const data = await Office.parseJson(res);
    if (!res.ok || !data.success) {
      wrap.innerHTML = `<p style="color:var(--err);">${Office.escapeHtml(data.error || "Σφάλμα φόρτωσης")}</p>`;
      showScheduleDayFormMsg(data.error || "Αποτυχία φόρτωσης", false);
      return;
    }
    scheduleDayFormState.rows = data.rows || [];
    renderScheduleDayFormTable(data);
  } catch (e) {
    wrap.innerHTML = `<p style="color:var(--err);">${Office.escapeHtml(String(e))}</p>`;
    showScheduleDayFormMsg(String(e), false);
  }
}

async function previewScheduleDayForm() {
  const { dateIso } = scheduleDayFormState;
  if (!dateIso) return;

  const btnPreview = document.getElementById("btnScheduleDayFormPreview");
  if (btnPreview) btnPreview.disabled = true;
  showScheduleDayFormMsg("Προεπισκόπηση…", true);

  const rows = collectScheduleDayFormRows();
  try {
    const res = await fetch("/api/schedule/day-form/preview", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ date: dateIso, rows }),
    });
    const data = await Office.parseJson(res);
    if (!res.ok || !data.success) {
      showScheduleDayFormMsg(data.error || "Αποτυχία προεπισκόπησης", false);
      return;
    }
    scheduleDayFormState.preview = data;
    renderScheduleDayFormPreview(data);
    const applyCount = data.summary?.apply || 0;
    showScheduleDayFormMsg(
      applyCount
        ? `${applyCount} αλλαγές προς αποστολή — ελέγξτε και πατήστε «Αποστολή Ergani».`
        : "Δεν υπάρχουν αλλαγές προς αποστολή.",
      applyCount > 0
    );
  } catch (e) {
    showScheduleDayFormMsg(String(e), false);
  } finally {
    if (btnPreview) btnPreview.disabled = false;
  }
}

async function submitScheduleDayForm() {
  const { dateIso, preview } = scheduleDayFormState;
  if (!dateIso) return;
  if (!preview || !(preview.summary?.apply > 0)) {
    await previewScheduleDayForm();
    if (!(scheduleDayFormState.preview?.summary?.apply > 0)) return;
  }

  const btnSubmit = document.getElementById("btnScheduleDayFormSubmit");
  if (btnSubmit) btnSubmit.disabled = true;
  showScheduleDayFormMsg("Αποστολή προς Ergani…", true);

  const rows = collectScheduleDayFormRows();
  try {
    const res = await fetch("/api/schedule/day-form/submit", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ date: dateIso, rows }),
    });
    const data = await Office.parseJson(res);
    const resultMsg = scheduleImportResultMessage(data);
    if (!res.ok || !data.success) {
      showScheduleDayFormMsg(data.error || resultMsg || "Αποτυχία αποστολής", false);
      if (btnSubmit) btnSubmit.disabled = Boolean(scheduleDayFormState.preview?.summary?.apply > 0);
      await previewScheduleDayForm();
      return;
    }
    showScheduleDayFormMsg(resultMsg || `Εφαρμόστηκαν ${data.applied || 0} αλλαγές`, true);
    Office.showMsg("schedMsg", resultMsg || `Εφαρμόστηκαν ${data.applied || 0} αλλαγές στο Ergani`, true);
    if (data.schedule_sync?.success) {
      await Office.recordStoreSync("schedule");
    }
    scheduleListDateIso = dateIso;
    if (scheduleListDatePicker) scheduleListDatePicker.setRange(dateIso, dateIso);
    const fresh = await Office.fetchActiveStore({ refresh: true });
    Office.applyActiveStoreChrome(fresh);
    await loadSchedule(fresh);
    closeScheduleDayForm();
  } catch (e) {
    showScheduleDayFormMsg(String(e), false);
    if (btnSubmit) btnSubmit.disabled = Boolean(scheduleDayFormState.preview?.summary?.apply > 0);
  }
}
