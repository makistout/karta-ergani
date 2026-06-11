let datePicker = null;
let tableState = { rows: [], page: 1, count: 0, store: null, range: null };
let initialAutoSyncDone = false;

document.addEventListener("DOMContentLoaded", async () => {
  Office.setActiveNav("worklog");
  datePicker = Office.createDatePicker({
    mountId: "workLogDatePicker",
    mode: "range",
    onApply: () => loadWorkLog(),
  });
  document.getElementById("btnSyncWorkLog").onclick = () => runSync();
  await maybeAutoSyncWorkLog();
  await loadWorkLog();
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
    const activeRes = await fetch("/api/store/active", { cache: "no-store" });
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
    await Office.refreshActiveStoreSyncMeta("workLogSyncMeta", "worklog");
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

async function maybeAutoSyncWorkLog() {
  if (initialAutoSyncDone) return;
  initialAutoSyncDone = true;
  try {
    const activeRes = await fetch("/api/store/active", { cache: "no-store" });
    const activeData = await activeRes.json();
    const store = activeData.store;
    if (!store) return;
    if (
      !Office.workLogNeedsAutoSync(
        store.work_log_last_sync_at,
        store.work_log_sync_interval_minutes
      )
    ) {
      return;
    }
    await runSync({ date: Office.todayIsoLocal() }, { auto: true });
  } catch {
    /* αγνόηση */
  }
}

async function runSync(bodyOverride, opts = {}) {
  const { auto = false } = opts;
  const r = getRange();
  const body =
    bodyOverride ||
    (r.start === r.end ? { date: r.start } : { from: r.start, to: r.end });
  if (!auto) {
    Office.beginSyncPanel("workLogWrap", "workLogMsg");
  } else {
    Office.showMsg(
      "workLogMsg",
      "Αυτόματος συγχρονισμός πραγματικής για σήμερα…",
      true
    );
  }
  try {
    const payload = await Office.runPortalSync({
      url: "/api/work-log/sync",
      body,
      msgId: "workLogMsg",
      btnId: "btnSyncWorkLog",
      startMessage: auto
        ? "Αυτόματος συγχρονισμός πραγματικής (σήμερα)"
        : "Συγχρονισμός πραγματικής απασχόλησης",
    });
    const result = Office.buildSyncResultMessage(payload, Office.portalHostFromSync);
    if (!auto) {
      Office.endSyncPanel("workLogWrap", "workLogMsg");
    }
    if (result.ok) {
      await Office.recordStoreSync("work_log");
      await Office.loadActiveStore();
      await loadWorkLog();
    }
    Office.showMsg(
      "workLogMsg",
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
      Office.endSyncPanel("workLogWrap", "workLogMsg");
    }
    Office.showMsg("workLogMsg", String(e), false);
    return false;
  }
}
