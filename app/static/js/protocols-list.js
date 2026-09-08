let datePicker = null;
let tableState = {
  rows: [],
  page: 1,
  count: 0,
  store: null,
  range: null,
  typeFilter: "",
};

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
  const typeFilter = document.getElementById("protocolsTypeFilter");
  if (typeFilter) {
    typeFilter.addEventListener("change", () => {
      tableState.typeFilter = String(typeFilter.value || "");
      tableState.page = 1;
      renderTablePage();
    });
  }
  bindProtocolPdfModal();

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
        `Κατάλογος πρωτοκόλλων Ergani (κάρτα & οργάνωση χρόνου) · ${data.store.name || ""}`;
    }
  } catch (e) {
    wrap.innerHTML = `<p style="color:var(--err);">${Office.formatMultilineHtml(String(e))}</p>`;
  }
}

function declarationTypeKey(row) {
  return String(row?.declaration_type || "").trim();
}

function uniqueDeclarationTypes(rows) {
  const seen = new Set();
  const out = [];
  (rows || []).forEach((row) => {
    const key = declarationTypeKey(row);
    if (!key || seen.has(key)) return;
    seen.add(key);
    out.push(key);
  });
  out.sort((a, b) => a.localeCompare(b, "el"));
  return out;
}

function rebuildTypeFilterOptions(rows) {
  const select = document.getElementById("protocolsTypeFilter");
  if (!select) return;
  const prev = tableState.typeFilter || "";
  const types = uniqueDeclarationTypes(rows);
  select.innerHTML = "";
  const allOpt = document.createElement("option");
  allOpt.value = "";
  allOpt.textContent = types.length ? `Όλα (${rows.length})` : "Όλα";
  select.appendChild(allOpt);
  types.forEach((type) => {
    const count = rows.filter((r) => declarationTypeKey(r) === type).length;
    const opt = document.createElement("option");
    opt.value = type;
    opt.title = type;
    const short =
      type.length > 56 ? `${type.slice(0, 53)}…` : type;
    opt.textContent = `${short} (${count})`;
    select.appendChild(opt);
  });
  select.disabled = !rows.length;
  if (prev && types.includes(prev)) {
    select.value = prev;
    tableState.typeFilter = prev;
  } else {
    select.value = "";
    tableState.typeFilter = "";
  }
}

function filteredProtocolRows() {
  const filter = String(tableState.typeFilter || "").trim();
  const rows = Array.isArray(tableState.rows) ? tableState.rows : [];
  if (!filter) return rows;
  return rows.filter((row) => declarationTypeKey(row) === filter);
}

function renderTable(rows, count, store, range) {
  const safeRows = Array.isArray(rows) ? rows : [];
  tableState = {
    ...tableState,
    rows: safeRows,
    page: 1,
    count: Number(count) || safeRows.length,
    store,
    range,
  };
  rebuildTypeFilterOptions(safeRows);
  renderTablePage();
}

function renderTablePage() {
  const wrap = document.getElementById("protocolsWrap");
  if (!wrap) return;
  const { store } = tableState;
  const allRows = Array.isArray(tableState.rows) ? tableState.rows : [];
  const rows = filteredProtocolRows();
  const pg = Office.paginateSlice(rows, tableState.page, 50);
  tableState.page = pg.page;

  const filterNote = tableState.typeFilter
    ? ` · φίλτρο: ${rows.length}/${allRows.length}`
    : "";
  const storeLine = store
    ? `<p class="table-meta">${Office.icon("shop-window")} <strong>${Office.escapeHtml(store.name)}</strong> · ${rows.length} πρωτόκολλα${Office.escapeHtml(filterNote)}</p>`
    : "";

  if (!rows.length) {
    wrap.innerHTML =
      storeLine +
      `<p style="color:var(--muted);">${Office.icon("info-circle")}<span style="margin-left:0.35rem;">` +
      (allRows.length
        ? "Δεν υπάρχουν πρωτόκολλα για το επιλεγμένο είδος δήλωσης."
        : "Δεν βρέθηκαν πρωτόκολλα για το διάστημα.") +
      `</span></p>`;
    return;
  }

  const headers = [
    "Αρ. πρωτοκόλλου",
    "Ημ/νία υποβολής",
    "Τύπος δήλωσης",
    "Κατάσταση",
    "Εκπρόθεσμο",
    "Παράρτημα",
    "PDF",
  ];

  const t = document.createElement("table");
  t.className = "data";
  const thead = document.createElement("thead");
  const hr = document.createElement("tr");
  headers.forEach((h) => {
    const th = document.createElement("th");
    th.textContent = h;
    if (h === "PDF") th.style.textAlign = "center";
    hr.appendChild(th);
  });
  thead.appendChild(hr);
  t.appendChild(thead);

  const tbody = document.createElement("tbody");
  pg.items.forEach((row) => {
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

    const pdfTd = document.createElement("td");
    pdfTd.className = "protocol-pdf-cell";
    if (row.has_pdf && row.pdf_url) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "protocol-pdf-btn";
      btn.title = "Προβολή PDF";
      btn.setAttribute("aria-label", `PDF ${row.protocol || ""}`);
      btn.innerHTML = Office.icon("file-earmark-pdf");
      btn.addEventListener("click", () => openProtocolPdfModal(row));
      pdfTd.appendChild(btn);
    } else {
      pdfTd.textContent = "—";
      pdfTd.style.color = "var(--muted)";
    }
    tr.appendChild(pdfTd);
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
  const m = raw.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
  if (m) return `${m[3]}/${m[2]}/${m[1]} ${m[4]}:${m[5]}`;
  return raw;
}

function formatOverdue(value) {
  if (value === true || value === 1 || value === "1") return "Ναι";
  if (value === false || value === 0 || value === "0") return "Όχι";
  return "—";
}

function bindProtocolPdfModal() {
  const modal = document.getElementById("protocolPdfModal");
  if (!modal || modal.dataset.bound) return;
  modal.dataset.bound = "1";
  modal.querySelectorAll("[data-protocol-pdf-close]").forEach((el) => {
    el.addEventListener("click", closeProtocolPdfModal);
  });
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && !modal.classList.contains("hidden")) {
      closeProtocolPdfModal();
    }
  });
}

function openProtocolPdfModal(row) {
  const modal = document.getElementById("protocolPdfModal");
  const frame = document.getElementById("protocolPdfFrame");
  const sub = document.getElementById("protocolPdfSub");
  const openTab = document.getElementById("protocolPdfOpenTab");
  const url = row.pdf_url;
  if (!modal || !frame || !url) return;
  if (sub) {
    sub.textContent = `${row.protocol || ""} · ${formatSubmitAt(row)}`;
  }
  frame.src = url;
  if (openTab) openTab.href = url;
  modal.classList.remove("hidden");
}

function closeProtocolPdfModal() {
  const modal = document.getElementById("protocolPdfModal");
  const frame = document.getElementById("protocolPdfFrame");
  if (frame) frame.src = "about:blank";
  modal?.classList.add("hidden");
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
