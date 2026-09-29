function esc(value) {
  return Office.escapeHtml(String(value ?? ""));
}

function todayIso() {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

function storeId() {
  const raw = String(document.getElementById("payrollStoreId").value || "").trim();
  if (!raw) return 0;
  const value = Number(raw);
  return Number.isInteger(value) && value >= 0 ? value : 0;
}

document.addEventListener("DOMContentLoaded", async () => {
  Office.setActiveNav("apologistic");
  const back = document.getElementById("payrollParamsBack");
  if (back && document.referrer.includes("/ui/apologistic/timekeeping")) {
    back.href = document.referrer;
    back.innerHTML = `<i class="bi bi-arrow-left"></i> Ωρομέτρηση`;
  }
  document.getElementById("payrollValidFrom").value = todayIso();
  document.getElementById("payrollSave")?.addEventListener("click", saveParameters);
  document.getElementById("payrollAddCustom")?.addEventListener("click", addCustom);
  document.getElementById("payrollStoreId").addEventListener("change", loadParameters);
  try {
    const active = await Office.fetchActiveStore();
    Office.applyActiveStoreChrome(active);
  } catch (_error) {
    /* η σελίδα δουλεύει και χωρίς ενεργό κατάστημα (εταιρικές παράμετροι) */
  }
  await loadParameters();
});

async function loadParameters() {
  const asOf = document.getElementById("payrollValidFrom").value || todayIso();
  const res = await fetch(`/api/payroll/parameters?store_id=${storeId()}&as_of=${encodeURIComponent(asOf)}`, {
    credentials: "same-origin",
  });
  const data = await Office.parseJson(res);
  if (!res.ok) {
    Office.showMsg("payrollParamMsg", data.error || `HTTP ${res.status}`, false);
    return;
  }
  renderForm(data);
  renderHistory(data.rows || []);
}

function renderForm(data) {
  const resolved = data.resolved || {};
  const groups = data.groups || [];
  const catalog = data.catalog || [];
  const byGroup = {};
  for (const item of catalog) {
    (byGroup[item.group_code] || (byGroup[item.group_code] = [])).push(item);
  }
  const extraCodes = Object.keys(resolved).filter((code) => !catalog.some((item) => item.code === code));
  if (extraCodes.length) {
    byGroup.custom = extraCodes.map((code) => ({
      code,
      label: code,
      value_kind: "text",
      note: "Προστέθηκε από τη βάση",
      legal_ref: "",
    }));
    if (!groups.some((group) => group.code === "custom")) {
      groups.push({ code: "custom", label: "Πρόσθετες" });
    }
  }
  document.getElementById("payrollParamSections").innerHTML = groups.map((group) => {
    const fields = (byGroup[group.code] || []).map((item) => fieldHtml(item, resolved[item.code])).join("");
    return `<section class="card settings-section">
      <div class="settings-section-head"><div><h2>${esc(group.label)}</h2></div></div>
      <div class="payroll-param-list">${fields}</div>
    </section>`;
  }).join("");
}

function fieldHtml(item, value) {
  const current = value ?? item.default ?? "";
  let control = "";
  if (item.choices) {
    const options = item.choices.map((choice) =>
      `<option value="${esc(choice)}" ${String(choice) === String(current) ? "selected" : ""}>${esc(choice)}</option>`
    ).join("");
    control = `<select class="input-select payroll-param-input" data-code="${esc(item.code)}">${options}</select>`;
  } else {
    control = `<input class="field-input payroll-param-input" data-code="${esc(item.code)}" value="${esc(current)}">`;
  }
  const hint = [item.legal_ref, item.note].filter(Boolean).join(" · ");
  return `<div class="payroll-param-row">
    <span class="payroll-param-label">${esc(item.label)}</span>
    ${control}
    <small class="payroll-param-hint">${esc(hint)}</small>
  </div>`;
}

function collectItems() {
  return Array.from(document.querySelectorAll(".payroll-param-input")).map((input) => ({
    code: input.getAttribute("data-code"),
    value: input.value,
  }));
}

async function saveParameters() {
  const payload = {
    store_id: storeId(),
    valid_from: document.getElementById("payrollValidFrom").value || todayIso(),
    items: collectItems(),
  };
  const res = await fetch("/api/payroll/parameters", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify(payload),
  });
  const data = await Office.parseJson(res);
  if (!res.ok) {
    Office.showMsg("payrollParamMsg", data.error || `HTTP ${res.status}`, false);
    return;
  }
  Office.showMsg("payrollParamMsg", "Αποθηκεύτηκαν οι παράμετροι.", true);
  renderHistory(data.rows || []);
}

async function addCustom() {
  const code = String(document.getElementById("customCode").value || "").trim();
  const value = String(document.getElementById("customValue").value || "").trim();
  if (!code || !value) {
    Office.showMsg("payrollParamMsg", "Συμπληρώστε κωδικό και τιμή.", false);
    return;
  }
  const payload = {
    store_id: storeId(),
    valid_from: document.getElementById("payrollValidFrom").value || todayIso(),
    items: [{
      code,
      value,
      label: document.getElementById("customLabel").value || code,
      value_kind: document.getElementById("customKind").value,
      group_code: "custom",
    }],
  };
  const res = await fetch("/api/payroll/parameters", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify(payload),
  });
  const data = await Office.parseJson(res);
  if (!res.ok) {
    Office.showMsg("payrollParamMsg", data.error || `HTTP ${res.status}`, false);
    return;
  }
  document.getElementById("customCode").value = "";
  document.getElementById("customLabel").value = "";
  document.getElementById("customValue").value = "";
  Office.showMsg("payrollParamMsg", "Προστέθηκε η παράμετρος.", true);
  await loadParameters();
}

function renderHistory(rows) {
  const body = document.getElementById("payrollHistoryBody");
  body.innerHTML = (rows || []).map((row) => `<tr>
    <td>${esc(row.code)}</td>
    <td>${esc(row.value)}</td>
    <td>${esc(row.valid_from)}</td>
    <td>${esc(row.valid_to || "—")}</td>
    <td>${esc(row.store_id || "εταιρεία")}</td>
    <td>${esc(row.legal_ref || "")}</td>
  </tr>`).join("") || `<tr><td colspan="6">Δεν υπάρχουν εγγραφές.</td></tr>`;
}
