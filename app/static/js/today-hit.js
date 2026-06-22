document.addEventListener("DOMContentLoaded", () => {
  const params = new URLSearchParams(window.location.search);
  const token = (params.get("t") || "").trim();
  const intro = document.getElementById("todayHitIntro");
  const details = document.getElementById("todayHitDetails");
  const pinInput = document.getElementById("todayHitPin");
  const btn = document.getElementById("btnTodayHitConfirm");
  const msg = document.getElementById("todayHitMsg");

  if (!token) {
    if (intro) intro.textContent = "Λείπει ή μη έγκυρος σύνδεσμος.";
    return;
  }

  async function loadPreview() {
    try {
      const res = await fetch(`/api/telegram/today-hit/${encodeURIComponent(token)}`, {
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
          "Υπάρχει πρόβλημα με εργαζόμενο — εισάγετε τον προσωπικό σας PIN.";
      }
      if (details) {
        details.classList.remove("hidden");
        details.innerHTML =
          `<strong>${Office.escapeHtml(p.store_name || "")}</strong><br>` +
          `${Office.escapeHtml(p.employee_name || "")} (ΑΦΜ ${Office.escapeHtml(p.employee_afm || "")})<br>` +
          `Ημερομηνία: ${Office.escapeHtml(p.work_date || "")}<br>` +
          `Θέμα: ${Office.escapeHtml(p.notify_kind_label || "")}` +
          (p.wto_daily_eligible && p.wto_hour_from
            ? `<br>Προτεινόμενο ωράριο: <strong>${Office.escapeHtml(p.wto_hour_from)}` +
              (p.wto_hour_to ? ` – ${Office.escapeHtml(p.wto_hour_to)}` : "") +
              `</strong>`
            : "");
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
      Office.showMsg("todayHitMsg", "Συμπληρώστε τον PIN σας.", false);
      return;
    }
    if (!/^\d{4}$/.test(pin)) {
      Office.showMsg("todayHitMsg", "Ο PIN πρέπει να είναι ακριβώς 4 αριθμητικά ψηφία.", false);
      return;
    }
    if (btn) btn.disabled = true;
    Office.showLoading("todayHitMsg", "Επαλήθευση PIN…");
    try {
      const res = await fetch(`/api/telegram/today-hit/${encodeURIComponent(token)}/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ pin }),
      });
      const data = await Office.parseJson(res);
      if (!res.ok || !data.success) {
        Office.showMsg(
          "todayHitMsg",
          data.error || data.errors?.join(" · ") || "Αποτυχία επαλήθευσης",
          false
        );
        if (btn && res.status !== 403) btn.disabled = false;
        return;
      }
      if (data.redirect) {
        Office.showMsg("todayHitMsg", data.detail || "Μετάβαση…", true);
        window.location.href = data.redirect;
        return;
      }
      Office.showMsg("todayHitMsg", data.detail || "Επιτυχία.", true);
      if (pinInput) pinInput.disabled = true;
    } catch (e) {
      Office.showMsg("todayHitMsg", String(e), false);
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
