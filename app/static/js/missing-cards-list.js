let tableState = {
  page: 1,
  total: 0,
  totalPages: 1,
  pageSize: Office.TABLE_PAGE_SIZE,
  store: null,
  excludeDate: "",
};

document.addEventListener("DOMContentLoaded", async () => {
  Office.setActiveNav("missingcards");
  Office.initWorkLogHistoryModal();
  const activeData = await Office.fetchActiveStore();
  Office.applyActiveStoreChrome(activeData);
  await loadMissingCards(1, activeData);
});

async function loadMissingCards(page, cachedActive) {
  const wrap = document.getElementById("missingCardsWrap");
  const desc = document.getElementById("missingCardsDesc");
  Office.showTableLoading(wrap);
  try {
    const activeData = cachedActive || (await Office.fetchActiveStore());
    if (!activeData.store) {
      wrap.innerHTML =
        `<p style="color:var(--muted);">${Office.icon("info-circle")}<span style="margin-left:0.35rem;">Επιλέξτε ενεργό κατάστημα (sidebar).</span></p>`;
      return;
    }
    const res = await fetch(
      `/api/work-log/missing-cards?page=${encodeURIComponent(page)}&page_size=${Office.TABLE_PAGE_SIZE}`,
      { cache: "no-store" }
    );
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
    tableState = {
      page: data.page || page,
      total: data.total || 0,
      totalPages: data.total_pages || 1,
      pageSize: data.page_size || Office.TABLE_PAGE_SIZE,
      store: data.store,
      excludeDate: data.exclude_date || "",
    };
    if (desc && data.exclude_date) {
      desc.textContent =
        `Εγγραφές πριν από σήμερα (${data.exclude_date}) με έλλειψη ώρας εισόδου ή εξόδου στην πραγματική απασχόληση (νεότερες πρώτα).`;
    }
    renderTablePage(data.work_log || []);
  } catch (e) {
    wrap.innerHTML = `<p style="color:var(--err);">${Office.escapeHtml(String(e))}</p>`;
  }
}

function renderTablePage(rows) {
  const wrap = document.getElementById("missingCardsWrap");
  const { store, page, total, totalPages, pageSize } = tableState;

  if (!total) {
    wrap.innerHTML =
      `<p style="color:var(--muted);">${Office.icon("check-circle")}<span style="margin-left:0.35rem;">Δεν υπάρχουν ελλιπή χτυπήματα πριν από σήμερα.</span></p>`;
    return;
  }

  const storeLine = store
    ? `<p class="table-meta">${Office.icon("shop-window")} <strong>${Office.escapeHtml(store.name)}</strong> · ${total} εγγραφές συνολικά</p>`
    : "";

  const t = document.createElement("table");
  t.className = "data";
  const headers = [
    "ΑΦΜ",
    "Επώνυμο",
    "Όνομα",
    "Ημερομηνία",
    "Ευελ. (λεπτά)",
    "Ψηφ. ωράριο",
    "Από",
    "Έως",
    "Κάρτα",
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
    if (Office.workLogRowIsDeficient(row)) {
      tr.classList.add("work-log-row--deficient");
    }
    const cells = [
      row.employee_afm || "",
      row.eponymo || "",
      row.onoma || "",
      row.work_date || "",
      Office.formatFlexMinutes(row.flex_arrival_minutes),
      row.schedule_label || "—",
      row.hour_from || "",
      row.hour_to || "",
    ];
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
    appendWorkCardLinkCell(tr, row);
    t.appendChild(tr);
  });

  wrap.innerHTML = storeLine;
  wrap.appendChild(t);
  if (totalPages > 1) {
    wrap.appendChild(
      Office.buildTablePager(page, totalPages, total, (p) => loadMissingCards(p), pageSize)
    );
  }
}

function appendWorkCardLinkCell(tr, row) {
  const td = document.createElement("td");
  td.className = "work-log-action-cell";
  if (!Office.shouldShowWorkCardLink(row)) {
    tr.appendChild(td);
    return;
  }
  const afm = (row.employee_afm || "").trim();
  const dateIso = Office.erganiDateToIso(row.work_date) || "";
  const name = `${row.eponymo || ""} ${row.onoma || ""}`.trim();
  const opts = {};
  if (row.needs_card_punch && row.retro_time) {
    opts.retro = true;
    opts.retro_time = row.retro_time;
    opts.card_event = row.card_event || "check_out";
    opts.retro_highlight = true;
  }
  const a = document.createElement("a");
  a.href = Office.workCardUrl(afm, dateIso, name, opts);
  a.className = row.needs_card_punch
    ? "work-log-card-link work-log-card-link--required"
    : "work-log-card-link";
  a.title = "Ψηφιακή κάρτα";
  a.setAttribute("aria-label", `Ψηφιακή κάρτα — ${name || afm}`);
  a.innerHTML = Office.icon("credit-card-2-front");
  td.appendChild(a);
  tr.appendChild(td);
}
