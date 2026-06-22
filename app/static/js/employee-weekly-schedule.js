const WEEK_DAYS = [
  { day: 1, label: "Δευτέρα", defaultType: "ΕΡΓ" },
  { day: 2, label: "Τρίτη", defaultType: "ΕΡΓ" },
  { day: 3, label: "Τετάρτη", defaultType: "ΕΡΓ" },
  { day: 4, label: "Πέμπτη", defaultType: "ΕΡΓ" },
  { day: 5, label: "Παρασκευή", defaultType: "ΕΡΓ" },
  { day: 6, label: "Σάββατο", defaultType: "ΑΝ" },
  { day: 0, label: "Κυριακή", defaultType: "ΑΝ" },
];

let selectedEmployee = null;
let wtoWeekAvailable = false;

document.addEventListener("DOMContentLoaded", async () => {
  Office.setActiveNav("employees");
  renderDays();
  setDefaultFromDate();
  document.getElementById("btnCopyMonday").addEventListener("click", copyMondayToWeekdays);
  document.getElementById("btnSubmitWeekly").addEventListener("click", submitWeekly);
  await Promise.all([loadEmployee(), checkAvailability()]);
  updateSubmitState();
});

function queryEmployee() {
  const params = new URLSearchParams(window.location.search);
  return {
    afm: (params.get("afm") || "").trim(),
    eponymo: (params.get("eponymo") || "").trim(),
    onoma: (params.get("onoma") || "").trim(),
  };
}

