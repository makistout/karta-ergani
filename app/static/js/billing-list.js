let billingCustomerAc = null;
let billingCustomers = [];

document.addEventListener("DOMContentLoaded", () => {
  Office.setActiveNav("billing-customers");
  initCustomerAutocomplete();
  loadCustomers();
});

function customerOptionText(row) {
  return `${row.eponimia || ""} · ${row.afm || ""}`.trim();
}

function customerAcItem(row) {
  return {
    value: String(row.id),
    description: customerOptionText(row),
    eponimia: row.eponimia || "",
    afm: row.afm || "",
    id: row.id,
  };
}

function initCustomerAutocomplete() {
  if (!Office.createAutocomplete) return;
  billingCustomerAc = Office.createAutocomplete({
    inputId: "billingCustomerInput",
    listId: "billingCustomerList",
    hiddenId: "billingCustomerId",
    maxItems: 40,
    labelFn: (item) => item.description || customerOptionText(item),
    onSelect: (item) => {
      const id = Number(item.value || item.id || 0);
      if (id) location.href = `/ui/billing/customer?id=${encodeURIComponent(id)}`;
    },
  });
  const input = document.getElementById("billingCustomerInput");
  if (!input) return;
  const openAll = () => billingCustomerAc?.openAll(false);
  input.addEventListener("focus", openAll);
  input.addEventListener("click", openAll);
  input.addEventListener("input", () => {
    document.getElementById("billingCustomerId").value = "";
    renderCustomerTable(filterCustomers(input.value));
  });
}

function filterCustomers(query) {
  const q = String(query || "").trim().toLowerCase();
  if (!q) return billingCustomers;
  return billingCustomers.filter((row) => customerOptionText(row).toLowerCase().includes(q)
    || String(row.afm || "").includes(q)
    || String(row.doy || "").toLowerCase().includes(q));
}

async function loadCustomers() {
  const wrap = document.getElementById("billingListWrap");
  if (!wrap) return;
  try {
    const res = await fetch("/api/billing/customers");
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    billingCustomers = data.customers || [];
    billingCustomerAc?.setItems(billingCustomers.map(customerAcItem));
    renderCustomerTable(filterCustomers(document.getElementById("billingCustomerInput")?.value || ""));
  } catch (error) {
    wrap.innerHTML = `<p style="color:var(--err);">${Office.formatMultilineHtml(String(error))}</p>`;
  }
}

function renderCustomerTable(rows) {
  const wrap = document.getElementById("billingListWrap");
  if (!wrap) return;
  if (!rows.length) {
    wrap.innerHTML = billingCustomers.length
      ? "<p style='color:var(--muted);'>Κανένας πελάτης δεν ταιριάζει στην αναζήτηση.</p>"
      : "<p style='color:var(--muted);'>Δεν υπάρχουν πελάτες. Πατήστε «Νέος πελάτης».</p>";
    return;
  }
  const t = document.createElement("table");
  t.className = "data";
  const header = document.createElement("tr");
  ["Επωνυμία", "ΑΦΜ", "ΔΟΥ", "Καταστήματα", "Συνδρομές", "Κατάσταση", "Ενέργειες"].forEach((label) => {
    const th = document.createElement("th");
    th.textContent = label;
    header.appendChild(th);
  });
  t.appendChild(header);
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.appendChild(tdHtml(`<strong>${Office.escapeHtml(row.eponimia || "")}</strong>`));
    tr.appendChild(tdText(row.afm || ""));
    tr.appendChild(tdText(row.doy || "—"));
    tr.appendChild(tdText(String(row.store_count ?? 0)));
    tr.appendChild(tdText(String(row.active_subscriptions ?? 0)));
    tr.appendChild(tdText(Number(row.is_active) ? "Ενεργός" : "Ανενεργός"));
    const act = document.createElement("td");
    act.className = "table-actions";
    const a = document.createElement("a");
    a.className = "btn btn-icon-only";
    a.href = `/ui/billing/customer?id=${encodeURIComponent(row.id)}`;
    a.title = "Καρτέλα πελάτη";
    a.setAttribute("aria-label", "Καρτέλα πελάτη");
    a.innerHTML = Office.icon("pencil-square");
    const inner = document.createElement("div");
    inner.className = "table-actions-inner";
    inner.appendChild(a);
    act.appendChild(inner);
    tr.appendChild(act);
    t.appendChild(tr);
  });
  wrap.innerHTML = "";
  wrap.appendChild(t);
  Office.enhanceResponsiveTable?.(t);
}

function tdText(text) {
  const td = document.createElement("td");
  td.textContent = text;
  return td;
}

function tdHtml(html) {
  const td = document.createElement("td");
  td.innerHTML = html;
  return td;
}
