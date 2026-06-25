Object.assign(window.Office, {
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

  scheduleDurationMinutes(schedStart, schedEnd) {
    if (schedStart == null || schedEnd == null) return null;
    let elapsed = schedEnd - schedStart;
    if (elapsed < 0) elapsed += 24 * 60;
    return elapsed > 0 ? elapsed : null;
  },

  expectedExitMinutesFromRow(row) {
    const hf = String(row?.hour_from || "").trim();
    const entryMin = this.parseClockToMinutes(hf);
    if (entryMin == null) return null;
    const schedStart = this.scheduleStartMinutesFromRow(row);
    let schedEnd = null;
    const sched = row?.schedule;
    if (sched && sched.hour_to) {
      schedEnd = this.parseClockToMinutes(sched.hour_to);
    }
    if (schedEnd == null) {
      const label = String(row?.schedule_label || "").trim();
      if (label && label !== "—" && !/ρεπο|ανάπαυση/i.test(label)) {
        const parts = label.split("·").map((x) => x.trim()).filter(Boolean);
        const last = parts[parts.length - 1] || label;
        const match = last.match(/\s[–\-]\s*(\d{1,2}:\d{2}(?::\d{2})?)\s*$/);
        if (match) schedEnd = this.parseClockToMinutes(match[1]);
      }
    }
    if (schedStart == null || schedEnd == null) return null;
    const duration = this.scheduleDurationMinutes(schedStart, schedEnd);
    if (duration == null) return null;
    return entryMin + duration;
  },

  minutesAfterExpectedExit(expectedExit, entryMin, nowMin, onNextCalendarDay = false) {
    if (expectedExit == null || entryMin == null || nowMin == null) return null;
    let nowAbs;
    if (onNextCalendarDay) {
      nowAbs = nowMin + 24 * 60;
    } else if (expectedExit >= 24 * 60 && nowMin < entryMin) {
      nowAbs = nowMin + 24 * 60;
    } else {
      nowAbs = nowMin;
    }
    const elapsed = nowAbs - expectedExit;
    return elapsed >= 0 ? elapsed : null;
  },

  expectedExitSpillsNextDay(expectedExit) {
    return expectedExit != null && expectedExit >= 24 * 60;
  },

  allowsOvernightExitOnToday(row) {
    const hf = String(row?.hour_from || "").trim();
    const ht = String(row?.hour_to || "").trim();
    if (!hf || ht) return false;
    const wd = this.workDateToIso(row?.work_date);
    const today = this.todayIsoLocal();
    if (!wd || wd === today) return false;
    const expected = this.expectedExitMinutesFromRow(row);
    if (expected == null || !this.expectedExitSpillsNextDay(expected)) return false;
    return this.addDaysIso(wd, 1) === today;
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

  /** Σήμερα, έχει είσοδο, λείπει έξοδος, ακόμα πριν την αναμενόμενη λήξη (είσοδος + διάρκεια ωραρίου). */
  workLogExitStillPending(row) {
    const hf = String(row?.hour_from || "").trim();
    const ht = String(row?.hour_to || "").trim();
    if (!hf || ht) return false;
    const wd = this.workDateToIso(row?.work_date);
    if (!wd) return false;
    const expectedExit = this.expectedExitMinutesFromRow(row);
    if (expectedExit == null) return false;
    const entryMin = this.parseClockToMinutes(hf);
    const today = this.todayIsoLocal();
    const nowMin = this.parseClockToMinutes(this.formatTime24(new Date(), { seconds: false }));
    if (nowMin == null || entryMin == null) return false;

    const spansMidnight = expectedExit >= 24 * 60;
    let timelineNow = null;
    if (wd === today) {
      timelineNow = nowMin < entryMin ? nowMin + 24 * 60 : nowMin;
    } else if (spansMidnight && this.addDaysIso(wd, 1) === today) {
      timelineNow = nowMin + 24 * 60;
    } else {
      return false;
    }
    return timelineNow < expectedExit;
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

  workLogRowIsTodayOrOvernightExit(row) {
    return this.workLogRowIsToday(row) || this.allowsOvernightExitOnToday(row);
  },

  elapsedWorkDayMinutes(fromMin, toMin) {
    if (fromMin == null || toMin == null) return null;
    let elapsed = toMin - fromMin;
    if (elapsed < 0) elapsed += 24 * 60;
    return elapsed;
  },

  /** Λεπτά ίδιας ημερολογιακής ημέρας — χωρίς wrap (για κανόνες ειδοποίησης σήμερα). */
  elapsedSameDateMinutes(fromMin, toMin) {
    if (fromMin == null || toMin == null) return null;
    const elapsed = toMin - fromMin;
    return elapsed >= 0 ? elapsed : null;
  },

  workLogHasDigitalSchedule(row) {
    return this.scheduleStartMinutesFromRow(row) != null;
  },

  /** Ετικέτα ειδοποίησης τύπου 2 (σήμερα). */
  todayNotifyLabel(kind) {
    const labels = {
      exit_without_entry: "εξόδος χωρίς είσοδο",
      late_check_in: "καθυστέρηση εισόδου (>10' από ωράριο)",
      late_check_out: "έλλειψη εξόδου (>10' από αναμενόμενη λήξη)",
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

  /** Ειδοποίηση τύπου 2 — σημερινές εγγραφές ή χθεσινή βάρδια με έξοδο σήμερα. */
  workLogTodayNotify(row) {
    if (!row) return null;
    const isToday = this.workLogRowIsToday(row);
    const overnightExit = this.allowsOvernightExitOnToday(row);
    if (!isToday && !overnightExit) return null;
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

    if (!hf && this.workLogHasDigitalSchedule(row) && isToday) {
      const schedStart = this.scheduleStartMinutesFromRow(row);
      const elapsed = this.elapsedSameDateMinutes(schedStart, nowMin);
      if (elapsed != null && elapsed >= 10) {
        return {
          kind: "late_check_in",
          label: "καθυστέρηση εισόδου (>10' από ωράριο)",
        };
      }
    }

    if (hf && !ht) {
      const entryMin = this.parseClockToMinutes(hf);
      const schedStart = this.scheduleStartMinutesFromRow(row);
      let schedEndRaw = null;
      const sched = row?.schedule;
      if (sched && sched.hour_to) {
        schedEndRaw = this.parseClockToMinutes(sched.hour_to);
      }
      if (schedEndRaw == null) {
        const label = String(row?.schedule_label || "").trim();
        if (label && label !== "—" && !/ρεπο|ανάπαυση/i.test(label)) {
          const parts = label.split("·").map((x) => x.trim()).filter(Boolean);
          const last = parts[parts.length - 1] || label;
          const match = last.match(/\s[–\-]\s*(\d{1,2}:\d{2}(?::\d{2})?)\s*$/);
          if (match) schedEndRaw = this.parseClockToMinutes(match[1]);
        }
      }
      if (entryMin != null && schedStart != null && schedEndRaw != null) {
        const duration = this.scheduleDurationMinutes(schedStart, schedEndRaw);
        if (duration != null) {
          const expectedExit = entryMin + duration;
          const elapsedEnd = this.minutesAfterExpectedExit(
            expectedExit,
            entryMin,
            nowMin,
            overnightExit
          );
          if (elapsedEnd != null && elapsedEnd >= 10) {
            return {
              kind: "late_check_out",
              label: "έλλειψη εξόδου (>10' από αναμενόμενη λήξη)",
            };
          }
          return null;
        }
      }
      const startMin = this.parseClockToMinutes(hf);
      const elapsed = this.elapsedSameDateMinutes(startMin, nowMin);
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
});
