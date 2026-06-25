const syncLogState = {
  page: 1,
  selectedRunId: null,
  refreshTimer: null,
  activeTab: "sync",
  actionsLoaded: false,
  storeId: "",
  storeAc: null,
};

document.addEventListener("DOMContentLoaded", () => {
  Office.setActiveNav("synclog");
  document.getElementById("btnRefreshLogs")?.addEventListener("click", () => {
    syncLogState.page = 1;
    loadRuns();
  });
  document.getElementById("btnClearSyncLogStore")?.addEventListener("click", () => {
    syncLogState.storeId = "";
    syncLogState.page = 1;
    syncLogState.selectedRunId = null;
    syncLogState.storeAc?.clearValue();
    document.getElementById("syncLogStoreInput")?.setAttribute("placeholder", "Όλα τα καταστήματα");
    loadRuns();
  });
  document.querySelectorAll("[data-log-tab]").forEach((btn) => {
    btn.addEventListener("click", () => setLogTab(btn.dataset.logTab || "sync"));
  });
  document.getElementById("btnRefreshNotifyActions")?.addEventListener("click", () => {
    loadNotifyActions();
  });
  if (location.hash === "#actions") {
    setLogTab("actions");
    return;
  }
  initSyncLogStorePicker().finally(() => loadRuns());
});

function formatTs(iso) {
  if (!iso) return "—";
  return String(iso).replace("T", " ").slice(0, 19);
}

function parseTsMs(iso) {
  if (!iso) return null;
  const t = Date.parse(String(iso).replace(" ", "T"));
  return Number.isFinite(t) ? t : null;
}

function runDurationSeconds(run) {
  if (run.duration_seconds != null && run.duration_seconds >= 0) {
    return run.duration_seconds;
  }
  const startMs = parseTsMs(run.started_at);
  const endMs = parseTsMs(run.finished_at);
  if (startMs != null && endMs != null) {
    return Math.max(0, Math.floor((endMs - startMs) / 1000));
  }
  if (startMs != null && String(run.status || "").toLowerCase() === "running") {
    return Math.max(0, Math.floor((Date.now() - startMs) / 1000));
  }
  return null;
}

function formatDuration(seconds, inProgress) {
  if (seconds == null || seconds < 0) return inProgress ? "…" : "—";
  const s = Math.floor(seconds);
  if (s < 60) return inProgress ? `${s} δευτ.` : `${s} δευτ.`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  if (m < 60) {
    const base = rem ? `${m} λεπτ. ${rem} δευτ.` : `${m} λεπτ.`;
    return inProgress ? `${base}…` : base;
  }
  const h = Math.floor(m / 60);
  const rm = m % 60;
  const base = rm ? `${h} ώρ. ${rm} λεπτ.` : `${h} ώρ.`;
  return inProgress ? `${base}…` : base;
}

function scheduleAutoRefresh(runs) {
  if (syncLogState.refreshTimer) {
    clearInterval(syncLogState.refreshTimer);
    syncLogState.refreshTimer = null;
  }
  const hasRunning = (runs || []).some(
    (r) => String(r.status || "").toLowerCase() === "running"
  );
  if (!hasRunning) return;
  syncLogState.refreshTimer = setInterval(() => loadRuns(true), 5000);
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

function setLogTab(tab) {
  const next = tab === "actions" ? "actions" : "sync";
  syncLogState.activeTab = next;
  document.querySelectorAll("[data-log-tab]").forEach((btn) => {
    const active = btn.dataset.logTab === next;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", active ? "true" : "false");
  });
  document.getElementById("syncLogsPanel")?.classList.toggle("hidden", next !== "sync");
  document.getElementById("notifyActionsPanel")?.classList.toggle("hidden", next !== "actions");
  if (next === "actions") {
    history.replaceState(null, "", `${location.pathname}#actions`);
    if (!syncLogState.actionsLoaded) loadNotifyActions();
  } else {
    history.replaceState(null, "", location.pathname);
    loadRuns();
  }
}

async function loadRuns(silent) {
  const wrap = document.getElementById("syncLogRunsWrap");
  const offset = (syncLogState.page - 1) * Office.TABLE_PAGE_SIZE;
  const qs = new URLSearchParams({
    limit: String(Office.TABLE_PAGE_SIZE),
    offset: String(offset),
  });
  if (syncLogState.storeId) qs.set("store_id", syncLogState.storeId);

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
    scheduleAutoRefresh(data.runs || []);
    if (syncLogState.selectedRunId) {
      await loadRunDetail(syncLogState.selectedRunId, false);
    }
  } catch (e) {
    if (!silent) {
      wrap.innerHTML = `<p style="color:var(--err);">${Office.escapeHtml(String(e))}</p>`;
    }
  }
}

