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
  const storeLine = store
    ? `<p style="font-size:0.85rem;color:var(--muted);margin-bottom:0.5rem;">` +
      `${Office.icon("shop-window")} <strong>${Office.escapeHtml(store.name)}</strong> · ` +
      `ΑΦΜ εργοδότη ${Office.escapeHtml(store.employer_afm)} · παράρτημα ${Office.escapeHtml(store.branch_aa)}</p>`
    : "";
  const t = document.createElement("table");
  t.className = "data";
  const hr = document.createElement("tr");
  ["ΑΦΜ", "Επώνυμο", "Όνομα", "Ευελ. (λεπτά)", "Παράρτημα Ergani", "Κατάσταση", "Μηνιαία"].forEach((h) => {
    const th = document.createElement("th");
    th.textContent = h;
    hr.appendChild(th);
  });
  t.appendChild(hr);
  rows.forEach((emp) => {
    const tr = document.createElement("tr");
    const tdAfm = document.createElement("td");
    tdAfm.textContent = emp.afm || "";
    tr.appendChild(tdAfm);
    const tdEp = document.createElement("td");
    tdEp.innerHTML = `<strong>${Office.escapeHtml(emp.eponymo || "")}</strong>`;
    tr.appendChild(tdEp);
    const tdOn = document.createElement("td");
    tdOn.textContent = emp.onoma || "";
    tr.appendChild(tdOn);
    const tdFlex = document.createElement("td");
    tdFlex.className = "col-flex";
    tdFlex.textContent = Office.formatFlexMinutes(emp.flex_arrival_minutes);
    tr.appendChild(tdFlex);
    const tdAa = document.createElement("td");
    const aa = emp.parartima_aa ?? "—";
    const pd = emp.parartima_desc ? ` — ${emp.parartima_desc}` : "";
    tdAa.textContent = `${aa}${pd}`;
    tr.appendChild(tdAa);
    const tdSt = document.createElement("td");
    const active = emp.active !== false && emp.active !== 0;
    tdSt.innerHTML = active
      ? `<span style="color:var(--ok);">${Office.icon("check-circle-fill")} Ενεργός</span>`
      : `<span style="color:var(--muted);">${Office.icon("dash-circle")} Ανενεργός</span>`;
    tr.appendChild(tdSt);
    const tdMonthly = document.createElement("td");
    tdMonthly.className = "work-log-action-cell";
    const empAfm = (emp.afm || "").trim();
    if (empAfm) {
      const a = document.createElement("a");
      a.href = `/ui/monthly-status?afm=${encodeURIComponent(empAfm)}`;
      a.className = "work-log-card-link";
      a.title = "Μηνιαία κατάσταση";
      a.setAttribute("aria-label", `Μηνιαία κατάσταση — ${emp.eponymo || ""} ${emp.onoma || ""}`.trim());
      a.innerHTML = Office.icon("calendar3");
      tdMonthly.appendChild(a);
    }
    tr.appendChild(tdMonthly);
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
