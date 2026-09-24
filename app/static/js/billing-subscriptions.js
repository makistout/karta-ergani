document.addEventListener("DOMContentLoaded", () => {
  Office.setActiveNav("billing-subs");
  loadPlans();
});

async function loadPlans() {
  const res = await fetch("/api/billing/plans");
  const data = await res.json();
  const plans = data.plans || [];
  const wrap = document.getElementById("billingPlansWrap");
  if (!wrap) return;
  wrap.innerHTML = `<table class="data billing-plans-table"><tr><th>Πακέτο</th><th>Μήνες</th><th>Καθαρό €</th><th>ΦΠΑ %</th><th>Κόστος / μήνα</th><th>Ενεργό</th><th></th></tr>${
    groupPlansByFamily(plans).map((group, index) => `
      <tr class="billing-plan-group" data-group="${index}"><td colspan="7">
        <button type="button" class="billing-group-toggle" aria-expanded="false">
          <span class="billing-group-sign" aria-hidden="true">+</span>
          <span>${Office.escapeHtml(group.title)}</span>
        </button>
      </td></tr>
      ${group.plans.map((plan) => `
      <tr class="hidden" data-plan="${plan.id}" data-group-body="${index}" data-months="${Office.escapeHtml(String(plan.months || ""))}" hidden>
        <td><input class="field-input" data-field="name" value="${Office.escapeHtml(plan.name || "")}"></td>
        <td>${Office.escapeHtml(String(plan.months || ""))}</td>
        <td><input class="field-input" data-field="amount_net" type="number" min="0" step="0.01" value="${Office.escapeHtml(String(plan.amount_net || "0"))}"></td>
        <td><input class="field-input" data-field="vat_rate" type="number" min="0" step="0.01" value="${Office.escapeHtml(String(plan.vat_rate || "24"))}"></td>
        <td class="billing-plan-monthly" data-monthly>${Office.escapeHtml(monthlyCost(plan.amount_net, plan.months))}</td>
        <td>
          <label class="billing-switch" title="Ενεργό">
            <input type="checkbox" data-field="is_active" ${Number(plan.is_active) ? "checked" : ""}>
            <span class="billing-switch-slider" aria-hidden="true"></span>
            <span class="sr-only">Ενεργό</span>
          </label>
        </td>
        <td class="table-actions">
          <div class="table-actions-inner">
            <button type="button" class="btn btn-icon-only" data-dup-plan="${plan.id}" title="Αντιγραφή πακέτου" aria-label="Αντιγραφή πακέτου">${Office.icon("copy")}</button>
            <button type="button" class="btn btn-icon-only" data-save-plan="${plan.id}" title="Αποθήκευση" aria-label="Αποθήκευση">${Office.icon("save")}</button>
          </div>
        </td>
      </tr>`).join("")}
    `).join("")
  }</table>`;
  Office.enhanceResponsiveTable?.(wrap.querySelector("table"));
  wrap.querySelectorAll("[data-save-plan]").forEach((btn) => {
    btn.addEventListener("click", () => savePlan(Number(btn.dataset.savePlan)));
  });
  wrap.querySelectorAll("[data-dup-plan]").forEach((btn) => {
    btn.addEventListener("click", () => duplicatePlan(Number(btn.dataset.dupPlan)));
  });
  wrap.querySelectorAll('[data-field="amount_net"]').forEach((input) => {
    input.addEventListener("input", () => updateMonthlyCost(input.closest("tr")));
    input.addEventListener("change", () => updateMonthlyCost(input.closest("tr")));
  });
  bindBillingGroupToggles(wrap);
}

function bindBillingGroupToggles(root) {
  root.querySelectorAll(".billing-group-toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      const expanded = btn.getAttribute("aria-expanded") !== "true";
      btn.setAttribute("aria-expanded", expanded ? "true" : "false");
      const sign = btn.querySelector(".billing-group-sign");
      if (sign) sign.textContent = expanded ? "−" : "+";
      const group = btn.closest("[data-group]");
      const id = group?.dataset.group;
      if (id == null) return;
      root.querySelectorAll(`[data-group-body="${id}"]`).forEach((el) => {
        el.hidden = !expanded;
        el.classList.toggle("hidden", !expanded);
      });
    });
  });
}

