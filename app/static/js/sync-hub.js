let syncDatePicker = null;

const MONTH_LABELS = [
  "Ιανουάριος",
  "Φεβρουάριος",
  "Μάρτιος",
  "Απρίλιος",
  "Μάιος",
  "Ιούνιος",
  "Ιούλιος",
  "Αύγουστος",
  "Σεπτέμβριος",
  "Οκτώβριος",
  "Νοέμβριος",
  "Δεκέμβριος",
];

document.addEventListener("DOMContentLoaded", async () => {
  Office.setActiveNav("sync");
  syncDatePicker = Office.createDatePicker({
    mountId: "syncHubDatePicker",
    mode: "range",
    autoApply: false,
    quickPresets: ["today", "yesterday", "last7", "last30"],
    quickLabels: {
      last7: "Τελευταία εβδομάδα",
      last30: "Τελευταίος μήνας",
    },
  });
  initMonthlySelectors();
  document.getElementById("btnPeriodSync").onclick = () => runPeriodSync();
  document.getElementById("btnMonthlySync").onclick = () => runMonthlySync();
  await refreshSyncButtons();
});

function initMonthlySelectors() {
  const yearSel = document.getElementById("monthlySyncYear");
  const monthSel = document.getElementById("monthlySyncMonth");
  if (!yearSel || !monthSel) return;
  const now = new Date();
  const curYear = now.getFullYear();
  yearSel.innerHTML = "";
  for (let y = curYear; y >= curYear - 5; y--) {
    const opt = document.createElement("option");
    opt.value = String(y);
    opt.textContent = String(y);
    yearSel.appendChild(opt);
  }
  monthSel.innerHTML = "";
  MONTH_LABELS.forEach((label, i) => {
    const opt = document.createElement("option");
    opt.value = String(i + 1);
    opt.textContent = label;
    monthSel.appendChild(opt);
  });
  const prevMonth = now.getMonth() === 0 ? 12 : now.getMonth();
  const prevYear = now.getMonth() === 0 ? curYear - 1 : curYear;
  yearSel.value = String(prevYear);
  monthSel.value = String(prevMonth);
}

function getRange() {
  return syncDatePicker ? syncDatePicker.getRange() : { start: "", end: "" };
}

async function refreshSyncButtons() {
  const btnPeriod = document.getElementById("btnPeriodSync");
  const btnMonthly = document.getElementById("btnMonthlySync");
  try {
    const res = await fetch("/api/store/active", { cache: "no-store" });
    const data = await res.json();
    const ok = Boolean(data.store);
    if (btnPeriod) btnPeriod.disabled = !ok;
    if (btnMonthly) btnMonthly.disabled = !ok;
  } catch {
    if (btnPeriod) btnPeriod.disabled = true;
    if (btnMonthly) btnMonthly.disabled = true;
  }
}

function renderLogLines(lines) {
  const wrap = document.getElementById("syncHubLogWrap");
  if (!wrap) return;
  if (!lines || !lines.length) {
    wrap.innerHTML = `<p style="color:var(--muted);">Αναμονή βημάτων…</p>`;
    return;
  }
  wrap.innerHTML = lines
    .map((line) => {
      const lvl = String(line.level || "INFO").toLowerCase();
      const ts = line.created_at ? String(line.created_at).replace("T", " ").slice(11, 19) : "";
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
  wrap.scrollTop = wrap.scrollHeight;
}

function showProgress(message, step, total, logLines) {
  const wrap = document.getElementById("syncHubLogWrap");
  if (!wrap) return;
  const pct = total > 0 ? Math.round((step / total) * 100) : 0;
  let html =
    `<p class="table-loading sync-hub-progress">` +
    `<i class="bi bi-arrow-repeat bi-spin" aria-hidden="true"></i>` +
    `<span>${Office.escapeHtml(message || "Συγχρονισμός…")}</span>`;
  if (total > 0) {
    html += ` <span class="sync-hub-progress-pct">(${step}/${total} · ${pct}%)</span>`;
  }
  html += `</p>`;
  if (logLines && logLines.length) {
    html += `<div class="sync-hub-log-live">${logLines
      .map((line) => {
        const lvl = String(line.level || "INFO").toLowerCase();
        return `<div class="sync-log-line sync-log-${lvl}">${Office.escapeHtml(line.message || "")}</div>`;
      })
      .join("")}</div>`;
  }
  wrap.innerHTML = html;
  wrap.scrollTop = wrap.scrollHeight;
}

async function pollPeriodJob(statusUrl) {
  const deadline = Date.now() + 45 * 60 * 1000;
  while (Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 400));
    const stRes = await fetch(statusUrl, { cache: "no-store" });
    const st = await stRes.json();
    if (!stRes.ok) {
      return {
        success: false,
        error: st.error || `Σφάλμα κατάστασης (HTTP ${stRes.status})`,
      };
    }
    showProgress(st.message, st.step, st.total, st.log_lines);
    if (st.status === "done" || st.status === "error") {
      const r = st.result || {};
      return {
        success: st.status === "done" && Boolean(r.success),
        sync: r.sync,
        error: r.error || st.message,
        logs: r.logs,
        log_lines: st.log_lines,
        message: st.message,
      };
    }
  }
  return { success: false, error: "Λήξη χρόνου αναμονής συγχρονισμού" };
}

