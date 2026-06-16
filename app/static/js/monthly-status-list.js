const MONTH_NAMES = [
  "",
  "Ιαν",
  "Φεβ",
  "Μαρ",
  "Απρ",
  "Μαι",
  "Ιουν",
  "Ιουλ",
  "Αυγ",
  "Σεπ",
  "Οκτ",
  "Νοε",
  "Δεκ",
];

let filterEmployeeAfm = "";

document.addEventListener("DOMContentLoaded", () => {
  Office.setActiveNav("employees");
  const params = new URLSearchParams(window.location.search);
  filterEmployeeAfm = (params.get("afm") || "").trim();
  initYearSelect();
  document.getElementById("btnFilterMonthly").onclick = () => loadRows();
  if (filterEmployeeAfm) {
    const back = document.getElementById("btnBackEmployees");
    if (back) back.style.display = "";
    const desc = document.getElementById("monthlyStatusDesc");
    if (desc) {
      desc.textContent = `Μηνιαία στοιχεία για ΑΦΜ ${filterEmployeeAfm}.`;
    }
  }
  loadRows();
});

function initYearSelect() {
  const sel = document.getElementById("filterYear");
  if (!sel) return;
  const now = new Date();
  const cur = now.getFullYear();
  sel.innerHTML = `<option value="">Όλα</option>`;
  for (let y = cur; y >= cur - 5; y--) {
    const opt = document.createElement("option");
    opt.value = String(y);
    opt.textContent = String(y);
    if (y === cur) opt.selected = true;
    sel.appendChild(opt);
  }
  const mSel = document.getElementById("filterMonth");
  if (mSel && !filterEmployeeAfm && now.getMonth() > 0) {
    mSel.value = String(now.getMonth());
  }
}

function monthLabel(m) {
  const n = parseInt(m, 10);
  return MONTH_NAMES[n] || String(m || "");
}

async function loadRows() {
  const wrap = document.getElementById("monthlyStatusWrap");
  Office.showTableLoading(wrap);
  const year = document.getElementById("filterYear")?.value || "";
  const month = document.getElementById("filterMonth")?.value || "";
  const qs = new URLSearchParams();
  if (year) qs.set("year", year);
  if (month) qs.set("month", month);
  if (filterEmployeeAfm) qs.set("afm", filterEmployeeAfm);
  try {
    const res = await fetch(`/api/monthly-status/list?${qs.toString()}`, { cache: "no-store" });
    const data = await res.json();
    if (!res.ok) {
      wrap.innerHTML = `<p style="color:var(--err);">${Office.escapeHtml(data.error || "Σφάλμα")}</p>`;
      if (data.db_setup) {
        wrap.innerHTML += `<p style="font-size:0.85rem;color:var(--muted);margin-top:0.5rem;">${Office.escapeHtml(data.db_setup)}</p>`;
      }
      return;
    }
    renderTable(data.rows || [], data.store, data.count || 0);
  } catch (e) {
    wrap.innerHTML = `<p style="color:var(--err);">${Office.escapeHtml(String(e))}</p>`;
  }
}

function renderTable(rows, store, count) {
  const wrap = document.getElementById("monthlyStatusWrap");
  if (!count) {
    wrap.innerHTML =
      `<p style="color:var(--muted);">${Office.icon("info-circle")}<span style="margin-left:0.35rem;">Δεν υπάρχουν αποθηκευμένα στοιχεία. Συγχρονίστε από τη σελίδα Συγχρονισμός.</span></p>`;
    return;
  }
  const storeLine = store
    ? `<p class="table-meta">${Office.icon("shop-window")} <strong>${Office.escapeHtml(store.name)}</strong> · ${count} εγγραφές</p>`
    : "";
  const headers = [
    "Έτος",
    "Μήνας",
    "ΑΦΜ",
    "Επώνυμο",
    "Όνομα",
    "Εργασία",
    "Τηλεργ.",
    "Ρεπό",
    "Μη εργ.",
    "Καν. άδεια",
    "Υπερωρ. (ημ.)",
    "Υπερωρ. (λεπ.)",
    "Κάρτα",
    "Άδεια (ασφ.)",
    "Ασθέν. (ασφ.)",
  ];
  const t = document.createElement("table");
  t.className = "data";
  const hr = document.createElement("tr");
  headers.forEach((h) => {
    const th = document.createElement("th");
    th.textContent = h;
    hr.appendChild(th);
  });
  t.appendChild(hr);
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    const cells = [
      row.report_year ?? "",
      monthLabel(row.report_month),
      row.employee_afm || "",
      row.eponymo || "",
      row.onoma || "",
      row.days_work ?? "0",
      row.days_telework ?? "0",
      row.days_repo ?? "0",
      row.days_no_work ?? "0",
      row.days_normal_leave ?? "0",
      row.overtime_days ?? "0",
      row.overtime_minutes ?? "0",
      row.days_work_card ?? "0",
      row.days_leave_insurance ?? "0",
      row.days_sick_insurance ?? "0",
    ];
    cells.forEach((txt, i) => {
      const td = document.createElement("td");
      if (i === 3) {
        td.innerHTML = `<strong>${Office.escapeHtml(String(txt))}</strong>`;
      } else {
        td.textContent = String(txt);
      }
      tr.appendChild(td);
    });
    t.appendChild(tr);
  });
  wrap.innerHTML = storeLine;
  wrap.appendChild(t);
}
