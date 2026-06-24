Object.assign(window.Office, {
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
        path.startsWith("/ui/retro-punch") ||
        path.startsWith("/ui/today-hit") ||
        path.startsWith("/ui/today-action")
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
});
