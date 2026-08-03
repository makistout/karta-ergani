function loginNextUrl() {
  const params = new URLSearchParams(location.search);
  const next = (params.get("next") || "/ui/").trim();
  if (!next.startsWith("/") || next.startsWith("//")) {
    return "/ui/";
  }
  // Μην γυρνάμε σε σελίδες auth utility μετά από επιτυχή login.
  const authUtility =
    next.startsWith("/ui/login") ||
    next.startsWith("/ui/forgot-password") ||
    next.startsWith("/ui/reset-password") ||
    next.startsWith("/ui/verify-email");
  if (authUtility) {
    return "/ui/";
  }
  return next;
}

function showLoginMsg(text, ok) {
  const el = document.getElementById("loginMsg");
  if (!el) return;
  el.textContent = text;
  el.className = ok ? "msg show ok" : "msg show err";
}

async function tryLogin() {
  const username = (document.getElementById("loginUser")?.value || "").trim();
  const password = document.getElementById("loginPass")?.value || "";
  const btn = document.getElementById("btnLogin");
  if (!username || !password) {
    showLoginMsg("Συμπληρώστε username και password.", false);
    return;
  }
  if (btn) btn.disabled = true;
  try {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.success) {
      showLoginMsg(data.error || "Αποτυχία σύνδεσης", false);
      return;
    }
    if (data.onboarding_redirect) {
      window.location.href = data.onboarding_redirect;
      return;
    }
    window.location.href = loginNextUrl();
  } catch (e) {
    showLoginMsg(String(e), false);
  } finally {
    if (btn) btn.disabled = false;
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  try {
    const res = await fetch("/api/auth/status", { credentials: "same-origin" });
    const data = await res.json();
    if (data.authenticated) {
      if (data.onboarding_redirect) {
        window.location.href = data.onboarding_redirect;
        return;
      }
      window.location.href = loginNextUrl();
      return;
    }
  } catch {
    /* ignore */
  }
  document.getElementById("btnLogin")?.addEventListener("click", tryLogin);
  document.getElementById("loginPass")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") tryLogin();
  });
  document.getElementById("loginUser")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") document.getElementById("loginPass")?.focus();
  });
});
