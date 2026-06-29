Object.assign(window.Office, {
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
      storenotify: "bell",
      employees: "people-fill",
      schedule: "calendar-week",
      worklog: "clock-history",
      workcard: "credit-card-2-front",
      sync: "arrow-repeat",
      synclog: "journal-text",
      users: "person-gear",
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
    this.initSidebarMenu();
  },

  initSidebarMenu() {
    document.querySelectorAll(".sidebar").forEach((sidebar) => {
      const toggle = sidebar.querySelector(".sidebar-menu-toggle");
      const nav = sidebar.querySelector("nav");
      if (!toggle || !nav || toggle.dataset.bound === "1") return;
      toggle.dataset.bound = "1";

      const setOpen = (open) => {
        sidebar.classList.toggle("is-open", open);
        toggle.setAttribute("aria-expanded", open ? "true" : "false");
        toggle.setAttribute("aria-label", open ? "Κλείσιμο μενού" : "Άνοιγμα μενού");
      };

      toggle.addEventListener("click", () => {
        setOpen(!sidebar.classList.contains("is-open"));
      });

      nav.addEventListener("click", (event) => {
        if (event.target.closest("a") && window.matchMedia("(max-width: 1024px)").matches) {
          setOpen(false);
        }
      });
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
});
