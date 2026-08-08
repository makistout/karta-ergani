document.addEventListener("DOMContentLoaded", () => {
  Office.setActiveNav("employees");
  const btn = document.getElementById("btnSyncContracts");
  if (btn) btn.onclick = () => runSync();
  document.querySelectorAll("[data-contract-history-close]").forEach((el) => {
    el.addEventListener("click", closeHistory);
  });
  loadContracts();
});

async function loadContracts() {
  const wrap = document.getElementById("contractsWrap");
  const btn = document.getElementById("btnSyncContracts");
  Office.showTableLoading(wrap);
  try {
    const activeData = await Office.fetchActiveStore
      ? await Office.fetchActiveStore()
      : await (await fetch("/api/store/active", { cache: "no-store" })).json();
    if (Office.applyActiveStoreChrome) {
      Office.applyActiveStoreChrome(activeData);
    } else {
      await Office.loadActiveStore();
    }
    if (!activeData.store) {
      if (btn) btn.disabled = true;
      wrap.innerHTML =
        `<p style="color:var(--muted);">${Office.icon("info-circle")}<span style="margin-left:0.35rem;">Επιλέξτε ενεργό κατάστημα.</span></p>`;
      return;
    }
    if (btn) btn.disabled = false;
    const res = await fetch("/api/employees/contract/list", { cache: "no-store" });
    const data = await res.json();
    if (!res.ok) {
      wrap.innerHTML = `<p style="color:var(--err);">${Office.escapeHtml(data.error || "Σφάλμα")}</p>`;
      if (data.db_setup) {
        wrap.innerHTML += `<p style="font-size:0.85rem;color:var(--muted);">${Office.escapeHtml(data.db_setup)}</p>`;
      }
      return;
    }
    renderTable(data.contracts || [], data.store);
  } catch (e) {
    wrap.innerHTML = `<p style="color:var(--err);">${Office.escapeHtml(String(e))}</p>`;
  }
}

function cell(text) {
  const td = document.createElement("td");
  td.textContent = text == null || text === "" ? "—" : String(text);
  return td;
}

function renderTable(rows, store) {
  const wrap = document.getElementById("contractsWrap");
  if (!rows.length) {
    wrap.innerHTML =
      `<p style="color:var(--muted);">${Office.icon("file-earmark")}<span style="margin-left:0.35rem;">Δεν υπάρχουν εγγραφές. Πατήστε «Συγχρονισμός από Ergani».</span></p>`;
    return;
  }
  const storeLine = store
    ? `<p class="table-meta">${Office.icon("shop-window")} <strong>${Office.escapeHtml(store.name)}</strong> · ${rows.length} τρέχουσες συμβάσεις</p>`
    : "";
  const t = document.createElement("table");
  t.className = "data";
  const headers = [
    "ΑΦΜ εργοδότη",
    "Παράρτημα",
    "ΑΦΜ",
    "Επώνυμο",
    "Όνομα",
    "Ειδικότητα",
    "ΣΤΕΠ 92",
    "Ώρες/εβδ.",
    "Αποδοχές",
    "Ευελ.",
    "Ενημ. Ergani",
    "",
  ];
  const hr = document.createElement("tr");
  headers.forEach((h) => {
    const th = document.createElement("th");
    th.textContent = h;
    hr.appendChild(th);
  });
  t.appendChild(hr);

  rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.appendChild(cell(row.employer_afm));
    tr.appendChild(cell(row.branch_aa));
    tr.appendChild(cell(row.employee_afm));
    tr.appendChild(cell(row.eponymo));
    tr.appendChild(cell(row.onoma));
    tr.appendChild(cell(row.specialty));
    tr.appendChild(cell(row.step92));
    tr.appendChild(cell(row.weekly_hours));
    tr.appendChild(cell(row.salary));
    tr.appendChild(
      cell(
        row.flex_arrival_minutes == null
          ? "—"
          : Office.formatFlexMinutes
            ? Office.formatFlexMinutes(row.flex_arrival_minutes)
            : `${row.flex_arrival_minutes}′`
      )
    );
    tr.appendChild(cell(row.ergani_updated_at));
    const tdAct = document.createElement("td");
    tdAct.className = "work-log-action-cell";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn btn-sm btn-secondary";
    btn.title = "Ιστορικό σύμβασης";
    btn.innerHTML = Office.icon("clock-history");
    btn.addEventListener("click", () => openHistory(row));
    tdAct.appendChild(btn);
    tr.appendChild(tdAct);
    t.appendChild(tr);
  });

  wrap.innerHTML = storeLine;
  wrap.appendChild(t);
}

