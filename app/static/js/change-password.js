function showChangePasswordMsg(text, ok) {
  const el = document.getElementById("changePasswordMsg");
  if (!el) return;
  el.textContent = text;
  el.className = ok ? "msg show ok" : "msg show err";
}

async function submitChangePassword() {
  const currentPassword = document.getElementById("currentPassword")?.value || "";
  const newPassword = document.getElementById("newPassword")?.value || "";
  const confirmPassword = document.getElementById("confirmPassword")?.value || "";
  const btn = document.getElementById("btnChangePassword");
  if (!currentPassword || !newPassword) {
    showChangePasswordMsg("Συμπληρώστε τον τρέχοντα και τον νέο κωδικό.", false);
    return;
  }
  if (newPassword !== confirmPassword) {
    showChangePasswordMsg("Η επιβεβαίωση νέου κωδικού δεν ταιριάζει.", false);
    return;
  }
  if (newPassword.length < 8) {
    showChangePasswordMsg("Ο νέος κωδικός πρέπει να έχει τουλάχιστον 8 χαρακτήρες.", false);
    return;
  }
  if (btn) btn.disabled = true;
  try {
    const res = await fetch("/api/auth/change-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
        confirm_password: confirmPassword,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.success) {
      showChangePasswordMsg(data.error || "Αποτυχία αλλαγής κωδικού.", false);
      return;
    }
    showChangePasswordMsg(data.message || "Ο κωδικός άλλαξε.", true);
    const next = data.onboarding_redirect || "/ui/";
    window.setTimeout(() => {
      window.location.href = next;
    }, 600);
  } catch (e) {
    showChangePasswordMsg(String(e), false);
  } finally {
    if (btn) btn.disabled = false;
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  try {
    const res = await fetch("/api/auth/status", { credentials: "same-origin" });
    const data = await res.json();
    if (!data.authenticated) {
      window.location.href = "/ui/login";
      return;
    }
    if (!data.must_change_password && data.onboarding_redirect) {
      window.location.href = data.onboarding_redirect;
      return;
    }
    if (!data.must_change_password && !data.onboarding_redirect) {
      window.location.href = "/ui/";
      return;
    }
  } catch {
    /* ignore */
  }
  document.getElementById("btnChangePassword")?.addEventListener("click", submitChangePassword);
  document.getElementById("confirmPassword")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") submitChangePassword();
  });
});
