const OFFICE_MSG_DISMISS_MS = 4000;

function scheduleOfficeMsgDismiss(el) {
  if (!el || !el.classList.contains("show") || el.classList.contains("loading") || el.classList.contains("sync-panel")) return;
  window.clearTimeout(el._officeMsgDismissTimer);
  el._officeMsgDismissTimer = window.setTimeout(() => {
    el.classList.remove("show", "ok", "err");
    el.innerHTML = "";
    el._officeMsgDismissTimer = null;
  }, OFFICE_MSG_DISMISS_MS);
}

function officeDialog({ title, message, confirmText, cancelText, alertOnly = false, danger = false }) {
  let modal = document.getElementById("officeConfirmModal");
  if (!modal) {
    modal = document.createElement("div");
    modal.id = "officeConfirmModal";
    modal.className = "office-confirm-modal hidden";
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    modal.setAttribute("aria-labelledby", "officeConfirmTitle");
    modal.setAttribute("aria-describedby", "officeConfirmMessage");
    modal.innerHTML =
      '<div class="office-confirm-backdrop" data-office-dialog-cancel></div>' +
      '<div class="office-confirm-panel">' +
        '<div class="office-confirm-icon"><i class="bi" aria-hidden="true"></i></div>' +
        '<div class="office-confirm-content"><h2 id="officeConfirmTitle"></h2>' +
        '<p id="officeConfirmMessage"></p></div>' +
        '<div class="office-confirm-actions">' +
          '<button type="button" class="btn btn-secondary" data-office-dialog-cancel>Ακύρωση</button>' +
          '<button type="button" class="btn btn-primary" data-office-dialog-confirm>Επιβεβαίωση</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(modal);
  }

  if (typeof modal._officeDialogResolve === "function") modal._officeDialogResolve(false);
  const previousFocus = document.activeElement;
  const titleEl = modal.querySelector("#officeConfirmTitle");
  const messageEl = modal.querySelector("#officeConfirmMessage");
  const icon = modal.querySelector(".office-confirm-icon .bi");
  const cancelButton = modal.querySelector("[data-office-dialog-cancel].btn");
  const confirmButton = modal.querySelector("[data-office-dialog-confirm]");
  titleEl.textContent = title || (alertOnly ? "Ενημέρωση" : "Επιβεβαίωση");
  messageEl.textContent = String(message || "");
  cancelButton.textContent = cancelText || "Ακύρωση";
  confirmButton.textContent = confirmText || (alertOnly ? "Κλείσιμο" : "Επιβεβαίωση");
  cancelButton.hidden = alertOnly;
  confirmButton.classList.toggle("btn-danger", Boolean(danger));
  icon.className = `bi ${alertOnly ? "bi-info-circle-fill" : danger ? "bi-exclamation-triangle-fill" : "bi-question-circle-fill"}`;
  modal.classList.remove("hidden");

  return new Promise((resolve) => {
    const finish = (accepted) => {
      if (modal.classList.contains("hidden")) return;
      modal.classList.add("hidden");
      modal.removeEventListener("click", onClick);
      document.removeEventListener("keydown", onKeydown);
      modal._officeDialogResolve = null;
      previousFocus?.focus?.();
      resolve(accepted);
    };
    const onClick = (event) => {
      if (event.target.closest("[data-office-dialog-confirm]")) finish(true);
      else if (event.target.closest("[data-office-dialog-cancel]")) finish(false);
    };
    const onKeydown = (event) => {
      if (event.key === "Escape") finish(false);
      if (event.key === "Enter") finish(true);
    };
    modal._officeDialogResolve = finish;
    modal.addEventListener("click", onClick);
    document.addEventListener("keydown", onKeydown);
    window.setTimeout(() => confirmButton.focus(), 0);
  });
}

Object.assign(window.Office, {
  confirm(message, options = {}) {
    return officeDialog({ ...options, message, alertOnly: false });
  },

  alert(message, options = {}) {
    return officeDialog({ ...options, message, alertOnly: true });
  },

  showMsg(elId, text, ok) {
    const el = document.getElementById(elId);
    if (!el) return;
    window.clearTimeout(el._officeMsgDismissTimer);
    if (!String(text || "").trim()) {
      el.innerHTML = "";
      el.className = "msg";
      return;
    }
    const ic = ok ? "check-circle-fill" : "exclamation-triangle-fill";
    el.innerHTML = `${this.icon(ic)} <span>${this.formatMultilineHtml(text)}</span>`;
    el.className = "msg show " + (ok ? "ok" : "err");
    scheduleOfficeMsgDismiss(el);
  },

  showLoading(elId, text, step, total, logLines) {
    const el = document.getElementById(elId);
    if (!el) return;
    window.clearTimeout(el._officeMsgDismissTimer);
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
            `${this.formatMultilineHtml(prefix + (line.message || ""))}</div>`
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

// Καλύπτει και παλαιότερες σελίδες που αλλάζουν απευθείας τις classes του msg.
const officeMsgObserver = new MutationObserver((mutations) => {
  mutations.forEach((mutation) => scheduleOfficeMsgDismiss(mutation.target));
});
document.querySelectorAll(".msg.show").forEach(scheduleOfficeMsgDismiss);
officeMsgObserver.observe(document.body, {
  subtree: true,
  attributes: true,
  attributeFilter: ["class"],
});
