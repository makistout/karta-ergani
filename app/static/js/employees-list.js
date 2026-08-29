document.addEventListener("DOMContentLoaded", () => {
  Office.setActiveNav("employees");
  const btnSync = document.getElementById("btnSyncEmployees");
  if (btnSync) btnSync.onclick = runSync;
  loadEmployees();
});

const employeesState = {
  allRows: [],
  store: null,
  openPunchesMonthLabel: "",
  normalLeaveLatestMonth: null,
  activeCount: 0,
  inactiveCount: 0,
  filter: "active",
};

function isEmployeeActive(emp) {
  const v = emp.active;
  if (v === false || v === 0 || v === "0") return false;
  return true;
}

function getEmployeeCounts() {
  const active = employeesState.allRows.filter(isEmployeeActive).length;
  return {
    active,
    inactive: employeesState.allRows.length - active,
  };
}

function createEmployeeActionLink({ href, icon, title, ariaLabel }) {
  const link = document.createElement("a");
  link.href = href;
  link.className = "employees-action-btn";
  link.title = title;
  link.setAttribute("aria-label", ariaLabel);
  link.innerHTML = Office.icon(icon);
  return link;
}

function createEmployeeActionButton({ icon, title, ariaLabel, disabled = false, onClick }) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "employees-action-btn employees-action-button";
  btn.title = title;
  btn.setAttribute("aria-label", ariaLabel);
  btn.disabled = Boolean(disabled);
  btn.innerHTML = Office.icon(icon);
  if (onClick && !disabled) btn.onclick = onClick;
  return btn;
}

async function loadEmployees() {
  const wrap = document.getElementById("employeesWrap");
  const desc = document.getElementById("employeesDesc");
  const btnSync = document.getElementById("btnSyncEmployees");
  try {
    const activeRes = await fetch("/api/store/active");
    const activeData = await activeRes.json();
    if (!activeData.store) {
      desc.textContent = "Επιλέξτε ενεργό κατάστημα από Καταστήματα (βλ. sidebar).";
      if (btnSync) btnSync.disabled = true;
      wrap.innerHTML =
        `<p style="color:var(--muted);">${Office.icon("info-circle")}<span style="margin-left:0.35rem;">Δεν υπάρχει ενεργό κατάστημα.</span></p>`;
      return;
    }
    desc.textContent = btnSync
      ? "Συγχρονισμός και προβολή εργαζομένων Ergani για το ενεργό κατάστημα. Τα QR ενημερώνονται από τον ημερήσιο συγχρονισμό Μητρώων."
      : "Προβολή εργαζομένων Ergani για το ενεργό κατάστημα.";
    if (btnSync) btnSync.disabled = false;
    await Office.loadActiveStore();

    const res = await fetch("/api/employees/list");
    const data = await res.json();
    if (!res.ok) {
      wrap.innerHTML = `<p style="color:var(--err);">${Office.formatMultilineHtml(data.error || "Σφάλμα")}</p>`;
      return;
    }
    employeesState.allRows = data.employees || [];
    employeesState.store = data.store || null;
    employeesState.openPunchesMonthLabel = data.open_punches_month_label || "";
    employeesState.normalLeaveLatestMonth = data.normal_leave_latest_month || null;
    const counts = getEmployeeCounts();
    employeesState.activeCount = counts.active;
    employeesState.inactiveCount = counts.inactive;
    if (
      employeesState.filter === "active" &&
      employeesState.activeCount === 0 &&
      employeesState.inactiveCount > 0
    ) {
      employeesState.filter = "inactive";
    }
    renderEmployeesView();
  } catch (e) {
    wrap.innerHTML = `<p style="color:var(--err);">${Office.formatMultilineHtml(String(e))}</p>`;
  }
}

function filterEmployees(rows, filter) {
  if (filter === "inactive") return rows.filter((emp) => !isEmployeeActive(emp));
  return rows.filter(isEmployeeActive);
}

function renderEmployeesView() {
  const wrap = document.getElementById("employeesWrap");
  wrap.innerHTML = "";
  wrap.appendChild(buildEmployeesTabs());
  const filtered = filterEmployees(employeesState.allRows, employeesState.filter);
  if (!filtered.length) {
    const empty = document.createElement("p");
    empty.style.color = "var(--muted)";
    empty.innerHTML =
      employeesState.filter === "inactive"
        ? `${Office.icon("person-x")}<span style="margin-left:0.35rem;">Δεν βρέθηκαν ανενεργοί εργαζόμενοι.</span>`
        : `${Office.icon("person-x")}<span style="margin-left:0.35rem;">Δεν βρέθηκαν ενεργοί εργαζόμενοι.</span>`;
    wrap.appendChild(empty);
    return;
  }
  wrap.appendChild(
    buildEmployeesTable(filtered, employeesState.store, employeesState.openPunchesMonthLabel)
  );
}