function storeAcLabel(item) {
  return `${item.description || "Κατάστημα"} (ID ${item.value})`;
}

async function initSyncLogStorePicker() {
  const input = document.getElementById("syncLogStoreInput");
  if (!input) return;
  syncLogState.storeAc = Office.createAutocomplete({
    inputId: "syncLogStoreInput",
    listId: "syncLogStoreList",
    hiddenId: "syncLogStoreId",
    maxItems: 50,
    labelFn: storeAcLabel,
    onSelect: (item) => {
      syncLogState.storeId = String(item.value || "");
      syncLogState.page = 1;
      syncLogState.selectedRunId = null;
      loadRuns();
    },
  });
  try {
    const res = await fetch("/api/store/list");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const stores = await res.json();
    syncLogState.storeAc?.setItems(
      (stores || []).map((s) => ({
        value: String(s.id),
        description: s.name || "Κατάστημα",
      }))
    );
  } catch (e) {
    input.placeholder = "Σφάλμα φόρτωσης καταστημάτων";
  }
  const openAllStores = () => {
    syncLogState.storeAc?.openAll(false);
  };
  input.addEventListener("focus", openAllStores);
  input.addEventListener("click", openAllStores);
}

function actionLabel(action, path) {
  const a = String(action || "");
  const p = String(path || "");
  if (a.endsWith("today_hit_confirm") || (p.includes("/today-hit/") && p.includes("/confirm"))) return "Επιβεβαίωση PIN";
  if (a.endsWith("today_hit_preview") || p.includes("/today-hit/")) return "Άνοιγμα ειδοποίησης";
  if (a.endsWith("today_action_context") || p.includes("/today-action/context")) return "Άνοιγμα ενεργειών";
  if (a.endsWith("today_action_snooze") || p.includes("/today-action/snooze")) return "Αναβολή ειδοποίησης";
  if (a.endsWith("today_action_card") || p.includes("/today-action/card")) return "Προετοιμασία κάρτας";
  if (a.endsWith("today_action_leave") || p.includes("/today-action/leave")) return "Υποβολή άδειας";
  if (a.endsWith("today_action_wto_daily") || p.includes("/today-action/wto-daily")) return "Υποβολή WTODaily";
  return a || p || "Ενέργεια";
}

function auditSuccessBadge(row) {
  if (row.success === true || row.success === 1) {
    return `<span class="sync-status-badge sync-status-done">OK</span>`;
  }
  if (row.success === false || row.success === 0) {
    return `<span class="sync-status-badge sync-status-error">Σφάλμα</span>`;
  }
  return `<span class="sync-status-badge sync-status-running">Άγνωστο</span>`;
}

function auditDetailsText(row) {
  const details = row.details || {};
  const response = details.response || {};
  const requestData = details.request || {};
  const bits = [];
  if (response.error) bits.push(response.error);
  if (response.notify_kind) bits.push(`Τύπος: ${response.notify_kind}`);
  if (response.sent != null || response.total != null) {
    bits.push(`Αποστολές: ${response.sent ?? "?"}/${response.total ?? "?"}`);
  }
  if (requestData.leave_type) bits.push(`Άδεια: ${requestData.leave_type}`);
  if (requestData.hour_from || requestData.hour_to) {
    bits.push(`${requestData.hour_from || "—"}–${requestData.hour_to || "—"}`);
  }
  if (!bits.length && details.error) bits.push(details.error);
  if (!bits.length && row.http_status) bits.push(`HTTP ${row.http_status}`);
  return bits.join(" · ") || "—";
}

function auditActorText(row) {
  const actor = row.notification_actor || {};
  const name = actor.name || row.actor_name || row.office_user || "";
  const mobile = actor.mobile ? ` (${actor.mobile})` : "";
  if (name) return `${name}${mobile}`;
  if (row.actor_type === "telegram_link") return "Λήπτης ειδοποίησης";
  return row.actor_type || "—";
}

