const Office = {
  draftKey: "kartaStoreDraft",
  TABLE_PAGE_SIZE: 20,

  icon(name) {
    return `<i class="bi bi-${name}" aria-hidden="true"></i>`;
  },

  initChrome() {
    document.querySelectorAll(".sidebar .logo").forEach((el) => {
      if (el.querySelector(".logo-img") || el.querySelector(".logo-icon")) return;
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
      sync: "arrow-repeat",
      synclog: "journal-text",
    };
    document.querySelectorAll(".sidebar nav a[data-nav]").forEach((a) => {
      if (a.querySelector(".bi")) return;
      const key = a.dataset.nav;
      const label = a.textContent.trim();
      a.innerHTML = `${this.icon(navIcons[key] || "circle")}<span>${label}</span>`;
    });
    document.querySelectorAll(".sidebar").forEach((sb) => {
      let box = sb.querySelector("#sidebarActiveStore");
      if (!box) {
        box = document.createElement("div");
        box.id = "sidebarActiveStore";
        box.className = "sidebar-active-store hidden";
      }
      const nav = sb.querySelector("nav");
      if (nav) nav.after(box);
      else sb.appendChild(box);
    });
  },

  initPageBackButton() {
    if (document.body.classList.contains("login-page")) return;
    const main = document.querySelector("main.main");
    const title = main?.querySelector(":scope > .page-title");
    if (!main || !title || title.closest(".page-title-bar")) return;
    if (main.querySelector(":scope > .page-back, :scope > .page-back-link")) return;

    const bar = document.createElement("div");
    bar.className = "page-title-bar";
    title.parentNode.insertBefore(bar, title);
    bar.appendChild(title);

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "page-back-btn";
    btn.title = "Πίσω";
    btn.setAttribute("aria-label", "Πίσω στην προηγούμενη σελίδα");
    btn.innerHTML = this.icon("arrow-left");
    btn.addEventListener("click", () => {
      if (window.history.length > 1) {
        window.history.back();
        return;
      }
      window.location.href = "/ui/";
    });
    bar.appendChild(btn);
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

  _activeStoreCache: null,
  _activeStoreInflight: null,

  invalidateActiveStoreCache() {
    this._activeStoreCache = null;
    this._activeStoreInflight = null;
  },

  async fetchActiveStore({ refresh = false } = {}) {
    if (!refresh && this._activeStoreCache) {
      return this._activeStoreCache;
    }
    if (!refresh && this._activeStoreInflight) {
      return this._activeStoreInflight;
    }
    const req = fetch("/api/store/active", { cache: "no-store" })
      .then(async (res) => {
        let data = {};
        try {
          data = await res.json();
        } catch {
          throw new Error(
            `Σφάλμα διακομιστή (HTTP ${res.status}). Δοκιμάστε επανεκκίνηση του site.`
          );
        }
        if (!res.ok) {
          throw new Error(data.error || `HTTP ${res.status}`);
        }
        this._activeStoreCache = data;
        this._activeStoreInflight = null;
        return data;
      })
      .catch((err) => {
        this._activeStoreInflight = null;
        throw err;
      });
    this._activeStoreInflight = req;
    return req;
  },

  applyActiveStoreChrome(data) {
    const el =
      document.getElementById("sidebarActiveStore") ||
      document.getElementById("activeStoreBanner");
    if (!el) return;
    const s = data && data.store;
    if (s) {
      el.classList.remove("hidden");
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
  },

  async loadActiveStore({ refresh = false } = {}) {
    try {
      const data = await this.fetchActiveStore({ refresh });
      this.applyActiveStoreChrome(data);
    } catch {
      this.applyActiveStoreChrome(null);
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
        return d.toLocaleString("el-GR", { hour12: false });
      }
    } catch {
      /* fallback */
    }
    return this.formatFDateTime(fDate);
  },

  /** Ώρα HH:mm:ss — πάντα 24ωρη μορφή. */
  formatTime24(date = new Date(), { seconds = true } = {}) {
    const d = date instanceof Date ? date : new Date(date);
    if (Number.isNaN(d.getTime())) return "—";
    const h = String(d.getHours()).padStart(2, "0");
    const m = String(d.getMinutes()).padStart(2, "0");
    if (!seconds) return `${h}:${m}`;
    const s = String(d.getSeconds()).padStart(2, "0");
    return `${h}:${m}:${s}`;
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

  todayIsoLocal() {
    const d = new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  },

  isoCalendarDay(iso) {
    if (!iso) return null;
    return String(iso).slice(0, 10);
  },

  formatSyncTimestamp(iso) {
    if (!iso) return "ποτέ";
    return String(iso).replace("T", " ").slice(0, 16);
  },

  scheduleNeedsAutoSync(scheduleLastSyncAt) {
    const today = this.todayIsoLocal();
    const last = this.isoCalendarDay(scheduleLastSyncAt);
    return !last || last < today;
  },

  erganiDateToIso(workDate) {
    const m = String(workDate || "")
      .trim()
      .match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    if (!m) return "";
    const day = String(parseInt(m[1], 10)).padStart(2, "0");
    const month = String(parseInt(m[2], 10)).padStart(2, "0");
    return `${m[3]}-${month}-${day}`;
  },

  /** Ημερομηνία εργασίας σε YYYY-MM-DD (ISO ή dd/mm/yyyy). */
  workDateToIso(workDate) {
    const s = String(workDate || "").trim();
    if (!s) return null;
    if (/^\d{4}-\d{2}-\d{2}/.test(s)) return s.slice(0, 10);
    const iso = this.erganiDateToIso(s);
    return iso || null;
  },

  addDaysIso(iso, days) {
    const p = String(iso || "").split("-");
    if (p.length !== 3) return null;
    const y = parseInt(p[0], 10);
    const m = parseInt(p[1], 10);
    const d = parseInt(p[2], 10);
    if (!Number.isFinite(y) || !Number.isFinite(m) || !Number.isFinite(d)) return null;
    const dt = new Date(y, m - 1, d + days);
    return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}-${String(dt.getDate()).padStart(2, "0")}`;
  },

  normalizeHourMinute(timeStr) {
    const raw = String(timeStr || "").trim();
    if (!raw) return "";
    const colon = raw.match(/^(\d{1,2}):(\d{2})$/);
    if (colon) {
      const h = parseInt(colon[1], 10);
      const m = parseInt(colon[2], 10);
      if (h >= 0 && h <= 23 && m >= 0 && m <= 59) {
        return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
      }
      return "";
    }
    const formatted = this.formatHourMinuteInput(raw);
    const parsed = formatted.match(/^(\d{1,2}):(\d{2})$/);
    if (!parsed) return "";
    const h = parseInt(parsed[1], 10);
    const m = parseInt(parsed[2], 10);
    if (h < 0 || h > 23 || m < 0 || m > 59) return "";
    return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
  },

  /** Μορφοποίηση ώρας κατά την πληκτρολόγηση (π.χ. 1030 → 10:30). */
  formatHourMinuteInput(value) {
    let s = String(value || "").replace(/[^\d:]/g, "");
    if (s.includes(":")) {
      const parts = s.split(":", 2);
      const h = parts[0].replace(/\D/g, "").slice(0, 2);
      const m = (parts[1] || "").replace(/\D/g, "").slice(0, 2);
      return m.length ? `${h}:${m}` : h;
    }
    const digits = s.replace(/\D/g, "").slice(0, 4);
    if (digits.length <= 2) return digits;
    if (digits.length === 3) return `0${digits.slice(0, 1)}:${digits.slice(1)}`;
    return `${digits.slice(0, 2)}:${digits.slice(2)}`;
  },

  bindHourMinuteInput(inputId) {
    const el = document.getElementById(inputId);
    if (!el) return;
    el.addEventListener("input", () => {
      const formatted = this.formatHourMinuteInput(el.value || "");
      if (el.value !== formatted) el.value = formatted;
    });
    el.addEventListener("blur", () => {
      const norm = this.normalizeHourMinute(el.value || "");
      if (norm) el.value = norm;
    });
  },

  workCardUrlOptsFromRow(row) {
    const opts = {};
    if (!row) return opts;
    if (row.needs_card_punch && row.retro_time) {
      opts.retro = true;
      opts.retro_time = this.normalizeHourMinute(row.retro_time) || row.retro_time;
      opts.card_event = row.card_event || "check_out";
      opts.retro_highlight = true;
      return opts;
    }
    const wl =
      row.work_log && typeof row.work_log === "object" ? row.work_log : row;
    const sched =
      row.schedule && typeof row.schedule === "object" ? row.schedule : null;
    const hf = String(wl.hour_from || row.hour_from || "").trim();
    const ht = String(wl.hour_to || row.hour_to || "").trim();
    if (hf && ht) return opts;
    const schedFrom = sched ? String(sched.hour_from || "").trim() : "";
    const schedTo = sched ? String(sched.hour_to || "").trim() : "";
    if (hf && !ht && schedTo) {
      opts.retro = true;
      opts.card_event = "check_out";
      opts.retro_time = this.normalizeHourMinute(schedTo) || schedTo;
      opts.retro_highlight = true;
    } else if (!hf && schedFrom) {
      opts.retro = true;
      opts.card_event = "check_in";
      opts.retro_time = this.normalizeHourMinute(schedFrom) || schedFrom;
      opts.retro_highlight = true;
    } else if (!hf) {
      opts.retro = true;
      opts.card_event = "check_in";
      opts.retro_highlight = true;
    } else if (!ht && !this.workLogExitStillPending(row)) {
      opts.retro = true;
      opts.card_event = "check_out";
      opts.retro_highlight = true;
    }
    return opts;
  },

  workCardUrl(employeeAfm, dateIso, employeeName, opts = {}) {
    const afm = String(employeeAfm || "").trim();
    if (!afm) return "/ui/work-card";
    const p = new URLSearchParams({ employee_afm: afm });
    const d = String(dateIso || "").trim();
    if (d) p.set("date", d);
    const name = String(employeeName || "").trim();
    if (name) p.set("employee_name", name);
    if (opts.retro) p.set("retro", "1");
    const retroTime = String(opts.retro_time || "").trim();
    const normRetro = retroTime ? this.normalizeHourMinute(retroTime) : "";
    if (normRetro) p.set("retro_time", normRetro);
    const cardEvent = String(opts.card_event || "").trim();
    if (cardEvent) p.set("card_event", cardEvent);
    if (opts.retro_highlight) p.set("retro_highlight", "1");
    return `/ui/work-card?${p}`;
  },

  readWorkCardQueryPrefill() {
    const p = new URLSearchParams(window.location.search);
    const afm = (p.get("employee_afm") || p.get("afm") || "").trim();
    const date = (p.get("date") || "").trim();
    return {
      employee_afm: afm,
      employee_name: (p.get("employee_name") || "").trim(),
      date: /^\d{4}-\d{2}-\d{2}$/.test(date) ? date : "",
      retro: p.get("retro") === "1",
      retro_time: (p.get("retro_time") || "").trim(),
      card_event: (p.get("card_event") || "").trim(),
      retro_highlight: p.get("retro_highlight") === "1",
    };
  },

  applyWorkCardQueryPrefill(datePicker, employeeAc, retroDatePicker) {
    const prefill = this.readWorkCardQueryPrefill();
    if (prefill.date && datePicker?.setRange) {
      datePicker.setRange(prefill.date, prefill.date);
    }
    if (prefill.employee_afm && employeeAc) {
      employeeAc.setValue(
        prefill.employee_afm,
        prefill.employee_name || prefill.employee_afm
      );
    }
    if (prefill.retro && prefill.date && retroDatePicker) {
      retroDatePicker.setIso(prefill.date);
    }
    if (prefill.retro && prefill.retro_time) {
      const retroTime = document.getElementById("wcRetroTime");
      const norm = this.normalizeHourMinute(prefill.retro_time);
      if (retroTime && norm) retroTime.value = norm;
    }
    if (prefill.retro_highlight) {
      document
        .querySelector(".work-card-retro")
        ?.classList.add("work-card-retro--required");
      requestAnimationFrame(() => {
        document
          .querySelector(".work-card-retro")
          ?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      });
    }
    if (prefill.card_event === "check_in" || prefill.card_event === "check_out") {
      const btnId = prefill.retro
        ? prefill.card_event === "check_in"
          ? "btnRetroCheckIn"
          : "btnRetroCheckOut"
        : prefill.card_event === "check_in"
          ? "btnCheckIn"
          : "btnCheckOut";
      document.getElementById(btnId)?.classList.add("work-card-action--required");
    }
    return prefill;
  },

  async recordStoreSync(kind) {
    try {
      const res = await fetch("/api/store/record-sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind }),
        cache: "no-store",
      });
      this.invalidateActiveStoreCache();
      return await this.parseJson(res);
    } catch (e) {
      return { success: false, error: String(e) };
    }
  },

  async refreshActiveStoreSyncMeta(elId, kind, store) {
    try {
      if (store) {
        this.updateSyncMetaLine(elId, store, kind);
        return store;
      }
      const data = await this.fetchActiveStore();
      if (data.store) {
        this.updateSyncMetaLine(elId, data.store, kind);
      }
      return data.store || null;
    } catch {
      return null;
    }
  },

  formatSyncedAt(iso) {
    if (!iso) return "—";
    return String(iso).replace("T", " ").slice(0, 16);
  },

  initWorkLogHistoryModal(modalId = "workLogHistoryModal") {
    const modal = document.getElementById(modalId);
    if (!modal || modal.dataset.historyBound) return;
    modal.dataset.historyBound = "1";
    modal.querySelectorAll("[data-history-close]").forEach((el) => {
      el.addEventListener("click", () => this.closeWorkLogHistoryModal(modalId));
    });
    document.addEventListener("keydown", (e) => {
      if (e.key !== "Escape") return;
      if (modal.classList.contains("hidden")) return;
      e.preventDefault();
      this.closeWorkLogHistoryModal(modalId);
    });
  },

  closeWorkLogHistoryModal(modalId = "workLogHistoryModal") {
    document.getElementById(modalId)?.classList.add("hidden");
  },

  parseClockToMinutes(value) {
    const s = String(value || "").trim();
    if (!s) return null;
    const m = s.match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?$/);
    if (!m) return null;
    const h = parseInt(m[1], 10);
    const min = parseInt(m[2], 10);
    if (!Number.isFinite(h) || !Number.isFinite(min)) return null;
    return h * 60 + min;
  },

  scheduleStartMinutesFromRow(row) {
    const sched = row?.schedule;
    if (sched && sched.hour_from) {
      const parsed = this.parseClockToMinutes(sched.hour_from);
      if (parsed != null) return parsed;
    }
    const label = String(row?.schedule_label || "").trim();
    if (!label || label === "—" || /ρεπο|ανάπαυση/i.test(label)) return null;
    const parts = label.split("·").map((x) => x.trim()).filter(Boolean);
    const last = parts[parts.length - 1] || label;
    const match = last.match(/(\d{1,2}:\d{2}(?::\d{2})?)\s*[–\-]/);
    if (match) return this.parseClockToMinutes(match[1]);
    return null;
  },

  scheduleEndMinutesFromRow(row) {
    let endMin = null;
    const sched = row?.schedule;
    if (sched && sched.hour_to) {
      endMin = this.parseClockToMinutes(sched.hour_to);
    }
    if (endMin == null) {
      const label = String(row?.schedule_label || "").trim();
      if (!label || label === "—" || /ρεπο|ανάπαυση/i.test(label)) return null;
      const parts = label.split("·").map((x) => x.trim()).filter(Boolean);
      const last = parts[parts.length - 1] || label;
      const match = last.match(/\s[–\-]\s*(\d{1,2}:\d{2}(?::\d{2})?)\s*$/);
      if (match) endMin = this.parseClockToMinutes(match[1]);
    }
    if (endMin == null) return null;
    const startMin = this.scheduleStartMinutesFromRow(row);
    if (startMin != null && endMin <= startMin) {
      endMin += 24 * 60;
    }
    return endMin;
  },

  /** Σήμερα, έχει είσοδο, λείπει έξοδος, ακόμα πριν το τέλος βάρδιας (ψηφ. ωράριο). */
  workLogExitStillPending(row) {
    const hf = String(row?.hour_from || "").trim();
    const ht = String(row?.hour_to || "").trim();
    if (!hf || ht) return false;
    const wd = this.workDateToIso(row?.work_date);
    if (!wd) return false;
    const endMin = this.scheduleEndMinutesFromRow(row);
    if (endMin == null) return false;
    const today = this.todayIsoLocal();
    const nowMin = this.parseClockToMinutes(this.formatTime24(new Date(), { seconds: false }));
    if (nowMin == null) return false;

    const spansMidnight = endMin >= 24 * 60;
    let timelineNow = null;
    if (wd === today) {
      timelineNow = nowMin;
    } else if (spansMidnight && this.addDaysIso(wd, 1) === today) {
      timelineNow = nowMin + 24 * 60;
    } else {
      return false;
    }
    return timelineNow < endMin;
  },

  formatWorkLogTimeCell(value, title = "Λείπει ώρα") {
    const txt = String(value || "").trim();
    if (txt) {
      return { html: this.escapeHtml(txt), isMissing: false };
    }
    return {
      html:
        `<span class="work-log-time-missing" title="${this.escapeHtml(title)}">` +
        `${this.icon("clock")}</span>`,
      isMissing: true,
    };
  },

  workLogRowIsDeficient(row) {
    const hf = String(row?.hour_from || "").trim();
    const ht = String(row?.hour_to || "").trim();
    if (hf && ht) return false;
    if (!hf) return true;
    if (!ht && this.workLogExitStillPending(row)) return false;
    return !ht;
  },

  workLogRowIsComplete(row) {
    const hf = String(row?.hour_from || "").trim();
    const ht = String(row?.hour_to || "").trim();
    return Boolean(hf && ht);
  },

  workLogMissingPunchSummary(row) {
    const hf = String(row?.hour_from || "").trim();
    const ht = String(row?.hour_to || "").trim();
    if (!hf && !ht) return "ελλιπή είσοδο και έξοδο";
    if (!hf) return "ελλιπή είσοδο";
    if (!ht && !this.workLogExitStillPending(row)) return "ελλιπή έξοδο";
    if (!ht) return "έξοδος εκκρεμεί";
    return "";
  },

  workLogRowIsToday(row) {
    const wd = this.workDateToIso(row?.work_date);
    return Boolean(wd && wd === this.todayIsoLocal());
  },

  elapsedWorkDayMinutes(fromMin, toMin) {
    if (fromMin == null || toMin == null) return null;
    let elapsed = toMin - fromMin;
    if (elapsed < 0) elapsed += 24 * 60;
    return elapsed;
  },

  workLogHasDigitalSchedule(row) {
    return this.scheduleStartMinutesFromRow(row) != null;
  },

  /** Ετικέτα ειδοποίησης τύπου 2 (σήμερα). */
  todayNotifyLabel(kind) {
    const labels = {
      exit_without_entry: "εξόδος χωρίς είσοδο",
      late_check_in: "καθυστέρηση εισόδου (>10' από ωράριο)",
      missing_exit_8h: "έλλειψη εξόδου (>8 ώρες από είσοδο)",
    };
    return labels[kind] || kind || "";
  },

  sendTodayPunchNotify(row, notify, btn, msgId = "workLogMsg") {
    const name = `${row.eponymo || ""} ${row.onoma || ""}`.trim() || row.employee_afm;
    const wl = row.work_log && typeof row.work_log === "object" ? row.work_log : {};
    if (btn) btn.disabled = true;
    this.showLoading(msgId, `Αποστολή ειδοποίησης για ${name}…`);
    return fetch("/api/telegram/notify/today-punch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({
        employee_afm: row.employee_afm,
        work_date: row.work_date,
        eponymo: row.eponymo,
        onoma: row.onoma,
        hour_from: wl.hour_from || row.hour_from || null,
        hour_to: wl.hour_to || row.hour_to || null,
        notify_kind: notify.kind,
      }),
    })
      .then((res) => this.parseJson(res).then((data) => ({ res, data })))
      .then(({ res, data }) => {
        if (!res.ok || !data.success) {
          this.showMsg(
            msgId,
            data.error ||
              data._parseError ||
              data.errors?.join(" · ") ||
              "Αποτυχία αποστολής",
            false
          );
          if (btn) btn.disabled = false;
          return false;
        }
        const n = data.sent || 0;
        this.showMsg(
          msgId,
          `Εστάλη σε ${n} λήπτη/ες — ${notify.label} (${row.work_date})`,
          true
        );
        return true;
      })
      .catch((e) => {
        this.showMsg(msgId, String(e), false);
        if (btn) btn.disabled = false;
        return false;
      });
  },

  /** Ειδοποίηση τύπου 2 — μόνο για σημερινές εγγραφές. */
  workLogTodayNotify(row) {
    if (!row || !this.workLogRowIsToday(row)) return null;
    if (!this.workLogEmployeeActive(row)) return null;

    const hf = String(row.hour_from || "").trim();
    const ht = String(row.hour_to || "").trim();
    const nowMin = this.parseClockToMinutes(
      this.formatTime24(new Date(), { seconds: false })
    );
    if (nowMin == null) return null;

    if (!hf && ht) {
      return {
        kind: "exit_without_entry",
        label: "εξόδος χωρίς είσοδο",
      };
    }

    if (!hf && this.workLogHasDigitalSchedule(row)) {
      const schedStart = this.scheduleStartMinutesFromRow(row);
      const elapsed = this.elapsedWorkDayMinutes(schedStart, nowMin);
      if (elapsed != null && elapsed >= 10) {
        return {
          kind: "late_check_in",
          label: "καθυστέρηση εισόδου (>10' από ωράριο)",
        };
      }
    }

    if (hf && !ht) {
      const startMin = this.parseClockToMinutes(hf);
      const elapsed = this.elapsedWorkDayMinutes(startMin, nowMin);
      if (elapsed != null && elapsed >= 8 * 60) {
        return {
          kind: "missing_exit_8h",
          label: "έλλειψη εξόδου (>8 ώρες από είσοδο)",
        };
      }
    }

    return null;
  },

  workLogEmployeeActive(row) {
    if (!row) return true;
    const v = row.employee_active;
    return !(v === false || v === 0 || v === "0");
  },

  clientDeviceInfo() {
    let timezone = "";
    try {
      timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
    } catch {
      timezone = "";
    }
    return {
      screen: `${window.screen?.width || 0}x${window.screen?.height || 0}`,
      viewport: `${window.innerWidth || 0}x${window.innerHeight || 0}`,
      platform: navigator.platform || "",
      language: navigator.language || "",
      timezone,
    };
  },

  workLogInactiveBadgeHtml() {
    return (
      `<span class="status-badge status-muted work-log-inactive-badge" ` +
      `title="Δεν είναι πλέον στο τρέχον προσωπικό">Ανενεργός</span>`
    );
  },

  formatWorkLogEponymoCell(row) {
    const name = this.escapeHtml(row?.eponymo || "");
    if (!this.workLogEmployeeActive(row)) {
      return `<strong>${name}</strong> ${this.workLogInactiveBadgeHtml()}`;
    }
    return `<strong>${name}</strong>`;
  },

  decorateWorkLogTableRow(tr, row) {
    if (this.workLogRowIsDeficient(row)) {
      tr.classList.add("work-log-row--deficient");
    }
    if (!this.workLogEmployeeActive(row)) {
      tr.classList.add("work-log-row--inactive");
    }
  },

  /** Εικονίδιο κάρτας μόνο όταν λείπει είσοδος ή έξοδος (όχι σε ολοκληρωμένη μέρα). */
  shouldShowWorkCardLink(row) {
    if (!row) return false;
    if (!this.workLogEmployeeActive(row)) return false;
    if (String(row.status || "").trim() === "completed") return false;
    if (row.work_log && typeof row.work_log === "object") {
      const hf = String(row.work_log.hour_from || "").trim();
      const ht = String(row.work_log.hour_to || "").trim();
      if (hf && ht) return false;
    }
    if (this.workLogRowIsComplete(row)) return false;
    return Boolean(String(row.employee_afm || row.afm || "").trim());
  },

  renderWorkLogHistoryCardLinkCell(row, ctx) {
    const employeeAfm = String(ctx.employee_afm || row.employee_afm || "").trim();
    const employeeName = String(ctx.employee_name || "").trim();
    if (!this.shouldShowWorkCardLink(row) || !employeeAfm) {
      return { html: "", isCard: false };
    }
    const dateIso = this.erganiDateToIso(row.work_date) || "";
    const name =
      employeeName || `${row.eponymo || ""} ${row.onoma || ""}`.trim();
    const opts = this.workCardUrlOptsFromRow(row);
    const url = this.workCardUrl(employeeAfm, dateIso, name, opts);
    const cls = opts.retro
      ? "work-log-card-link work-log-card-link--required"
      : "work-log-card-link";
    const title = opts.retro ? "Προγενέστερο χτύπημα — ψηφιακή κάρτα" : "Ψηφιακή κάρτα";
    return {
      html:
        `<a href="${this.escapeHtml(url)}" class="${cls}" ` +
        `title="${this.escapeHtml(title)}" aria-label="${this.escapeHtml(title)}">` +
        `${this.icon("credit-card-2-front")}</a>`,
      isCard: true,
    };
  },

  renderWorkLogHistoryTable(rows, ctx = {}) {
    if (!rows.length) {
      return (
        `<p style="color:var(--muted);">${this.icon("clock")}` +
        `<span style="margin-left:0.35rem;">Δεν υπάρχουν εγγραφές στη βάση για αυτόν τον εργαζόμενο.</span></p>`
      );
    }
    const headers = ["Ημερομηνία", "Ψηφ. ωράριο", "Από", "Έως", "Συγχρονισμός", "Κάρτα"];
    let html = `<table class="data work-log-history-table"><tr>${headers
      .map((h) => `<th>${this.escapeHtml(h)}</th>`)
      .join("")}</tr>`;
    rows.forEach((row) => {
      const hf = String(row.hour_from || "").trim();
      const ht = String(row.hour_to || "").trim();
      const pending = this.workLogExitStillPending(row);
      const apoCell = this.formatWorkLogTimeCell(hf, "Λείπει ώρα εισόδου");
      const ewsCell = this.formatWorkLogTimeCell(
        ht,
        pending ? "Έξοδος μετά το τέλος βάρδιας" : "Λείπει ώρα εξόδου"
      );
      const cardCell = this.renderWorkLogHistoryCardLinkCell(row, ctx);
      const sched = (row.schedule_label || "—").trim() || "—";
      const deficient = this.workLogRowIsDeficient(row);
      html +=
        `<tr${deficient ? ' class="work-log-row--deficient"' : ""}>` +
        `<td>${this.escapeHtml(String(row.work_date || ""))}</td>` +
        `<td>${this.escapeHtml(sched)}</td>` +
        `<td>${apoCell.html}</td>` +
        `<td>${ewsCell.html}</td>` +
        `<td>${this.escapeHtml(String(this.formatSyncedAt(row.synced_at)))}</td>` +
        `<td${cardCell.isCard ? ' class="work-log-action-cell"' : ""}>${cardCell.html}</td>` +
        "</tr>";
    });
    html += "</table>";
    return html;
  },

  async loadWorkLogHistory({ wrap, sub, afm, name = "" }) {
    const employeeAfm = String(afm || "").trim();
    if (!wrap || !employeeAfm) return;
    const displayName = String(name || "").trim();
    if (sub) {
      sub.textContent = `${displayName || "Εργαζόμενος"} · ΑΦΜ ${employeeAfm}`;
    }
    wrap.innerHTML = `<p class="table-loading">${this.icon("arrow-repeat")}<span>Φόρτωση ιστορικού…</span></p>`;
    try {
      const res = await fetch(
        `/api/work-log/history?employee_afm=${encodeURIComponent(employeeAfm)}`,
        { cache: "no-store" }
      );
      const data = await res.json();
      if (!res.ok) {
        wrap.innerHTML = `<p style="color:var(--err);">${this.escapeHtml(data.error || "Σφάλμα")}</p>`;
        return;
      }
      const employeeName = displayName || data.employee_name || "";
      if (sub && data.employee_name && !displayName) {
        sub.textContent = `${data.employee_name} · ΑΦΜ ${employeeAfm}`;
      }
      const count = data.count || 0;
      const meta =
        count > 0
          ? `<p class="table-meta" style="margin:0 0 0.5rem;">${this.icon("database")} <strong>${count}</strong> εγγραφές στη βάση (νεότερες πρώτα)</p>`
          : "";
      wrap.innerHTML =
        meta +
        this.renderWorkLogHistoryTable(data.work_log || [], {
          employee_afm: employeeAfm,
          employee_name: employeeName,
        });
    } catch (e) {
      wrap.innerHTML = `<p style="color:var(--err);">${this.escapeHtml(String(e))}</p>`;
    }
  },

  workLogHistoryUrl(employeeAfm, employeeName, from = "") {
    const afm = String(employeeAfm || "").trim();
    if (!afm) return "/ui/work-log/history";
    const p = new URLSearchParams({ employee_afm: afm });
    const n = String(employeeName || "").trim();
    if (n) p.set("employee_name", n);
    const src = String(from || "").trim();
    if (src) p.set("from", src);
    return `/ui/work-log/history?${p}`;
  },

  async openWorkLogHistoryModal(row, ids = {}) {
    const modalId = ids.modalId || "workLogHistoryModal";
    const subId = ids.subId || "workLogHistoryEmployee";
    const wrapId = ids.wrapId || "workLogHistoryWrap";
    const afm = (row.employee_afm || "").trim();
    if (!afm) return;
    const modal = document.getElementById(modalId);
    const sub = document.getElementById(subId);
    const wrap = document.getElementById(wrapId);
    if (!modal || !sub || !wrap) return;
    const name = `${row.eponymo || ""} ${row.onoma || ""}`.trim();
    sub.textContent = `${name || "Εργαζόμενος"} · ΑΦΜ ${afm}`;
    wrap.innerHTML = `<p class="table-loading">${this.icon("arrow-repeat")}<span>Φόρτωση ιστορικού…</span></p>`;
    modal.classList.remove("hidden");
    await this.loadWorkLogHistory({ wrap, sub, afm, name });
  },

  createWorkLogHistoryCell(row) {
    const td = document.createElement("td");
    td.className = "col-history work-log-history-cell";
    this.appendWorkLogHistoryButton(td, row);
    return td;
  },

  appendWorkLogHistoryButton(td, row) {
    const afm = (row.employee_afm || "").trim();
    if (!afm) return;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn btn-sm btn-secondary work-log-history-btn";
    btn.title = "Πραγματική απασχόληση — ιστορικό";
    btn.setAttribute(
      "aria-label",
      `Πραγματική απασχόληση για ${row.eponymo || ""} ${row.onoma || ""}`.trim()
    );
    btn.innerHTML = this.icon("clock-history");
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      this.openWorkLogHistoryModal(row);
    });
    td.appendChild(btn);
  },

  updateSyncMetaLine(elId, store, kind) {
    const el = document.getElementById(elId);
    if (!el || !store) return;
    if (kind === "schedule") {
      const last = this.formatSyncTimestamp(store.schedule_last_sync_at);
      el.innerHTML =
        `Τελευταίος συγχρονισμός ωραρίου: <strong>${this.escapeHtml(last)}</strong>` +
        ` · Αυτόματη ανανέωση σήμερα αν λείπει.`;
      return;
    }
    if (kind === "worklog-open") {
      const last = this.formatSyncTimestamp(store.work_log_last_sync_at);
      el.innerHTML =
        `Τελευταίος συγχρονισμός πραγματικής: <strong>${this.escapeHtml(last)}</strong>` +
        ` · Συγχρονισμός Ergani κατά το άνοιγμα της σελίδας.`;
      return;
    }
    const last = this.formatSyncTimestamp(store.work_log_last_sync_at);
    el.innerHTML =
      `Τελευταίος συγχρονισμός πραγματικής: <strong>${this.escapeHtml(last)}</strong>` +
      ` · Αυτόματος συγχρονισμός server κάθε 10 λεπτά.`;
  },

  installFetchAuthGuard() {
    if (window.__officeFetchGuard) return;
    window.__officeFetchGuard = true;
    const nativeFetch = window.fetch.bind(window);
    const skipLoginRedirect = () => {
      const path = window.location.pathname || "";
      return (
        path.startsWith("/ui/login") ||
        path.startsWith("/ui/telegram-hit") ||
        path.startsWith("/ui/telegram-punch") ||
        path.startsWith("/ui/retro-hit") ||
        path.startsWith("/ui/retro-punch")
      );
    };
    window.fetch = async (...args) => {
      const res = await nativeFetch(...args);
      if (res.status === 401 && !skipLoginRedirect()) {
        const data = await res.clone().json().catch(() => ({}));
        if (data.login || data.error === "Απαιτείται σύνδεση") {
          const next = encodeURIComponent(location.pathname + location.search);
          window.location.href = `/ui/login?next=${next}`;
        }
      }
      return res;
    };
  },

  ensureLogoutLink() {
    document.querySelectorAll(".sidebar nav").forEach((nav) => {
      if (nav.querySelector('[data-nav="logout"]')) return;
      const a = document.createElement("a");
      a.href = "#";
      a.dataset.nav = "logout";
      a.innerHTML = `${this.icon("box-arrow-right")}<span>Αποσύνδεση</span>`;
      a.addEventListener("click", async (e) => {
        e.preventDefault();
        try {
          await fetch("/api/auth/logout", {
            method: "POST",
            credentials: "same-origin",
          });
        } catch {
          /* ignore */
        }
        window.location.href = "/ui/login";
      });
      nav.appendChild(a);
    });
  },
};

document.addEventListener("DOMContentLoaded", () => {
  Office.installFetchAuthGuard();
  Office.initChrome();
  Office.initPageBackButton();
  Office.ensureLogoutLink();
  Office.loadActiveStore();
});
