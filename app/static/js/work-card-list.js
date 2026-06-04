let datePicker = null;
let employeeAc = null;
let clockTimer = null;

document.addEventListener("DOMContentLoaded", () => {
  Office.setActiveNav("workcard");
  startTerminalClock();
  employeeAc = Office.createAutocomplete({
    inputId: "wcEmployeeInput",
    listId: "wcEmployeeList",
    hiddenId: "wcEmployeeAfm",
    maxItems: 40,
    labelFn: (row) => row.label || `${row.value} — ${row.description || ""}`.trim(),
  });
  datePicker = Office.createDatePicker({
    mountId: "workCardDatePicker",
    mode: "single",
    onApply: () => loadDayData(),
  });
  document.getElementById("btnRefreshCards").onclick = () => refreshDayData();
  document.getElementById("btnCheckIn").onclick = () => submitCard("check_in");
  document.getElementById("btnCheckOut").onclick = () => submitCard("check_out");
  initPage();
});

function startTerminalClock() {
  const tick = () => {
    const clock = document.getElementById("terminalClock");
    if (clock) {
      clock.textContent = new Date().toLocaleTimeString("el-GR");
    }
  };
  tick();
  if (clockTimer) clearInterval(clockTimer);
  clockTimer = setInterval(tick, 1000);
}

function cardDate() {
  const r = datePicker ? datePicker.getRange() : { start: "" };
  return r.start || "";
}

function selectedEmployeeAfm() {
  return employeeAc ? employeeAc.getValue().code : "";
}

function setFormEnabled(enabled) {
  const input = document.getElementById("wcEmployeeInput");
  const btnIn = document.getElementById("btnCheckIn");
  const btnOut = document.getElementById("btnCheckOut");
  if (input) input.disabled = !enabled;
  if (btnIn) btnIn.disabled = !enabled;
  if (btnOut) btnOut.disabled = !enabled;
}

async function initPage() {
  const activeRes = await fetch("/api/store/active");
  const activeData = await activeRes.json();
  const logWrap = document.getElementById("workLogWrap");
  const cardWrap = document.getElementById("workCardWrap");
  if (!activeData.store) {
    setFormEnabled(false);
    if (employeeAc) employeeAc.setItems([]);
    const msg =
      `<p style="color:var(--muted);">${Office.icon("info-circle")}<span style="margin-left:0.35rem;">Επιλέξτε ενεργό κατάστημα (sidebar).</span></p>`;
    if (logWrap) logWrap.innerHTML = msg;
    if (cardWrap) cardWrap.innerHTML = msg;
    return;
  }
  await Office.loadActiveStore();
  await loadEmployees();
  setFormEnabled(true);
  loadDayData();
}

async function loadEmployees() {
  const input = document.getElementById("wcEmployeeInput");
  try {
    const res = await fetch("/api/employees/list");
    const data = await res.json();
    if (!res.ok) {
      if (employeeAc) employeeAc.setItems([]);
      if (input) input.placeholder = data.error || "Σφάλμα φόρτωσης";
      return;
    }
    const items = (data.employees || []).map((emp) => ({
      value: emp.afm,
      description: `${emp.eponymo || ""} ${emp.onoma || ""}`.trim(),
      label: `${emp.afm} — ${emp.eponymo || ""} ${emp.onoma || ""}`.trim(),
    }));
    if (employeeAc) employeeAc.setItems(items);
    if (input) input.placeholder = "ΑΦΜ, επώνυμο ή όνομα…";
  } catch (e) {
    if (employeeAc) employeeAc.setItems([]);
    if (input) input.placeholder = String(e);
  }
}

