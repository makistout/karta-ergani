const syncLogState = { page: 1, selectedRunId: null };

document.addEventListener("DOMContentLoaded", () => {
  Office.setActiveNav("synclog");
  document.getElementById("btnRefreshLogs")?.addEventListener("click", () => {
    syncLogState.page = 1;
    loadRuns();
  });
  document.getElementById("chkActiveStoreOnly")?.addEventListener("change", () => {
    syncLogState.page = 1;
    syncLogState.selectedRunId = null;
    loadRuns();
  });
  loadRuns();
});

function formatTs(iso) {
  if (!iso) return "—";
  return String(iso).replace("T", " ").slice(0, 19);
}

function statusBadge(status) {
  const s = String(status || "").toLowerCase();
  let cls = "sync-status-running";
  let label = status || "—";
  if (s === "done") {
    cls = "sync-status-done";
    label = "Ολοκληρώθηκε";
  } else if (s === "error") {
    cls = "sync-status-error";
    label = "Σφάλμα";
  } else if (s === "running") {
    label = "Σε εξέλιξη";
  }
  return `<span class="sync-status-badge ${cls}">${Office.escapeHtml(label)}</span>`;
}

async function loadRuns() {
  const wrap = document.getElementById("syncLogRunsWrap");
  const activeOnly = document.getElementById("chkActiveStoreOnly")?.checked;
  const offset = (syncLogState.page - 1) * Office.TABLE_PAGE_SIZE;
  const qs = new URLSearchParams({
    limit: String(Office.TABLE_PAGE_SIZE),
    offset: String(offset),
  });
  if (activeOnly) qs.set("active_store", "1");

  try {
    const res = await fetch(`/api/sync-log/runs?${qs}`);
    const data = await res.json();
    if (!res.ok) {
      wrap.innerHTML = `<p style="color:var(--err);">${Office.escapeHtml(data.error || "Σφάλμα")}</p>`;
      if (data.db_setup) {
        wrap.innerHTML += `<p style="font-size:0.85rem;color:var(--muted);">Εκτελέστε: <code>${Office.escapeHtml(data.db_setup)}</code></p>`;
      }
      return;
    }
    renderRunsTable(data.runs || [], data.count || 0);
    if (syncLogState.selectedRunId) {
      await loadRunDetail(syncLogState.selectedRunId, false);
    }
  } catch (e) {
    wrap.innerHTML = `<p style="color:var(--err);">${Office.escapeHtml(String(e))}</p>`;
  }
}

function renderRunsTable(runs, pageCount) {
  const wrap = document.getElementById("syncLogRunsWrap");
  if (!runs.length) {
    wrap.innerHTML =
      `<p style="color:var(--muted);">${Office.icon("journal-x")}<span style="margin-left:0.35rem;">Δεν υπάρχουν καταγραφές ακόμα. Κάντε συγχρονισμό ή επιλογή καταστήματος.</span></p>`;
    document.getElementById("syncLogDetailCard")?.classList.add("hidden");
    return;
  }

  const t = document.createElement("table");
  t.className = "data sync-log-runs-table";
  const hr = document.createElement("tr");
  ["Ημ/νία", "Λειτουργία", "Κατάστημα", "Κατάσταση", "Μήνυμα", ""].forEach((h) => {
    const th = document.createElement("th");
    th.textContent = h;
    hr.appendChild(th);
  });
  t.appendChild(hr);

  runs.forEach((run) => {
    const tr = document.createElement("tr");
    tr.className = "sync-log-run-row";
    if (run.run_id === syncLogState.selectedRunId) tr.classList.add("selected");

    const tdDate = document.createElement("td");
    tdDate.textContent = formatTs(run.started_at);
    tr.appendChild(tdDate);

    const tdOp = document.createElement("td");
    tdOp.textContent = run.operation_label || run.operation || "—";
    tr.appendChild(tdOp);

    const tdStore = document.createElement("td");
    tdStore.textContent = run.store_name || (run.store_id ? `#${run.store_id}` : "—");
    tr.appendChild(tdStore);

    const tdStatus = document.createElement("td");
    tdStatus.innerHTML = statusBadge(run.status);
    tr.appendChild(tdStatus);

    const tdMsg = document.createElement("td");
    tdMsg.textContent = (run.message || "").slice(0, 80);
    tdMsg.title = run.message || "";
    tr.appendChild(tdMsg);

    const tdAct = document.createElement("td");
    tdAct.className = "table-actions";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn btn-sm";
    btn.innerHTML = `${Office.icon("eye")}<span>Προβολή</span>`;
    btn.onclick = () => loadRunDetail(run.run_id, true);
    tdAct.appendChild(btn);
    tr.appendChild(tdAct);

    tr.addEventListener("click", (e) => {
      if (e.target.closest("button")) return;
      loadRunDetail(run.run_id, true);
    });

    t.appendChild(tr);
  });

  wrap.innerHTML = "";
  wrap.appendChild(t);

  const totalPages = Math.max(1, Math.ceil(pageCount / Office.TABLE_PAGE_SIZE) || 1);
  if (totalPages > 1 || syncLogState.page > 1) {
    wrap.appendChild(
      Office.buildTablePager(syncLogState.page, totalPages, pageCount, (p) => {
        syncLogState.page = p;
        loadRuns();
      })
    );
  }
}