function buildEmployeesTabs() {
  const tabs = document.createElement("div");
  tabs.className = "log-tabs employees-filter-tabs";
  tabs.setAttribute("role", "tablist");
  tabs.setAttribute("aria-label", "Φίλτρο κατάστασης εργαζομένων");
  const counts = getEmployeeCounts();

  [
    { id: "active", label: "Ενεργοί", count: counts.active },
    { id: "inactive", label: "Ανενεργοί", count: counts.inactive },
  ].forEach(({ id, label, count }) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "log-tab" + (employeesState.filter === id ? " active" : "");
    btn.dataset.employeesFilter = id;
    btn.setAttribute("role", "tab");
    btn.setAttribute("aria-selected", employeesState.filter === id ? "true" : "false");
    btn.innerHTML =
      `${Office.escapeHtml(label)} <span class="employees-tab-count">${count}</span>`;
    btn.onclick = () => {
      if (employeesState.filter === id) return;
      employeesState.filter = id;
      renderEmployeesView();
    };
    tabs.appendChild(btn);
  });
  return tabs;
}

function buildEmployeesTable(rows, store, openPunchesMonthLabel) {
  const fragment = document.createDocumentFragment();
  const branchAa = store?.branch_aa ?? rows[0]?.parartima_aa ?? "—";
  const branchDesc = rows.find((r) => r.parartima_desc)?.parartima_desc || "";
  const branchText = branchDesc
    ? `Παράρτημα Ergani ${Office.escapeHtml(String(branchAa))} — ${Office.escapeHtml(branchDesc)}`
    : `Παράρτημα Ergani ${Office.escapeHtml(String(branchAa))}`;
  if (store) {
    const storeLine = document.createElement("div");
    storeLine.className = "employees-store-meta";
    storeLine.style.cssText =
      "font-size:0.85rem;color:var(--muted);margin:0.75rem 0 0.5rem;line-height:1.45;";
    storeLine.innerHTML =
      `<div>${Office.icon("shop-window")} <strong>${Office.escapeHtml(store.name)}</strong> · ` +
      `ΑΦΜ εργοδότη ${Office.escapeHtml(store.employer_afm)}</div>` +
      `<div style="margin-top:0.15rem;padding-left:1.35rem;">${branchText}</div>`;
    fragment.appendChild(storeLine);
  }
  const meta = document.createElement("p");
  meta.style.cssText = "font-size:0.85rem;color:var(--muted);margin-bottom:0.75rem;";
  meta.textContent = `${rows.length} εργαζόμενοι (${employeesState.filter === "inactive" ? "ανενεργοί" : "ενεργοί"})`;
  fragment.appendChild(meta);

  const openPunchesHeader = "Ανοιχτά";
  const t = document.createElement("table");
  t.className = "data employees-list-table";
  const hr = document.createElement("tr");
  [
    "__detail__",
    "__qr__",
    "ΑΦΜ",
    "Επώνυμο",
    "Όνομα",
    "Σύμβαση",
    "Ευελ. (λεπτά)",
    "Άδεια",
    openPunchesHeader,
    "Κατάσταση",
    "__monthly__",
    "__weekly__",
    "__history__",
  ].forEach((h) => {
    const th = document.createElement("th");
    if (h === "__detail__") {
      th.className = "work-log-action-cell";
      th.setAttribute("aria-label", "Στοιχεία σύμβασης");
    } else if (h === "__qr__") {
      th.className = "work-log-action-cell";
      th.setAttribute("aria-label", "QR ψηφιακής οργάνωσης");
    } else if (h === "__monthly__") {
      th.className = "work-log-action-cell";
      th.setAttribute("aria-label", "Μηνιαία εικόνα");
    } else if (h === "__weekly__") {
      th.className = "work-log-action-cell";
      th.setAttribute("aria-label", "Εβδομαδιαίο ωράριο");
    } else if (h === "__history__") {
      th.className = "col-history work-log-action-cell";
      th.setAttribute("aria-label", "Πραγματική απασχόληση");
    } else if (h.startsWith("Ανοιχτά")) {
      th.className = "col-open-punches";
      th.innerHTML = `<span>${Office.escapeHtml(h)}</span>` +
        (openPunchesMonthLabel ? `<small>${Office.escapeHtml(openPunchesMonthLabel)}</small>` : "");
      th.title = openPunchesMonthLabel
        ? `Ανοιχτά χτυπήματα ${openPunchesMonthLabel}`
        : "Ανοιχτά χτυπήματα";
    } else if (h === "Άδεια") {
      th.className = "col-normal-leave";
      th.innerHTML = `<span>Άδεια</span>` +
        (employeesState.normalLeaveLatestMonth ? `<small>${Office.escapeHtml(employeesState.normalLeaveLatestMonth)}</small>` : "");
      th.title = "Ημέρες κανονικής άδειας που έχουν ληφθεί / δικαιούμενες ημέρες";
    } else if (h === "Κατάσταση") {
      th.className = "col-status";
      th.textContent = h;
    } else if (h === "Σύμβαση") {
      th.className = "col-contract";
      th.textContent = h;
    } else {
      th.textContent = h;
    }
    hr.appendChild(th);
  });
  t.appendChild(hr);

  rows.forEach((emp) => {
    const tr = document.createElement("tr");
    const empAfm = (emp.afm || "").trim();
    const empName = `${emp.eponymo || ""} ${emp.onoma || ""}`.trim();
    const active = isEmployeeActive(emp);
    const query =
      `afm=${encodeURIComponent(empAfm)}` +
      `&eponymo=${encodeURIComponent(emp.eponymo || "")}` +
      `&onoma=${encodeURIComponent(emp.onoma || "")}`;

    const tdDetail = document.createElement("td");
    tdDetail.className = "work-log-action-cell";
    if (empAfm) {
      tdDetail.appendChild(
        createEmployeeActionLink({
          href: `/ui/employees/detail?${query}`,
          icon: "info-circle",
          title: "Στοιχεία σύμβασης Ergani",
          ariaLabel: `Στοιχεία σύμβασης — ${empName}`,
        })
      );
    }
    tr.appendChild(tdDetail);

    const tdQr = document.createElement("td");
    tdQr.className = "work-log-action-cell";
    if (empAfm) {
      const hasQr = Boolean(emp.has_work_time_qr);
      tdQr.appendChild(
        createEmployeeActionButton({
          icon: "qr-code",
          title: hasQr
            ? "QR ψηφιακής οργάνωσης χρόνου εργασίας"
            : "Δεν έχει συγχρονιστεί QR από το portal",
          ariaLabel: `QR ψηφιακής οργάνωσης — ${empName}`,
          disabled: !hasQr,
          onClick: () => openEmployeeQrModal(empAfm),
        })
      );
    }
    tr.appendChild(tdQr);

    const tdAfm = document.createElement("td");
    tdAfm.textContent = emp.afm || "";
    tr.appendChild(tdAfm);

    const tdEp = document.createElement("td");
    tdEp.innerHTML = `<span class="employee-name-actions"><strong>${Office.escapeHtml(emp.eponymo || "")}</strong></span>`;
    tr.appendChild(tdEp);

    const tdOn = document.createElement("td");
    tdOn.textContent = emp.onoma || "";
    tr.appendChild(tdOn);

    const tdContract = document.createElement("td");
    tdContract.className = "col-contract";
    tdContract.textContent = (emp.contract_label || "").trim() || "—";
    tr.appendChild(tdContract);

    const tdFlex = document.createElement("td");
    tdFlex.className = "col-flex";
    tdFlex.textContent = Office.formatFlexMinutes(emp.flex_arrival_minutes);
    tr.appendChild(tdFlex);

    const leaveTaken = emp.normal_leave_days_taken;
    const leaveEntitled = emp.normal_leave_entitled_days;
    const tdLeave = document.createElement("td");
    tdLeave.className = "col-normal-leave";
    tdLeave.textContent = leaveTaken == null || leaveEntitled == null
      ? "—"
      : `${Number(leaveTaken)}/${Number(leaveEntitled)}`;
    tdLeave.title = leaveTaken == null || leaveEntitled == null
      ? "Δεν υπάρχουν διαθέσιμα στοιχεία κανονικής άδειας για το τρέχον έτος"
      : `${leaveTaken} ημέρες κανονικής άδειας από ${leaveEntitled} δικαιούμενες`;
    tr.appendChild(tdLeave);

    const openCount = Number(emp.open_punches_month) || 0;
    const tdOpen = document.createElement("td");
    tdOpen.className = "col-open-punches";
    if (openCount > 0) {
      tdOpen.innerHTML =
        `<span class="employees-open-punches employees-open-punches--warn" title="Ελλιπή χτυπήματα τον τρέχοντα μήνα">${openCount}</span>`;
    } else {
      tdOpen.innerHTML = `<span class="employees-open-punches">0</span>`;
    }
    tr.appendChild(tdOpen);

    const statusLabel = active ? "Ενεργός" : "Ανενεργός";
    const tdSt = document.createElement("td");
    tdSt.className = "col-status employees-status-cell";
    tdSt.innerHTML = active
      ? `<span class="employees-status-icon employees-status-icon--active" title="${statusLabel}" aria-label="${statusLabel}">${Office.icon("check-circle-fill")}</span>`
      : `<span class="employees-status-icon employees-status-icon--inactive" title="${statusLabel}" aria-label="${statusLabel}">${Office.icon("dash-circle")}</span>`;
    tr.appendChild(tdSt);

    const tdMonthly = document.createElement("td");
    tdMonthly.className = "work-log-action-cell";
    if (empAfm) {
      tdMonthly.appendChild(
        createEmployeeActionLink({
          href: `/ui/employees/monthly-overview?${query}`,
          icon: "calendar3",
          title: "Συγκεντρωτική μηνιαία εικόνα",
          ariaLabel: `Μηνιαία εικόνα — ${empName}`,
        })
      );
    }
    tr.appendChild(tdMonthly);

    const tdWeekly = document.createElement("td");
    tdWeekly.className = "work-log-action-cell";
    if (empAfm && active) {
      tdWeekly.appendChild(
        createEmployeeActionLink({
          href: `/ui/employees/weekly-schedule?${query}`,
          icon: "table",
          title: "Δήλωση σταθερού εβδομαδιαίου ωραρίου",
          ariaLabel: `Εβδομαδιαίο ωράριο — ${empName}`,
        })
      );
    }
    tr.appendChild(tdWeekly);

    const tdHistory = document.createElement("td");
    tdHistory.className = "col-history work-log-history-cell work-log-action-cell";
    if (empAfm) {
      tdHistory.appendChild(
        createEmployeeActionLink({
          href: Office.workLogHistoryUrl(empAfm, empName, "employees"),
          icon: "clock-history",
          title: "Πραγματική απασχόληση — ιστορικό",
          ariaLabel: `Πραγματική απασχόληση — ${empName}`,
        })
      );
    }
    tr.appendChild(tdHistory);
    t.appendChild(tr);
  });
  fragment.appendChild(t);
  return fragment;
}

