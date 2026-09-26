let invCustomerAc = null;
let invStartPicker = null;
let invPlans = [];
let amountEditBtn = null;

document.addEventListener("DOMContentLoaded", () => {
  Office.setActiveNav("billing-invoices");
  invStartPicker = Office.attachGreekDateField({
    inputId: "invStartsOn",
    allowEmpty: false,
  });
  document.getElementById("btnIssue")?.addEventListener("click", issueInvoice);
  document.getElementById("btnAmountSave")?.addEventListener("click", applyAmountModal);
  document.getElementById("billingAmountInput")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      applyAmountModal();
    }
  });
  document.querySelectorAll("[data-amount-close]").forEach((el) => {
    el.addEventListener("click", closeAmountModal);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeAmountModal();
  });
  initCustomerAutocomplete();
  Promise.all([loadCustomers(), loadPlans(), loadInvoices()]);
});

function customerOptionText(row) {
  return `${row.eponimia || ""} · ${row.afm || ""}`.trim();
}

function initCustomerAutocomplete() {
  if (!Office.createAutocomplete) return;
  invCustomerAc = Office.createAutocomplete({
    inputId: "invCustomerInput",
    listId: "invCustomerList",
    hiddenId: "invCustomer",
    maxItems: 40,
    labelFn: (item) => item.description || customerOptionText(item),
    onSelect: () => renderPlanPick(),
  });
  const input = document.getElementById("invCustomerInput");
  if (!input) return;
  const openAll = () => invCustomerAc?.openAll(false);
  input.addEventListener("focus", openAll);
  input.addEventListener("click", openAll);
  input.addEventListener("input", () => {
    document.getElementById("invCustomer").value = "";
    renderPlanPick();
  });
}

async function loadCustomers() {
  const res = await fetch("/api/billing/customers");
  const data = await res.json();
  const rows = (data.customers || []).filter((c) => Number(c.is_active));
  invCustomerAc?.setItems(rows.map((row) => ({
    value: String(row.id),
    description: customerOptionText(row),
    id: row.id,
  })));
}

async function loadPlans() {
  const res = await fetch("/api/billing/plans");
  const data = await res.json();
  invPlans = (data.plans || []).filter((p) => Number(p.is_active));
  renderPlanPick();
}

function renderPlanPick() {
  const wrap = document.getElementById("invSubsWrap");
  const customerId = document.getElementById("invCustomer")?.value;
  if (!wrap) return;
  if (!customerId) {
    wrap.innerHTML = "<p style='color:var(--muted);'>Επιλέξτε πελάτη και μετά τις συνδρομές που θα εκδοθούν.</p>";
    return;
  }
  if (!invPlans.length) {
    wrap.innerHTML = "<p style='color:var(--muted);'>Δεν υπάρχουν ενεργά πακέτα συνδρομών.</p>";
    return;
  }
  wrap.innerHTML = `<div class="billing-sub-pick">${groupPlansByFamily(invPlans).map((group, index) => `
    <div class="billing-sub-group" data-group="${index}">
      <button type="button" class="billing-group-toggle billing-sub-group-title" aria-expanded="false">
        <span class="billing-group-sign" aria-hidden="true">+</span>
        <span>${Office.escapeHtml(group.title)}</span>
      </button>
      <div class="billing-sub-group-body hidden" data-group-body="${index}" hidden>
      ${group.plans.map((plan) => `
    <label class="billing-plan-option">
      <input type="checkbox" name="plan" value="${plan.id}">
      <span>${Office.escapeHtml(plan.name || "")}</span>
      <button type="button" class="billing-plan-amount" data-plan="${plan.id}" data-original="${Office.escapeHtml(String(plan.amount_net || "0"))}" data-amount="${Office.escapeHtml(String(plan.amount_net || "0"))}">${Office.escapeHtml(String(plan.amount_net || "0"))} €</button>
    </label>`).join("")}
      </div>
    </div>
  `).join("")}</div>`;
  wrap.querySelectorAll(".billing-plan-amount").forEach((btn) => {
    btn.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      openAmountModal(btn);
    });
  });
  wrap.querySelectorAll(".billing-group-toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      const expanded = btn.getAttribute("aria-expanded") !== "true";
      btn.setAttribute("aria-expanded", expanded ? "true" : "false");
      const sign = btn.querySelector(".billing-group-sign");
      if (sign) sign.textContent = expanded ? "−" : "+";
      const group = btn.closest("[data-group]");
      const body = group?.querySelector("[data-group-body]");
      if (body) {
        body.hidden = !expanded;
        body.classList.toggle("hidden", !expanded);
      }
    });
  });
  wrap.querySelectorAll(".billing-plan-option input[name='plan']").forEach((input) => {
    input.addEventListener("change", () => {
      syncPlanOption(input);
      if (!input.checked) restorePlanAmount(planAmountButton(input));
    });
    syncPlanOption(input);
  });
}

