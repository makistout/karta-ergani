document.addEventListener("DOMContentLoaded", () => {
  const params = new URLSearchParams(window.location.search);
  const token = (params.get("t") || "").trim();
  const intro = document.getElementById("tgHitIntro");
  const details = document.getElementById("tgHitDetails");
  const pinInput = document.getElementById("tgHitPin");
  const btn = document.getElementById("btnTgHitConfirm");
  const msg = document.getElementById("tgHitMsg");

  if (!token) {
    if (intro) intro.textContent = "Λείπει ή μη έγκυρος σύνδεσμος.";
    return;
  }

  async function loadPreview() {
    try {
      const res = await fetch(`/api/telegram/hit/${encodeURIComponent(token)}`, {
        credentials: "same-origin",
      });
      const data = await Office.parseJson(res);
      if (!res.ok || !data.preview) {
        if (intro) intro.textContent = data.error || "Ο σύνδεσμος δεν είναι έγκυρος.";
        return;
      }
      const p = data.preview;
      if (intro) {
        intro.textContent =
          "Ελλιπές χτύπημα — εισάγετε τον προσωπικό σας PIN για την προγενέστερη καταχώρηση.";
      }
      if (details) {
        details.classList.remove("hidden");
        const timeLine = p.retro_time
          ? `<br>Προτεινόμενη ώρα: ${Office.escapeHtml(p.retro_time)}`
          : "";
        details.innerHTML =
          `<strong>${Office.escapeHtml(p.store_name || "")}</strong><br>` +
          `${Office.escapeHtml(p.employee_name || "")} (ΑΦΜ ${Office.escapeHtml(p.employee_afm || "")})<br>` +
          `Ημερομηνία: ${Office.escapeHtml(p.work_date || "")}<br>` +
          `Ελλιπές χτύπημα ${Office.escapeHtml(p.card_event_label || "")}${timeLine}`;
      }
      if (pinInput) pinInput.disabled = false;
      if (btn) btn.disabled = false;
    } catch (e) {
      if (intro) intro.textContent = String(e);
    }
  }

  async function confirmHit() {
    const pin = String(pinInput?.value || "").replace(/\D/g, "").slice(0, 4);
    if (pinInput && pinInput.value !== pin) pinInput.value = pin;
    if (!pin) {
      Office.showMsg("tgHitMsg", "Συμπληρώστε τον PIN σας.", false);
      return;
    }
    if (!/^\d{4}$/.test(pin)) {
      Office.showMsg("tgHitMsg", "Ο PIN πρέπει να είναι ακριβώς 4 αριθμητικά ψηφία.", false);
      return;
    }
    if (btn) btn.disabled = true;
    Office.showLoading("tgHitMsg", "Επαλήθευση PIN…");
    try {
      const res = await fetch(`/api/telegram/hit/${encodeURIComponent(token)}/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ pin }),
      });
      const data = await Office.parseJson(res);
      if (!res.ok || !data.success) {
        Office.showMsg(
          "tgHitMsg",
          data.error || data.errors?.join(" · ") || "Αποτυχία επαλήθευσης",
          false
        );
        if (btn && res.status !== 403) btn.disabled = false;
        return;
      }
      if (data.redirect) {
        Office.showMsg("tgHitMsg", data.detail || "Μετάβαση στην προγενέστερη καταχώρηση…", true);
        window.location.href = data.redirect;
        return;
      }
      Office.showMsg("tgHitMsg", data.detail || "Επιτυχία.", true);
      if (pinInput) pinInput.disabled = true;
    } catch (e) {
      Office.showMsg("tgHitMsg", String(e), false);
      if (btn) btn.disabled = false;
    }
  }

  btn?.addEventListener("click", confirmHit);
  pinInput?.addEventListener("input", () => {
    if (!pinInput) return;
    const cleaned = String(pinInput.value || "").replace(/\D/g, "").slice(0, 4);
    if (pinInput.value !== cleaned) pinInput.value = cleaned;
  });
  pinInput?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") confirmHit();
  });
  loadPreview();
});