async function refreshDayData() {
  const date = cardDate();
  const btn = document.getElementById("btnRefreshCards");
  if (!date) {
    Office.showMsg("wcMsg", "Επιλέξτε ημερομηνία.", false);
    return;
  }
  if (btn) btn.disabled = true;
  Office.showMsg("wcMsg", `Συγχρονισμός portal Ergani για ${date}…`, true);
  try {
    const activeRes = await fetch("/api/store/active");
    const activeData = await activeRes.json();
    if (!activeData.store) {
      Office.showMsg("wcMsg", "Επιλέξτε ενεργό κατάστημα (sidebar).", false);
      await loadDayData();
      return;
    }
    const syncRes = await fetch("/api/work-log/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ date }),
    });
    const syncData = await Office.parseJson(syncRes);
    if (syncData._parseError) {
      Office.showMsg("wcMsg", syncData._parseError, false);
      await loadDayData();
      return;
    }
    if (!syncRes.ok || !syncData.success) {
      Office.showMsg(
        "wcMsg",
        syncData.error || syncData.sync?.detail || "Αποτυχία συγχρονισμού portal",
        false
      );
      await loadDayData();
      return;
    }
    const host = Office.portalHostFromSync(syncData.sync);
    const n = syncData.sync?.count ?? 0;
    await loadDayData();
    Office.showMsg(
      "wcMsg",
      `Ενημερώθηκε — portal: ${n} εγγραφές${host ? ` (${host})` : ""}.`,
      true
    );
  } catch (e) {
    Office.showMsg("wcMsg", String(e), false);
    try {
      await loadDayData();
    } catch {
      /* ignore */
    }
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function loadDayData() {
  const logWrap = document.getElementById("workLogWrap");
  const cardWrap = document.getElementById("workCardWrap");
  const date = cardDate();
  if (!date || !logWrap || !cardWrap) return;

  Office.showTableLoading(logWrap, "Φόρτωση πραγματικής απασχόλησης…");
  Office.showTableLoading(cardWrap, "Φόρτωση δηλώσεων κάρτας…");

  const q = `date=${encodeURIComponent(date)}`;
  const [logRes, cardRes] = await Promise.all([
    fetch(`/api/work-log/list?${q}`),
    fetch(`/api/work-card/list?${q}`),
  ]);

  let logData = {};
  let cardData = {};
  try {
    logData = await logRes.json();
  } catch {
    logWrap.innerHTML = `<p style="color:var(--err);">Σφάλμα πραγματικής (HTTP ${logRes.status}).</p>`;
  }
  try {
    cardData = await cardRes.json();
  } catch {
    cardWrap.innerHTML = `<p style="color:var(--err);">Σφάλμα κάρτας (HTTP ${cardRes.status}).</p>`;
  }

  if (logRes.ok) {
    renderWorkLogTable(logWrap, logData.work_log || [], logData.count || 0, date, logData.db_setup);
  } else {
    logWrap.innerHTML = `<p style="color:var(--err);">${Office.escapeHtml(logData.error || "Σφάλμα")}</p>`;
    if (logData.db_setup) {
      logWrap.innerHTML += `<p style="font-size:0.85rem;color:var(--muted);">${Office.escapeHtml(logData.db_setup)}</p>`;
    }
  }

  if (cardRes.ok) {
    renderCardTable(cardWrap, cardData.events || [], cardData.count || 0, date);
  } else {
    cardWrap.innerHTML = `<p style="color:var(--err);">${Office.escapeHtml(cardData.error || "Σφάλμα")}</p>`;
  }
}

function renderWorkLogTable(wrap, rows, count, dateIso, dbSetup) {
  if (!rows.length) {
    wrap.innerHTML =
      `<p style="color:var(--muted);">${Office.icon("clock")}<span style="margin-left:0.35rem;">Δεν υπάρχει πραγματική απασχόληση για ${Office.escapeHtml(dateIso)}. ` +
      `Συγχρονίστε από <a href="/ui/work-log">Πραγματική απασχόληση</a>.</span></p>` +
      (dbSetup ? `<p style="font-size:0.85rem;color:var(--muted);">${Office.escapeHtml(dbSetup)}</p>` : "");
    return;
  }
  wrap.innerHTML = `<p class="table-meta">${count} εγγραφές · portal → karta_work_log</p>`;
  const t = document.createElement("table");
  t.className = "data";
  const hr = document.createElement("tr");
  ["ΑΦΜ", "Επώνυμο", "Όνομα", "Ημ/νία", "Ώρα από", "Ώρα έως"].forEach((h) => {
    const th = document.createElement("th");
    th.textContent = h;
    hr.appendChild(th);
  });
  t.appendChild(hr);
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    [row.employee_afm, row.eponymo, row.onoma, row.work_date, row.hour_from || "—", row.hour_to || "—"].forEach(
      (txt, i) => {
        const td = document.createElement("td");
        if (i === 0) td.innerHTML = `<strong>${Office.escapeHtml(txt || "")}</strong>`;
        else td.textContent = txt || "";
        tr.appendChild(td);
      }
    );
    t.appendChild(tr);
  });
  wrap.appendChild(t);
}