async function runPeriodSync() {
  const btn = document.getElementById("btnPeriodSync");
  const r = getRange();
  if (!r.start) {
    Office.showMsg("syncHubMsg", "Επιλέξτε περίοδο.", false);
    return;
  }
  const body =
    r.start === r.end
      ? { date: r.start, async: true }
      : { from: r.start, to: r.end, async: true };

  Office.setButtonLoading(btn, true);
  showProgress("Έναρξη συγχρονισμού…", 0, 3);
  const msgEl = document.getElementById("syncHubMsg");
  if (msgEl) {
    msgEl.innerHTML = "";
    msgEl.className = "msg";
  }

  try {
    const res = await fetch("/api/period-sync/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const start = await res.json();
    if (!res.ok || !start.job_id) {
      Office.showMsg("syncHubMsg", start.error || "Αποτυχία εκκίνησης", false);
      return;
    }

    const statusUrl = `/api/period-sync/run/status/${encodeURIComponent(start.job_id)}`;
    const polled = await pollPeriodJob(statusUrl);

    if (polled.log_lines && polled.log_lines.length) {
      renderLogLines(polled.log_lines);
    } else if (polled.logs && polled.logs.length) {
      renderLogLines(
        polled.logs.map((entry) => ({
          level: entry.level || "INFO",
          message: entry.message || String(entry),
          created_at: entry.ts || "",
        }))
      );
    }

    const ok = Boolean(polled.success);
    Office.showMsg(
      "syncHubMsg",
      polled.error && !ok ? polled.error : polled.message || (ok ? "Ολοκληρώθηκε." : "Αποτυχία."),
      ok
    );
    await Office.loadActiveStore();
  } catch (e) {
    Office.showMsg("syncHubMsg", String(e), false);
  } finally {
    Office.setButtonLoading(btn, false);
  }
}

async function runMonthlySync() {
  const btn = document.getElementById("btnMonthlySync");
  const year = parseInt(document.getElementById("monthlySyncYear")?.value || "0", 10);
  const month = parseInt(document.getElementById("monthlySyncMonth")?.value || "0", 10);
  if (!year || !month) {
    Office.showMsg("syncHubMsg", "Επιλέξτε έτος και μήνα.", false);
    return;
  }

  Office.setButtonLoading(btn, true);
  showProgress(`Μηνιαία κατάσταση ${String(month).padStart(2, "0")}/${year}…`, 0, 1);
  const msgEl = document.getElementById("syncHubMsg");
  if (msgEl) {
    msgEl.innerHTML = "";
    msgEl.className = "msg";
  }

  try {
    const res = await fetch("/api/monthly-status/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ year, month, async: true }),
    });
    const start = await res.json();
    if (!res.ok || !start.job_id) {
      Office.showMsg("syncHubMsg", start.error || "Αποτυχία εκκίνησης", false);
      return;
    }

    const statusUrl = `/api/monthly-status/sync/status/${encodeURIComponent(start.job_id)}`;
    const polled = await pollPeriodJob(statusUrl);

    if (polled.log_lines && polled.log_lines.length) {
      renderLogLines(polled.log_lines);
    }

    const ok = Boolean(polled.success);
    Office.showMsg(
      "syncHubMsg",
      polled.error && !ok ? polled.error : polled.message || (ok ? "Ολοκληρώθηκε." : "Αποτυχία."),
      ok
    );
    await Office.loadActiveStore();
  } catch (e) {
    Office.showMsg("syncHubMsg", String(e), false);
  } finally {
    Office.setButtonLoading(btn, false);
  }
}
