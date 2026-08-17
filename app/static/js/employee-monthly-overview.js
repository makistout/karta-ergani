const EMP_MONTH_NAMES = ["Ιανουάριος", "Φεβρουάριος", "Μάρτιος", "Απρίλιος", "Μάιος", "Ιούνιος", "Ιούλιος", "Αύγουστος", "Σεπτέμβριος", "Οκτώβριος", "Νοέμβριος", "Δεκέμβριος"];
let selectedMonth = new Date(new Date().getFullYear(), new Date().getMonth(), 1);
const query = new URLSearchParams(location.search);
const employeeAfm = (query.get("afm") || "").trim();

document.addEventListener("DOMContentLoaded", () => {
  Office.setActiveNav("employees");
  initMonths();
  document.getElementById("btnPrevMonth").onclick = () => changeMonth(-1);
  document.getElementById("btnNextMonth").onclick = () => changeMonth(1);
  document.getElementById("employeeMonthSelect").onchange = (event) => {
    const [year, month] = event.target.value.split("-").map(Number);
    selectedMonth = new Date(year, month - 1, 1);
    loadMonth();
  };
  loadMonth();
});

function initMonths() {
  const select = document.getElementById("employeeMonthSelect");
  const now = new Date();
  for (let offset = 0; offset < 60; offset += 1) {
    const d = new Date(now.getFullYear(), now.getMonth() - offset, 1);
    const option = document.createElement("option");
    option.value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    option.textContent = `${EMP_MONTH_NAMES[d.getMonth()]} ${d.getFullYear()}`;
    select.appendChild(option);
  }
}

function changeMonth(delta) {
  const candidate = new Date(selectedMonth.getFullYear(), selectedMonth.getMonth() + delta, 1);
  const now = new Date();
  const current = new Date(now.getFullYear(), now.getMonth(), 1);
  if (candidate > current) return;
  selectedMonth = candidate;
  loadMonth();
}

async function loadMonth() {
  const wrap = document.getElementById("employeeMonthWrap");
  const select = document.getElementById("employeeMonthSelect");
  const key = `${selectedMonth.getFullYear()}-${String(selectedMonth.getMonth() + 1).padStart(2, "0")}`;
  select.value = key;
  document.getElementById("btnNextMonth").disabled = select.selectedIndex === 0;
  Office.showTableLoading(wrap);
  if (!employeeAfm) {
    wrap.innerHTML = '<p style="color:var(--err);">Λείπει το ΑΦΜ εργαζομένου.</p>';
    return;
  }
  const qs = new URLSearchParams({ afm: employeeAfm, year: String(selectedMonth.getFullYear()), month: String(selectedMonth.getMonth() + 1) });
  try {
    const response = await fetch(`/api/employees/monthly-overview?${qs}`, { cache: "no-store" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Αποτυχία φόρτωσης");
    renderMonth(data);
  } catch (error) {
    wrap.innerHTML = `<p style="color:var(--err);">${Office.formatMultilineHtml(String(error.message || error))}</p>`;
  }
}

function minutesText(raw) {
  const minutes = Number(raw);
  if (!Number.isFinite(minutes)) return "—";
  const sign = minutes < 0 ? "−" : minutes > 0 ? "+" : "";
  const absolute = Math.abs(minutes);
  return `${sign}${Math.floor(absolute / 60)}:${String(absolute % 60).padStart(2, "0")}`;
}
function duration(row) { return minutesText(row.effective_actual_minutes ?? row.actual_minutes ?? row.declared_minutes); }
function value(row, key) { return row[key] || "—"; }

function renderMonth(data) {
  const wrap = document.getElementById("employeeMonthWrap");
  const employeeName = `${data.employee?.eponymo || query.get("eponymo") || ""} ${data.employee?.onoma || query.get("onoma") || ""}`.trim();
  document.getElementById("employeeMonthDesc").textContent = `${employeeName || "Εργαζόμενος"} · ΑΦΜ ${employeeAfm} · ${data.store?.name || ""}`;
  const rows = data.days || [];
  const finalized = rows.filter((row) => row.finalized).length;
  const changes = rows.filter((row) => row.status === "change").length;
  const reviews = rows.filter((row) => row.status === "review").length;
  document.getElementById("employeeMonthSummary").innerHTML =
    `<div class="employee-month-stat"><span>Ημέρες μήνα</span><strong>${rows.length}</strong></div>` +
    `<div class="employee-month-stat ok"><span>Υπολογισμένες</span><strong>${finalized}</strong></div>` +
    `<div class="employee-month-stat warn"><span>Μεταβολές</span><strong>${changes}</strong></div>` +
    `<div class="employee-month-stat err"><span>Για έλεγχο</span><strong>${reviews}</strong></div>`;
  const table = document.createElement("table");
  table.className = "data employee-month-table";
  table.innerHTML = "<thead><tr><th>Ημερομηνία</th><th>Δηλωμένο</th><th>Χτύπημα</th><th>Διάρκεια</th><th>Διαφορά</th><th>Υπερωρίες</th><th>Πρόταση</th><th>Αποτέλεσμα</th></tr></thead>";
  const body = document.createElement("tbody");
  rows.forEach((row) => {
    const shortDate = String(row.work_date || "").split("/").slice(0, 2).join("/") || "—";
    const tr = document.createElement("tr");
    if (!row.finalized) tr.className = row.source === "future" ? "employee-month-future" : "employee-month-pending";
    const statusLabels = { ok: "Σύμφωνο", change: "Μεταβολή", review: "Για έλεγχο" };
    const result = row.finalized
      ? (statusLabels[row.status] || row.status || "—")
      : row.source === "future"
        ? "Μελλοντική"
        : row.source === "live_preview"
          ? `Προσωρινό · ${statusLabels[row.status] || "στοιχεία"}`
          : "Δεν έχει υπολογιστεί";
    const overtime = Array.isArray(row.overtime_segments) && row.overtime_segments.length
      ? row.overtime_segments.map((item) => `${item.from}–${item.to}`).join(", ") : "—";
    [shortDate, value(row, "declared"), value(row, "punch_recorded"), duration(row), minutesText(row.net_difference_minutes), overtime, value(row, "proposed"), result].forEach((text, index) => {
      const td = document.createElement("td");
      td.textContent = String(text);
      if (index === 7 && row.finalized) td.className = `employee-month-result status-${row.status || ""}`;
      tr.appendChild(td);
    });
    body.appendChild(tr);
  });
  table.appendChild(body);
  wrap.innerHTML = "";
  wrap.appendChild(table);
}
