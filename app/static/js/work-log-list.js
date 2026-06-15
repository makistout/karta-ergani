let datePicker = null;
let tableState = { rows: [], page: 1, count: 0, store: null, range: null };
let initialAutoSyncDone = false;

document.addEventListener("DOMContentLoaded", async () => {
  Office.setActiveNav("worklog");
  Office.initWorkLogHistoryModal();
  datePicker = Office.createDatePicker({
    mountId: "workLogDatePicker",
    mode: "range",
    onApply: () => loadWorkLog(),
  });
  document.getElementById("btnSyncWorkLog").onclick = () => runSync();

  const activeData = await Office.fetchActiveStore();
  Office.applyActiveStoreChrome(activeData);
  await loadWorkLog(activeData);

  void maybeAutoSyncWorkLog(activeData).then(async (synced) => {
    if (synced) {
      await loadWorkLog(await Office.fetchActiveStore({ refresh: true }));
    }
  });
});

function getRange() {
  return datePicker ? datePicker.getRange() : { start: "", end: "" };
}

function listQuery(r) {
  if (r.start === r.end) return `date=${encodeURIComponent(r.start)}`;
  return `from=${encodeURIComponent(r.start)}&to=${encodeURIComponent(r.end)}`;
}

async function loadWorkLog(cachedActive) {
  const wrap = document.getElementById("workLogWrap");
  const btn = document.getElementById("btnSyncWorkLog");
  const r = getRange();
  if (!r.start) {
    return;
  }
  Office.showTableLoading(wrap);
  try {
    const activeData = cachedActive || (await Office.fetchActiveStore());
    if (!activeData.store) {
      btn.disabled = true;
      wrap.innerHTML =
        `<p style="color:var(--muted);">${Office.icon("info-circle")}<span style="margin-left:0.35rem;">Επιλέξτε ενεργό κατάστημα (sidebar).</span></p>`;
      return;
    }
    btn.disabled = false;
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
    Office.updateSyncMetaLine("workLogSyncMeta", activeData.store, "worklog");
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
  headers.push("Ευελ. (λεπτά)", "Ψηφ. ωράριο", "Από", "Έως", "ΑΑ", "Κάρτα");
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
      row.schedule_label || "—",
      row.hour_from || "",
      row.hour_to || "",
      row.source_aa || "0"
    );
    cells.forEach((txt, i) => {
      const td = document.createElement("td");
      if (i === 1) {
        td.innerHTML = `<strong>${Office.escapeHtml(txt)}</strong>`;
      } else if (i === 2) {
        td.className = "work-log-name-cell";
        const span = document.createElement("span");
        span.textContent = txt;
        td.appendChild(span);
        Office.appendWorkLogHistoryButton(td, row);
      } else {
        td.textContent = txt;
      }
      tr.appendChild(td);
    });
    appendWorkCardLinkCell(tr, row, range);
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

function appendWorkCardLinkCell(tr, row, range) {
  const td = document.createElement("td");
  td.className = "work-log-action-cell";
  const afm = (row.employee_afm || "").trim();
  if (afm) {
    const dateIso =
      Office.erganiDateToIso(row.work_date) || range?.start || "";
    const name = `${row.eponymo || ""} ${row.onoma || ""}`.trim();
    const a = document.createElement("a");
    a.href = Office.workCardUrl(afm, dateIso, name);
    a.className = "work-log-card-link";
    a.title = "Ψηφιακή κάρτα";
    a.setAttribute("aria-label", `Ψηφιακή κάρτα — ${name || afm}`);
    a.innerHTML = Office.icon("credit-card-2-front");
    td.appendChild(a);
  }
  tr.appendChild(td);
}

async function maybeAutoSyncWorkLog(activeData) {
  if (initialAutoSyncDone) return false;
  initialAutoSyncDone = true;
  try {
    const data = activeData || (await Office.fetchActiveStore());
    const store = data.store;
    if (!store) return false;
    if (
      !Office.workLogNeedsAutoSync(
        store.work_log_last_sync_at,
        store.work_log_sync_interval_minutes
      )
    ) {
      return false;
    }
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
      const fresh = await Office.fetchActiveStore({ refresh: true });
      Office.applyActiveStoreChrome(fresh);
      await loadWorkLog(fresh);
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