function planFamilyTitle(plan) {
  const fromName = String(plan.name || "").replace(/\s*\([^)]*\)\s*$/, "").trim();
  if (fromName) return fromName;
  const kind = Number(plan.includes_apologistic)
    ? "Απολογιστικό"
    : Number(plan.includes_ai_agent)
      ? "AI Agent"
      : "ErganiOS";
  const months = Number(plan.months) || "";
  return months ? `ErganiOS + ${kind} ${months} μήνες` : `ErganiOS + ${kind}`;
}

function groupPlansByFamily(plans) {
  const groups = new Map();
  (plans || []).forEach((plan) => {
    const title = planFamilyTitle(plan);
    if (!groups.has(title)) groups.set(title, []);
    groups.get(title).push(plan);
  });
  return [...groups.entries()]
    .map(([title, rows]) => ({
      title,
      months: Number(rows[0]?.months) || 0,
      plans: rows.slice().sort((a, b) => {
        const price = Number(a.amount_net || 0) - Number(b.amount_net || 0);
        if (price !== 0) return price;
        return String(a.name || "").localeCompare(String(b.name || ""), "el");
      }),
    }))
    .sort((a, b) => {
      if (a.months !== b.months) return a.months - b.months;
      return a.title.localeCompare(b.title, "el");
    });
}

function monthlyCost(amount, months) {
  const net = Number(amount);
  const count = Number(months);
  if (!Number.isFinite(net) || !Number.isFinite(count) || count <= 0) return "—";
  return `${(net / count).toFixed(2)} €`;
}

function updateMonthlyCost(row) {
  if (!row) return;
  const cell = row.querySelector("[data-monthly]");
  if (!cell) return;
  cell.textContent = monthlyCost(row.querySelector('[data-field="amount_net"]')?.value, row.dataset.months);
}

function planNameKey(value) {
  return String(value || "").trim().replace(/\s+/g, " ").toLowerCase();
}

function planNameTaken(name, excludeId) {
  const key = planNameKey(name);
  if (!key) return false;
  return Array.from(document.querySelectorAll("tr[data-plan]")).some((row) => {
    if (Number(row.dataset.plan) === Number(excludeId)) return false;
    return planNameKey(row.querySelector('[data-field="name"]')?.value) === key;
  });
}

async function savePlan(id) {
  const row = document.querySelector(`tr[data-plan="${id}"]`);
  if (!row) return;
  const name = row.querySelector('[data-field="name"]').value;
  if (planNameTaken(name, id)) {
    Office.showMsg("billingSubMsg", "Υπάρχει ήδη πακέτο με το ίδιο όνομα.", false);
    return;
  }
  const res = await fetch(`/api/billing/plans/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: row.querySelector('[data-field="name"]').value,
      amount_net: row.querySelector('[data-field="amount_net"]').value,
      vat_rate: row.querySelector('[data-field="vat_rate"]').value,
      is_active: row.querySelector('[data-field="is_active"]').checked ? 1 : 0,
    }),
  });
  const data = await res.json();
  if (!res.ok) {
    Office.showMsg("billingSubMsg", data.error || "Αποτυχία πακέτου", false);
    return;
  }
  Office.showMsg("billingSubMsg", "Το πακέτο αποθηκεύτηκε.", true);
  await loadPlans();
}

async function duplicatePlan(id) {
  const res = await fetch(`/api/billing/plans/${id}/duplicate`, { method: "POST" });
  const data = await res.json();
  if (!res.ok) {
    Office.showMsg("billingSubMsg", data.error || "Αποτυχία αντιγραφής", false);
    return;
  }
  Office.showMsg("billingSubMsg", "Δημιουργήθηκε αντίγραφο. Άλλαξε το όνομα και αποθήκευσε.", true);
  await loadPlans();
}
