document.addEventListener("DOMContentLoaded", () => {
  Office.setActiveNav("employees");
  document.getElementById("btnSyncEmployees").onclick = runSync;
  loadEmployees();
});

async function loadEmployees() {
  const wrap = document.getElementById("employeesWrap");
  const desc = document.getElementById("employeesDesc");
  const btnSync = document.getElementById("btnSyncEmployees");
  try {
    const activeRes = await fetch("/api/store/active");
    const activeData = await activeRes.json();
    if (!activeData.store) {
      desc.textContent = "Επιλέξτε ενεργό κατάστημα από Καταστήματα (βλ. sidebar).";
      btnSync.disabled = true;
      wrap.innerHTML =
        `<p style="color:var(--muted);">${Office.icon("info-circle")}<span style="margin-left:0.35rem;">Δεν υπάρχει ενεργό κατάστημα.</span></p>`;
      return;
    }
    desc.textContent = "Συγχρονισμός και προβολή εργαζομένων Ergani για το ενεργό κατάστημα.";
    btnSync.disabled = false;
    await Office.loadActiveStore();

    const res = await fetch("/api/employees/list");
    const data = await res.json();
    if (!res.ok) {
      wrap.innerHTML = `<p style="color:var(--err);">${Office.escapeHtml(data.error || "Σφάλμα")}</p>`;
      return;
    }
    renderTable(data.employees || [], data.count || 0, data.store);
  } catch (e) {
    wrap.innerHTML = `<p style="color:var(--err);">${Office.escapeHtml(String(e))}</p>`;
  }
}

function renderTable(rows, count, store) {
  const wrap = document.getElementById("employeesWrap");
  if (!rows.length) {
    wrap.innerHTML =
      `<p style="color:var(--muted);">${Office.icon("person-x")}<span style="margin-left:0.35rem;">Δεν βρέθηκαν εργαζόμενοι. Πατήστε «Συγχρονισμός Ergani».</span></p>`;
    return;
  }
  const branchAa = store?.branch_aa ?? rows[0]?.parartima_aa ?? "—";
  const branchDesc = rows.find((r) => r.parartima_desc)?.parartima_desc || "";
  const branchText = branchDesc
    ? `Παράρτημα Ergani ${Office.escapeHtml(String(branchAa))} — ${Office.escapeHtml(branchDesc)}`
    : `Παράρτημα Ergani ${Office.escapeHtml(String(branchAa))}`;
  const storeLine = store
    ? `<div class="employees-store-meta" style="font-size:0.85rem;color:var(--muted);margin-bottom:0.5rem;line-height:1.45;">` +
      `<div>${Office.icon("shop-window")} <strong>${Office.escapeHtml(store.name)}</strong> · ` +
      `ΑΦΜ εργοδότη ${Office.escapeHtml(store.employer_afm)}</div>` +
      `<div style="margin-top:0.15rem;padding-left:1.35rem;">${branchText}</div></div>`
    : "";
  const t = document.createElement("table");
  t.className = "data";
  const hr = document.createElement("tr");
  ["ΑΦΜ", "Επώνυμο", "Όνομα", "Ευελ. (λεπτά)", "Κατάσταση", "Μηνιαία", "__history__"].forEach((h) => {
    const th = document.createElement("th");
    if (h === "__history__") {
      th.className = "col-history work-log-action-cell";
      th.setAttribute("aria-label", "Πραγματική απασχόληση");
    } else {
      th.textContent = h;
    }
    hr.appendChild(th);
  });
  t.appendChild(hr);
  rows.forEach((emp) => {
    const tr = document.createElement("tr");
    const tdAfm = document.createElement("td");
    tdAfm.textContent = emp.afm || "";
    tr.appendChild(tdAfm);
    const tdEp = document.createElement("td");
    tdEp.innerHTML = `<span class="employee-name-actions"><strong>${Office.escapeHtml(emp.eponymo || "")}</strong></span>`;
    const empAfm = (emp.afm || "").trim();
    const empName = `${emp.eponymo || ""} ${emp.onoma || ""}`.trim();
    const active = emp.active !== false && emp.active !== 0;
    if (empAfm && active) {
      const weeklyLink = document.createElement("a");
      weeklyLink.href =
        `/ui/employees/weekly-schedule?afm=${encodeURIComponent(empAfm)}` +
        `&eponymo=${encodeURIComponent(emp.eponymo || "")}` +
        `&onoma=${encodeURIComponent(emp.onoma || "")}`;
      weeklyLink.className = "employee-weekly-schedule-link";
      weeklyLink.title = "Δήλωση σταθερού εβδομαδιαίου ωραρίου";
      weeklyLink.setAttribute("aria-label", `Εβδομαδιαίο ωράριο — ${empName}`);
      weeklyLink.innerHTML = Office.icon("calendar-week");
      tdEp.querySelector(".employee-name-actions")?.appendChild(weeklyLink);
    }
    tr.appendChild(tdEp);
    const tdOn = document.createElement("td");
    tdOn.textContent = emp.onoma || "";
    tr.appendChild(tdOn);
    const tdFlex = document.createElement("td");
    tdFlex.className = "col-flex";
    tdFlex.textContent = Office.formatFlexMinutes(emp.flex_arrival_minutes);
    tr.appendChild(tdFlex);
    const tdSt = document.createElement("td");
    tdSt.innerHTML = active
      ? `<span style="color:var(--ok);">${Office.icon("check-circle-fill")} Ενεργός</span>`
      : `<span style="color:var(--muted);">${Office.icon("dash-circle")} Ανενεργός</span>`;
    tr.appendChild(tdSt);
    const tdMonthly = document.createElement("td");
    tdMonthly.className = "work-log-action-cell";
    if (empAfm) {
      const a = document.createElement("a");
      a.href = `/ui/monthly-status?afm=${encodeURIComponent(empAfm)}`;
      a.className = "work-log-card-link";
      a.title = "Μηνιαία κατάσταση";
      a.setAttribute("aria-label", `Μηνιαία κατάσταση — ${empName}`);
      a.innerHTML = Office.icon("calendar3");
      tdMonthly.appendChild(a);
    }
    tr.appendChild(tdMonthly);
    const tdHistory = document.createElement("td");
    tdHistory.className = "col-history work-log-history-cell work-log-action-cell";
    if (empAfm) {
      const historyLink = document.createElement("a");
      historyLink.href = Office.workLogHistoryUrl(empAfm, empName, "employees");
      historyLink.className = "btn btn-sm btn-secondary work-log-history-btn";
      historyLink.title = "Πραγματική απασχόληση — ιστορικό";
      historyLink.setAttribute("aria-label", `Πραγματική απασχόληση — ${empName}`);
      historyLink.innerHTML = Office.icon("clock-history");
      tdHistory.appendChild(historyLink);
    }
    tr.appendChild(tdHistory);
    t.appendChild(tr);
  });
  wrap.innerHTML =
    storeLine +
    `<p style="font-size:0.85rem;color:var(--muted);margin-bottom:0.75rem;">${count} εργαζόμενοι για αυτόν τον εργοδότη</p>`;
  wrap.appendChild(t);
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
