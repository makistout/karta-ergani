let datePicker = null;
let retroDatePicker = null;
let employeeAc = null;
let clockTimer = null;

const RETRO_AITIOLOGIA = "001";
const RETRO_AITIOLOGIA_LABEL =
  "001 — ΠΡΟΒΛΗΜΑ ΣΤΗΝ ΗΛΕΚΤΡΟΔΟΤΗΣΗ/ΤΗΛΕΠΙΚΟΙΝΩΝΙΕΣ";

document.addEventListener("DOMContentLoaded", () => {
  Office.setActiveNav("workcard");
  Office.initWorkLogHistoryModal();
  startTerminalClock();
  employeeAc = Office.createAutocomplete({
    inputId: "wcEmployeeInput",
    listId: "wcEmployeeList",
    hiddenId: "wcEmployeeAfm",
    maxItems: 40,
    labelFn: (row) => row.label || `${row.value} — ${row.description || ""}`.trim(),
    onSelect: () => updateWorkCardEmployeeHistoryLink(),
  });
  datePicker = Office.createDatePicker({
    mountId: "workCardDatePicker",
    mode: "single",
    onApply: () => loadDayData(),
  });
  retroDatePicker = Office.attachGreekDateField({ inputId: "wcRetroDate" });
  if (retroDatePicker) retroDatePicker.setDisabled(true);
  document.getElementById("btnRefreshCards").onclick = () => refreshDayData();
  document.getElementById("btnCheckIn").onclick = () => submitCard("check_in");
  document.getElementById("btnCheckOut").onclick = () => submitCard("check_out");
  document.getElementById("btnRetroCheckIn").onclick = () => submitCard("check_in", { retro: true });
  document.getElementById("btnRetroCheckOut").onclick = () => submitCard("check_out", { retro: true });
  document.getElementById("wcEmployeeInput")?.addEventListener("input", () => {
    document.querySelector(".work-card-form .ac-wrap.field-err")?.classList.remove("field-err");
    updateWorkCardEmployeeHistoryLink();
  });
  initRetroDefaults();
  initPage();
});

function setRetroTimeValue(hhmm) {
  const t = document.getElementById("wcRetroTime");
  if (!t) return;
  const norm = Office.normalizeHourMinute(hhmm);
  t.value = norm || "";
}

function readRetroTimeValue() {
  return Office.normalizeHourMinute(document.getElementById("wcRetroTime")?.value || "");
}

function initRetroDefaults() {
  const now = new Date();
  if (retroDatePicker) {
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, "0");
    const day = String(now.getDate()).padStart(2, "0");
    retroDatePicker.setIso(`${y}-${m}-${day}`);
  }
  setRetroTimeValue(Office.formatTime24(now, { seconds: false }));
}

