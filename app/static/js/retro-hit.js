const RETRO_AITIOLOGIA = "001";

let retroDatePicker = null;
let hitContext = null;
const hitToken = (new URLSearchParams(window.location.search).get("t") || "").trim();

document.addEventListener("DOMContentLoaded", () => {
  retroDatePicker = Office.attachGreekDateField({ inputId: "rhRetroDate" });
  Office.bindHourMinuteInput("rhRetroTime");
  document.getElementById("btnRhCheckIn")?.addEventListener("click", () => submitRetro("check_in"));
  document.getElementById("btnRhCheckOut")?.addEventListener("click", () => submitRetro("check_out"));
  loadContext();
});

function setFormEnabled(enabled) {
  if (retroDatePicker) retroDatePicker.setDisabled(!enabled);
  else {
    const d = document.getElementById("rhRetroDate");
    if (d) d.disabled = !enabled;
  }
  const t = document.getElementById("rhRetroTime");
  if (t) t.disabled = !enabled;
  ["btnRhCheckIn", "btnRhCheckOut"].forEach((id) => {
    const b = document.getElementById(id);
    if (b) b.disabled = !enabled;
  });
}

function highlightSuggestedEvent(cardEvent) {
  const inBtn = document.getElementById("btnRhCheckIn");
  const outBtn = document.getElementById("btnRhCheckOut");
  inBtn?.classList.remove("work-card-action--required");
  outBtn?.classList.remove("work-card-action--required");
  if (cardEvent === "check_in") inBtn?.classList.add("work-card-action--required");
  if (cardEvent === "check_out") outBtn?.classList.add("work-card-action--required");
}

async function loadContext() {
  const intro = document.getElementById("rhIntro");
  const emp = document.getElementById("rhEmployee");
  try {
    const ctxUrl = hitToken
      ? `/api/telegram/retro-hit/context?t=${encodeURIComponent(hitToken)}`
      : "/api/telegram/retro-hit/context";
    const res = await fetch(ctxUrl, { cache: "no-store", credentials: "same-origin" });
    const data = await Office.parseJson(res);
    if (!res.ok || !data.context) {
      if (intro) {
        intro.textContent =
          data.error || "Η συνεδρία έληξε. Ανοίξτε ξανά τον σύνδεσμο από το Telegram.";
      }
      return;
    }
    hitContext = data.context;
    const c = hitContext;
    const name = c.employee_name || c.employee_afm || "";
    if (intro) {
      intro.textContent = `Κατάστημα: ${c.store_name || ""} — επιβεβαιώστε την προγενέστερη καταχώρηση.`;
    }
    if (emp) {
      emp.classList.remove("hidden");
      emp.innerHTML =
        `<strong>${Office.escapeHtml(name)}</strong>` +
        ` <span class="retro-hit-afm">(ΑΦΜ ${Office.escapeHtml(c.employee_afm || "")})</span>`;
    }
    const refIso = c.reference_date_iso || "";
    if (retroDatePicker && refIso) retroDatePicker.setIso(refIso);
    const timeEl = document.getElementById("rhRetroTime");
    const norm = Office.normalizeHourMinute(c.retro_time || "");
    if (timeEl && norm) timeEl.value = norm;
    highlightSuggestedEvent(c.card_event || "");
    setFormEnabled(true);
  } catch (e) {
    if (intro) intro.textContent = String(e);
  }
}

function readRetroTimeValue() {
  return Office.normalizeHourMinute(document.getElementById("rhRetroTime")?.value || "");
}

async function submitRetro(eventName) {
  if (!hitContext) return;
  const referenceDate =
    retroDatePicker?.getIso() ||
    document.getElementById("rhRetroDate")?.dataset?.iso ||
    Office.parseDateGr(document.getElementById("rhRetroDate")?.value || "") ||
    hitContext.reference_date_iso ||
    "";
  const retroTime = readRetroTimeValue();
  if (!referenceDate || !retroTime) {
    Office.showMsg("rhMsg", "Συμπληρώστε ημερομηνία και ώρα κτυπήματος.", false);
    return;
  }
  setFormEnabled(false);
  const label = eventName === "check_in" ? "Είσοδος" : "Έξοδος";
  Office.showLoading("rhMsg", `Υποβολή προγενέστερης ${label} (WRKCardSE)…`);
  try {
    const res = await fetch("/api/telegram/retro-hit/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({
        event: eventName,
        reference_date: referenceDate,
        retro_time: retroTime,
        aitiologia: RETRO_AITIOLOGIA,
        token: hitToken || undefined,
        device_info: Office.clientDeviceInfo(),
      }),
    });
    const data = await Office.parseJson(res);
    if (!res.ok || !data.success) {
      Office.showMsg(
        "rhMsg",
        data.error || data.errors?.join(" · ") || "Αποτυχία υποβολής",
        false
      );
      setFormEnabled(true);
      return;
    }
    let ok = `Επιτυχία — ${data.f_type_label || label}`;
    if (data.protocol) ok += ` · Πρωτόκολο: ${data.protocol}`;
    Office.showMsg("rhMsg", ok, true);
  } catch (e) {
    Office.showMsg("rhMsg", String(e), false);
    setFormEnabled(true);
  }
}
