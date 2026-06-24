Object.assign(window.Office, {
  showMsg(elId, text, ok) {
    const el = document.getElementById(elId);
    if (!el) return;
    const ic = ok ? "check-circle-fill" : "exclamation-triangle-fill";
    el.innerHTML = `${this.icon(ic)} <span>${this.escapeHtml(text)}</span>`;
    el.className = "msg show " + (ok ? "ok" : "err");
  },

  showLoading(elId, text, step, total, logLines) {
    const el = document.getElementById(elId);
    if (!el) return;
    let progressHtml = "";
    const tot = Number(total) || 0;
    const stp = Number(step) || 0;
    if (tot > 0) {
      const pct = Math.min(100, Math.max(0, Math.round((stp / tot) * 100)));
      progressHtml =
        `<div class="sync-progress" role="progressbar" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100">` +
        `<div class="sync-progress-bar" style="width:${pct}%"></div></div>`;
    }
    let logsHtml = "";
    if (Array.isArray(logLines) && logLines.length) {
      const lines = logLines
        .slice(-40)
        .map((line) => {
          const lvl = String(line.level || "INFO").toLowerCase();
          const ts = line.ts ? String(line.ts).replace("T", " ").slice(0, 19) : "";
          const prefix = ts ? `[${ts}] ` : "";
          return (
            `<div class="sync-log-line sync-log-${lvl}">` +
            `${this.escapeHtml(prefix + (line.message || ""))}</div>`
          );
        })
        .join("");
      logsHtml = `<div class="sync-log-lines" aria-live="polite">${lines}</div>`;
    }
    el.innerHTML =
      `<i class="bi bi-arrow-repeat bi-spin" aria-hidden="true"></i>` +
      `<span class="sync-loading-text">${this.escapeHtml(text)}</span>` +
      progressHtml +
      logsHtml;
    el.className = "msg show loading";
    el.setAttribute("role", "status");
    el.setAttribute("aria-live", "polite");
    const logBox = el.querySelector(".sync-log-lines");
    if (logBox) {
      logBox.scrollTop = logBox.scrollHeight;
    }
  },

  /** Polling κατάστασης background sync job. */
  async pollSyncJob(statusUrl, msgId, deadlineMs = 45 * 60 * 1000) {
    const deadline = Date.now() + deadlineMs;
    while (Date.now() < deadline) {
      await this._sleep(400);
      const stRes = await fetch(statusUrl);
      const st = await stRes.json();
      if (!stRes.ok) {
        return {
          success: false,
          error: st.error || `Σφάλμα κατάστασης (HTTP ${stRes.status})`,
        };
      }
      if (st.message || st.log_lines) {
        this.showLoading(msgId, st.message || "Συγχρονισμός…", st.step, st.total, st.log_lines);
      }
      if (st.status === "done" || st.status === "error") {
        const r = st.result || {};
        return {
          success: st.status === "done" && Boolean(r.success),
          sync: r.sync,
          error: r.error || st.message,
          logs: r.logs || st.log_lines,
        };
      }
    }
    return { success: false, error: "Λήξη χρόνου αναμονής συγχρονισμού" };
  },

  setButtonLoading(btn, loading) {
    if (!btn) return;
    btn.disabled = loading;
    btn.classList.toggle("is-loading", loading);
    btn.querySelectorAll(".bi").forEach((ic) => {
      ic.classList.toggle("bi-spin", loading);
    });
  },

  /** Κρύβει τη λίστα — εμφανίζει μόνο το panel προόδου μέσα στην κάρτα. */
  beginSyncPanel(wrapId, msgId) {
    const wrap = document.getElementById(wrapId);
    const msg = document.getElementById(msgId);
    if (!wrap || !msg) return;
    const card = wrap.closest(".card");
    wrap.hidden = true;
    card?.classList.add("sync-active");
    if (!msg._syncRestoreParent) {
      msg._syncRestoreParent = msg.parentElement;
      msg._syncRestoreNext = msg.nextSibling;
    }
    if (card && msg.parentElement !== card) {
      card.appendChild(msg);
    }
    msg.classList.add("sync-panel");
  },

  /** Επαναφέρει τη λίστα — το μήνυμα γυρίζει κάτω από την κάρτα. */
  endSyncPanel(wrapId, msgId) {
    const wrap = document.getElementById(wrapId);
    const msg = document.getElementById(msgId);
    if (!wrap || !msg) return;
    const card = wrap.closest(".card");
    wrap.hidden = false;
    card?.classList.remove("sync-active");
    msg.classList.remove("sync-panel");
    if (msg._syncRestoreParent && msg.parentElement !== msg._syncRestoreParent) {
      const parent = msg._syncRestoreParent;
      if (msg._syncRestoreNext) {
        parent.insertBefore(msg, msg._syncRestoreNext);
      } else {
        parent.appendChild(msg);
      }
    }
  },
});