function startTerminalClock() {
  const tick = () => {
    const clock = document.getElementById("terminalClock");
    if (clock) {
      clock.textContent = Office.formatTime24(new Date());
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

function todayIsoLocal() {
  const n = new Date();
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}-${String(n.getDate()).padStart(2, "0")}`;
}

function formatIsoDateGr(iso) {
  const p = String(iso || "").trim().split("-");
  if (p.length !== 3) return iso || "";
  return `${p[2]}/${p[1]}/${p[0]}`;
}

function shouldSkipErganiSyncForRetro(dateIso) {
  const prefill = Office.readWorkCardQueryPrefill();
  if (!prefill.retro) return false;
  const d = String(dateIso || cardDate() || prefill.date || "").trim();
  return Boolean(d && d !== todayIsoLocal());
}

function showWorkCardInfo(text) {
  const el = document.getElementById("wcMsg");
  if (!el) return;
  el.innerHTML = `${Office.icon("info-circle")} <span>${Office.escapeHtml(text)}</span>`;
  el.className = "msg show loading";
  el.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function selectedEmployeeAfm() {
  return employeeAc ? employeeAc.getValue().code : "";
}

function selectedEmployeeName() {
  if (!employeeAc) return "";
  const { label } = employeeAc.getValue();
  const m = String(label || "").match(/^\d+\s*—\s*(.+)$/);
  return m ? m[1].trim() : "";
}

function updateWorkCardEmployeeHistoryLink() {
  const link = document.getElementById("wcEmployeeHistoryLink");
  if (!link) return;
  const afm = (selectedEmployeeAfm() || "").trim();
  if (!afm) {
    link.classList.add("hidden");
    link.setAttribute("aria-hidden", "true");
    link.tabIndex = -1;
    return;
  }
  link.href = Office.workLogHistoryUrl(afm, selectedEmployeeName(), "work-card");
  link.classList.remove("hidden");
  link.removeAttribute("aria-hidden");
  link.tabIndex = 0;
}

function showWorkCardMsg(text, ok) {
  Office.showMsg("wcMsg", text, ok);
  const el = document.getElementById("wcMsg");
  const input = document.getElementById("wcEmployeeInput");
  if (!ok && input) {
    input.focus();
    input.closest(".ac-wrap")?.classList.add("field-err");
  } else if (input) {
    input.closest(".ac-wrap")?.classList.remove("field-err");
  }
  if (el) {
    el.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
}

function requireEmployee() {
  const afm = (selectedEmployeeAfm() || "").trim();
  if (!afm) {
    showWorkCardMsg("Επίλεξε εργαζόμενο", false);
    return false;
  }
  return true;
}

function setFormEnabled(enabled) {
  const input = document.getElementById("wcEmployeeInput");
  const btnIn = document.getElementById("btnCheckIn");
  const btnOut = document.getElementById("btnCheckOut");
  const retroDate = document.getElementById("wcRetroDate");
  const retroTime = document.getElementById("wcRetroTime");
  const btnRetroIn = document.getElementById("btnRetroCheckIn");
  const btnRetroOut = document.getElementById("btnRetroCheckOut");
  if (input) input.disabled = !enabled;
  if (btnIn) btnIn.disabled = !enabled;
  if (btnOut) btnOut.disabled = !enabled;
  if (retroDatePicker) retroDatePicker.setDisabled(!enabled);
  else if (retroDate) retroDate.disabled = !enabled;
  if (retroTime) retroTime.disabled = !enabled;
  if (btnRetroIn) btnRetroIn.disabled = !enabled;
  if (btnRetroOut) btnRetroOut.disabled = !enabled;
}

async function initPage() {
  const activeRes = await fetch("/api/store/active");
  const activeData = await activeRes.json();
  const logWrap = document.getElementById("workLogWrap");
  const cardWrap = document.getElementById("workCardWrap");
  if (!activeData.store) {
    setFormEnabled(false);
    if (employeeAc) employeeAc.setItems([]);
    const syncMeta = document.getElementById("workCardWorkLogSyncMeta");
    if (syncMeta) syncMeta.innerHTML = "";
    const msg =
      `<p style="color:var(--muted);">${Office.icon("info-circle")}<span style="margin-left:0.35rem;">Επιλέξτε ενεργό κατάστημα (sidebar).</span></p>`;
    if (logWrap) logWrap.innerHTML = msg;
    if (cardWrap) cardWrap.innerHTML = msg;
    return;
  }
  await Office.loadActiveStore();
  await Office.refreshActiveStoreSyncMeta("workCardWorkLogSyncMeta", "worklog");
  await loadEmployees();
  const prefill = Office.applyWorkCardQueryPrefill(
    datePicker,
    employeeAc,
    retroDatePicker
  );
  updateWorkCardEmployeeHistoryLink();
  setFormEnabled(true);
  await refreshDayData({ auto: true });
  if (prefill.employee_afm) {
    document.getElementById("wcEmployeeInput")?.focus();
  }
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

async function refreshDayData(options = {}) {
  const auto = Boolean(options.auto);
  const date = cardDate();
  const logWrap = document.getElementById("workLogWrap");
  const cardWrap = document.getElementById("workCardWrap");
  if (!date) {
    if (!auto) Office.showMsg("wcMsg", "Επιλέξτε ημερομηνία.", false);
    return;
  }

  if (shouldSkipErganiSyncForRetro(date)) {
    if (logWrap) Office.showTableLoading(logWrap, "Φόρτωση τοπικών δεδομένων…");
    if (cardWrap) Office.showTableLoading(cardWrap, "Φόρτωση τοπικών δεδομένων…");
    try {
      await loadDayData();
      showWorkCardInfo(
        `Προγενέστερη καταχώρηση για ${formatIsoDateGr(date)} — δεν εκτελείται συγχρονισμός με Ergani. ` +
          "Εμφανίζονται μόνο τα δεδομένα από τη βάση."
      );
    } catch (e) {
      if (!auto) Office.showMsg("wcMsg", String(e), false);
    }
    return;
  }

  if (logWrap) Office.showTableLoading(logWrap, "Συγχρονισμός Ergani…");
  if (cardWrap) Office.showTableLoading(cardWrap, "Συγχρονισμός Ergani…");
  try {
    const activeRes = await fetch("/api/store/active");
    const activeData = await activeRes.json();
    if (!activeData.store) {
      if (!auto) Office.showMsg("wcMsg", "Επιλέξτε ενεργό κατάστημα (sidebar).", false);
      await loadDayData();
      return;
    }
    const payload = await Office.runPortalSync({
      url: "/api/work-log/sync",
      body: { date },
      msgId: "wcMsg",
      btnId: "btnRefreshCards",
      startMessage: `Συγχρονισμός πραγματικής για ${date}`,
    });
    const result = Office.buildSyncResultMessage(payload, Office.portalHostFromSync);
    if (result.ok) {
      await Office.recordStoreSync("work_log");
    }
    await loadDayData();
    if (!auto || !result.ok) {
      Office.showMsg("wcMsg", result.text, result.ok);
    } else {
      const el = document.getElementById("wcMsg");
      if (el) {
        el.className = "msg";
        el.innerHTML = "";
      }
    }
  } catch (e) {
    if (!auto) Office.showMsg("wcMsg", String(e), false);
    try {
      await loadDayData();
    } catch {
      /* ignore */
    }
  }
}

async function loadDayData() {
  const logWrap = document.getElementById("workLogWrap");
  const cardWrap = document.getElementById("workCardWrap");
  const date = cardDate();
  if (!date || !logWrap || !cardWrap) return;

  await Office.refreshActiveStoreSyncMeta("workCardWorkLogSyncMeta", "worklog");

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
  const headers = ["ΑΦΜ", "", "Επώνυμο", "Όνομα", "Ψηφ. ωράριο", "Ευελ. (λεπτά)", "Ημ/νία", "Ώρα από", "Ώρα έως"];
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
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    if (Office.workLogRowIsDeficient(row)) {
      tr.classList.add("work-log-row--deficient");
    }
    const tdAfm = document.createElement("td");
    tdAfm.innerHTML = `<strong>${Office.escapeHtml(row.employee_afm || "")}</strong>`;
    tr.appendChild(tdAfm);
    tr.appendChild(Office.createWorkLogHistoryCell(row));

    const cells = [
      row.eponymo,
      row.onoma,
      row.schedule_label || "—",
      Office.formatFlexMinutes(row.flex_arrival_minutes),
      row.work_date,
      row.hour_from,
      row.hour_to,
    ];
    cells.forEach((txt, i) => {
      const td = document.createElement("td");
      if (i === 0) td.innerHTML = `<strong>${Office.escapeHtml(txt || "")}</strong>`;
      else if (i === 3) {
        td.className = "col-flex";
        td.textContent = txt || "";
      } else if (i === 5) {
        td.innerHTML = Office.formatWorkLogTimeCell(txt, "Λείπει ώρα εισόδου").html;
      } else if (i === 6) {
        const pending = Office.workLogExitStillPending(row);
        td.innerHTML = Office.formatWorkLogTimeCell(
          txt,
          pending ? "Έξοδος μετά το τέλος βάρδιας" : "Λείπει ώρα εξόδου"
        ).html;
      } else td.textContent = txt || "";
      tr.appendChild(td);
    });
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
  ["ΑΦΜ", "Επώνυμο", "Όνομα", "Ευελ. (λεπτά)", "Τύπος", "Ώρα", "Πρωτόκολο", "Ημ/νία υποβολής"].forEach((h) => {
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
      Office.formatFlexMinutes(row.flex_arrival_minutes),
      row.f_type_label || row.f_type,
      Office.formatFDateTime(row.f_time || row.f_date),
      row.protocol || "—",
      row.submit_date_text || "—",
    ].forEach((txt, i) => {
      const td = document.createElement("td");
      if (i === 0) td.innerHTML = `<strong>${Office.escapeHtml(txt || "")}</strong>`;
      else if (i === 3) {
        td.className = "col-flex";
        td.textContent = txt || "";
      } else if (i === 4) {
        td.innerHTML = `<span class="report-chip ${typeCls}">${Office.escapeHtml(txt || "")}</span>`;
      } else td.textContent = txt || "";
      tr.appendChild(td);
    });
    t.appendChild(tr);
  });
  wrap.appendChild(t);
}

function setSubmitButtonsDisabled(disabled) {
  ["btnCheckIn", "btnCheckOut", "btnRetroCheckIn", "btnRetroCheckOut"].forEach((id) => {
    const b = document.getElementById(id);
    if (b) b.disabled = disabled;
  });
}

async function submitCard(eventName, options = {}) {
  const retro = Boolean(options.retro);
  if (!requireEmployee()) return;
  const afm = selectedEmployeeAfm();

  let referenceDate;
  let eventAt = null;
  let aitiologia = null;
  if (retro) {
    referenceDate =
      retroDatePicker?.getIso() ||
      document.getElementById("wcRetroDate")?.dataset?.iso ||
      Office.parseDateGr(document.getElementById("wcRetroDate")?.value || "") ||
      "";
    const retroTime = readRetroTimeValue();
    if (!referenceDate || !retroTime) {
      showWorkCardMsg("Συμπληρώστε ημερομηνία και ώρα προγενέστερης καταχώρησης.", false);
      return;
    }
    eventAt = `${referenceDate}T${retroTime}:00`;
    aitiologia = RETRO_AITIOLOGIA;
  } else {
    referenceDate = cardDate();
    if (!referenceDate) {
      showWorkCardMsg("Επίλεξε ημερομηνία αναφοράς (κάτω).", false);
      return;
    }
  }

  setSubmitButtonsDisabled(true);
  const label = eventName === "check_in" ? "Είσοδος" : "Έξοδος";
  const prefix = retro ? "Προγενέστερη " : "";
  Office.showLoading("wcMsg", `Υποβολή ${prefix}${label} (WRKCardSE)… Παρακαλώ περιμένετε.`);
  document.getElementById("wcMsg")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  try {
    const body = {
      employee_afm: afm,
      event: eventName,
      reference_date: referenceDate,
      comments: document.getElementById("wcComments").value.trim() || null,
    };
    if (eventAt) body.event_at = eventAt;
    if (aitiologia) body.aitiologia = aitiologia;

    const res = await fetch("/api/work-card/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await Office.parseJson(res);
    if (data._parseError) {
      showWorkCardMsg(data._parseError, false);
      return;
    }
    if (!res.ok || !data.success) {
      const err =
        data.error ||
        data.data?.message ||
        data.data?.Message ||
        data.data?.error ||
        "Αποτυχία υποβολής";
      showWorkCardMsg(err, false);
      return;
    }
    if (retro && datePicker && referenceDate !== cardDate()) {
      datePicker.setRange(referenceDate, referenceDate);
    }
    let okMsg = `Επιτυχία — ${data.f_type_label || label}`;
    if (retro) okMsg += ` · ${referenceDate}`;
    if (data.protocol) okMsg += ` · ${data.protocol}`;
    showWorkCardMsg(okMsg, true);
    await loadDayData();
  } catch (e) {
    showWorkCardMsg(String(e), false);
  } finally {
    setFormEnabled(true);
  }
}