function ensureEmployeeQrModal() {
  let modal = document.getElementById("employeeQrModal");
  if (modal) return modal;
  modal = document.createElement("div");
  modal.id = "employeeQrModal";
  modal.className = "office-modal hidden";
  modal.setAttribute("role", "dialog");
  modal.setAttribute("aria-modal", "true");
  modal.setAttribute("aria-labelledby", "employeeQrTitle");
  modal.innerHTML =
    `<div class="office-modal-backdrop" data-employee-qr-close></div>` +
    `<div class="office-modal-panel employee-qr-modal-panel">` +
      `<div class="employee-qr-modal-head">` +
        `<div>` +
          `<h2 class="office-modal-title" id="employeeQrTitle">Στοιχεια ψηφιακης οργανωσης χρονου εργασιας</h2>` +
          `<p class="office-modal-sub" id="employeeQrSub"></p>` +
        `</div>` +
        `<button type="button" class="employees-action-btn" data-employee-qr-close aria-label="Κλείσιμο">${Office.icon("x-lg")}</button>` +
      `</div>` +
      `<div class="employee-qr-modal-body" id="employeeQrBody"></div>` +
      `<div class="office-modal-actions">` +
        `<button type="button" class="btn" data-employee-qr-close>Κλείσιμο</button>` +
      `</div>` +
    `</div>`;
  modal.addEventListener("click", (event) => {
    if (event.target.closest("[data-employee-qr-close]")) closeEmployeeQrModal();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !modal.classList.contains("hidden")) {
      closeEmployeeQrModal();
    }
  });
  document.body.appendChild(modal);
  return modal;
}

