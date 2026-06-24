Object.assign(window.Office, {
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
});
