let pageToken = "";
let pageContext = null;
let leaveTypes = [];

document.addEventListener("DOMContentLoaded", () => {
  const params = new URLSearchParams(window.location.search);
  pageToken = (params.get("t") || "").trim();
  document.getElementById("btnTodaySnooze")?.addEventListener("click", onSnooze);
  document.getElementById("btnTodayLeave")?.addEventListener("click", showLeavePanel);
  document.getElementById("btnTodayWtoDaily")?.addEventListener("click", showWtoDailyPanel);
  document.getElementById("btnTodayCard")?.addEventListener("click", onCard);
  document.getElementById("btnTodayLeaveBack")?.addEventListener("click", hideLeavePanel);
  document.getElementById("btnTodayLeaveSubmit")?.addEventListener("click", onLeaveSubmit);
  document.getElementById("btnTodayWtoBack")?.addEventListener("click", hideWtoDailyPanel);
  document.getElementById("btnTodayWtoSubmit")?.addEventListener("click", onWtoDailySubmit);
  Office.bindHourMinuteInput("todayWtoHourFrom");
  Office.bindHourMinuteInput("todayWtoHourTo");
  loadContext();
});

function hmToTimeInput(hm) {
  return Office.normalizeHourMinute(hm);
}

function timeInputToHm(value) {
  return Office.normalizeHourMinute(value);
}

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
      let detailHtml =
        `<strong>${Office.escapeHtml(pageContext.store_name || "")}</strong><br>` +
        `${Office.escapeHtml(pageContext.employee_name || "")} ` +
        `(ΑΦΜ ${Office.escapeHtml(pageContext.employee_afm || "")})<br>` +
        `${Office.escapeHtml(pageContext.work_date_ergani || "")} — ` +
        `${Office.escapeHtml(pageContext.notify_kind_label || "")}`;
      if (pageContext.wto_daily_eligible && pageContext.wto_hour_from) {
        detailHtml +=
          `<br>Προτεινόμενο ωράριο: <strong>${Office.escapeHtml(pageContext.wto_hour_from)}` +
          (pageContext.wto_hour_to
            ? ` – ${Office.escapeHtml(pageContext.wto_hour_to)}`
            : "") +
          `</strong>`;
      }
      details.innerHTML = detailHtml;
    }
    choices?.classList.remove("hidden");
    const leaveBtn = document.getElementById("btnTodayLeave");
    if (leaveBtn) {
      leaveBtn.classList.toggle("hidden", !pageContext.leave_eligible);
    }
    const wtoBtn = document.getElementById("btnTodayWtoDaily");
    if (wtoBtn) {
      wtoBtn.classList.toggle("hidden", !pageContext.wto_daily_eligible);
    }
    const cardBtn = document.getElementById("btnTodayCard");
    if (cardBtn) {
      const hideCard =
        pageContext.wto_daily_eligible &&
        ["rest_day", "no_schedule"].includes(pageContext.notify_kind);
      cardBtn.classList.toggle("hidden", hideCard);
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

function showWtoDailyPanel() {
  if (!pageContext?.wto_daily_eligible) return;
  const hint = document.getElementById("todayWtoDailyHint");
  const fromEl = document.getElementById("todayWtoHourFrom");
  const toEl = document.getElementById("todayWtoHourTo");
  const comments = document.getElementById("todayWtoComments");
  if (hint) {
    const kind = pageContext.notify_kind || "";
    hint.textContent =
      kind === "rest_day"
        ? "Ρεπό/ανάπαυση — δηλώστε ωράριο εργασίας αν θα απασχοληθεί ο εργαζόμενος."
        : kind === "no_schedule"
          ? "Δεν υπάρχει ψηφιακό ωράριο — δηλώστε ωράριο εργασίας για σήμερα."
          : "Κάρτα/πραγματική πριν το ωράριο — προσαρμόστε το ψηφιακό ωράριο.";
  }
  if (fromEl) fromEl.value = hmToTimeInput(pageContext.wto_hour_from);
  if (toEl) toEl.value = hmToTimeInput(pageContext.wto_hour_to);
  if (comments) comments.value = "";
  document.getElementById("todayActionChoices")?.classList.add("hidden");
  document.getElementById("todayWtoDailyPanel")?.classList.remove("hidden");
  Office.showMsg("todayActionMsg", "", false);
}

function hideWtoDailyPanel() {
  document.getElementById("todayWtoDailyPanel")?.classList.add("hidden");
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

async function onWtoDailySubmit() {
  const hourFrom = timeInputToHm(document.getElementById("todayWtoHourFrom")?.value);
  const hourTo = timeInputToHm(document.getElementById("todayWtoHourTo")?.value);
  const comments = document.getElementById("todayWtoComments")?.value?.trim() || "";
  if (!hourFrom) {
    Office.showMsg("todayActionMsg", "Συμπληρώστε ώρα έναρξης.", false);
    return;
  }
  const btn = document.getElementById("btnTodayWtoSubmit");
  if (btn) btn.disabled = true;
  Office.showLoading("todayActionMsg", "Υποβολή WTODaily στο Ergani…");
  try {
    const res = await fetch("/api/telegram/today-action/wto-daily", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: apiBody({
        hour_from: hourFrom,
        hour_to: hourTo || null,
        comments: comments || null,
      }),
    });
    const data = await Office.parseJson(res);
    if (!res.ok || !data.success) {
      Office.showMsg(
        "todayActionMsg",
        data.error || "Αποτυχία υποβολής",
        false
      );
      if (btn) btn.disabled = false;
      return;
    }
    const proto = data.protocol ? ` (πρωτ. ${data.protocol})` : "";
    Office.showMsg(
      "todayActionMsg",
      `Το ωράριο υποβλήθηκε${proto}. Συγχρονίστε το ψηφιακό ωράριο.`,
      true
    );
    document.getElementById("todayWtoDailyPanel")?.classList.add("hidden");
    document.getElementById("todayActionChoices")?.classList.add("hidden");
  } catch (e) {
    Office.showMsg("todayActionMsg", String(e), false);
    if (btn) btn.disabled = false;
  }
}