function closeEmployeeQrModal() {
  document.getElementById("employeeQrModal")?.classList.add("hidden");
}

function qrField(label, value) {
  return `<div class="employee-qr-field"><span>${Office.escapeHtml(label)}</span><strong>${Office.escapeHtml(value || "—")}</strong></div>`;
}

async function openEmployeeQrModal(employeeAfm) {
  const modal = ensureEmployeeQrModal();
  const sub = modal.querySelector("#employeeQrSub");
  const body = modal.querySelector("#employeeQrBody");
  sub.textContent = "";
  body.innerHTML = `<p class="employee-qr-loading">${Office.icon("hourglass-split")} Φόρτωση QR…</p>`;
  modal.classList.remove("hidden");
  try {
    const res = await fetch(`/api/employees/work-time-qr?employee_afm=${encodeURIComponent(employeeAfm)}`, {
      cache: "no-store",
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Αποτυχία φόρτωσης QR");
    const employee = data.employee || {};
    const business = data.business || {};
    const employeeName = `${employee.eponymo || ""} ${employee.onoma || ""}`.trim();
    sub.textContent = data.synced_at ? `Τελευταίος συγχρονισμός: ${data.synced_at}` : "";
    body.innerHTML =
      `<section class="employee-qr-info">` +
        `<h3>Στοιχεια επιχειρησης</h3>` +
        `<div class="employee-qr-fields">` +
          qrField("ΑΑ", business.branch_aa || "") +
          qrField("ΑΦΜ", business.afm || "") +
          qrField("Επωνυμια", business.eponimia || business.branch_desc || "") +
        `</div>` +
        `<h3>Στοιχεια εργαζομενου</h3>` +
        `<div class="employee-qr-fields">` +
          qrField("ΑΦΜ", employee.afm || "") +
          qrField("Επωνυμο", employee.eponymo || "") +
          qrField("Ονομα", employee.onoma || "") +
        `</div>` +
      `</section>` +
      `<section class="employee-qr-image-wrap">` +
        (data.qr_data_url
          ? `<img src="${Office.escapeHtml(data.qr_data_url)}" alt="QR ψηφιακής οργάνωσης ${Office.escapeHtml(employeeName || employeeAfm)}">`
          : `<div class="employee-qr-empty">${Office.icon("qr-code")} Δεν έχει αποθηκευτεί QR για τον εργαζόμενο.</div>`) +
      `</section>`;
  } catch (e) {
    body.innerHTML = `<p class="employee-qr-error">${Office.formatMultilineHtml(String(e.message || e))}</p>`;
  }
}

async function runSync() {
  const btn = document.getElementById("btnSyncEmployees");
  Office.setButtonLoading(btn, true);
  Office.beginSyncPanel("employeesWrap", "empMsg");
  Office.showLoading("empMsg", "Έναρξη συγχρονισμού Ergani…", 0, 5);
  try {
    const res = await fetch("/api/ergani/sync-all", { method: "POST" });
    const data = await res.json();
    if (!res.ok) {
      Office.endSyncPanel("employeesWrap", "empMsg");
      Office.showMsg("empMsg", data.error || "Αποτυχία", false);
      return;
    }
    if (!data.job_id) {
      Office.endSyncPanel("employeesWrap", "empMsg");
      Office.showMsg("empMsg", "Δεν ξεκίνησε background συγχρονισμός (λείπει job_id).", false);
      return;
    }
    const statusUrl = `/api/ergani/sync-all/status/${encodeURIComponent(data.job_id)}`;
    const polled = await Office.pollSyncJob(statusUrl, "empMsg");
    Office.endSyncPanel("employeesWrap", "empMsg");
    if (polled.success) {
      const n = polled.sync?.sync_results?.employees?.count ?? 0;
      Office.showMsg("empMsg", `Ολοκληρώθηκε — ${n} εργαζόμενοι.`, true);
      await loadEmployees();
    } else {
      const det =
        polled.sync?.sync_results?.employees?.detail || polled.error || "Αποτυχία";
      Office.showMsg("empMsg", det, false);
    }
  } catch (e) {
    Office.endSyncPanel("employeesWrap", "empMsg");
    Office.showMsg("empMsg", String(e), false);
  } finally {
    Office.setButtonLoading(btn, false);
  }
}
