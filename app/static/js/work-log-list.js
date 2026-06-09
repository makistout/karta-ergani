let datePicker = null;
let tableState = { rows: [], page: 1, count: 0, store: null, range: null };

document.addEventListener("DOMContentLoaded", () => {
  Office.setActiveNav("worklog");
  datePicker = Office.createDatePicker({
    mountId: "workLogDatePicker",
    mode: "range",
    onApply: () => loadWorkLog(),
  });
  document.getElementById("btnSyncWorkLog").onclick = runSync;
  loadWorkLog();
});

function getRange() {
  return datePicker ? datePicker.getRange() : { start: "", end: "" };
}

function listQuery(r) {
  if (r.start === r.end) return `date=${encodeURIComponent(r.start)}`;
  return `from=${encodeURIComponent(r.start)}&to=${encodeURIComponent(r.end)}`;
}

async function loadWorkLog() {
  const wrap = document.getElementById("workLogWrap");
  const btn = document.getElementById("btnSyncWorkLog");
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
    const res = await fetch(`/api/work-log/list?${listQuery(r)}`);
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
    renderTable(data.work_log || [], data.count || 0, data.store, r);
  } catch (e) {
    wrap.innerHTML = `<p style="color:var(--err);">${Office.escapeHtml(String(e))}</p>`;
  }
}

function renderTable(rows, count, store, range) {
  tableState = { rows, page: 1, count, store, range };
  renderTablePage();
}

function renderTablePage() {
  const wrap = document.getElementById("workLogWrap");
  const { rows, store, range } = tableState;
  const multi = range.start !== range.end;
  if (!rows.length) {
    wrap.innerHTML =
      `<p style="color:var(--muted);">${Office.icon("clock")}<span style="margin-left:0.35rem;">Δεν υπάρχουν εγγραφές. Πατήστε «Συγχρονισμός Ergani».</span></p>`;
    return;
  }

  const pg = Office.paginateSlice(rows, tableState.page);
  tableState.page = pg.page;

  const storeLine = store
    ? `<p class="table-meta">${Office.icon("shop-window")} <strong>${Office.escapeHtml(store.name)}</strong> · ${rows.length} εγγραφές</p>`
    : "";

  const t = document.createElement("table");
  t.className = "data";
  const headers = ["ΑΦΜ", "Επώνυμο", "Όνομα"];
  if (multi) headers.push("Ημερομηνία");
  headers.push("Ευελ. (λεπτά)", "Από", "Έως", "ΑΑ");
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
      Office.formatFlexMinutes(row.flex_arrival_minutes),
      row.hour_from || "",
      row.hour_to || "",
      row.source_aa || "0"
    );
    cells.forEach((txt, i) => {
      const td = document.createElement("td");
      if (i === 1) td.innerHTML = `<strong>${Office.escapeHtml(txt)}</strong>`;
      else td.textContent = txt;
      tr.appendChild(td);
    });
    t.appendChild(tr);
  });

  wrap.innerHTML = storeLine;
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
  const body = r.start === r.end ? { date: r.start } : { from: r.start, to: r.end };
  Office.beginSyncPanel("workLogWrap", "workLogMsg");
  try {
    const payload = await Office.runPortalSync({
      url: "/api/work-log/sync",
      body,
      msgId: "workLogMsg",
      btnId: "btnSyncWorkLog",
      startMessage: "Συγχρονισμός πραγματικής απασχόλησης",
    });
    const result = Office.buildSyncResultMessage(payload, Office.portalHostFromSync);
    Office.endSyncPanel("workLogWrap", "workLogMsg");
    if (result.ok) {
      await loadWorkLog();
    }
    Office.showMsg("workLogMsg", result.text, result.ok);
  } catch (e) {
    Office.endSyncPanel("workLogWrap", "workLogMsg");
    Office.showMsg("workLogMsg", String(e), false);
  }
}
