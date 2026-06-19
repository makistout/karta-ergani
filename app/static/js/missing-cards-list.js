let tableState = {
  page: 1,
  total: 0,
  totalPages: 1,
  pageSize: Office.TABLE_PAGE_SIZE,
  closedPage: 1,
  closedTotal: 0,
  closedTotalPages: 1,
  closedPageSize: Office.TABLE_PAGE_SIZE,
  store: null,
  excludeDate: "",
};

document.addEventListener("DOMContentLoaded", async () => {
  Office.setActiveNav("missingcards");
  Office.initWorkLogHistoryModal();
  const activeData = await Office.fetchActiveStore();
  Office.applyActiveStoreChrome(activeData);
  await loadMissingCards(1, 1, activeData);
});

async function loadMissingCards(page, closedPage = 1, cachedActive) {
  const wrap = document.getElementById("missingCardsWrap");
  const closedWrap = document.getElementById("missingCardsClosedWrap");
  const desc = document.getElementById("missingCardsDesc");
  Office.showTableLoading(wrap);
  Office.showTableLoading(closedWrap);
  try {
    const activeData = cachedActive || (await Office.fetchActiveStore());
    if (!activeData.store) {
      const noStore =
        `<p style="color:var(--muted);">${Office.icon("info-circle")}<span style="margin-left:0.35rem;">Επιλέξτε ενεργό κατάστημα (sidebar).</span></p>`;
      wrap.innerHTML = noStore;
      if (closedWrap) closedWrap.innerHTML = noStore;
      return;
    }
    const qs = new URLSearchParams({
      page: String(page),
      page_size: String(Office.TABLE_PAGE_SIZE),
      closed_page: String(closedPage),
      closed_page_size: String(Office.TABLE_PAGE_SIZE),
    });
    const res = await fetch(`/api/work-log/missing-cards?${qs}`, { cache: "no-store" });
    let data = {};
    try {
      data = await res.json();
    } catch {
      wrap.innerHTML = `<p style="color:var(--err);">Σφάλμα διακομιστή (HTTP ${res.status}).</p>`;
      if (closedWrap) closedWrap.innerHTML = "";
      return;
    }
    if (!res.ok) {
      const err = `<p style="color:var(--err);">${Office.escapeHtml(data.error || "Σφάλμα")}</p>`;
      wrap.innerHTML = err;
      if (closedWrap) closedWrap.innerHTML = err;
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
      closedPage: data.closed_page || closedPage,
      closedTotal: data.closed_total || 0,
      closedTotalPages: data.closed_total_pages || 1,
      closedPageSize: data.closed_page_size || Office.TABLE_PAGE_SIZE,
      store: data.store,
      excludeDate: data.exclude_date || "",
    };
    if (desc && data.exclude_date) {
      desc.textContent =
        `Εγγραφές πριν από σήμερα (${data.exclude_date}) με έλλειψη στην πραγματική portal — χωρίς αντίστοιχη δήλωση κάρτας στη βάση erganiOS (νεότερες πρώτα).`;
    }
    renderTablePage(data.work_log || []);
    renderClosedTablePage(data.closed_work_log || []);
  } catch (e) {
    wrap.innerHTML = `<p style="color:var(--err);">${Office.escapeHtml(String(e))}</p>`;
    if (closedWrap) closedWrap.innerHTML = "";
  }
}

function renderTablePage(rows) {
  const wrap = document.getElementById("missingCardsWrap");
  const { store, page, total, totalPages, pageSize } = tableState;

  if (!total) {
    wrap.innerHTML =
      `<p style="color:var(--muted);">${Office.icon("check-circle")}<span style="margin-left:0.35rem;">Δεν υπάρχουν εκκρεμή ελλιπή χτυπήματα πριν από σήμερα.</span></p>`;
    return;
  }

  const storeLine = store
    ? `<p class="table-meta">${Office.icon("shop-window")} <strong>${Office.escapeHtml(store.name)}</strong> · ${total} εκκρεμείς</p>`
    : "";

  const t = buildPendingTable(rows);
  wrap.innerHTML = storeLine;
  wrap.appendChild(t);
  if (totalPages > 1) {
    wrap.appendChild(
      Office.buildTablePager(page, totalPages, total, (p) => loadMissingCards(p, tableState.closedPage), pageSize)
    );
  }
}

