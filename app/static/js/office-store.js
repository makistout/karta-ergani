Object.assign(window.Office, {
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
});