async function loadRunDetail(runId, scrollIntoView) {
  syncLogState.selectedRunId = runId;
  const card = document.getElementById("syncLogDetailCard");
  const title = document.getElementById("syncLogDetailTitle");
  const meta = document.getElementById("syncLogDetailMeta");
  const linesEl = document.getElementById("syncLogDetailLines");

  document.querySelectorAll(".sync-log-run-row.selected").forEach((r) => r.classList.remove("selected"));

  try {
    const res = await fetch(`/api/sync-log/runs/${encodeURIComponent(runId)}`);
    const run = await res.json();
    if (!res.ok) {
      Office.showMsg("syncLogMsg", run.error || "Σφάλμα", false);
      return;
    }

    card?.classList.remove("hidden");
    if (title) {
      title.textContent = run.operation_label || run.operation || "Λεπτομέρειες";
    }
    if (meta) {
      meta.innerHTML =
        `<div class="sync-log-meta-grid">` +
        `<span><strong>Run ID:</strong> <code>${Office.escapeHtml(run.run_id)}</code></span>` +
        `<span><strong>Έναρξη:</strong> ${Office.escapeHtml(formatTs(run.started_at))}</span>` +
        `<span><strong>Λήξη:</strong> ${Office.escapeHtml(formatTs(run.finished_at))}</span>` +
        `<span><strong>Κατάστημα:</strong> ${Office.escapeHtml(run.store_name || "—")}</span>` +
        `<span><strong>Κατάσταση:</strong> ${statusBadge(run.status)}</span>` +
        (run.message
          ? `<span class="sync-log-meta-full"><strong>Σύνοψη:</strong> ${Office.escapeHtml(run.message)}</span>`
          : "") +
        `</div>`;
    }

    const lines = run.lines || [];
    if (linesEl) {
      if (!lines.length) {
        linesEl.innerHTML = `<p style="color:var(--muted);">Δεν υπάρχουν γραμμές log.</p>`;
      } else {
        linesEl.innerHTML = lines
          .map((line) => {
            const lvl = String(line.level || "INFO").toLowerCase();
            const ts = formatTs(line.ts);
            const fields =
              line.fields && Object.keys(line.fields).length
                ? ` <span class="sync-log-fields">${Office.escapeHtml(JSON.stringify(line.fields))}</span>`
                : "";
            return (
              `<div class="sync-log-line sync-log-${lvl}">` +
              `<span class="sync-log-line-ts">${Office.escapeHtml(ts)}</span> ` +
              `<span class="sync-log-line-level">[${Office.escapeHtml(line.level || "INFO")}]</span> ` +
              `<span class="sync-log-line-msg">${Office.escapeHtml(line.message || "")}</span>${fields}` +
              `</div>`
            );
          })
          .join("");
      }
    }

    if (scrollIntoView) {
      card?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  } catch (e) {
    Office.showMsg("syncLogMsg", String(e), false);
  }
}
