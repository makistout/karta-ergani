let datePicker = null;
let tableState = { rows: [], page: 1, count: 0, store: null, range: null };

document.addEventListener("DOMContentLoaded", async () => {
  Office.setActiveNav("worklog");
  Office.initWorkLogHistoryModal();
  datePicker = Office.createDatePicker({
    mountId: "workLogDatePicker",
    mode: "range",
    onApply: () => loadWorkLog(),
  });
  document.getElementById("btnSyncWorkLog").onclick = () => runSync();

  try {
    const activeData = await Office.fetchActiveStore();
    Office.applyActiveStoreChrome(activeData);
    await loadWorkLog(activeData);
  } catch (e) {
    const wrap = document.getElementById("workLogWrap");
    if (wrap) {
      wrap.innerHTML = `<p style="color:var(--err);">${Office.escapeHtml(String(e))}</p>`;
    }
  }
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
  const headers = ["ΑΦΜ", "", "Επώνυμο", "Όνομα"];
  if (multi) headers.push("Ημερομηνία");
  headers.push("Ευελ. (λεπτά)", "Ψηφ. ωράριο", "Από", "Έως", "Κάρτα");
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
    Office.decorateWorkLogTableRow(tr, row);
    const tdAfm = document.createElement("td");
    tdAfm.innerHTML = `<strong>${Office.escapeHtml(row.employee_afm || "")}</strong>`;
    tr.appendChild(tdAfm);
    tr.appendChild(Office.createWorkLogHistoryCell(row));

    const cells = [row.eponymo || "", row.onoma || ""];
    if (multi) cells.push(row.work_date || "");
    cells.push(
      Office.formatFlexMinutes(row.flex_arrival_minutes),
      row.schedule_label || "—",
      row.hour_from || "",
      row.hour_to || ""
    );
    cells.forEach((txt, i) => {
      const td = document.createElement("td");
      const colHourFrom = multi ? 5 : 4;
      const colHourTo = multi ? 6 : 5;
      if (i === 0) {
        td.innerHTML = Office.formatWorkLogEponymoCell(row);
      } else if (i === colHourFrom) {
        td.innerHTML = Office.formatWorkLogTimeCell(txt, "Λείπει ώρα εισόδου").html;
      } else if (i === colHourTo) {
        const pending = Office.workLogExitStillPending(row);
        td.innerHTML = Office.formatWorkLogTimeCell(
          txt,
          pending ? "Έξοδος μετά το τέλος βάρδιας" : "Λείπει ώρα εξόδου"
        ).html;
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
  if (Office.shouldShowWorkCardLink(row)) {
    const afm = (row.employee_afm || "").trim();
    const dateIso =
      Office.erganiDateToIso(row.work_date) || range?.start || "";
    const name = `${row.eponymo || ""} ${row.onoma || ""}`.trim();
    const opts = Office.workCardUrlOptsFromRow(row);
    const a = document.createElement("a");
    a.href = Office.workCardUrl(afm, dateIso, name, opts);
    a.className = opts.retro
      ? "work-log-card-link work-log-card-link--required"
      : "work-log-card-link";
    a.title = "Ψηφιακή κάρτα";
    a.setAttribute("aria-label", `Ψηφιακή κάρτα — ${name || afm}`);
    a.innerHTML = Office.icon("credit-card-2-front");
    td.appendChild(a);
  }
  tr.appendChild(td);
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
