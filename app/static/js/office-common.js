const Office = {
  draftKey: "kartaStoreDraft",

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
      `<p class="table-loading">${this.icon("hourglass-split")}` +
      `<span>${this.escapeHtml(msg)}</span></p>`;
  },
};

document.addEventListener("DOMContentLoaded", () => {
  Office.initChrome();
  Office.loadActiveStore();
});