function planAmountButton(input) {
  return input?.closest("label")?.querySelector(".billing-plan-amount") || null;
}

function catalogAmount(btn) {
  return String(btn?.dataset.original || btn?.dataset.amount || "0");
}

function restorePlanAmount(btn) {
  if (!btn) return;
  const original = catalogAmount(btn);
  btn.dataset.amount = original;
  btn.textContent = `${original} €`;
}

function syncPlanOption(input) {
  input?.closest(".billing-plan-option")?.classList.toggle("is-selected", Boolean(input?.checked));
}

function selectPlanOption(input) {
  if (!input) return;
  input.checked = true;
  syncPlanOption(input);
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

function openAmountModal(btn) {
  amountEditBtn = btn;
  const modal = document.getElementById("billingAmountModal");
  const input = document.getElementById("billingAmountInput");
  const sub = document.getElementById("billingAmountModalSub");
  const name = btn.closest("label")?.querySelector("span")?.textContent || "Πακέτο";
  if (sub) sub.textContent = `${name} · μόνο για αυτόν τον πελάτη / παραστατικό.`;
  if (input) input.value = String(btn.dataset.amount || "0");
  modal?.classList.remove("hidden");
  input?.focus();
  input?.select();
}

function closeAmountModal() {
  document.getElementById("billingAmountModal")?.classList.add("hidden");
  amountEditBtn = null;
}

function applyAmountModal() {
  if (!amountEditBtn) {
    closeAmountModal();
    return;
  }
  const raw = document.getElementById("billingAmountInput")?.value.trim() || "";
  const num = Number(raw);
  const current = String(amountEditBtn.dataset.amount || "0");
  const next = Number.isFinite(num) && num >= 0 ? num.toFixed(2) : current;
  amountEditBtn.dataset.amount = next;
  amountEditBtn.textContent = `${next} €`;
  selectPlanOption(amountEditBtn.closest("label")?.querySelector('input[name="plan"]'));
  closeAmountModal();
}

function selectedPlans() {
  return Array.from(document.querySelectorAll('input[name="plan"]:checked')).map((el) => {
    const amountBtn = document.querySelector(`.billing-plan-amount[data-plan="${el.value}"]`);
    return {
      plan_id: Number(el.value),
      amount_net: amountBtn?.dataset.amount || undefined,
    };
  });
}

function billingDate(iso) {
  if (Office.formatDateGr) return Office.formatDateGr(iso) || "";
  const parts = String(iso || "").slice(0, 10).split("-");
  if (parts.length === 3 && parts[0].length === 4) return `${parts[2]}/${parts[1]}/${parts[0]}`;
  return String(iso || "");
}

async function loadInvoices() {
  const wrap = document.getElementById("billingInvList");
  const res = await fetch("/api/billing/documents");
  const data = await res.json();
  if (!res.ok) {
    wrap.innerHTML = `<p style="color:var(--err);">${Office.escapeHtml(data.error || "Σφάλμα")}</p>`;
    return;
  }
  const rows = data.documents || [];
  if (!rows.length) {
    wrap.innerHTML = "<p style='color:var(--muted);'>Δεν έχουν κοπεί τιμολόγια.</p>";
    return;
  }
  wrap.innerHTML = `<table class="data"><tr><th>Ημ/νία</th><th>Πελάτης</th><th>Τύπος</th><th>Αριθμός</th><th>Σύνολο</th><th>MARK</th><th>Έντυπο</th><th>Oxygen</th><th></th></tr>${
    rows.map((row) => `
      <tr>
        <td>${Office.escapeHtml(billingDate(row.issued_on))}</td>
        <td>${Office.escapeHtml(row.customer_name || "")}</td>
        <td>${Office.escapeHtml(row.doc_type_label || row.doc_type || "")}${row.invoice_type ? ` · ${Office.escapeHtml(row.invoice_type)}` : ""}${row.related_label ? ` · για ${Office.escapeHtml(row.related_label)}` : ""}</td>
        <td>${row.number ? `${Office.escapeHtml(row.series || "")}-${row.number}` : "—"}</td>
        <td>${Office.escapeHtml(String(row.total_gross || "0"))} €</td>
        <td>${Office.escapeHtml(row.mark || row.oxygen_error || "—")}</td>
        <td>${row.form_url ? `<a class="btn btn-icon-only" href="${Office.escapeHtml(row.form_url)}" target="_blank" rel="noopener" title="Έντυπο" aria-label="Έντυπο">${Office.icon("file-earmark-text")}</a>` : "—"}</td>
        <td>${row.qr_url ? `<a class="btn btn-icon-only" href="${Office.escapeHtml(row.qr_url)}" target="_blank" rel="noopener" title="Oxygen PDF" aria-label="Oxygen PDF">${Office.icon("file-earmark-pdf")}</a>` : "—"}</td>
        <td>${creditAction(row)}</td>
      </tr>
    `).join("")
  }</table>`;
  Office.enhanceResponsiveTable?.(wrap.querySelector("table"));
  wrap.querySelectorAll("[data-credit]").forEach((btn) => {
    btn.addEventListener("click", () => issueCredit(Number(btn.dataset.credit)));
  });
}

function creditAction(row) {
  if (row.can_credit) {
    return `<button type="button" class="btn btn-secondary" data-credit="${row.id}">Πιστωτικό</button>`;
  }
  if (row.credit_label) {
    return Office.escapeHtml(row.credit_label);
  }
  return "—";
}

async function issueCredit(documentId) {
  if (!documentId) return;
  if (!await Office.confirm("Έκδοση πιστωτικού μέσω Oxygen για αυτό το παραστατικό;", {
    title: "Πιστωτικό",
    confirmText: "Έκδοση",
  })) return;
  const res = await fetch(`/api/billing/documents/${documentId}/credit`, { method: "POST" });
  const data = await res.json();
  if (!res.ok) {
    Office.showMsg("billingInvMsg", data.error || "Αποτυχία πιστωτικού", false);
    return;
  }
  Office.showMsg("billingInvMsg", data.document?.mark ? `Πιστωτικό · MARK ${data.document.mark}` : "Εκδόθηκε πιστωτικό.", true);
  if (data.document?.form_url) window.open(data.document.form_url, "_blank", "noopener");
  await loadInvoices();
}

async function issueInvoice() {
  const customerId = Number(document.getElementById("invCustomer").value || 0);
  const res = await fetch("/api/billing/documents/issue", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      customer_id: customerId,
      plans: selectedPlans(),
      starts_on: invStartPicker?.getIso?.() || undefined,
      doc_type: document.getElementById("invType").value,
      series: document.getElementById("invSeries").value || "1",
    }),
  });
  const data = await res.json();
  if (!res.ok) {
    Office.showMsg("billingInvMsg", data.error || "Αποτυχία έκδοσης", false);
    return;
  }
  Office.showMsg("billingInvMsg", data.document?.mark ? `Εκδόθηκε · MARK ${data.document.mark}` : "Εκδόθηκε.", true);
  document.querySelectorAll('input[name="plan"]:checked').forEach((el) => {
    el.checked = false;
    syncPlanOption(el);
    restorePlanAmount(planAmountButton(el));
  });
  if (data.document?.form_url) {
    window.open(data.document.form_url, "_blank", "noopener");
  }
  await loadInvoices();
}