function closeHistory() {
  document.getElementById("contractHistoryModal")?.classList.add("hidden");
}

async function openHistory(row) {
  const modal = document.getElementById("contractHistoryModal");
  const titleEmp = document.getElementById("contractHistoryEmployee");
  const histWrap = document.getElementById("contractHistoryWrap");
  modal.classList.remove("hidden");
  titleEmp.textContent = `${row.eponymo || ""} ${row.onoma || ""} · ΑΦΜ ${row.employee_afm || ""}`.trim();
  Office.showTableLoading(histWrap);
  try {
    const res = await fetch(
      `/api/employees/contract/history?employee_afm=${encodeURIComponent(row.employee_afm || "")}`,
      { cache: "no-store" }
    );
    const data = await res.json();
    if (!res.ok) {
      histWrap.innerHTML = `<p style="color:var(--err);">${Office.escapeHtml(data.error || "Σφάλμα")}</p>`;
      return;
    }
    const rows = data.contracts || [];
    if (!rows.length) {
      histWrap.innerHTML = `<p style="color:var(--muted);">Δεν υπάρχει ιστορικό.</p>`;
      return;
    }
    const t = document.createElement("table");
    t.className = "data";
    const hr = document.createElement("tr");
    ["Συγχρονισμός", "Ενημ. Ergani", "Ειδικότητα", "Ώρες", "Αποδοχές", "Ευελ.", "Τρέχουσα"].forEach((h) => {
      const th = document.createElement("th");
      th.textContent = h;
      hr.appendChild(th);
    });
    t.appendChild(hr);
    rows.forEach((r) => {
      const tr = document.createElement("tr");
      tr.appendChild(cell((r.synced_at || "").toString().replace("T", " ").slice(0, 16)));
      tr.appendChild(cell(r.ergani_updated_at));
      tr.appendChild(cell(r.specialty));
      tr.appendChild(cell(r.weekly_hours));
      tr.appendChild(cell(r.salary));
      tr.appendChild(cell(r.flex_arrival_minutes));
      tr.appendChild(cell(r.is_current ? "Ναι" : ""));
      t.appendChild(tr);
    });
    histWrap.innerHTML = "";
    histWrap.appendChild(t);
  } catch (e) {
    histWrap.innerHTML = `<p style="color:var(--err);">${Office.escapeHtml(String(e))}</p>`;
  }
}

async function runSync() {
  if (Office.beginSyncPanel) {
    Office.beginSyncPanel("contractsWrap", "contractMsg");
  }
  try {
    const payload = await Office.runPortalSync({
      url: "/api/employees/contract/sync",
      body: {},
      msgId: "contractMsg",
      btnId: "btnSyncContracts",
      startMessage: "Συγχρονισμός στοιχείων σύμβασης από Μητρώα",
    });
    const result = Office.buildSyncResultMessage
      ? Office.buildSyncResultMessage(payload, Office.portalHostFromSync)
      : {
          ok: Boolean(payload?.success || payload?.sync?.success),
          text: payload?.error || payload?.sync?.detail || "Ολοκληρώθηκε",
        };
    if (Office.endSyncPanel) {
      Office.endSyncPanel("contractsWrap", "contractMsg");
    }
    if (result.ok) {
      await loadContracts();
    }
    Office.showMsg("contractMsg", result.text, result.ok);
  } catch (e) {
    if (Office.endSyncPanel) {
      Office.endSyncPanel("contractsWrap", "contractMsg");
    }
    Office.showMsg("contractMsg", String(e), false);
  }
}
