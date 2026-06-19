document.addEventListener("DOMContentLoaded", () => {
  const params = new URLSearchParams(window.location.search);
  const token = (params.get("t") || "").trim();
  const intro = document.getElementById("tgPunchIntro");
  const details = document.getElementById("tgPunchDetails");
  const pinInput = document.getElementById("tgPunchPin");
  const btn = document.getElementById("btnTgPunchConfirm");
  const msg = document.getElementById("tgPunchMsg");

  if (!token) {
    if (intro) intro.textContent = "Λείπει ή μη έγκυρος σύνδεσμος.";
    return;
  }

  async function loadPreview() {
    try {
      const res = await fetch(`/api/telegram/punch/${encodeURIComponent(token)}`);
      const data = await res.json();
      if (!res.ok || !data.preview) {
        if (intro) intro.textContent = data.error || "Ο σύνδεσμος δεν είναι έγκυρος.";
        return;
      }
      const p = data.preview;
      if (intro) intro.textContent = "Επιβεβαιώστε το χτύπημα με τον προσωπικό σας PIN.";
      if (details) {
        details.classList.remove("hidden");
        details.innerHTML =
          `<strong>${Office.escapeHtml(p.store_name || "")}</strong><br>` +
          `${Office.escapeHtml(p.employee_name || "")} (ΑΦΜ ${Office.escapeHtml(p.employee_afm || "")})<br>` +
          `Ημερομηνία: ${Office.escapeHtml(p.work_date || "")}<br>` +
          `${Office.escapeHtml(p.card_event_label || "Χτύπημα")} στις ${Office.escapeHtml(p.retro_time || "")}`;
      }
      if (pinInput) pinInput.disabled = false;
      if (btn) btn.disabled = false;
    } catch (e) {
      if (intro) intro.textContent = String(e);
    }
  }

  async function confirmPunch() {
    const pin = String(pinInput?.value || "").replace(/\D/g, "").slice(0, 4);
    if (pinInput && pinInput.value !== pin) pinInput.value = pin;
    if (!pin) {
      Office.showMsg("tgPunchMsg", "Συμπληρώστε τον PIN σας.", false);
      return;
    }
    if (!/^\d{4}$/.test(pin)) {
      Office.showMsg("tgPunchMsg", "Ο PIN πρέπει να είναι ακριβώς 4 αριθμητικά ψηφία.", false);
      return;
    }
    if (btn) btn.disabled = true;
    Office.showLoading("tgPunchMsg", "Υποβολή WRKCardSE στο Ergani…");
    try {
      const res = await fetch(`/api/telegram/punch/${encodeURIComponent(token)}/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pin }),
      });
      const data = await Office.parseJson(res);
      if (!res.ok || !data.success) {
        Office.showMsg(
          "tgPunchMsg",
          data.error || data.errors?.join(" · ") || "Αποτυχία υποβολής",
          false
        );
        if (btn && res.status !== 403) btn.disabled = false;
        return;
      }
      let ok = "Το χτύπημα καταχωρήθηκε επιτυχώς στο Ergani.";
      if (data.protocol) ok += ` Πρωτόκολο: ${data.protocol}`;
      Office.showMsg("tgPunchMsg", ok, true);
      if (pinInput) pinInput.disabled = true;
    } catch (e) {
      Office.showMsg("tgPunchMsg", String(e), false);
      if (btn) btn.disabled = false;
    }
  }

  btn?.addEventListener("click", confirmPunch);
  pinInput?.addEventListener("input", () => {
    if (!pinInput) return;
    const cleaned = String(pinInput.value || "").replace(/\D/g, "").slice(0, 4);
    if (pinInput.value !== cleaned) pinInput.value = cleaned;
  });
  pinInput?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") confirmPunch();
  });
  loadPreview();
});