function buildPendingTable(rows) {
  const t = document.createElement("table");
  t.className = "data";
  const columns = [
    { text: "ΑΦΜ" },
    { aria: "Ιστορικό", className: "col-history" },
    { text: "Επώνυμο" },
    { text: "Όνομα" },
    { text: "Ημερομηνία" },
    { text: "Ευελ. (λεπτά)" },
    { text: "Ψηφ. ωράριο" },
    { text: "Από" },
    { text: "Έως" },
    { text: "Κάρτα" },
    { aria: "Ειδοποίηση", className: "work-log-action-cell--notify", icon: "bell" },
  ];
  const hr = document.createElement("tr");
  columns.forEach((col) => {
    const th = document.createElement("th");
    if (col.className) th.className = col.className;
    if (col.icon) {
      th.innerHTML = Office.icon(col.icon);
      th.setAttribute("aria-label", col.aria || "");
    } else if (col.aria) {
      th.setAttribute("aria-label", col.aria);
    } else {
      th.textContent = col.text || "";
    }
    hr.appendChild(th);
  });
  t.appendChild(hr);

  rows.forEach((row) => {
    const tr = document.createElement("tr");
    Office.decorateWorkLogTableRow(tr, row);
    const tdAfm = document.createElement("td");
    tdAfm.innerHTML = `<strong>${Office.escapeHtml(row.employee_afm || "")}</strong>`;
    tr.appendChild(tdAfm);
    tr.appendChild(Office.createWorkLogHistoryCell(row));

    const cells = [
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
      if (i === 0) {
        td.innerHTML = Office.formatWorkLogEponymoCell(row);
      } else if (i === 5) {
        td.innerHTML = Office.formatWorkLogTimeCell(txt, "Λείπει ώρα εισόδου").html;
      } else if (i === 6) {
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
    appendWorkCardLinkCell(tr, row);
    appendNotifyCell(tr, row);
    t.appendChild(tr);
  });
  return t;
}

function formatCardDbCell(entry) {
  if (!entry || !entry.time) return "—";
  let html = `<span class="missing-cards-db-time">${Office.escapeHtml(entry.time)}</span>`;
  if (entry.protocol) {
    html += `<br><span class="table-meta">${Office.escapeHtml(entry.protocol)}</span>`;
  } else if (entry.from_token) {
    html += `<br><span class="table-meta">ολοκλ. retro-hit</span>`;
  }
  const recorded = String(entry.recorded_at || "").trim();
  if (recorded) {
    html += `<span class="missing-cards-recorded-at">καταγραφή ${Office.escapeHtml(recorded)}</span>`;
  }
  return html;
}

function renderClosedTablePage(rows) {
  const wrap = document.getElementById("missingCardsClosedWrap");
  if (!wrap) return;
  const { store, closedPage, closedTotal, closedTotalPages, closedPageSize } = tableState;

  if (!closedTotal) {
    wrap.innerHTML =
      `<p style="color:var(--muted);">${Office.icon("info-circle")}<span style="margin-left:0.35rem;">Δεν υπάρχουν ολοκληρωμένα χτυπήματα στη βάση για ελλιπή πραγματική.</span></p>`;
    return;
  }

  const storeLine = store
    ? `<p class="table-meta">${Office.icon("check-circle")} <strong>${Office.escapeHtml(store.name)}</strong> · ${closedTotal} ολοκληρωμένα χτυπήματα</p>`
    : "";

  const t = document.createElement("table");
  t.className = "data missing-cards-closed-table";
  const headers = [
    "ΑΦΜ",
    "Ιστορικό",
    "Επώνυμο",
    "Όνομα",
    "Ημερομηνία",
    "Πραγμ. Από",
    "Πραγμ. Έως",
    "Καταχ. είσοδος",
    "Καταχ. έξοδος",
  ];
  const hr = document.createElement("tr");
  headers.forEach((h, i) => {
    const th = document.createElement("th");
    if (i === 1) {
      th.className = "col-history";
      th.setAttribute("aria-label", "Ιστορικό");
    } else {
      th.textContent = h;
    }
    hr.appendChild(th);
  });
  t.appendChild(hr);

  rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.classList.add("work-log-row--resolved-db");
    const tdAfm = document.createElement("td");
    tdAfm.innerHTML = `<strong>${Office.escapeHtml(row.employee_afm || "")}</strong>`;
    tr.appendChild(tdAfm);
    tr.appendChild(Office.createWorkLogHistoryCell(row));

    const tdName = document.createElement("td");
    tdName.innerHTML = Office.formatWorkLogEponymoCell(row);
    tr.appendChild(tdName);

    const tdOnoma = document.createElement("td");
    tdOnoma.textContent = row.onoma || "";
    tr.appendChild(tdOnoma);

    const tdDate = document.createElement("td");
    tdDate.textContent = row.work_date || "";
    tr.appendChild(tdDate);

    const tdFrom = document.createElement("td");
    tdFrom.innerHTML = Office.formatWorkLogTimeCell(row.hour_from || "", "Λείπει στην πραγματική").html;
    tr.appendChild(tdFrom);

    const tdTo = document.createElement("td");
    tdTo.innerHTML = Office.formatWorkLogTimeCell(row.hour_to || "", "Λείπει στην πραγματική").html;
    tr.appendChild(tdTo);

    const tdDbIn = document.createElement("td");
    tdDbIn.innerHTML = formatCardDbCell(row.card_db_in);
    tr.appendChild(tdDbIn);

    const tdDbOut = document.createElement("td");
    tdDbOut.innerHTML = formatCardDbCell(row.card_db_out);
    tr.appendChild(tdDbOut);

    t.appendChild(tr);
  });

  wrap.innerHTML = storeLine;
  wrap.appendChild(t);
  if (closedTotalPages > 1) {
    wrap.appendChild(
      Office.buildTablePager(
        closedPage,
        closedTotalPages,
        closedTotal,
        (p) => loadMissingCards(tableState.page, p),
        closedPageSize
      )
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
  tr.appendChild(td);
}

async function sendMissingPunchNotify(row, btn) {
  const summary = Office.workLogMissingPunchSummary(row);
  if (!summary || summary === "έξοδος εκκρεμεί") {
    Office.showMsg(
      "missingCardsMsg",
      "Δεν αποστέλλεται ειδοποίηση όταν η έξοδος εκκρεμεί (βάρδια σε εξέλιξη).",
      false
    );
    return;
  }
  const name = `${row.eponymo || ""} ${row.onoma || ""}`.trim() || row.employee_afm;
  if (btn) btn.disabled = true;
  Office.showLoading("missingCardsMsg", `Αποστολή ειδοποίησης για ${name}…`);
  try {
    const res = await fetch("/api/telegram/notify/missing-punch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        employee_afm: row.employee_afm,
        work_date: row.work_date,
        eponymo: row.eponymo,
        onoma: row.onoma,
        hour_from: row.hour_from,
        hour_to: row.hour_to,
      }),
    });
    const data = await Office.parseJson(res);
    if (!res.ok || !data.success) {
      Office.showMsg(
        "missingCardsMsg",
        data.error || data.errors?.join(" · ") || "Αποτυχία αποστολής",
        false
      );
      return;
    }
    const n = data.sent || 0;
    Office.showMsg(
      "missingCardsMsg",
      `Εστάλη σε ${n} λήπτη/ες — ${summary} (${row.work_date})`,
      true
    );
  } catch (e) {
    Office.showMsg("missingCardsMsg", String(e), false);
  } finally {
    if (btn) btn.disabled = false;
  }
}

function appendNotifyCell(tr, row) {
  const td = document.createElement("td");
  td.className = "work-log-action-cell work-log-action-cell--notify";
  const summary = Office.workLogMissingPunchSummary(row);
  if (!summary || !Office.workLogEmployeeActive(row)) {
    tr.appendChild(td);
    return;
  }
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "work-log-notify-btn";
  btn.title = `Ειδοποίηση Telegram — ${summary}`;
  btn.setAttribute("aria-label", `Ειδοποίηση — ${summary}`);
  btn.innerHTML = Office.icon("bell");
  btn.addEventListener("click", () => sendMissingPunchNotify(row, btn));
  td.appendChild(btn);
  tr.appendChild(td);
}
