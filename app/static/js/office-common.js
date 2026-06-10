const Office = {
  draftKey: "kartaStoreDraft",
  TABLE_PAGE_SIZE: 20,

  icon(name) {
    return `<i class="bi bi-${name}" aria-hidden="true"></i>`;
  },

  initChrome() {
    document.querySelectorAll(".sidebar .logo").forEach((el) => {
      if (el.querySelector(".logo-icon")) return;
      const text = el.innerHTML;
      el.innerHTML =
        `${this.icon("briefcase-fill")}<span class="logo-icon-wrap">${text}</span>`;
      el.querySelector(".bi")?.classList.add("logo-icon");
    });
    const navIcons = {
      home: "house-door",
      stores: "shop-window",
      employees: "people-fill",
      schedule: "calendar-week",
      worklog: "clock-history",
      workcard: "credit-card-2-front",
      synclog: "journal-text",
    };
    document.querySelectorAll(".sidebar nav a[data-nav]").forEach((a) => {
      if (a.querySelector(".bi")) return;
      const key = a.dataset.nav;
      const label = a.textContent.trim();
      a.innerHTML = `${this.icon(navIcons[key] || "circle")}<span>${label}</span>`;
    });
    document.querySelectorAll(".sidebar").forEach((sb) => {
      if (sb.querySelector("#sidebarActiveStore")) return;
      const box = document.createElement("div");
      box.id = "sidebarActiveStore";
      box.className = "sidebar-active-store hidden";
      const nav = sb.querySelector("nav");
      if (nav) sb.insertBefore(box, nav);
      else sb.appendChild(box);
    });
  },

  getDraft() {
    try {
      return JSON.parse(sessionStorage.getItem(this.draftKey) || "{}");
    } catch {
      return {};
    }
  },

  setDraft(patch) {
    const d = { ...this.getDraft(), ...patch };
    sessionStorage.setItem(this.draftKey, JSON.stringify(d));
    return d;
  },

  clearDraft() {
    sessionStorage.removeItem(this.draftKey);
  },

  escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  },

  async loadActiveStore() {
    const el =
      document.getElementById("sidebarActiveStore") ||
      document.getElementById("activeStoreBanner");
    if (!el) return;
    try {
      const res = await fetch("/api/store/active");
      const data = await res.json();
      if (data.store) {
        el.classList.remove("hidden");
        const s = data.store;
        if (el.id === "sidebarActiveStore") {
          el.innerHTML =
            `${this.icon("shop-window")}<div class="sidebar-active-body">` +
            `<strong>${this.escapeHtml(s.name)}</strong>` +
            `<span>ΑΦΜ ${this.escapeHtml(s.employer_afm)}</span>` +
            `<span>Παράρτημα ${this.escapeHtml(s.branch_aa)}</span>` +
            (s.ergani_env_label
              ? `<span class="env-badge env-${(s.ergani_env || "production").toLowerCase()}">${this.escapeHtml(s.ergani_env_label)}</span>`
              : "") +
            (s.portal_base_url
              ? `<span style="font-size:0.7rem;opacity:0.85;">${this.escapeHtml(this.portalHostFromSync({ portal_base: s.portal_base_url }))}</span>`
              : "") +
            `</div>`;
        } else {
          el.innerHTML =
            `${this.icon("check-circle-fill")}<span><strong>Ενεργό κατάστημα:</strong> ` +
            `${this.escapeHtml(s.name)} (ΑΦΜ ${this.escapeHtml(s.employer_afm)}, ` +
            `παράρτημα ${this.escapeHtml(s.branch_aa)})</span>`;
        }
      } else {
        el.classList.add("hidden");
        el.innerHTML = "";
      }
    } catch {
      el.classList.add("hidden");
    }
  },

  setActiveNav(id) {
    document.querySelectorAll(".sidebar nav a").forEach((a) => {
      a.classList.toggle("active", a.dataset.nav === id);
    });
  },

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

  paginateSlice(rows, page, pageSize = this.TABLE_PAGE_SIZE) {
    const total = rows.length;
    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    const safePage = Math.min(Math.max(1, page), totalPages);
    const start = (safePage - 1) * pageSize;
    return {
      page: safePage,
      totalPages,
      total,
      items: rows.slice(start, start + pageSize),
    };
  },

  buildTablePager(page, totalPages, totalItems, onPageChange, pageSize = this.TABLE_PAGE_SIZE) {
    const nav = document.createElement("nav");
    nav.className = "table-pager";
    nav.setAttribute("aria-label", "Σελίδες αποτελεσμάτων");

    const from = totalItems ? (page - 1) * pageSize + 1 : 0;
    const to = Math.min(page * pageSize, totalItems);
    const info = document.createElement("span");
    info.className = "table-pager-info";
    info.textContent =
      totalItems > 0
        ? `${from}–${to} από ${totalItems}`
        : "0 αποτελέσματα";

    const mkBtn = (label, disabled, handler, extraClass) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = `table-pager-btn${extraClass ? ` ${extraClass}` : ""}`;
      b.textContent = label;
      b.disabled = disabled;
      if (!disabled) b.onclick = handler;
      return b;
    };

    nav.appendChild(mkBtn("‹", page <= 1, () => onPageChange(page - 1), "prev"));
    const pages = document.createElement("span");
    pages.className = "table-pager-pages";
    pages.textContent = `Σελίδα ${page} / ${totalPages}`;
    nav.appendChild(pages);
    nav.appendChild(mkBtn("›", page >= totalPages, () => onPageChange(page + 1), "next"));
    nav.appendChild(info);
    return nav;
  },

  /** Μήνυμα επιτυχίας/αποτυχίας μετά portal sync. */
  buildSyncResultMessage(payload, hostFn) {
    const s = payload?.sync || {};
    const host = hostFn ? hostFn(s) : "";
    if (!payload?.success) {
      let err = payload?.error || s.detail || "Αποτυχία συγχρονισμού";
      if (s.errors?.length) {
        err += ` — ${s.errors.slice(0, 2).join("; ")}`;
      }
      return { ok: false, text: err };
    }
    let msg = `Ολοκληρώθηκε — ${s.count ?? 0} εγγραφές`;
    if (s.work_dates?.length > 1) {
      msg += ` · ${s.days_synced ?? 0}/${s.work_dates.length} ημέρες`;
    }
    if (host) msg += ` (${host})`;
    return { ok: true, text: `${msg}.` };
  },

  _syncStatusUrl(syncUrl, jobId) {
    const base = syncUrl.replace(/\/sync\/?$/, "");
    return `${base}/sync/status/${encodeURIComponent(jobId)}`;
  },

  _sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  },

  /**
   * Portal sync — μία ειδοποίηση (msgId), live progress για διάστημα (polling job).
   */
  async runPortalSync(opts) {
    const {
      url,
      body,
      msgId,
      btnId,
      startMessage = "Συγχρονισμός portal Ergani",
    } = opts;
    const btn = btnId ? document.getElementById(btnId) : null;
    this.setButtonLoading(btn, true);
    const isRange = body.from && body.to && body.from !== body.to;
    try {
      if (isRange) {
        this.showLoading(msgId, `${startMessage} — έναρξη…`, 0, 0);
        const ctrl = new AbortController();
        const startTimer = setTimeout(() => ctrl.abort(), 15000);
        let res;
        try {
          res = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ...body, async: true }),
            signal: ctrl.signal,
          });
        } catch (e) {
          if (e && e.name === "AbortError") {
            return {
              success: false,
              error:
                "Ο server δεν απάντησε εντός 15 δευτ. — επανεκκινήστε την εφαρμογή (python run.py) και δοκιμάστε ξανά.",
            };
          }
          throw e;
        } finally {
          clearTimeout(startTimer);
        }
        const start = await this.parseJson(res);
        if (!res.ok) {
          return {
            success: false,
            error: start.error || start._parseError || `HTTP ${res.status}`,
          };
        }
        if (!start.job_id) {
          if (start.success !== undefined) {
            return {
              success: Boolean(start.success),
              sync: start.sync,
              error: start.error || start.sync?.detail,
              logs: start.sync?.logs,
            };
          }
          return {
            success: false,
            error:
              start.error ||
              "Ο server δεν ξεκίνησε background job (λείπει job_id). Επανεκκινήστε python run.py.",
          };
        }
        const statusUrl = this._syncStatusUrl(url, start.job_id);
        return this.pollSyncJob(statusUrl, msgId);
      }

      this.showLoading(msgId, `${startMessage} — έναρξη…`, 0, 0);
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...body, async: true }),
      });
      const start = await this.parseJson(res);
      if (!res.ok) {
        return {
          success: false,
          error: start.error || start._parseError || `HTTP ${res.status}`,
        };
      }
      if (!start.job_id) {
        if (start.success !== undefined) {
          return {
            success: Boolean(start.success),
            sync: start.sync,
            error: start.error || start.sync?.detail,
            logs: start.sync?.logs,
          };
        }
        return {
          success: false,
          error: start.error || "Δεν ξεκίνησε background job (λείπει job_id).",
        };
      }
      const statusUrl = this._syncStatusUrl(url, start.job_id);
      return this.pollSyncJob(statusUrl, msgId);
    } catch (e) {
      return { success: false, error: String(e) };
    } finally {
      this.setButtonLoading(btn, false);
    }
  },

  async parseJson(res) {
    const text = await res.text();
    if (!text || !text.trim()) {
      return { _parseError: `Κενή απάντηση (HTTP ${res.status})` };
    }
    try {
      return JSON.parse(text);
    } catch {
      const snippet = text.trim().slice(0, 80).replace(/\s+/g, " ");
      if (snippet.toLowerCase().startsWith("<!doctype") || snippet.startsWith("<")) {
        return {
          _parseError:
            res.status === 404
              ? "Δεν βρέθηκε το API — επανεκκινήστε τον διακομιστή (python run.py) και κάντε Ctrl+F5."
              : `Ο διακομιστής επέστρεψε HTML αντί JSON (HTTP ${res.status}).`,
        };
      }
      return { _parseError: `Μη έγκυρη απάντηση (HTTP ${res.status})` };
    }
  },

  /** Ώρα από f_date — ίδια λογική με ergani api-console (HH:MM:SS). */
  /** Ευέλικτη προσέλευση (EueliktoWrario) — λεπτά καθυστέρησης άφιξης/αποχώρησης. */
  formatFlexMinutes(value) {
    if (value === null || value === undefined || value === "") return "—";
    const n = Number(value);
    if (!Number.isFinite(n)) return "—";
    if (n <= 0) return "0′";
    return `${Math.round(n)}′`;
  },

  formatFDateTime(fDate) {
    if (!fDate) return "—";
    let timeVal = String(fDate);
    if (timeVal.includes("T")) {
      timeVal = timeVal.split("T")[1];
    } else if (timeVal.includes(" ")) {
      timeVal = timeVal.split(" ")[1];
    }
    return timeVal.slice(0, 8) || "—";
  },

  /** Πλήρης ημερομηνία+ώρα — όπως ergani console.html (el-GR). */
  portalHostFromSync(sync) {
    const base = sync && sync.portal_base;
    if (!base) return "";
    try {
      return new URL(base).hostname;
    } catch {
      return String(base).replace(/\/$/, "");
    }
  },

  formatFDateTimeEl(fDate) {
    if (!fDate) return "—";
    try {
      const d = new Date(String(fDate).replace("Z", "+00:00"));
      if (!Number.isNaN(d.getTime())) {
        return d.toLocaleString("el-GR");
      }
    } catch {
      /* fallback */
    }
    return this.formatFDateTime(fDate);
  },

  showTableLoading(wrapEl, text) {
    const el =
      typeof wrapEl === "string" ? document.getElementById(wrapEl) : wrapEl;
    if (!el) return;
    const msg = text || "Φόρτωση…";
    el.innerHTML =
      `<p class="table-loading"><i class="bi bi-arrow-repeat bi-spin" aria-hidden="true"></i>` +
      `<span>${this.escapeHtml(msg)}</span></p>`;
  },
};

document.addEventListener("DOMContentLoaded", () => {
  Office.initChrome();
  Office.loadActiveStore();
});