async function loadNotifyActions() {
  const wrap = document.getElementById("notifyActionsWrap");
  if (!wrap) return;
  wrap.innerHTML =
    `<p style="color:var(--muted);">${Office.icon("hourglass-split")}<span style="margin-left:0.35rem;">Φόρτωση…</span></p>`;
  try {
    const qs = new URLSearchParams({
      kind: "today_notifications",
      limit: "200",
    });
    const res = await fetch(`/api/audit/list?${qs}`);
    const data = await res.json();
    if (!res.ok) {
      wrap.innerHTML = `<p style="color:var(--err);">${Office.escapeHtml(data.error || "Σφάλμα")}</p>`;
      return;
    }
    renderNotifyActions(data.audit || []);
    syncLogState.actionsLoaded = true;
  } catch (e) {
    wrap.innerHTML = `<p style="color:var(--err);">${Office.escapeHtml(String(e))}</p>`;
  }
}

function renderNotifyActions(rows) {
  const wrap = document.getElementById("notifyActionsWrap");
  if (!wrap) return;
  if (!rows.length) {
    wrap.innerHTML =
      `<p style="color:var(--muted);">${Office.icon("journal-x")}<span style="margin-left:0.35rem;">Δεν υπάρχουν ακόμα ενέργειες από ειδοποιήσεις today-hit.</span></p>`;
    return;
  }

  const t = document.createElement("table");
  t.className = "data notify-actions-table";
  const hr = document.createElement("tr");
  ["Ώρα", "Ενέργεια", "Ποιος", "Κατάστημα", "Κατάσταση", "Συσκευή/IP", "Λεπτομέρειες"].forEach((h) => {
    const th = document.createElement("th");
    th.textContent = h;
    hr.appendChild(th);
  });
  t.appendChild(hr);

  rows.forEach((row) => {
    const tr = document.createElement("tr");

    const tdTs = document.createElement("td");
    tdTs.className = "sync-log-ts";
    tdTs.textContent = formatTs(row.created_at);
    tr.appendChild(tdTs);

    const tdAction = document.createElement("td");
    tdAction.innerHTML =
      `<strong>${Office.escapeHtml(actionLabel(row.action, row.request_path))}</strong>` +
      (row.request_method ? `<br><span class="sync-log-muted">${Office.escapeHtml(row.request_method)}</span>` : "");
    tr.appendChild(tdAction);

    const tdActor = document.createElement("td");
    tdActor.textContent = auditActorText(row);
    tr.appendChild(tdActor);

    const tdStore = document.createElement("td");
    tdStore.textContent = row.notification_actor?.store_name || (row.store_id ? `#${row.store_id}` : "—");
    tr.appendChild(tdStore);

    const tdStatus = document.createElement("td");
    tdStatus.innerHTML = auditSuccessBadge(row);
    tr.appendChild(tdStatus);

    const tdDevice = document.createElement("td");
    const device = row.client_device || "";
    const ip = row.client_ip || "";
    tdDevice.textContent = [ip, device].filter(Boolean).join(" · ") || "—";
    tdDevice.title = tdDevice.textContent;
    tr.appendChild(tdDevice);

    const tdDetails = document.createElement("td");
    tdDetails.textContent = auditDetailsText(row);
    tdDetails.title = row.request_path || "";
    tr.appendChild(tdDetails);

    t.appendChild(tr);
  });

  wrap.innerHTML = "";
  wrap.appendChild(t);
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
  ["Έναρξη", "Λήξη", "Διάρκεια", "Λειτουργία", "Κατάστημα", "Κατάσταση", "Μήνυμα", ""].forEach((h) => {
    const th = document.createElement("th");
    th.textContent = h;
    hr.appendChild(th);
  });
  t.appendChild(hr);

  runs.forEach((run) => {
    const tr = document.createElement("tr");
    tr.className = "sync-log-run-row";
    if (run.run_id === syncLogState.selectedRunId) tr.classList.add("selected");

    const tdStart = document.createElement("td");
    tdStart.textContent = formatTs(run.started_at);
    tdStart.className = "sync-log-ts";
    tr.appendChild(tdStart);

    const tdEnd = document.createElement("td");
    const inProgress = String(run.status || "").toLowerCase() === "running";
    tdEnd.textContent = inProgress ? "—" : formatTs(run.finished_at);
    tdEnd.className = "sync-log-ts";
    tr.appendChild(tdEnd);

    const tdDur = document.createElement("td");
    tdDur.textContent = formatDuration(runDurationSeconds(run), run.in_progress);
    tdDur.className = "sync-log-duration";
    tr.appendChild(tdDur);

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
        `<span><strong>Λήξη:</strong> ${Office.escapeHtml(
          String(run.status || "").toLowerCase() === "running" ? "—" : formatTs(run.finished_at)
        )}</span>` +
        `<span><strong>Διάρκεια:</strong> ${Office.escapeHtml(
          formatDuration(runDurationSeconds(run), run.in_progress)
        )}</span>` +
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
