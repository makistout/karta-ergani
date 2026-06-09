let datePicker = null;
let currentRange = { start: "", end: "" };
let tableState = { rows: [], page: 1, count: 0, store: null, range: null, workDates: [] };

document.addEventListener("DOMContentLoaded", () => {
  Office.setActiveNav("schedule");
  datePicker = Office.createDatePicker({
    mountId: "scheduleDatePicker",
    mode: "range",
    onApply: () => loadSchedule(),
  });
  document.getElementById("btnSyncSchedule").onclick = runSync;
  loadSchedule();
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

async function loadSchedule() {
  const wrap = document.getElementById("scheduleWrap");
  const btn = document.getElementById("btnSyncSchedule");
  const r = getRange();
  if (!r.start) {
    return;
  }
  Office.showTableLoading(wrap);
  try {
    const activeRes = await fetch("/api/store/active");
    const activeData = await activeRes.json();
    if (!activeData.store) {
      btn.disabled = true;
      wrap.innerHTML =
        `<p style="color:var(--muted);">${Office.icon("info-circle")}<span style="margin-left:0.35rem;">Επιλέξτε ενεργό κατάστημα (sidebar).</span></p>`;
      return;
    }
    btn.disabled = false;
    await Office.loadActiveStore();
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
      `<p style="color:var(--muted);">${Office.icon("calendar-x")}<span style="margin-left:0.35rem;">Δεν υπάρχουν εγγραφές για το επιλεγμένο διάστημα. Πατήστε «Συγχρονισμός Ergani».</span></p>`;
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
  const headers = ["ΑΦΜ", "Επώνυμο", "Όνομα"];
  if (multi) headers.push("Ημερομηνία");
  headers.push("Από", "Έως", "Τύπος", "Διάλειμμα");
  const hr = document.createElement("tr");
  headers.forEach((h) => {
    const th = document.createElement("th");
    th.textContent = h;
    hr.appendChild(th);
  });
  t.appendChild(hr);

  pg.items.forEach((row) => {
    const tr = document.createElement("tr");
    const cells = [row.employee_afm || "", row.eponymo || "", row.onoma || ""];
    if (multi) cells.push(row.work_date || "");
    cells.push(
      row.hour_from || "",
      row.hour_to || "",
      row.shift_type || "",
      row.break_minutes != null ? String(row.break_minutes) : ""
    );
    cells.forEach((txt, i) => {
      const td = document.createElement("td");
      if (i === 1) td.innerHTML = `<strong>${Office.escapeHtml(txt)}</strong>`;
      else td.textContent = txt;
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

async function runSync() {
  const r = getRange();
  const body =
    r.start === r.end ? { date: r.start } : { from: r.start, to: r.end };
  Office.beginSyncPanel("scheduleWrap", "schedMsg");
  try {
    const payload = await Office.runPortalSync({
      url: "/api/schedule/sync",
      body,
      msgId: "schedMsg",
      btnId: "btnSyncSchedule",
      startMessage: "Συγχρονισμός ψηφιακού ωραρίου",
    });
    const result = Office.buildSyncResultMessage(payload, Office.portalHostFromSync);
    Office.endSyncPanel("scheduleWrap", "schedMsg");
    if (result.ok) {
      await loadSchedule();
    }
    Office.showMsg("schedMsg", result.text, result.ok);
  } catch (e) {
    Office.endSyncPanel("scheduleWrap", "schedMsg");
    Office.showMsg("schedMsg", String(e), false);
  }
}
