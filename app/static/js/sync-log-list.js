const syncLogState = {
  page: 1,
  actionsPage: 1,
  actionsCursors: [null],
  sentPage: 1,
  sentCursors: [null],
  punchesPage: 1,
  punchesCursors: [null],
  schedulePage: 1,
  scheduleCursors: [null],
  apologisticPage: 1,
  apologisticCursors: [null],
  authPage: 1,
  authCursors: [null],
  selectedRunId: null,
  refreshTimer: null,
  activeTab: "sync",
  actionsLoaded: false,
  sentLoaded: false,
  punchesLoaded: false,
  scheduleLoaded: false,
  scheduleStoreId: "",
  scheduleStoreAc: null,
  apologisticLoaded: false,
  apologisticStoreId: "",
  apologisticStoreAc: null,
  authLoaded: false,
  punchesStoreId: "",
  punchesStoreAc: null,
  storeId: "",
  query: "",
  sentQuery: "",
  storeAc: null,
  searchTimer: null,
  sentSearchTimer: null,
};

function pageSize() {
  return Office.TABLE_PAGE_SIZE || 20;
}

function pageOffset(page) {
  return (Math.max(1, page || 1) - 1) * pageSize();
}

function resetCursorPager(keyPrefix) {
  syncLogState[`${keyPrefix}Page`] = 1;
  syncLogState[`${keyPrefix}Cursors`] = [null];
}

function appendTablePager(wrap, page, total, onPageChange) {
  if (!wrap) return;
  const totalPages = Math.max(1, Math.ceil((total || 0) / pageSize()) || 1);
  if (totalPages > 1 || page > 1) {
    wrap.appendChild(
      Office.buildTablePager(page, totalPages, total || 0, onPageChange, pageSize())
    );
  }
}

function appendCursorPager(wrap, keyPrefix, itemCount, hasMore, reloadFn) {
  if (!wrap) return;
  const page = syncLogState[`${keyPrefix}Page`] || 1;
  if (page <= 1 && !hasMore) return;
  wrap.appendChild(
    Office.buildCursorPager({
      page,
      hasMore: Boolean(hasMore),
      itemCount: itemCount || 0,
      pageSize: pageSize(),
      onPrev: () => {
        if (page <= 1) return;
        syncLogState[`${keyPrefix}Page`] = page - 1;
        reloadFn();
      },
      onNext: () => {
        if (!hasMore) return;
        syncLogState[`${keyPrefix}Page`] = page + 1;
        reloadFn();
      },
    })
  );
}

function rememberNextCursor(keyPrefix, nextBeforeId, hasMore) {
  const page = syncLogState[`${keyPrefix}Page`] || 1;
  const cursors = syncLogState[`${keyPrefix}Cursors`] || [null];
  if (hasMore && nextBeforeId != null) {
    cursors[page] = nextBeforeId;
  }
  syncLogState[`${keyPrefix}Cursors`] = cursors;
}

function currentBeforeId(keyPrefix) {
  const page = syncLogState[`${keyPrefix}Page`] || 1;
  const cursors = syncLogState[`${keyPrefix}Cursors`] || [null];
  return cursors[page - 1] ?? null;
}

