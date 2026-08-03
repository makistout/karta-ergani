function showResetMsg(text, ok) {
  const el = document.getElementById("resetPasswordMsg");
  if (!el) return;
  el.textContent = text;
  el.className = ok ? "msg show ok" : "msg show err";
}

function resetToken() {
  const params = new URLSearchParams(window.location.search);
  return (params.get("t") || params.get("token") || "").trim();
}

async function submitResetPassword() {
  const token = resetToken();
  const newPassword = document.getElementById("newPassword")?.value || "";
  const confirmPassword = document.getElementById("confirmPassword")?.value || "";
  const btn = document.getElementById("btnResetPassword");
  if (!token) {
    showResetMsg("Λείπει ο σύνδεσμος επαναφοράς.", false);
    return;
  }
  if (!newPassword || newPassword.length < 8) {
    showResetMsg("Ο νέος κωδικός πρέπει να έχει τουλάχιστον 8 χαρακτήρες.", false);
    return;
  }
  if (newPassword !== confirmPassword) {
    showResetMsg("Η επιβεβαίωση νέου κωδικού δεν ταιριάζει.", false);
    return;
  }
  if (btn) btn.disabled = true;
  try {
    const res = await fetch("/api/auth/reset-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({
        token,
        new_password: newPassword,
        confirm_password: confirmPassword,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.success) {
      showResetMsg(data.error || "Αποτυχία επαναφοράς.", false);
      return;
    }
    showResetMsg(data.message || "Ο κωδικός άλλαξε.", true);
    window.setTimeout(() => {
      window.location.href = "/ui/login";
    }, 900);
  } catch (e) {
    showResetMsg(String(e), false);
  } finally {
    if (btn) btn.disabled = false;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  if (!resetToken()) {
    showResetMsg("Λείπει ή δεν είναι έγκυρος ο σύνδεσμος επαναφοράς.", false);
  }
  document.getElementById("btnResetPassword")?.addEventListener("click", submitResetPassword);
  document.getElementById("confirmPassword")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") submitResetPassword();
  });
});
