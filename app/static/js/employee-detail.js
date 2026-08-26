document.addEventListener("DOMContentLoaded", () => {
  Office.setActiveNav("employees");
  loadEmployeeDetail();
});

const CONTRACT_FIELDS = [
  ["employer_afm", "ΑΦΜ εργοδότη"],
  ["branch_aa", "Παράρτημα"],
  ["employee_afm", "ΑΦΜ εργαζομένου"],
  ["eponymo", "Επώνυμο"],
  ["onoma", "Όνομα"],
  ["specialty", "Ειδικότητα"],
  ["characterization", "Χαρακτηρισμός"],
  ["step92", "ΣΤΕΠ 92"],
  ["weekly_work_days", "Ημέρες εβδομαδιαίας απασχόλησης"],
  ["prior_service", "Προϋπηρεσία"],
  ["employment_relation", "Σχέση απασχόλησης"],
  ["fixed_term_from", "Ορισμένου χρόνου από"],
  ["fixed_term_to", "Ορισμένου χρόνου έως"],
  ["regime", "Καθεστώς"],
  ["weekly_hours", "Ώρες εβδομαδιαίως"],
  ["salary", "Αποδοχές"],
  ["hourly_wage", "Ωρομίσθιο"],
  ["total_weekly_hours", "Συνολικές ώρες εβδομαδιαίως"],
  ["fulltime_contract_weekly_hours", "Συμβατικές ώρες πλήρους απασχόλησης"],
  ["break_minutes", "Διάλειμμα (λεπτά)"],
  ["break_in_work", "Διάλειμμα εντός ωραρίου"],
  ["flex_arrival_minutes", "Ευέλικτη προσέλευση (λεπτά)"],
  ["ergani_updated_at", "Ημ/νία τελευταίας ενημέρωσης Ergani"],
  ["synced_at", "Τελευταίος συγχρονισμός"],
  ["source", "Πηγή"],
];

function displayValue(key, value) {
  if (value == null || value === "") return "—";
  if (key === "break_in_work") {
    if (value === 1 || value === true || value === "1") return "Ναι";
    if (value === 0 || value === false || value === "0") return "Όχι";
  }
  if (key === "flex_arrival_minutes" && Office.formatFlexMinutes) {
    return Office.formatFlexMinutes(value);
  }
  if (key === "synced_at") {
    return String(value).replace("T", " ").slice(0, 19);
  }
  return String(value);
}

function renderContractFieldsTable(row) {
  const t = document.createElement("table");
  t.className = "data employee-contract-fields-table";
  const hr = document.createElement("tr");
  ["Πεδίο", "Τιμή"].forEach((h) => {
    const th = document.createElement("th");
    th.textContent = h;
    hr.appendChild(th);
  });
  t.appendChild(hr);
  CONTRACT_FIELDS.forEach(([key, label]) => {
    const tr = document.createElement("tr");
    const tdLabel = document.createElement("td");
    tdLabel.className = "employee-contract-field-label";
    tdLabel.textContent = label;
    const tdVal = document.createElement("td");
    tdVal.textContent = displayValue(key, row?.[key]);
    tr.appendChild(tdLabel);
    tr.appendChild(tdVal);
    t.appendChild(tr);
  });
  return t;
}

