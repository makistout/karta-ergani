let datePicker = null;

document.addEventListener("DOMContentLoaded", () => {
  Office.setActiveNav("worklog");
  datePicker = Office.createDatePicker({
    mountId: "workLogDatePicker",
    mode: "range",
    onApply: () => loadWorkLog(),
  });
  document.getElementById("btnSyncWorkLog").onclick = runSync;
  loadWorkLog();
});

function getRange() {
  return datePicker ? datePicker.getRange() : { start: "", end: "" };
}

function listQuery(r) {
  if (r.start === r.end) return `date=${encodeURIComponent(r.start)}`;
  return `from=${encodeURIComponent(r.start)}&to=${encodeURIComponent(r.end)}`;
}

async function loadWorkLog() {
  const wrap = document.getElementById("workLogWrap");
  const btn = document.getElementById("btnSyncWorkLog");
  const r = getRange();
  if (!r.start) {
    return;
  }
  Office.showTableLoading(wrap);
  try {
    const activeRes = await fetch("/api/store/active");
    const activeData = await activeRes.json();
    if (!activeData.store) {
      btn.disabled = true;
      wrap.innerHTML =
        `<p style="color:var(--muted);">${Office.icon("info-circle")}<span style="margin-left:0.35rem;">Επιλέξτε ενεργό κατάστημα (sidebar).</span></p>`;
      return;
    }
    btn.disabled = false;
    await Office.loadActiveStore();
    const res = await fetch(`/api/work-log/list?${listQuery(r)}`);
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
    renderTable(data.work_log || [], data.count || 0, data.store, r);
  } catch (e) {
    wrap.innerHTML = `<p style="color:var(--err);">${Office.escapeHtml(String(e))}</p>`;
  }
}

function renderTable(rows, count, store, range) {
  const wrap = document.getElementById("workLogWrap");
  const multi = range.start !== range.end;
  if (!rows.length) {
    wrap.innerHTML =
      `<p style="color:var(--muted);">${Office.icon("clock")}<span style="margin-left:0.35rem;">Δεν υπάρχουν εγγραφές. Πατήστε «Συγχρονισμός Ergani».</span></p>`;
    return;
  }
  const storeLine = store
    ? `<p class="table-meta">${Office.icon("shop-window")} <strong>${Office.escapeHtml(store.name)}</strong> · ${count} εγγραφές</p>`
    : "";
  const t = document.createElement("table");
  t.className = "data";
  const headers = ["ΑΦΜ", "Επώνυμο", "Όνομα"];
  if (multi) headers.push("Ημερομηνία");
  headers.push("Από", "Έως", "ΑΑ");
  const hr = document.createElement("tr");
  headers.forEach((h) => {
    const th = document.createElement("th");
    th.textContent = h;
    hr.appendChild(th);
  });
  t.appendChild(hr);
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    const cells = [row.employee_afm || "", row.eponymo || "", row.onoma || ""];
    if (multi) cells.push(row.work_date || "");
    cells.push(row.hour_from || "", row.hour_to || "", row.source_aa || "0");
    cells.forEach((txt, i) => {
      const td = document.createElement("td");
      if (i === 1) td.innerHTML = `<strong>${Office.escapeHtml(txt)}</strong>`;
      else td.textContent = txt;
      tr.appendChild(td);
    });
    t.appendChild(tr);
  });
  wrap.innerHTML = storeLine;
  wrap.appendChild(t);
}

async function runSync() {
  const btn = document.getElementById("btnSyncWorkLog");
  const r = getRange();
  btn.disabled = true;
  const days = r.start === r.end ? "μία ημέρα" : `${r.start} – ${r.end}`;
  Office.showMsg("workLogMsg", `Συγχρονισμός portal Ergani (${days})…`, true);
  try {
    const body = r.start === r.end ? { date: r.start } : { from: r.start, to: r.end };
    const res = await fetch("/api/work-log/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    let data = {};
    try {
      data = await res.json();
    } catch {
      Office.showMsg("workLogMsg", `Σφάλμα HTTP ${res.status}`, false);
      return;
    }
    if (res.ok && data.success) {
      const host = Office.portalHostFromSync(data.sync);
      Office.showMsg(
        "workLogMsg",
        `Ολοκληρώθηκε — ${data.sync?.count ?? 0} εγγραφές${host ? ` (${host})` : ""}.`,
        true
      );
      await loadWorkLog();
    } else {
      Office.showMsg("workLogMsg", data.error || data.sync?.detail || "Αποτυχία", false);
    }
  } catch (e) {
    Office.showMsg("workLogMsg", String(e), false);
  } finally {
    btn.disabled = false;
  }
}
