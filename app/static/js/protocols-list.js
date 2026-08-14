let datePicker = null;
let tableState = { rows: [], page: 1, count: 0, store: null, range: null };

document.addEventListener("DOMContentLoaded", async () => {
  Office.setActiveNav("protocols");
  datePicker = Office.createDatePicker({
    mountId: "protocolsDatePicker",
    mode: "range",
    quickPresets: ["yesterday", "today", "last7", "last30"],
    onApply: () => loadProtocols(),
  });
  const btnSync = document.getElementById("btnSyncProtocols");
  if (btnSync) btnSync.onclick = () => runSync();

  try {
    const activeData = await Office.fetchActiveStore();
    Office.applyActiveStoreChrome(activeData);
    await loadProtocols(activeData);
  } catch (e) {
    const wrap = document.getElementById("protocolsWrap");
    if (wrap) {
      wrap.innerHTML = `<p style="color:var(--err);">${Office.formatMultilineHtml(String(e))}</p>`;
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

async function loadProtocols(cachedActive) {
  const wrap = document.getElementById("protocolsWrap");
  const btn = document.getElementById("btnSyncProtocols");
  const r = getRange();
  if (!r.start) return;
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
    const res = await fetch(`/api/protocols/list?${listQuery(r)}`);
    let data = {};
    try {
      data = await res.json();
    } catch {
      wrap.innerHTML = `<p style="color:var(--err);">Σφάλμα διακομιστή (HTTP ${res.status}).</p>`;
      return;
    }
    if (!res.ok) {
      wrap.innerHTML = `<p style="color:var(--err);">${Office.formatMultilineHtml(data.error || "Σφάλμα")}</p>`;
      if (data.db_setup) {
        wrap.innerHTML += `<p style="font-size:0.85rem;color:var(--muted);margin-top:0.5rem;">${Office.escapeHtml(data.db_setup)}</p>`;
      }
      return;
    }
    renderTable(data.protocols || [], data.count || 0, data.store, r);
    const meta = document.getElementById("protocolsSyncMeta");
    if (meta && data.store) {
      meta.textContent =
        `Κατάλογος πρωτοκόλλων Ergani (WorkCardSearch) · ${data.store.name || ""}`;
    }
  } catch (e) {
    wrap.innerHTML = `<p style="color:var(--err);">${Office.formatMultilineHtml(String(e))}</p>`;
  }
}

function renderTable(rows, count, store, range) {
  tableState = { rows, page: 1, count, store, range };
  renderTablePage();
}

function renderTablePage() {
  const wrap = document.getElementById("protocolsWrap");
  if (!wrap) return;
  const { rows, store, range } = tableState;
  const pg = Office.paginateSlice(rows, tableState.page, 50);
  tableState.page = pg.page;

  const storeLine = store
    ? `<p class="table-meta">${Office.icon("shop-window")} <strong>${Office.escapeHtml(store.name)}</strong> · ${rows.length} πρωτόκολλα</p>`
    : "";

  if (!rows.length) {
    wrap.innerHTML =
      storeLine +
      `<p style="color:var(--muted);">${Office.icon("info-circle")}<span style="margin-left:0.35rem;">Δεν βρέθηκαν πρωτόκολλα για το διάστημα.</span></p>`;
    return;
  }

  const headers = [
    "Αρ. πρωτοκόλλου",
    "Ημ/νία υποβολής",
    "Τύπος δήλωσης",
    "Κατάσταση",
    "Εκπρόθεσμο",
    "Παράρτημα",
  ];

  const t = document.createElement("table");
  t.className = "data";
  const thead = document.createElement("thead");
  const hr = document.createElement("tr");
  headers.forEach((h) => {
    const th = document.createElement("th");
    th.textContent = h;
    hr.appendChild(th);
  });
  thead.appendChild(hr);
  t.appendChild(thead);

  const tbody = document.createElement("tbody");
  pg.slice.forEach((row) => {
    const tr = document.createElement("tr");
    const cells = [
      row.protocol || "",
      formatSubmitAt(row),
      row.declaration_type || "—",
      row.submission_status || "—",
      formatOverdue(row.overdue),
      row.branch_aa || "—",
    ];
    cells.forEach((txt, i) => {
      const td = document.createElement("td");
      if (i === 0) {
        td.innerHTML = `<strong>${Office.escapeHtml(txt)}</strong>`;
      } else {
        td.textContent = txt;
      }
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  t.appendChild(tbody);

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

function formatSubmitAt(row) {
  const text = String(row.submit_date_text || "").trim();
  if (text) return text;
  const raw = String(row.submit_at || "").trim();
  if (!raw) return "—";
  // 2026-08-14T08:22:00 or with Z
  const m = raw.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
  if (m) return `${m[3]}/${m[2]}/${m[1]} ${m[4]}:${m[5]}`;
  return raw;
}

function formatOverdue(value) {
  if (value === true || value === 1 || value === "1") return "Ναι";
  if (value === false || value === 0 || value === "0") return "Όχι";
  return "—";
}

async function runSync() {
  const r = getRange();
  const body = r.start === r.end ? { date: r.start } : { from: r.start, to: r.end };
  Office.beginSyncPanel("protocolsWrap", "protocolsMsg");
  try {
    const payload = await Office.runPortalSync({
      url: "/api/protocols/sync",
      body,
      msgId: "protocolsMsg",
      btnId: "btnSyncProtocols",
      startMessage: "Συγχρονισμός πρωτοκόλλων Ergani",
    });
    const result = Office.buildSyncResultMessage(payload, Office.portalHostFromSync);
    Office.endSyncPanel("protocolsWrap", "protocolsMsg");
    if (result.ok) {
      Office.showMsg("protocolsMsg", result.text, true);
      await loadProtocols();
    } else {
      Office.showMsg("protocolsMsg", result.text, false);
    }
  } catch (e) {
    Office.endSyncPanel("protocolsWrap", "protocolsMsg");
    Office.showMsg("protocolsMsg", String(e), false);
  }
}