function renderCardTable(wrap, rows, count, dateIso) {
  if (!rows.length) {
    wrap.innerHTML =
      `<p style="color:var(--muted);">${Office.icon("inbox")}<span style="margin-left:0.35rem;">Δεν υπάρχουν δηλώσεις κάρτας για ${Office.escapeHtml(dateIso)}.</span></p>`;
    return;
  }
  wrap.innerHTML = `<p class="table-meta">${count} δηλώσεις · WRKCardSE → karta_card_event</p>`;
  const t = document.createElement("table");
  t.className = "data";
  const hr = document.createElement("tr");
  ["ΑΦΜ", "Επώνυμο", "Όνομα", "Τύπος", "Ώρα", "Πρωτόκολο", "Ημ/νία υποβολής"].forEach((h) => {
    const th = document.createElement("th");
    th.textContent = h;
    hr.appendChild(th);
  });
  t.appendChild(hr);
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    const typeCls = row.f_type === "0" ? "status-ok" : "status-info";
    [
      row.f_afm,
      row.f_eponymo,
      row.f_onoma,
      row.f_type_label || row.f_type,
      Office.formatFDateTime(row.f_time || row.f_date),
      row.protocol || "—",
      row.submit_date_text || "—",
    ].forEach((txt, i) => {
      const td = document.createElement("td");
      if (i === 0) td.innerHTML = `<strong>${Office.escapeHtml(txt || "")}</strong>`;
      else if (i === 3) {
        td.innerHTML = `<span class="report-chip ${typeCls}">${Office.escapeHtml(txt || "")}</span>`;
      } else td.textContent = txt || "";
      tr.appendChild(td);
    });
    t.appendChild(tr);
  });
  wrap.appendChild(t);
}

async function submitCard(eventName) {
  const afm = selectedEmployeeAfm();
  const date = cardDate();
  if (!afm) {
    Office.showMsg("wcMsg", "Επιλέξτε εργαζόμενο από τη λίστα (↑/↓ + Enter ή Tab).", false);
    return;
  }
  if (!date) {
    Office.showMsg("wcMsg", "Επιλέξτε ημερομηνία.", false);
    return;
  }
  const btnIn = document.getElementById("btnCheckIn");
  const btnOut = document.getElementById("btnCheckOut");
  btnIn.disabled = true;
  btnOut.disabled = true;
  const label = eventName === "check_in" ? "Είσοδος" : "Έξοδος";
  Office.showMsg("wcMsg", `Υποβολή ${label} (WRKCardSE)…`, true);
  try {
    const res = await fetch("/api/work-card/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        employee_afm: afm,
        event: eventName,
        reference_date: date,
        comments: document.getElementById("wcComments").value.trim() || null,
      }),
    });
    const data = await Office.parseJson(res);
    if (data._parseError) {
      Office.showMsg("wcMsg", data._parseError, false);
      return;
    }
    if (!res.ok || !data.success) {
      Office.showMsg("wcMsg", data.error || data.data?.error || "Αποτυχία υποβολής", false);
      return;
    }
    Office.showMsg(
      "wcMsg",
      `Επιτυχία — ${data.f_type_label || label}${data.protocol ? ` · ${data.protocol}` : ""}`,
      true
    );
    await loadDayData();
  } catch (e) {
    Office.showMsg("wcMsg", String(e), false);
  } finally {
    setFormEnabled(true);
  }
}
