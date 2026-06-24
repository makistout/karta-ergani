Object.assign(window.Office, {
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
});