function isoLocal(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function setDefaultFromDate() {
  const date = new Date();
  const daysUntilMonday = (8 - date.getDay()) % 7;
  date.setDate(date.getDate() + daysUntilMonday);
  document.getElementById("weeklyFromDate").value = isoLocal(date);
}

async function loadEmployee() {
  const requested = queryEmployee();
  if (!requested.afm) {
    Office.showMsg("weeklyMsg", "Λείπει το ΑΦΜ εργαζομένου.", false);
    return;
  }
  try {
    const res = await fetch("/api/employees/list", { cache: "no-store" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    selectedEmployee = (data.employees || []).find(
      (employee) => String(employee.afm || "").trim() === requested.afm
    );
    if (!selectedEmployee) {
      throw new Error("Ο εργαζόμενος δεν είναι ενεργός στο επιλεγμένο παράρτημα.");
    }
    const fullName =
      `${selectedEmployee.eponymo || requested.eponymo} ${selectedEmployee.onoma || requested.onoma}`.trim();
    document.getElementById("weeklyEmployeeTitle").textContent = fullName || requested.afm;
    document.getElementById("weeklyEmployeeMeta").textContent =
      `ΑΦΜ ${requested.afm} · Παράρτημα ${data.store?.branch_aa ?? "—"} · ${data.store?.name || ""}`;
  } catch (error) {
    Office.showMsg("weeklyMsg", String(error.message || error), false);
  }
}

async function checkAvailability() {
  const badge = document.getElementById("weeklyAvailability");
  try {
    const res = await fetch("/api/wto-week/availability", { cache: "no-store" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    wtoWeekAvailable = Boolean(data.available);
    badge.className = `weekly-availability ${
      wtoWeekAvailable ? "weekly-availability--ok" : "weekly-availability--error"
    }`;
    badge.innerHTML = wtoWeekAvailable
      ? `${Office.icon("check-circle-fill")} WTOWeek ενεργό`
      : `${Office.icon("x-circle-fill")} WTOWeek μη διαθέσιμο`;
    if (!wtoWeekAvailable) {
      Office.showMsg(
        "weeklyMsg",
        "Το WTOWeek δεν είναι ενεργό για τον συνδεδεμένο χρήστη Ergani.",
        false
      );
    }
  } catch (error) {
    badge.className = "weekly-availability weekly-availability--error";
    badge.innerHTML = `${Office.icon("exclamation-triangle-fill")} Αποτυχία ελέγχου`;
    Office.showMsg("weeklyMsg", String(error.message || error), false);
  }
}

function typeOptions(selected) {
  return [
    ["ΕΡΓ", "Εργασία"],
    ["ΤΗΛ", "Τηλεργασία"],
    ["ΑΝ", "Ανάπαυση / Ρεπό"],
    ["ΜΕ", "Μη εργασία"],
  ]
    .map(
      ([value, label]) =>
        `<option value="${value}"${selected === value ? " selected" : ""}>${label}</option>`
    )
    .join("");
}

function intervalHtml(from = "09:00", to = "17:00", removable = false) {
  return (
    `<div class="weekly-interval">` +
    `<label><span>Από</span><input type="text" class="weekly-from input-time-24" value="${from}" ` +
    `inputmode="numeric" maxlength="5" placeholder="ΩΩ:ΛΛ" pattern="[0-2][0-9]:[0-5][0-9]"></label>` +
    `<label><span>Έως</span><input type="text" class="weekly-to input-time-24" value="${to}" ` +
    `inputmode="numeric" maxlength="5" placeholder="ΩΩ:ΛΛ" pattern="[0-2][0-9]:[0-5][0-9]"></label>` +
    (removable
      ? `<button type="button" class="weekly-remove-interval" title="Αφαίρεση διαστήματος" aria-label="Αφαίρεση διαστήματος">${Office.icon("x-lg")}</button>`
      : "") +
    `</div>`
  );
}

function bindIntervalInputs(container) {
  container.querySelectorAll(".input-time-24").forEach((input) => {
    input.addEventListener("input", () => {
      const formatted = Office.formatHourMinuteInput(input.value || "");
      if (input.value !== formatted) input.value = formatted;
    });
    input.addEventListener("blur", () => {
      const normalized = Office.normalizeHourMinute(input.value || "");
      if (normalized) input.value = normalized;
    });
  });
}

function renderDays() {
  const wrap = document.getElementById("weeklyDays");
  wrap.innerHTML = WEEK_DAYS.map(
    ({ day, label, defaultType }) =>
      `<article class="weekly-day" data-day="${day}">` +
      `<div class="weekly-day-name"><strong>${label}</strong><span>Κωδικός ${day}</span></div>` +
      `<label class="weekly-type-field"><span>Τύπος</span>` +
      `<select class="weekly-type">${typeOptions(defaultType)}</select></label>` +
      `<div class="weekly-intervals">${defaultType === "ΕΡΓ" ? intervalHtml() : ""}</div>` +
      `<button type="button" class="weekly-add-interval${defaultType === "ΕΡΓ" ? "" : " hidden"}">` +
      `${Office.icon("plus-circle")}<span>Διάστημα</span></button>` +
      `</article>`
  ).join("");

  wrap.querySelectorAll(".weekly-day").forEach((row) => {
    row.querySelector(".weekly-type").addEventListener("change", () => updateDayType(row));
    row.querySelector(".weekly-add-interval").addEventListener("click", () => addInterval(row));
    bindIntervalInputs(row);
  });
}

function updateDayType(row) {
  const type = row.querySelector(".weekly-type").value;
  const intervals = row.querySelector(".weekly-intervals");
  const add = row.querySelector(".weekly-add-interval");
  if (type === "ΕΡΓ" || type === "ΤΗΛ") {
    if (!intervals.children.length) {
      intervals.innerHTML = intervalHtml();
      bindIntervalInputs(intervals);
    }
    add.classList.remove("hidden");
  } else {
    intervals.innerHTML = "";
    add.classList.add("hidden");
  }
}

function addInterval(row) {
  const intervals = row.querySelector(".weekly-intervals");
  const holder = document.createElement("div");
  holder.innerHTML = intervalHtml("17:00", "21:00", true);
  const interval = holder.firstElementChild;
  interval.querySelector(".weekly-remove-interval").addEventListener("click", () => interval.remove());
  bindIntervalInputs(interval);
  intervals.appendChild(interval);
}

function copyMondayToWeekdays() {
  const monday = document.querySelector('.weekly-day[data-day="1"]');
  const type = monday.querySelector(".weekly-type").value;
  const sourceIntervals = [...monday.querySelectorAll(".weekly-interval")].map((row) => ({
    from: row.querySelector(".weekly-from").value,
    to: row.querySelector(".weekly-to").value,
  }));
  [2, 3, 4, 5].forEach((day) => {
    const row = document.querySelector(`.weekly-day[data-day="${day}"]`);
    row.querySelector(".weekly-type").value = type;
    updateDayType(row);
    if (type === "ΕΡΓ" || type === "ΤΗΛ") {
      const intervals = row.querySelector(".weekly-intervals");
      intervals.innerHTML = "";
      sourceIntervals.forEach((item, index) => {
        const holder = document.createElement("div");
        holder.innerHTML = intervalHtml(item.from, item.to, index > 0);
        const interval = holder.firstElementChild;
        interval.querySelector(".weekly-remove-interval")?.addEventListener("click", () => interval.remove());
        bindIntervalInputs(interval);
        intervals.appendChild(interval);
      });
    }
  });
  Office.showMsg("weeklyMsg", "Το πρόγραμμα της Δευτέρας αντιγράφηκε έως την Παρασκευή.", true);
}

function collectDays() {
  return [...document.querySelectorAll(".weekly-day")].map((row) => {
    const type = row.querySelector(".weekly-type").value;
    const entries =
      type === "ΕΡΓ" || type === "ΤΗΛ"
        ? [...row.querySelectorAll(".weekly-interval")].map((interval) => ({
            type,
            from: Office.normalizeHourMinute(interval.querySelector(".weekly-from").value),
            to: Office.normalizeHourMinute(interval.querySelector(".weekly-to").value),
          }))
        : [{ type }];
    return { day: Number(row.dataset.day), entries };
  });
}

function updateSubmitState() {
  document.getElementById("btnSubmitWeekly").disabled = !(selectedEmployee && wtoWeekAvailable);
}

async function submitWeekly() {
  if (!selectedEmployee || !wtoWeekAvailable) return;
  const fromDate = document.getElementById("weeklyFromDate").value;
  if (!fromDate) {
    Office.showMsg("weeklyMsg", "Συμπληρώστε ημερομηνία έναρξης.", false);
    return;
  }
  const days = collectDays();
  const invalidTime = days.some((day) =>
    day.entries.some(
      (entry) =>
        (entry.type === "ΕΡΓ" || entry.type === "ΤΗΛ") &&
        (!entry.from || !entry.to)
    )
  );
  if (invalidTime) {
    Office.showMsg("weeklyMsg", "Όλες οι ώρες πρέπει να είναι σε 24ωρη μορφή ΩΩ:ΛΛ.", false);
    return;
  }
  const fullName = `${selectedEmployee.eponymo || ""} ${selectedEmployee.onoma || ""}`.trim();
  if (!window.confirm(`Να υποβληθεί το σταθερό εβδομαδιαίο ωράριο για ${fullName};`)) return;

  const button = document.getElementById("btnSubmitWeekly");
  Office.setButtonLoading(button, true);
  Office.showLoading("weeklyMsg", "Υποβολή WTOWeek στο Ergani…");
  try {
    const res = await fetch("/api/wto-week/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        employee_afm: selectedEmployee.afm,
        from_date: fromDate,
        to_date: document.getElementById("weeklyToDate").value || null,
        comments: document.getElementById("weeklyComments").value,
        days,
      }),
    });
    const data = await res.json();
    if (!res.ok || !data.success) {
      throw new Error(data.error || data.data?.message || `HTTP ${res.status}`);
    }
    const protocol = data.protocol ? ` · Πρωτόκολλο ${data.protocol}` : "";
    Office.showMsg("weeklyMsg", `Η δήλωση WTOWeek υποβλήθηκε επιτυχώς${protocol}.`, true);
  } catch (error) {
    Office.showMsg("weeklyMsg", String(error.message || error), false);
  } finally {
    Office.setButtonLoading(button, false);
    updateSubmitState();
  }
}