async function loadEmployeeDetail() {
  const params = new URLSearchParams(window.location.search);
  const afm = (params.get("afm") || params.get("employee_afm") || "").trim();
  const nameQ = `${(params.get("eponymo") || "").trim()} ${(params.get("onoma") || "").trim()}`.trim();
  const title = document.getElementById("employeeDetailTitle");
  const meta = document.getElementById("employeeDetailMeta");
  const wrap = document.getElementById("employeeContractWrap");
  const histSection = document.getElementById("employeeContractHistorySection");
  const histWrap = document.getElementById("employeeContractHistoryWrap");

  if (!afm) {
    title.textContent = "Άγνωστος εργαζόμενος";
    wrap.innerHTML = '<p style="color:var(--err);">Λείπει <code>afm</code> στο URL.</p>';
    return;
  }
  title.textContent = nameQ || `ΑΦΜ ${afm}`;
  meta.textContent = `ΑΦΜ ${afm}`;
  setupEmploymentDates(afm);

  try {
    await Office.loadActiveStore();
    const res = await fetch(
      `/api/employees/contract/history?employee_afm=${encodeURIComponent(afm)}`,
      { cache: "no-store" }
    );
    const data = await res.json();
    if (!res.ok) {
      wrap.innerHTML = `<p style="color:var(--err);">${Office.formatMultilineHtml(data.error || "Σφάλμα")}</p>`;
      return;
    }
    const rows = data.contracts || [];
    if (data.employee_name) title.textContent = data.employee_name;
    if (data.store) {
      meta.textContent = `ΑΦΜ ${afm} · ${data.store.name || ""} · παράρτημα ${data.store.branch_aa ?? "0"}`;
    }
    if (!rows.length) {
      wrap.innerHTML =
        `<p style="color:var(--muted);">Δεν υπάρχουν στοιχεία σύμβασης.</p>`;
      histSection.classList.add("hidden");
      return;
    }
    const current =
      rows.find((r) => r.is_current === true || r.is_current === 1 || r.is_current === "1") ||
      rows[0];
    const previous = rows.filter((r) => r !== current);
    wrap.innerHTML = "";
    wrap.appendChild(renderContractFieldsTable(current));

    if (!previous.length) {
      histSection.classList.add("hidden");
      return;
    }
    histSection.classList.remove("hidden");
    const t = document.createElement("table");
    t.className = "data";
    const hr = document.createElement("tr");
    ["Συγχρονισμός", "Ενημ. Ergani", "Ειδικότητα", "Ώρες", "Αποδοχές", ""].forEach((h) => {
      const th = document.createElement("th");
      th.textContent = h;
      hr.appendChild(th);
    });
    t.appendChild(hr);
    previous.forEach((row) => {
      const tr = document.createElement("tr");
      [
        displayValue("synced_at", row.synced_at),
        displayValue("ergani_updated_at", row.ergani_updated_at),
        displayValue("specialty", row.specialty),
        displayValue("weekly_hours", row.weekly_hours),
        displayValue("salary", row.salary),
      ].forEach((text) => {
        const td = document.createElement("td");
        td.textContent = text;
        tr.appendChild(td);
      });
      const tdAct = document.createElement("td");
      tdAct.className = "work-log-action-cell";
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn-sm btn-secondary";
      btn.innerHTML = Office.icon("table");
      btn.title = "Αναλυτικά";
      btn.addEventListener("click", () => {
        wrap.innerHTML = "";
        const note = document.createElement("p");
        note.className = "table-meta";
        note.textContent =
          `Προβολή προηγούμενης έκδοσης · συγχρ. ${displayValue("synced_at", row.synced_at)}`;
        wrap.appendChild(note);
        wrap.appendChild(renderContractFieldsTable(row));
        wrap.scrollIntoView({ behavior: "smooth", block: "start" });
      });
      tdAct.appendChild(btn);
      tr.appendChild(tdAct);
      t.appendChild(tr);
    });
    histWrap.innerHTML = "";
    histWrap.appendChild(t);
  } catch (e) {
    wrap.innerHTML = `<p style="color:var(--err);">${Office.formatMultilineHtml(String(e))}</p>`;
  }
}

async function setupEmploymentDates(afm) {
  const form = document.getElementById("employeeEmploymentDatesForm");
  const hire = document.getElementById("employeeHireDate");
  const departure = document.getElementById("employeeDepartureDate");
  const status = document.getElementById("employeeEmploymentDatesStatus");
  const hirePicker = Office.attachGreekDateField({inputEl: hire, allowEmpty: true});
  const departurePicker = Office.attachGreekDateField({inputEl: departure, allowEmpty: true});
  try {
    const res = await fetch("/api/employees/list?limit=5000", {cache: "no-store"});
    const data = await res.json();
    const row = (data.employees || []).find((item) => String(item.afm || "") === afm);
    if (row) {
      hirePicker?.setIso(row.hire_date || "", true);
      departurePicker?.setIso(row.departure_date || "", true);
    }
  } catch (_) {}
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    status.textContent = "Αποθήκευση…";
    const res = await fetch("/api/employees/employment-dates", {
      method: "PATCH", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        employee_afm: afm,
        hire_date: hirePicker?.getIso() || "",
        departure_date: departurePicker?.getIso() || "",
      }),
    });
    const data = await res.json();
    status.textContent = res.ok ? "Αποθηκεύτηκε" : (data.error || "Αποτυχία αποθήκευσης");
  });
}
