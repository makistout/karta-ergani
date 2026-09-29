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

let loginBusy = false;

function showLoginMsg(text, ok) {
  const el = document.getElementById("loginMsg");
  if (!el) return;
  if (window.Office?.showMsg) {
    Office.showMsg("loginMsg", text, ok);
    return;
  }
  el.textContent = text;
  el.className = ok ? "msg show ok" : "msg show err";
}

function setLoginBusy(busy) {
  loginBusy = Boolean(busy);
  const btn = document.getElementById("btnLogin");
  const user = document.getElementById("loginUser");
  const pass = document.getElementById("loginPass");
  const label = btn?.querySelector("span");
  if (window.Office?.setButtonLoading) {
    Office.setButtonLoading(btn, loginBusy);
  } else if (btn) {
    btn.disabled = loginBusy;
  }
  if (label) label.textContent = loginBusy ? "Σύνδεση…" : "Είσοδος";
  if (user) user.disabled = loginBusy;
  if (pass) pass.disabled = loginBusy;
  btn?.setAttribute("aria-busy", loginBusy ? "true" : "false");
}

async function tryLogin() {
  if (loginBusy) return;
  const username = (document.getElementById("loginUser")?.value || "").trim();
  const password = document.getElementById("loginPass")?.value || "";
  if (!username || !password) {
    showLoginMsg("Συμπληρώστε username και password.", false);
    return;
  }
  setLoginBusy(true);
  if (window.Office?.showLoading) {
    Office.showLoading("loginMsg", "Γίνεται σύνδεση… περιμένετε.");
  } else {
    showLoginMsg("Γίνεται σύνδεση… περιμένετε.", true);
  }
  try {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.success) {
      setLoginBusy(false);
      showLoginMsg(data.error || "Αποτυχία σύνδεσης", false);
      return;
    }
    if (window.Office?.showLoading) {
      Office.showLoading("loginMsg", "Επιτυχής σύνδεση… μεταφορά.");
    }
    if (data.onboarding_redirect) {
      window.location.href = data.onboarding_redirect;
      return;
    }
    window.location.href = loginNextUrl();
  } catch (e) {
    setLoginBusy(false);
    showLoginMsg(String(e), false);
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
