let syncDatePicker = null;

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
  document.getElementById("btnPeriodSync").onclick = () => runPeriodSync();
  await refreshSyncButton();
});

function getRange() {
  return syncDatePicker ? syncDatePicker.getRange() : { start: "", end: "" };
}

async function refreshSyncButton() {
  const btn = document.getElementById("btnPeriodSync");
  if (!btn) return;
  try {
    const res = await fetch("/api/store/active", { cache: "no-store" });
    const data = await res.json();
    btn.disabled = !data.store;
  } catch {
    btn.disabled = true;
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
