function showForgotMsg(text, ok) {
  const el = document.getElementById("forgotPasswordMsg");
  if (!el) return;
  el.textContent = text;
  el.className = ok ? "msg show ok" : "msg show err";
}

async function submitForgotPassword() {
  const identity = (document.getElementById("forgotIdentity")?.value || "").trim();
  const btn = document.getElementById("btnForgotPassword");
  if (!identity) {
    showForgotMsg("Συμπληρώστε username ή email.", false);
    return;
  }
  if (btn) btn.disabled = true;
  try {
    const res = await fetch("/api/auth/forgot-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ identity }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.success) {
      showForgotMsg(data.error || "Αποτυχία αποστολής.", false);
      return;
    }
    showForgotMsg(data.message || "Ελέγξτε το email σας.", true);
  } catch (e) {
    showForgotMsg(String(e), false);
  } finally {
    if (btn) btn.disabled = false;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("btnForgotPassword")?.addEventListener("click", submitForgotPassword);
  document.getElementById("forgotIdentity")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") submitForgotPassword();
  });
});
