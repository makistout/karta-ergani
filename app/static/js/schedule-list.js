let datePicker = null;
let currentRange = { start: "", end: "" };
let tableState = { rows: [], page: 1, count: 0, store: null, range: null, workDates: [] };
let initialAutoSyncDone = false;
let scheduleImportBatchId = null;

document.addEventListener("DOMContentLoaded", async () => {
  Office.setActiveNav("schedule");
  Office.initWorkLogHistoryModal();
  datePicker = Office.createDatePicker({
    mountId: "scheduleDatePicker",
    mode: "range",
    quickPresets: ["yesterday", "today", "tomorrow", "dayAfterTomorrow"],
    onApply: () => loadSchedule(),
  });
  const btnSync = document.getElementById("btnSyncSchedule");
  if (btnSync) btnSync.onclick = () => runSync();
  initScheduleImportUi();
  initScheduleTemplateDownload();

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
  const r = datePicker ? datePicker.getRange() : { start: "", end: "" };
  currentRange = r;
  return r;
}

function listQuery(r) {
  if (r.start === r.end) {
    return `date=${encodeURIComponent(r.start)}`;
  }
  return `from=${encodeURIComponent(r.start)}&to=${encodeURIComponent(r.end)}`;
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
  const { rows, store, range, workDates } = tableState;
  const multi = range.start !== range.end;
  if (!rows.length) {
    wrap.innerHTML =
      `<p style="color:var(--muted);">${Office.icon("calendar-x")}<span style="margin-left:0.35rem;">Δεν υπάρχουν εγγραφές για το επιλεγμένο διάστημα.</span></p>`;
    return;
  }

  const pg = Office.paginateSlice(rows, tableState.page);
  tableState.page = pg.page;

  const storeLine = store
    ? `<p class="table-meta">${Office.icon("shop-window")} <strong>${Office.escapeHtml(store.name)}</strong></p>`
    : "";
  const rangeLine = `<p class="table-meta">${rows.length} εγγραφές · ${workDates?.length || 1} ημέρες στο διάστημα</p>`;

  const t = document.createElement("table");
  t.className = "data";
  const headers = ["ΑΦΜ", "", "Επώνυμο", "Όνομα"];
  if (multi) headers.push("Ημερομηνία");
  headers.push("Ευελ. (λεπτά)", "Από", "Έως", "Τύπος", "Διάλειμμα");
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
    if (multi) cells.push(row.work_date || "");
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
  const body =
    bodyOverride ||
    (r.start === r.end ? { date: r.start } : { from: r.start, to: r.end });
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

  const visibleRows = rows.filter((r) => r.change_kind !== "skip");
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
