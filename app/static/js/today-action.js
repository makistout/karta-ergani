let pageToken = "";
let pageContext = null;
let leaveTypes = [];

document.addEventListener("DOMContentLoaded", () => {
  const params = new URLSearchParams(window.location.search);
  pageToken = (params.get("t") || "").trim();
  document.getElementById("btnTodaySnooze")?.addEventListener("click", onSnooze);
  document.getElementById("btnTodayLeave")?.addEventListener("click", showLeavePanel);
  document.getElementById("btnTodayCard")?.addEventListener("click", onCard);
  document.getElementById("btnTodayLeaveBack")?.addEventListener("click", hideLeavePanel);
  document.getElementById("btnTodayLeaveSubmit")?.addEventListener("click", onLeaveSubmit);
  loadContext();
});

function apiBody(extra = {}) {
  return JSON.stringify({ token: pageToken || undefined, ...extra });
}

async function loadContext() {
  const intro = document.getElementById("todayActionIntro");
  const details = document.getElementById("todayActionDetails");
  const choices = document.getElementById("todayActionChoices");
  const qs = pageToken ? `?t=${encodeURIComponent(pageToken)}` : "";
  try {
    const res = await fetch(`/api/telegram/today-action/context${qs}`, {
      credentials: "same-origin",
    });
    const data = await Office.parseJson(res);
    if (!res.ok || !data.context) {
      if (intro) intro.textContent = data.error || "Η συνεδρία έληξε.";
      return;
    }
    pageContext = data.context;
    leaveTypes = data.leave_types || [];
    populateLeaveTypes();
    if (intro) {
      intro.textContent = "Επιλέξτε πώς θέλετε να προχωρήσετε:";
    }
    if (details) {
      details.classList.remove("hidden");
      details.innerHTML =
        `<strong>${Office.escapeHtml(pageContext.store_name || "")}</strong><br>` +
        `${Office.escapeHtml(pageContext.employee_name || "")} ` +
        `(ΑΦΜ ${Office.escapeHtml(pageContext.employee_afm || "")})<br>` +
        `${Office.escapeHtml(pageContext.work_date_ergani || "")} — ` +
        `${Office.escapeHtml(pageContext.notify_kind_label || "")}`;
    }
    choices?.classList.remove("hidden");
    const leaveBtn = document.getElementById("btnTodayLeave");
    if (leaveBtn) {
      leaveBtn.classList.toggle("hidden", !pageContext.leave_eligible);
    }
  } catch (e) {
    if (intro) intro.textContent = String(e);
  }
}

function populateLeaveTypes() {
  const sel = document.getElementById("todayLeaveType");
  if (!sel) return;
  sel.innerHTML = "";
  leaveTypes.forEach((t) => {
    const opt = document.createElement("option");
    opt.value = t.code;
    opt.textContent = `${t.code} — ${t.label}`;
    sel.appendChild(opt);
  });
}

function showLeavePanel() {
  document.getElementById("todayActionChoices")?.classList.add("hidden");
  document.getElementById("todayLeavePanel")?.classList.remove("hidden");
}

function hideLeavePanel() {
  document.getElementById("todayLeavePanel")?.classList.add("hidden");
  document.getElementById("todayActionChoices")?.classList.remove("hidden");
  Office.showMsg("todayActionMsg", "", false);
}

async function onSnooze() {
  const btn = document.getElementById("btnTodaySnooze");
  if (btn) btn.disabled = true;
  Office.showLoading("todayActionMsg", "Αποθήκευση αναβολής…");
  try {
    const res = await fetch("/api/telegram/today-action/snooze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: apiBody(),
    });
    const data = await Office.parseJson(res);
    Office.showMsg("todayActionMsg", data.detail || data.error || "Ολοκληρώθηκε", Boolean(data.success));
    if (data.success) {
      document.getElementById("todayActionChoices")?.classList.add("hidden");
    } else if (btn) {
      btn.disabled = false;
    }
  } catch (e) {
    Office.showMsg("todayActionMsg", String(e), false);
    if (btn) btn.disabled = false;
  }
}

async function onCard() {
  const btn = document.getElementById("btnTodayCard");
  if (btn) btn.disabled = true;
  Office.showLoading("todayActionMsg", "Μετάβαση στην κάρτα…");
  try {
    const res = await fetch("/api/telegram/today-action/card", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: apiBody(),
    });
    const data = await Office.parseJson(res);
    if (!res.ok || !data.success) {
      Office.showMsg("todayActionMsg", data.error || "Αποτυχία", false);
      if (btn) btn.disabled = false;
      return;
    }
    if (data.redirect) {
      window.location.href = data.redirect;
      return;
    }
    Office.showMsg("todayActionMsg", data.detail || "Επιτυχία", true);
  } catch (e) {
    Office.showMsg("todayActionMsg", String(e), false);
    if (btn) btn.disabled = false;
  }
}

async function onLeaveSubmit() {
  const leaveType = document.getElementById("todayLeaveType")?.value || "";
  const comments = document.getElementById("todayLeaveComments")?.value?.trim() || "";
  if (!leaveType) {
    Office.showMsg("todayActionMsg", "Επιλέξτε τύπο άδειας.", false);
    return;
  }
  const btn = document.getElementById("btnTodayLeaveSubmit");
  if (btn) btn.disabled = true;
  Office.showLoading("todayActionMsg", "Υποβολή άδειας στο Ergani…");
  try {
    const res = await fetch("/api/telegram/today-action/leave", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: apiBody({ leave_type: leaveType, comments: comments || null }),
    });
    const data = await Office.parseJson(res);
    if (!res.ok || !data.success) {
      Office.showMsg("todayActionMsg", data.error || "Αποτυχία υποβολής", false);
      if (btn) btn.disabled = false;
      return;
    }
    const proto = data.protocol ? ` (πρωτ. ${data.protocol})` : "";
    Office.showMsg("todayActionMsg", `Η άδεια υποβλήθηκε${proto}.`, true);
    document.getElementById("todayLeavePanel")?.classList.add("hidden");
  } catch (e) {
    Office.showMsg("todayActionMsg", String(e), false);
    if (btn) btn.disabled = false;
  }
}