document.addEventListener("DOMContentLoaded", () => {
  Office.setActiveNav("synclog");
  document.getElementById("btnRefreshLogs")?.addEventListener("click", () => {
    syncLogState.page = 1;
    loadRuns();
  });
  document.getElementById("btnClearSyncLogStore")?.addEventListener("click", () => {
    syncLogState.storeId = "";
    syncLogState.query = "";
    syncLogState.page = 1;
    syncLogState.selectedRunId = null;
    syncLogState.storeAc?.clearValue();
    document.getElementById("syncLogStoreInput")?.setAttribute("placeholder", "Όλα τα καταστήματα");
    const search = document.getElementById("syncLogSearchInput");
    if (search) search.value = "";
    loadRuns();
  });
  document.getElementById("syncLogSearchInput")?.addEventListener("input", (e) => {
    syncLogState.query = String(e.target.value || "").trim();
    syncLogState.page = 1;
    syncLogState.selectedRunId = null;
    if (syncLogState.searchTimer) clearTimeout(syncLogState.searchTimer);
    syncLogState.searchTimer = setTimeout(() => loadRuns(), 250);
  });
  document.querySelectorAll("[data-log-tab]").forEach((btn) => {
    btn.addEventListener("click", () => setLogTab(btn.dataset.logTab || "sync"));
  });
  document.getElementById("btnRefreshNotifyActions")?.addEventListener("click", () => {
    resetCursorPager("actions");
    loadNotifyActions();
  });
  document.getElementById("btnRefreshNotifySent")?.addEventListener("click", () => {
    resetCursorPager("sent");
    loadNotifySent();
  });
  document.getElementById("btnRefreshWorkCardPunches")?.addEventListener("click", () => {
    resetCursorPager("punches");
    loadWorkCardPunches();
  });
  document.getElementById("btnRefreshScheduleChanges")?.addEventListener("click", () => {
    resetCursorPager("schedule");
    loadScheduleChanges();
  });
  document.getElementById("btnRefreshApologisticChanges")?.addEventListener("click", () => {
    resetCursorPager("apologistic");
    loadApologisticChanges();
  });
  document.getElementById("btnClearApologisticChangesStore")?.addEventListener("click", () => {
    syncLogState.apologisticStoreId = "";
    resetCursorPager("apologistic");
    syncLogState.apologisticStoreAc?.clearValue();
    document.getElementById("apologisticChangesStoreInput")?.setAttribute("placeholder", "Όλα τα καταστήματα");
    loadApologisticChanges();
  });
  document.getElementById("btnClearScheduleChangesStore")?.addEventListener("click", () => {
    syncLogState.scheduleStoreId = "";
    resetCursorPager("schedule");
    syncLogState.scheduleStoreAc?.clearValue();
    document.getElementById("scheduleChangesStoreInput")?.setAttribute("placeholder", "Όλα τα καταστήματα");
    loadScheduleChanges();
  });
  document.getElementById("btnRefreshAuthLogs")?.addEventListener("click", () => {
    resetCursorPager("auth");
    loadAuthLogs();
  });
  document.getElementById("btnClearWorkCardPunchesStore")?.addEventListener("click", () => {
    syncLogState.punchesStoreId = "";
    resetCursorPager("punches");
    syncLogState.punchesStoreAc?.clearValue();
    document.getElementById("workCardPunchesStoreInput")?.setAttribute("placeholder", "Όλα τα καταστήματα");
    loadWorkCardPunches();
  });
  document.getElementById("notifySentSearchInput")?.addEventListener("input", (e) => {
    syncLogState.sentQuery = String(e.target.value || "").trim();
    resetCursorPager("sent");
    if (syncLogState.sentSearchTimer) clearTimeout(syncLogState.sentSearchTimer);
    syncLogState.sentSearchTimer = setTimeout(() => loadNotifySent(), 250);
  });
  if (location.hash === "#actions") {
    setLogTab("actions");
    return;
  }
  if (location.hash === "#sent") {
    setLogTab("sent");
    return;
  }
  if (location.hash === "#punches") {
    initWorkCardPunchesStorePicker().finally(() => setLogTab("punches"));
    return;
  }
  if (location.hash === "#schedule") {
    initScheduleChangesStorePicker().finally(() => setLogTab("schedule"));
    return;
  }
  if (location.hash === "#apologistic") {
    initApologisticChangesStorePicker().finally(() => setLogTab("apologistic"));
    return;
  }
  if (location.hash === "#auth") {
    setLogTab("auth");
    return;
  }
  initSyncLogStorePicker().finally(() => loadRuns());
  initWorkCardPunchesStorePicker();
  initScheduleChangesStorePicker();
  initApologisticChangesStorePicker();
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

function currentApologisticBefore() {
  const page = syncLogState.apologisticPage || 1;
  const cursors = syncLogState.apologisticCursors || [null];
  return cursors[page - 1] ?? null;
}

function rememberApologisticCursor(hasMore, nextBefore) {
  const page = syncLogState.apologisticPage || 1;
  const cursors = syncLogState.apologisticCursors || [null];
  if (hasMore && nextBefore && nextBefore.at && nextBefore.type && nextBefore.id != null) {
    cursors[page] = nextBefore;
  }
  syncLogState.apologisticCursors = cursors;
}

function setLogTab(tab) {
  const next =
    tab === "actions" || tab === "sent" || tab === "punches" || tab === "schedule" || tab === "apologistic" || tab === "auth"
      ? tab
      : "sync";
  syncLogState.activeTab = next;
  document.querySelectorAll("[data-log-tab]").forEach((btn) => {
    const active = btn.dataset.logTab === next;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", active ? "true" : "false");
  });
  document.getElementById("syncLogsPanel")?.classList.toggle("hidden", next !== "sync");
  document.getElementById("notifyActionsPanel")?.classList.toggle("hidden", next !== "actions");
  document.getElementById("notifySentPanel")?.classList.toggle("hidden", next !== "sent");
  document.getElementById("workCardPunchesPanel")?.classList.toggle("hidden", next !== "punches");
  document.getElementById("scheduleChangesPanel")?.classList.toggle("hidden", next !== "schedule");
  document.getElementById("apologisticChangesPanel")?.classList.toggle("hidden", next !== "apologistic");
  document.getElementById("authLogsPanel")?.classList.toggle("hidden", next !== "auth");
  if (next === "actions") {
    history.replaceState(null, "", `${location.pathname}#actions`);
    if (!syncLogState.actionsLoaded) loadNotifyActions();
  } else if (next === "sent") {
    history.replaceState(null, "", `${location.pathname}#sent`);
    if (!syncLogState.sentLoaded) loadNotifySent();
  } else if (next === "punches") {
    history.replaceState(null, "", `${location.pathname}#punches`);
    loadWorkCardPunches();
  } else if (next === "schedule") {
    history.replaceState(null, "", `${location.pathname}#schedule`);
    loadScheduleChanges();
  } else if (next === "apologistic") {
    history.replaceState(null, "", `${location.pathname}#apologistic`);
    loadApologisticChanges();
  } else if (next === "auth") {
    history.replaceState(null, "", `${location.pathname}#auth`);
    if (!syncLogState.authLoaded) loadAuthLogs();
  } else {
    history.replaceState(null, "", location.pathname);
    loadRuns();
  }
}

function authActionLabel(action, details) {
  const a = String(action || "");
  const reason = String(details?.reason || "");
  if (a === "auth.login_success") return "Σύνδεση";
  if (a === "auth.logout") return "Αποσύνδεση";
  if (a === "auth.login_failed") {
    if (reason === "missing_credentials") return "Αποτυχημένη σύνδεση · λείπουν στοιχεία";
    if (reason === "invalid_credentials") return "Αποτυχημένη σύνδεση · λάθος στοιχεία";
    return "Αποτυχημένη σύνδεση";
  }
  return a || "Auth";
}

function authUserText(row) {
  const details = row.details || {};
  return details.username || row.entity_id || row.actor_name || row.office_user || "—";
}

function authRoleText(row) {
  const details = row.details || {};
  return details.role || "—";
}

function authDetailsText(row) {
  const details = row.details || {};
  const bits = [];
  if (details.reason) bits.push(`Reason: ${details.reason}`);
  if (row.http_status) bits.push(`HTTP ${row.http_status}`);
  return bits.join(" · ") || "—";
}

async function loadAuthLogs() {
  const wrap = document.getElementById("authLogsWrap");
  if (!wrap) return;
  wrap.innerHTML =
    `<p style="color:var(--muted);">${Office.icon("hourglass-split")}<span style="margin-left:0.35rem;">Φόρτωση…</span></p>`;
  try {
    const qs = new URLSearchParams({
      kind: "auth",
      limit: String(pageSize()),
    });
    const beforeId = currentBeforeId("auth");
    if (beforeId != null) qs.set("before_id", String(beforeId));
    const res = await fetch(`/api/audit/list?${qs}`);
    const data = await res.json();
    if (!res.ok) {
      wrap.innerHTML = `<p style="color:var(--err);">${Office.formatMultilineHtml(data.error || "Σφάλμα")}</p>`;
      return;
    }
    rememberNextCursor("auth", data.next_before_id, data.has_more);
    renderAuthLogs(data.audit || [], Boolean(data.has_more));
    syncLogState.authLoaded = true;
  } catch (e) {
    wrap.innerHTML = `<p style="color:var(--err);">${Office.formatMultilineHtml(String(e))}</p>`;
  }
}

function renderAuthLogs(rows, hasMore) {
  const wrap = document.getElementById("authLogsWrap");
  if (!wrap) return;
  if (!rows.length) {
    wrap.innerHTML =
      `<p style="color:var(--muted);">${Office.icon("journal-x")}<span style="margin-left:0.35rem;">Δεν υπάρχουν ακόμα καταγραφές σύνδεσης.</span></p>`;
    return;
  }

  const t = document.createElement("table");
  t.className = "data auth-logs-table";
  const hr = document.createElement("tr");
  ["Ώρα", "Ενέργεια", "Χρήστης", "Ρόλος", "Κατάσταση", "Συσκευή/IP", "Λεπτομέρειες"].forEach((h) => {
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
    tdAction.textContent = authActionLabel(row.action, row.details || {});
    tr.appendChild(tdAction);

    const tdUser = document.createElement("td");
    tdUser.textContent = authUserText(row);
    tr.appendChild(tdUser);

    const tdRole = document.createElement("td");
    tdRole.textContent = authRoleText(row);
    tr.appendChild(tdRole);

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
    tdDetails.textContent = authDetailsText(row);
    tr.appendChild(tdDetails);

    t.appendChild(tr);
  });

  wrap.innerHTML = "";
  wrap.appendChild(t);
  appendCursorPager(wrap, "auth", rows.length, hasMore, loadAuthLogs);
}

async function loadRuns(silent) {
  const wrap = document.getElementById("syncLogRunsWrap");
  const qs = new URLSearchParams({
    limit: String(pageSize()),
    offset: String(pageOffset(syncLogState.page)),
  });
  if (syncLogState.storeId) qs.set("store_id", syncLogState.storeId);
  if (syncLogState.query) qs.set("q", syncLogState.query);

  try {
    const res = await fetch(`/api/sync-log/runs?${qs}`);
    const data = await res.json();
    if (!res.ok) {
      wrap.innerHTML = `<p style="color:var(--err);">${Office.formatMultilineHtml(data.error || "Σφάλμα")}</p>`;
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
      wrap.innerHTML = `<p style="color:var(--err);">${Office.formatMultilineHtml(String(e))}</p>`;
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
    Office.rememberStoreNames(stores || []);
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

async function initWorkCardPunchesStorePicker() {
  const input = document.getElementById("workCardPunchesStoreInput");
  if (!input || syncLogState.punchesStoreAc) return;
  syncLogState.punchesStoreAc = Office.createAutocomplete({
    inputId: "workCardPunchesStoreInput",
    listId: "workCardPunchesStoreList",
    hiddenId: "workCardPunchesStoreId",
    maxItems: 50,
    labelFn: storeAcLabel,
    onSelect: (item) => {
      syncLogState.punchesStoreId = String(item.value || "");
      resetCursorPager("punches");
      loadWorkCardPunches();
    },
  });
  try {
    const res = await fetch("/api/store/list");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const stores = await res.json();
    Office.rememberStoreNames(stores || []);
    syncLogState.punchesStoreAc?.setItems(
      (stores || []).map((s) => ({
        value: String(s.id),
        description: s.name || "Κατάστημα",
      }))
    );
  } catch (e) {
    input.placeholder = "Σφάλμα φόρτωσης καταστημάτων";
  }
  const openAllStores = () => {
    syncLogState.punchesStoreAc?.openAll(false);
  };
  input.addEventListener("focus", openAllStores);
  input.addEventListener("click", openAllStores);
}

function workCardPunchSourceLabel(source) {
  const s = String(source || "").trim();
  if (s === "close_all") return "Κλείστε όλα";
  if (s === "telegram_retro") return "Telegram retro";
  if (s === "office_ui") return "Ψηφ. κάρτα";
  if (s === "auto_close_prev_day") return "Αυτόματο κλείσιμο";
  return s || "—";
}

function workCardPunchChannelLabel(details) {
  const d = details && typeof details === "object" ? details : {};
  const channel = String(d.submission_channel || "").trim().toLowerCase();
  const fallback = String(d.listener_fallback_reason || "").trim();
  if (channel === "listener") return "listener";
  if (channel === "erganios") {
    if (fallback === "listener_timeout") return "erganiOS (timeout listener)";
    if (fallback === "listener_offline") return "erganiOS (listener offline)";
    return "erganiOS";
  }
  return "—";
}

function workCardPunchEmployeeMeta(row) {
  const d = row.details || {};
  const afm = String(d.employee_afm || row.entity_id || "").trim();
  const fullName = String(
    d.employee_name ||
    `${d.eponymo || d.employee_last_name || ""} ${d.onoma || d.employee_first_name || ""}`
  ).trim();
  return { afm: afm || "—", fullName: fullName && fullName !== afm ? fullName : "" };
}

function workCardPunchErganiResponseText(parsed) {
  if (!parsed) return "";
  const parts = [];
  const push = (msg) => {
    const text = String(msg || "").trim();
    if (text && !parts.includes(text)) parts.push(text);
  };
  if (typeof parsed === "string") {
    push(parsed);
    return parts.join(" · ");
  }
  if (Array.isArray(parsed)) {
    parsed.forEach((item) => {
      if (item && typeof item === "object") {
        push(item.message || item.Message || item.error || item.Error);
      } else {
        push(item);
      }
    });
    return parts.join(" · ");
  }
  if (typeof parsed === "object") {
    push(parsed.message || parsed.Message || parsed.error || parsed.Error || parsed.detail);
    const errors = parsed.errors || parsed.Errors;
    if (Array.isArray(errors)) {
      errors.forEach((item) => {
        if (item && typeof item === "object") {
          push(item.message || item.Message || item.error);
        } else {
          push(item);
        }
      });
    } else if (typeof errors === "string") {
      push(errors);
    }
  }
  return parts.join(" · ");
}

function workCardPunchDetailsText(row) {
  const d = row.details || {};
  const resp = d.response && typeof d.response === "object" ? d.response : {};
  const messages = [];

  const push = (msg) => {
    const text = String(msg || "").trim();
    if (text && !messages.includes(text)) messages.push(text);
  };

  push(d.error_message);
  push(d.error);
  const erganiFromStored = workCardPunchErganiResponseText(d.ergani_response);
  if (erganiFromStored) {
    const code = d.ergani_http_status || row.http_status;
    push(code ? `Ergani (${code}): ${erganiFromStored}` : erganiFromStored);
  }
  if (d.persist_error) push(`Αποθήκευση βάσης: ${d.persist_error}`);
  if (d.ergani_ok === true && d.persisted === false) {
    push("Ergani OK αλλά δεν αποθηκεύτηκε στη βάση erganiOS");
  }
  push(resp.error);
  if (resp.data && typeof resp.data === "object") {
    push(resp.data.message || resp.data.Message || resp.data.error);
  }
  if (d.protocol) push(`Πρωτόκολο: ${d.protocol}`);
  if (d.batch_index != null && d.batch_total != null) {
    push(`Σειρά ${d.batch_index}/${d.batch_total}`);
  }
  if (!messages.length && row.http_status) {
    push(`HTTP ${row.http_status} — δεν επέστρεψε αναλυτικό μήνυμα`);
  }
  return messages.join(" · ") || "—";
}

async function loadWorkCardPunches() {
  const wrap = document.getElementById("workCardPunchesWrap");
  if (!wrap) return;
  wrap.innerHTML =
    `<p style="color:var(--muted);">${Office.icon("hourglass-split")}<span style="margin-left:0.35rem;">Φόρτωση…</span></p>`;
  try {
    const qs = new URLSearchParams({
      kind: "work_card_punches",
      limit: String(pageSize()),
    });
    if (syncLogState.punchesStoreId) qs.set("store_id", syncLogState.punchesStoreId);
    const beforeId = currentBeforeId("punches");
    if (beforeId != null) qs.set("before_id", String(beforeId));
    const res = await fetch(`/api/audit/list?${qs}`);
    const data = await res.json();
    if (!res.ok) {
      wrap.innerHTML = `<p style="color:var(--err);">${Office.formatMultilineHtml(data.error || "Σφάλμα")}</p>`;
      return;
    }
    rememberNextCursor("punches", data.next_before_id, data.has_more);
    renderWorkCardPunches(data.audit || [], Boolean(data.has_more));
    syncLogState.punchesLoaded = true;
  } catch (e) {
    wrap.innerHTML = `<p style="color:var(--err);">${Office.formatMultilineHtml(String(e))}</p>`;
  }
}

function renderWorkCardPunches(rows, hasMore) {
  const wrap = document.getElementById("workCardPunchesWrap");
  if (!wrap) return;
  if (!rows.length) {
    wrap.innerHTML =
      `<p style="color:var(--muted);">${Office.icon("journal-x")}<span style="margin-left:0.35rem;">Δεν υπάρχουν ακόμα καταγραφές χτυπημάτων κάρτας.</span></p>`;
    return;
  }

  const t = document.createElement("table");
  t.className = "data work-card-punches-table";
  const thead = document.createElement("thead");
  const hr = document.createElement("tr");
  [
    "Ώρα",
    "Πηγή",
    "Κανάλι",
    "Εργαζόμενος",
    "Ημ/νία",
    "Ενέργεια",
    "Κατάστημα",
    "Κατάσταση",
    "Λεπτομέρειες",
  ].forEach((h) => {
    const th = document.createElement("th");
    th.textContent = h;
    hr.appendChild(th);
  });
  thead.appendChild(hr);
  t.appendChild(thead);

  const tbody = document.createElement("tbody");
  rows.forEach((row) => {
    const d = row.details || {};
    const tr = document.createElement("tr");
    tr.className = "work-card-punch-row";

    const tdTs = document.createElement("td");
    tdTs.className = "sync-log-ts work-card-punch-col-ts";
    tdTs.textContent = formatTs(row.created_at);
    tr.appendChild(tdTs);

    const tdSource = document.createElement("td");
    tdSource.className = "work-card-punch-col-source";
    tdSource.textContent = workCardPunchSourceLabel(d.source);
    tr.appendChild(tdSource);

    const tdChannel = document.createElement("td");
    tdChannel.className = "work-card-punch-col-channel";
    const channel = workCardPunchChannelLabel(d);
    tdChannel.textContent = channel;
    if (channel.startsWith("listener")) {
      tdChannel.classList.add("work-card-punch-channel--listener");
    } else if (channel.startsWith("erganiOS")) {
      tdChannel.classList.add("work-card-punch-channel--erganios");
    }
    tr.appendChild(tdChannel);

    const tdEmp = document.createElement("td");
    tdEmp.className = "work-card-punch-col-emp";
    const employee = workCardPunchEmployeeMeta(row);
    tdEmp.textContent = employee.afm;
    if (employee.fullName) {
      tdEmp.title = employee.fullName;
      tdEmp.setAttribute("aria-label", `${employee.afm} — ${employee.fullName}`);
    }
    tr.appendChild(tdEmp);

    const tdDate = document.createElement("td");
    tdDate.className = "work-card-punch-col-date";
    tdDate.textContent = d.reference_date || d.event_at || "—";
    tr.appendChild(tdDate);

    const tdAction = document.createElement("td");
    tdAction.className = "work-card-punch-col-action";
    tdAction.textContent = d.f_type_label || d.event || "—";
    tr.appendChild(tdAction);

    const tdStore = document.createElement("td");
    tdStore.className = "work-card-punch-col-store";
    Office.setStoreIdText(tdStore, row.store_id, { storeName: row.store_name });
    tr.appendChild(tdStore);

    const tdStatus = document.createElement("td");
    tdStatus.className = "work-card-punch-col-status";
    tdStatus.innerHTML = auditSuccessBadge(row);
    tr.appendChild(tdStatus);

    const tdDetails = document.createElement("td");
    tdDetails.className = "work-card-punch-details";
    tdDetails.textContent = workCardPunchDetailsText(row);
    if (row.success === false || row.success === 0) {
      tdDetails.title = workCardPunchDetailsText(row);
    }
    tr.appendChild(tdDetails);

    tbody.appendChild(tr);
  });
  t.appendChild(tbody);

  wrap.innerHTML = "";
  wrap.appendChild(t);
  appendCursorPager(wrap, "punches", rows.length, hasMore, loadWorkCardPunches);
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
  if (a === "wto_daily.schedule_change") return "Αλλαγή ωραρίου";
  if (a === "schedule_import.batch_applied") return "Εισαγωγή Excel (σύνολο)";
  if (a.includes("schedule_import")) return "Εισαγωγή Excel";
  return a || p || "Ενέργεια";
}

function scheduleChangeSourceLabel(source) {
  const s = String(source || "").trim().toLowerCase();
  if (s === "excel_import") return "Excel";
  if (s === "telegram") return "Ειδοποίηση";
  if (s === "manual") return "Χειροκίνητα";
  return source || "—";
}

function scheduleSnapshotText(snapshot) {
  if (!Array.isArray(snapshot) || !snapshot.length) return "—";
  const parts = snapshot.map((item) => {
    if (!item || typeof item !== "object") return "";
    const st = String(item.shift_type || "").toUpperCase();
    if (st.includes("ΑΝΑΠΑΥ") || st.includes("ΡΕΠΟ") || st === "ΑΝ") return "ΡΕΠΟ";
    const hf = String(item.hour_from || "").slice(0, 5);
    const ht = String(item.hour_to || "").slice(0, 5);
    if (hf || ht) return `${hf || "—"}–${ht || "—"}`;
    return st || "—";
  }).filter(Boolean);
  return parts.join(" / ") || "—";
}

function scheduleChangeEmployeeText(row) {
  const d = row.details || {};
  const name = d.employee_name || "";
  const afm = d.employee_afm || row.entity_id || "";
  return [name, afm].filter(Boolean).join(" · ") || "—";
}

function scheduleChangeDetailsText(row) {
  const d = row.details || {};
  const action = String(row.action || "");
  if (action === "schedule_import.batch_applied") {
    const bits = [];
    if (d.original_filename) bits.push(d.original_filename);
    if (d.week_label) bits.push(d.week_label);
    if (d.applied != null || d.failed != null) {
      bits.push(`Επιτυχίες: ${d.applied ?? 0}, αποτυχίες: ${d.failed ?? 0}`);
    }
    const sync = d.schedule_sync;
    if (sync && typeof sync === "object" && sync.attempted) {
      bits.push(sync.success ? "Συγχρονισμός OK" : `Συγχρονισμός: ${sync.detail || "αποτυχία"}`);
    }
    return bits.join(" · ") || "—";
  }
  const bits = [];
  const oldText = scheduleSnapshotText(d.old_schedule);
  const newText = scheduleSnapshotText(d.requested_schedule || d.new_schedule);
  if (oldText !== newText) bits.push(`${oldText} → ${newText}`);
  else if (newText !== "—") bits.push(newText);
  if (d.protocol) bits.push(`Πρωτόκολο: ${d.protocol}`);
  if (d.original_filename) bits.push(d.original_filename);
  if (d.week_label) bits.push(d.week_label);
  if (d.error_message) bits.push(d.error_message);
  if (!bits.length && row.http_status) bits.push(`HTTP ${row.http_status}`);
  return bits.join(" · ") || "—";
}

async function initScheduleChangesStorePicker() {
  const input = document.getElementById("scheduleChangesStoreInput");
  if (!input || syncLogState.scheduleStoreAc) return;
  syncLogState.scheduleStoreAc = Office.createAutocomplete({
    inputId: "scheduleChangesStoreInput",
    listId: "scheduleChangesStoreList",
    hiddenId: "scheduleChangesStoreId",
    maxItems: 50,
    labelFn: storeAcLabel,
    onSelect: (item) => {
      syncLogState.scheduleStoreId = String(item.value || "");
      resetCursorPager("schedule");
      loadScheduleChanges();
    },
  });
  try {
    const res = await fetch("/api/store/list");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const stores = await res.json();
    Office.rememberStoreNames(stores || []);
    syncLogState.scheduleStoreAc?.setItems(
      (stores || []).map((s) => ({
        value: String(s.id),
        description: s.name || "Κατάστημα",
      }))
    );
  } catch (e) {
    input.placeholder = "Σφάλμα φόρτωσης καταστημάτων";
  }
  const openAllStores = () => {
    syncLogState.scheduleStoreAc?.openAll(false);
  };
  input.addEventListener("focus", openAllStores);
  input.addEventListener("click", openAllStores);
}

async function loadScheduleChanges() {
  const wrap = document.getElementById("scheduleChangesWrap");
  if (!wrap) return;
  wrap.innerHTML =
    `<p style="color:var(--muted);">${Office.icon("hourglass-split")}<span style="margin-left:0.35rem;">Φόρτωση…</span></p>`;
  try {
    const qs = new URLSearchParams({
      kind: "schedule_changes",
      limit: String(pageSize()),
    });
    if (syncLogState.scheduleStoreId) qs.set("store_id", syncLogState.scheduleStoreId);
    const beforeId = currentBeforeId("schedule");
    if (beforeId != null) qs.set("before_id", String(beforeId));
    const res = await fetch(`/api/audit/list?${qs}`);
    const data = await res.json();
    if (!res.ok) {
      wrap.innerHTML = `<p style="color:var(--err);">${Office.formatMultilineHtml(data.error || "Σφάλμα")}</p>`;
      return;
    }
    rememberNextCursor("schedule", data.next_before_id, data.has_more);
    renderScheduleChanges(data.audit || [], Boolean(data.has_more));
    syncLogState.scheduleLoaded = true;
  } catch (e) {
    wrap.innerHTML = `<p style="color:var(--err);">${Office.formatMultilineHtml(String(e))}</p>`;
  }
}

function renderScheduleChanges(rows, hasMore) {
  const wrap = document.getElementById("scheduleChangesWrap");
  if (!wrap) return;
  if (!rows.length) {
    wrap.innerHTML =
      `<p style="color:var(--muted);">${Office.icon("journal-x")}<span style="margin-left:0.35rem;">Δεν υπάρχουν ακόμα καταγραφές αλλαγών ωραρίου.</span></p>`;
    return;
  }

  const t = document.createElement("table");
  t.className = "data work-card-punches-table";
  const thead = document.createElement("thead");
  const hr = document.createElement("tr");
  ["Ώρα", "Πηγή", "Εργαζόμενος", "Ημ/νία", "Ενέργεια", "Κατάστημα", "Κατάσταση", "Λεπτομέρειες"].forEach((h) => {
    const th = document.createElement("th");
    th.textContent = h;
    hr.appendChild(th);
  });
  thead.appendChild(hr);
  t.appendChild(thead);

  const tbody = document.createElement("tbody");
  rows.forEach((row) => {
    const d = row.details || {};
    const tr = document.createElement("tr");

    const tdTs = document.createElement("td");
    tdTs.className = "sync-log-ts work-card-punch-col-ts";
    tdTs.textContent = formatTs(row.created_at);
    tr.appendChild(tdTs);

    const tdSource = document.createElement("td");
    tdSource.textContent = scheduleChangeSourceLabel(d.source || (row.action || "").includes("schedule_import") ? "excel_import" : "");
    tr.appendChild(tdSource);

    const tdEmp = document.createElement("td");
    tdEmp.textContent =
      row.action === "schedule_import.batch_applied"
        ? `Batch #${d.batch_id || row.entity_id || "—"}`
        : scheduleChangeEmployeeText(row);
    tr.appendChild(tdEmp);

    const tdDate = document.createElement("td");
    tdDate.textContent = d.work_date || "—";
    tr.appendChild(tdDate);

    const tdAction = document.createElement("td");
    tdAction.textContent = actionLabel(row.action, row.request_path);
    tr.appendChild(tdAction);

    const tdStore = document.createElement("td");
    Office.setStoreIdText(tdStore, row.store_id, { storeName: row.store_name });
    tr.appendChild(tdStore);

    const tdStatus = document.createElement("td");
    tdStatus.innerHTML = auditSuccessBadge(row);
    tr.appendChild(tdStatus);

    const tdDetails = document.createElement("td");
    tdDetails.className = "work-card-punch-details";
    tdDetails.textContent = scheduleChangeDetailsText(row);
    if (row.success === false || row.success === 0) {
      tdDetails.title = scheduleChangeDetailsText(row);
    }
    tr.appendChild(tdDetails);

    tbody.appendChild(tr);
  });
  t.appendChild(tbody);
  wrap.innerHTML = "";
  wrap.appendChild(t);
  appendCursorPager(wrap, "schedule", rows.length, hasMore, loadScheduleChanges);
}

function apologisticEventTypeLabel(eventType) {
  const t = String(eventType || "");
  if (t === "recalc") return "Επαναϋπολογισμός";
  if (t === "proposal_edit") return "Χειροκίνητη πρόταση";
  if (t === "ergani_submit") return "Υποβολή Ergani";
  return t || "—";
}

function apologisticSubmissionLabel(code) {
  const c = String(code || "");
  if (c === "WTODailyA") return "Μεταβολή ωραρίου";
  if (c === "WTOOvA") return "Υπερωρία";
  return c || "—";
}

function apologisticRunStatusBadge(status) {
  const s = String(status || "").toLowerCase();
  if (s === "draft") return `<span class="sync-status-badge sync-status-ok">Πρόχειρο</span>`;
  if (s === "approved") return `<span class="sync-status-badge sync-status-ok">Εγκεκριμένο</span>`;
  if (s === "locked") return `<span class="sync-status-badge sync-status-warn">Κλειδωμένο</span>`;
  if (s === "failed") return `<span class="sync-status-badge sync-status-err">Αποτυχία</span>`;
  return `<span class="sync-status-badge">${Office.escapeHtml(status || "—")}</span>`;
}

function apologisticWeekLabel(row) {
  if (!row.week_from) return "—";
  const from = String(row.week_from).slice(0, 10);
  const to = row.week_to ? String(row.week_to).slice(0, 10) : "";
  return to && to !== from ? `${from} – ${to}` : from;
}

function apologisticEmployeeText(row) {
  const name = String(row.employee_name || "").trim();
  const afm = String(row.employee_afm || "").trim();
  return [name, afm].filter(Boolean).join(" · ") || "—";
}

function apologisticDetailsText(row) {
  const type = String(row.event_type || "");
  if (type === "recalc") {
    const bits = [];
    if (row.calculation_version) bits.push(`Έκδοση: ${row.calculation_version}`);
    if (row.day_count != null) bits.push(`Ημέρες: ${row.day_count}`);
    if (row.error_summary) bits.push(String(row.error_summary));
    return bits.join(" · ") || "—";
  }
  if (type === "proposal_edit") {
    const oldVal = row.old_value || "—";
    const newVal = row.new_value || "—";
    const by = row.changed_by ? ` · από ${row.changed_by}` : "";
    return `${oldVal} → ${newVal}${by}`;
  }
  if (type === "ergani_submit") {
    const bits = [apologisticSubmissionLabel(row.submission_code)];
    if (row.proposed_at_submit) bits.push(`Πρόταση: ${row.proposed_at_submit}`);
    if (row.protocol) bits.push(`Πρωτόκολο: ${row.protocol}`);
    if (row.segment_date && row.segment_date !== row.work_date) bits.push(`Τμήμα: ${row.segment_date}`);
    if (row.submitted_by) bits.push(`Από: ${row.submitted_by}`);
    return bits.join(" · ") || "—";
  }
  return "—";
}

async function initApologisticChangesStorePicker() {
  const input = document.getElementById("apologisticChangesStoreInput");
  if (!input || syncLogState.apologisticStoreAc) return;
  syncLogState.apologisticStoreAc = Office.createAutocomplete({
    inputId: "apologisticChangesStoreInput",
    listId: "apologisticChangesStoreList",
    hiddenId: "apologisticChangesStoreId",
    maxItems: 50,
    labelFn: storeAcLabel,
    onSelect: (item) => {
      syncLogState.apologisticStoreId = String(item.value || "");
      resetCursorPager("apologistic");
      loadApologisticChanges();
    },
  });
  try {
    const res = await fetch("/api/store/list");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const stores = await res.json();
    Office.rememberStoreNames(stores || []);
    syncLogState.apologisticStoreAc?.setItems(
      (stores || []).map((s) => ({
        value: String(s.id),
        description: s.name || "Κατάστημα",
      }))
    );
  } catch (e) {
    input.placeholder = "Σφάλμα φόρτωσης καταστημάτων";
  }
  const openAllStores = () => syncLogState.apologisticStoreAc?.openAll(false);
  input.addEventListener("focus", openAllStores);
  input.addEventListener("click", openAllStores);
}

async function loadApologisticChanges() {
  const wrap = document.getElementById("apologisticChangesWrap");
  if (!wrap) return;
  wrap.innerHTML =
    `<p style="color:var(--muted);">${Office.icon("hourglass-split")}<span style="margin-left:0.35rem;">Φόρτωση…</span></p>`;
  try {
    const qs = new URLSearchParams({ limit: String(pageSize()) });
    if (syncLogState.apologisticStoreId) qs.set("store_id", syncLogState.apologisticStoreId);
    const before = currentApologisticBefore();
    if (before?.at && before?.type && before?.id != null) {
      qs.set("before_at", before.at);
      qs.set("before_type", before.type);
      qs.set("before_id", String(before.id));
    }
    const res = await fetch(`/api/sync-log/apologistic?${qs}`);
    const data = await Office.parseJson(res);
    if (data._parseError) {
      wrap.innerHTML = `<p style="color:var(--err);">${Office.formatMultilineHtml(data._parseError)}</p>`;
      return;
    }
    if (!res.ok) {
      wrap.innerHTML = `<p style="color:var(--err);">${Office.formatMultilineHtml(data.error || "Σφάλμα")}</p>`;
      if (data.db_setup) {
        wrap.innerHTML += `<p style="font-size:0.85rem;color:var(--muted);">Εκτελέστε: <code>${Office.escapeHtml(data.db_setup)}</code></p>`;
      }
      return;
    }
    rememberApologisticCursor(Boolean(data.has_more), data.next_before);
    renderApologisticChanges(data.events || [], Boolean(data.has_more));
    syncLogState.apologisticLoaded = true;
  } catch (e) {
    wrap.innerHTML = `<p style="color:var(--err);">${Office.formatMultilineHtml(String(e))}</p>`;
  }
}

function appendApologisticPager(wrap, itemCount, hasMore) {
  if (!wrap) return;
  const page = syncLogState.apologisticPage || 1;
  if (page <= 1 && !hasMore) return;
  wrap.appendChild(
    Office.buildCursorPager({
      page,
      hasMore: Boolean(hasMore),
      itemCount: itemCount || 0,
      pageSize: pageSize(),
      onPrev: () => {
        if (page <= 1) return;
        syncLogState.apologisticPage = page - 1;
        loadApologisticChanges();
      },
      onNext: () => {
        if (!hasMore) return;
        syncLogState.apologisticPage = page + 1;
        loadApologisticChanges();
      },
    })
  );
}

function renderApologisticChanges(rows, hasMore) {
  const wrap = document.getElementById("apologisticChangesWrap");
  if (!wrap) return;
  if (!rows.length) {
    wrap.innerHTML =
      `<p style="color:var(--muted);">${Office.icon("journal-x")}<span style="margin-left:0.35rem;">Δεν υπάρχουν ακόμα καταγραφές απολογιστικού.</span></p>`;
    return;
  }

  const t = document.createElement("table");
  t.className = "data work-card-punches-table";
  const thead = document.createElement("thead");
  const hr = document.createElement("tr");
  ["Ώρα", "Τύπος", "Κατάστημα", "Εβδομάδα", "Εργαζόμενος", "Ημ/νία", "Κατάσταση", "Λεπτομέρειες"].forEach((h) => {
    const th = document.createElement("th");
    th.textContent = h;
    hr.appendChild(th);
  });
  thead.appendChild(hr);
  t.appendChild(thead);

  const tbody = document.createElement("tbody");
  rows.forEach((row) => {
    const tr = document.createElement("tr");

    const tdTs = document.createElement("td");
    tdTs.className = "sync-log-ts work-card-punch-col-ts";
    tdTs.textContent = formatTs(row.event_at);
    tr.appendChild(tdTs);

    const tdType = document.createElement("td");
    tdType.textContent = apologisticEventTypeLabel(row.event_type);
    tr.appendChild(tdType);

    const tdStore = document.createElement("td");
    Office.setStoreIdText(tdStore, row.store_id, { storeName: row.store_name });
    tr.appendChild(tdStore);

    const tdWeek = document.createElement("td");
    tdWeek.textContent = apologisticWeekLabel(row);
    tr.appendChild(tdWeek);

    const tdEmp = document.createElement("td");
    tdEmp.textContent = row.event_type === "recalc" ? "—" : apologisticEmployeeText(row);
    tr.appendChild(tdEmp);

    const tdDate = document.createElement("td");
    tdDate.textContent = row.work_date || "—";
    tr.appendChild(tdDate);

    const tdStatus = document.createElement("td");
    if (row.event_type === "recalc") {
      tdStatus.innerHTML = apologisticRunStatusBadge(row.run_status);
    } else if (row.event_type === "ergani_submit") {
      tdStatus.innerHTML = `<span class="sync-status-badge sync-status-ok">OK</span>`;
    } else {
      tdStatus.innerHTML = `<span class="sync-status-badge sync-status-warn">Επεξεργασία</span>`;
    }
    tr.appendChild(tdStatus);

    const tdDetails = document.createElement("td");
    tdDetails.className = "work-card-punch-details";
    tdDetails.textContent = apologisticDetailsText(row);
    tdDetails.title = tdDetails.textContent;
    tr.appendChild(tdDetails);

    tbody.appendChild(tr);
  });
  t.appendChild(tbody);
  wrap.innerHTML = "";
  wrap.appendChild(t);
  appendApologisticPager(wrap, rows.length, hasMore);
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

function syncLineFieldsText(fields) {
  if (!fields || !Object.keys(fields).length) return "";
  if (fields.event === "today_notification_send") {
    const bits = [];
    if (fields.notification_channel) bits.push(`Κανάλι: ${fields.notification_channel}`);
    if (fields.recipient_name || fields.recipient_mobile || fields.recipient_email) {
      bits.push(
        `Λήπτης: ${[fields.recipient_name, fields.recipient_mobile, fields.recipient_email]
          .filter(Boolean)
          .join(" / ")}`
      );
    }
    if (fields.employee_name || fields.employee_afm) {
      bits.push(`Εργαζόμενος: ${[fields.employee_name, fields.employee_afm].filter(Boolean).join(" / ")}`);
    }
    if (fields.notify_kind_label || fields.notify_kind) {
      bits.push(`Τύπος: ${fields.notify_kind_label || fields.notify_kind}`);
    }
    if (fields.recipient_policy) bits.push(`Πολιτική: ${fields.recipient_policy}`);
    if (fields.error) bits.push(`Σφάλμα: ${fields.error}`);
    return bits.join(" · ");
  }
  if (fields.event === "today_notification_auto_snooze") {
    const bits = ["Αυτόματο snooze"];
    if (fields.recipient_id) bits.push(`Λήπτης #${fields.recipient_id}`);
    if (fields.employee_name || fields.employee_afm) {
      bits.push(`Εργαζόμενος: ${[fields.employee_name, fields.employee_afm].filter(Boolean).join(" / ")}`);
    }
    if (fields.notify_kind_label || fields.notify_kind) {
      bits.push(`Τύπος: ${fields.notify_kind_label || fields.notify_kind}`);
    }
    return bits.join(" · ");
  }
  return JSON.stringify(fields);
}

function sentNotificationStatus(row) {
  const lvl = String(row.level || "").toLowerCase();
  const sent = row.fields?.sent;
  if (sent === true || sent === 1 || (sent == null && lvl !== "error")) {
    return `<span class="sync-status-badge sync-status-done">Εστάλη</span>`;
  }
  return `<span class="sync-status-badge sync-status-error">Σφάλμα</span>`;
}

async function loadNotifySent() {
  const wrap = document.getElementById("notifySentWrap");
  if (!wrap) return;
  wrap.innerHTML =
    `<p style="color:var(--muted);">${Office.icon("hourglass-split")}<span style="margin-left:0.35rem;">Φόρτωση…</span></p>`;
  try {
    const qs = new URLSearchParams({
      limit: String(pageSize()),
    });
    if (syncLogState.sentQuery) qs.set("q", syncLogState.sentQuery);
    const beforeId = currentBeforeId("sent");
    if (beforeId != null) qs.set("before_id", String(beforeId));
    const res = await fetch(`/api/sync-log/notifications?${qs}`);
    const data = await res.json();
    if (!res.ok) {
      wrap.innerHTML = `<p style="color:var(--err);">${Office.formatMultilineHtml(data.error || "Σφάλμα")}</p>`;
      return;
    }
    rememberNextCursor("sent", data.next_before_id, data.has_more);
    renderNotifySent(data.notifications || [], Boolean(data.has_more));
    syncLogState.sentLoaded = true;
  } catch (e) {
    wrap.innerHTML = `<p style="color:var(--err);">${Office.formatMultilineHtml(String(e))}</p>`;
  }
}

function renderNotifySent(rows, hasMore) {
  const wrap = document.getElementById("notifySentWrap");
  if (!wrap) return;
  if (!rows.length) {
    wrap.innerHTML =
      `<p style="color:var(--muted);">${Office.icon("send-x")}<span style="margin-left:0.35rem;">Δεν υπάρχουν ακόμα καταγεγραμμένες αποστολές ειδοποιήσεων.</span></p>`;
    return;
  }

  const t = document.createElement("table");
  t.className = "data notify-sent-table";
  const hr = document.createElement("tr");
  ["Ώρα", "Κατάστημα", "Κανάλι", "Λήπτης", "Εργαζόμενος", "Τύπος", "Κατάσταση", "Run"].forEach((h) => {
    const th = document.createElement("th");
    th.textContent = h;
    hr.appendChild(th);
  });
  t.appendChild(hr);

  rows.forEach((row) => {
    const f = row.fields || {};
    const tr = document.createElement("tr");

    const tdTs = document.createElement("td");
    tdTs.className = "sync-log-ts";
    tdTs.textContent = formatTs(row.created_at);
    tr.appendChild(tdTs);

    const tdStore = document.createElement("td");
    Office.setStoreNameOrIdText(tdStore, {
      storeId: row.store_id,
      storeName: row.store_name,
    });
    tr.appendChild(tdStore);

    const tdChannel = document.createElement("td");
    tdChannel.textContent = f.notification_channel || "—";
    tr.appendChild(tdChannel);

    const tdRecipient = document.createElement("td");
    tdRecipient.textContent =
      [f.recipient_name, f.recipient_mobile, f.recipient_email].filter(Boolean).join(" / ") || "—";
    tr.appendChild(tdRecipient);

    const tdEmployee = document.createElement("td");
    tdEmployee.textContent = [f.employee_name, f.employee_afm].filter(Boolean).join(" / ") || "—";
    tr.appendChild(tdEmployee);

    const tdKind = document.createElement("td");
    tdKind.textContent = f.notify_kind_label || f.notify_kind || "—";
    tr.appendChild(tdKind);

    const tdStatus = document.createElement("td");
    tdStatus.innerHTML = sentNotificationStatus(row);
    if (f.error) tdStatus.title = f.error;
    tr.appendChild(tdStatus);

    const tdRun = document.createElement("td");
    tdRun.innerHTML = `<code>${Office.escapeHtml(String(row.run_id || "").slice(0, 8))}</code>`;
    tdRun.title = row.run_id || "";
    tr.appendChild(tdRun);

    t.appendChild(tr);
  });

  wrap.innerHTML = "";
  wrap.appendChild(t);
  appendCursorPager(wrap, "sent", rows.length, hasMore, loadNotifySent);
}

async function loadNotifyActions() {
  const wrap = document.getElementById("notifyActionsWrap");
  if (!wrap) return;
  wrap.innerHTML =
    `<p style="color:var(--muted);">${Office.icon("hourglass-split")}<span style="margin-left:0.35rem;">Φόρτωση…</span></p>`;
  try {
    const qs = new URLSearchParams({
      kind: "today_notifications",
      limit: String(pageSize()),
    });
    const beforeId = currentBeforeId("actions");
    if (beforeId != null) qs.set("before_id", String(beforeId));
    const res = await fetch(`/api/audit/list?${qs}`);
    const data = await res.json();
    if (!res.ok) {
      wrap.innerHTML = `<p style="color:var(--err);">${Office.formatMultilineHtml(data.error || "Σφάλμα")}</p>`;
      return;
    }
    rememberNextCursor("actions", data.next_before_id, data.has_more);
    renderNotifyActions(data.audit || [], Boolean(data.has_more));
    syncLogState.actionsLoaded = true;
  } catch (e) {
    wrap.innerHTML = `<p style="color:var(--err);">${Office.formatMultilineHtml(String(e))}</p>`;
  }
}

function renderNotifyActions(rows, hasMore) {
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
    Office.setStoreNameOrIdText(tdStore, {
      storeId: row.store_id,
      storeName: row.notification_actor?.store_name || row.store_name,
    });
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
  appendCursorPager(wrap, "actions", rows.length, hasMore, loadNotifyActions);
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
    Office.setStoreNameOrIdText(tdStore, {
      storeId: run.store_id,
      storeName: run.store_name,
    });
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
  appendTablePager(wrap, syncLogState.page, pageCount, (p) => {
    syncLogState.page = p;
    loadRuns();
  });
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
                ? ` <span class="sync-log-fields">${Office.escapeHtml(syncLineFieldsText(line.fields))}</span>`
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
