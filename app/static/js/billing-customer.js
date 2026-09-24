const billingState = { id: null, stores: [], assigned: [] };
let billingStoreAc = null;

document.addEventListener("DOMContentLoaded", () => {
  Office.setActiveNav("billing-customers");
  const params = new URLSearchParams(location.search);
  billingState.id = params.get("id") ? Number(params.get("id")) : null;
  document.getElementById("btnSaveCustomer")?.addEventListener("click", saveCustomer);
  document.getElementById("btnAddStore")?.addEventListener("click", addStore);
  initStoreAutocomplete();
  if (billingState.id) loadCustomer();
});

function storeOptionText(store) {
  return `${store.store_name || ""} · ${store.employer_afm || ""} / ${store.branch_aa || "0"}`.trim();
}

function initStoreAutocomplete() {
  if (!Office.createAutocomplete) return;
  billingStoreAc = Office.createAutocomplete({
    inputId: "custStoreInput",
    listId: "custStoreList",
    hiddenId: "custStorePick",
    maxItems: 40,
    labelFn: (item) => item.description || storeOptionText(item),
  });
  const input = document.getElementById("custStoreInput");
  if (!input) return;
  const openAll = () => billingStoreAc?.openAll(false);
  input.addEventListener("focus", openAll);
  input.addEventListener("click", openAll);
  input.addEventListener("input", () => {
    document.getElementById("custStorePick").value = "";
    input.closest(".ac-wrap")?.classList.remove("field-err");
  });
}

function val(id) {
  return document.getElementById(id)?.value?.trim() || "";
}

function customerPayload() {
  return {
    eponimia: val("custEponimia"),
    epaggelma: val("custEpaggelma"),
    address: val("custAddress"),
    afm: val("custAfm"),
    doy: val("custDoy"),
    email: val("custEmail"),
    phone: val("custPhone"),
    notes: val("custNotes"),
    is_active: document.getElementById("custActive")?.checked ? 1 : 0,
  };
}

function fillCustomer(c) {
  document.getElementById("custEponimia").value = c.eponimia || "";
  document.getElementById("custEpaggelma").value = c.epaggelma || "";
  document.getElementById("custAddress").value = c.address || "";
  document.getElementById("custAfm").value = c.afm || "";
  document.getElementById("custDoy").value = c.doy || "";
  document.getElementById("custEmail").value = c.email || "";
  document.getElementById("custPhone").value = c.phone || "";
  document.getElementById("custNotes").value = c.notes || "";
  document.getElementById("custActive").checked = Number(c.is_active) !== 0;
  document.getElementById("billingCustomerTitle").innerHTML =
    `${Office.icon("building")} ${Office.escapeHtml(c.eponimia || "Πελάτης")}`;
  billingState.assigned = c.stores || [];
  renderStores();
  renderSubscriptions(c.subscriptions || []);
  renderDocuments(c.documents || []);
}

async function loadCustomer() {
  const res = await fetch(`/api/billing/customers/${billingState.id}`);
  const data = await res.json();
  if (!res.ok) {
    Office.showMsg("billingCustMsg", data.error || "Σφάλμα", false);
    return;
  }
  fillCustomer(data.customer);
  document.getElementById("billingStoresCard").hidden = false;
  document.getElementById("billingSubsCard").hidden = false;
  document.getElementById("billingDocsCard").hidden = false;
  await loadStoreOptions();
}

async function saveCustomer() {
  const url = billingState.id ? `/api/billing/customers/${billingState.id}` : "/api/billing/customers";
  const res = await fetch(url, {
    method: billingState.id ? "PUT" : "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(customerPayload()),
  });
  const data = await res.json();
  if (!res.ok) {
    Office.showMsg("billingCustMsg", data.error || "Αποτυχία", false);
    return;
  }
  billingState.id = data.customer.id;
  history.replaceState(null, "", `/ui/billing/customer?id=${billingState.id}`);
  fillCustomer(data.customer);
  document.getElementById("billingStoresCard").hidden = false;
  document.getElementById("billingSubsCard").hidden = false;
  document.getElementById("billingDocsCard").hidden = false;
  await loadStoreOptions();
  Office.showMsg("billingCustMsg", "Αποθηκεύτηκε.", true);
}

async function loadStoreOptions() {
  const res = await fetch("/api/billing/stores");
  const data = await res.json();
  billingState.stores = data.stores || [];
  const assigned = new Set(billingState.assigned.map((s) => Number(s.store_id)));
  const available = billingState.stores.filter((store) => {
    const taken = store.customer_id && Number(store.customer_id) !== Number(billingState.id);
    return !assigned.has(Number(store.store_id)) && !taken;
  }).map((store) => ({
    value: String(store.store_id),
    description: storeOptionText(store),
    store_id: store.store_id,
  }));
  billingStoreAc?.setItems(available);
}

function renderStores() {
  const wrap = document.getElementById("custStoresWrap");
  if (!wrap) return;
  if (!billingState.assigned.length) {
    wrap.innerHTML = "<p style='color:var(--muted);'>Δεν έχουν συνδεθεί καταστήματα.</p>";
    return;
  }
  wrap.innerHTML = billingState.assigned.map((store) => `
    <div class="billing-chip">
      <strong>${Office.escapeHtml(store.store_name || "")}</strong>
      <span>${Office.escapeHtml(store.employer_afm || "")} · παρ. ${Office.escapeHtml(String(store.branch_aa || "0"))}</span>
      <button type="button" class="btn btn-secondary" data-remove-store="${store.store_id}">Αφαίρεση</button>
    </div>
  `).join("");
  wrap.querySelectorAll("[data-remove-store]").forEach((btn) => {
    btn.addEventListener("click", () => removeStore(Number(btn.dataset.removeStore)));
  });
}

async function saveStores(ids) {
  const res = await fetch(`/api/billing/customers/${billingState.id}/stores`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ store_ids: ids }),
  });
  const data = await res.json();
  if (!res.ok) {
    Office.showMsg("billingCustMsg", data.error || "Αποτυχία καταστημάτων", false);
    return;
  }
  billingState.assigned = data.stores || [];
  renderStores();
  await loadStoreOptions();
}

function renderSubscriptions(rows) {
  const wrap = document.getElementById("custSubsWrap");
  if (!wrap) return;
  if (!rows.length) {
    wrap.innerHTML = "<p style='color:var(--muted);'>Δεν έχουν καταχωρηθεί συνδρομές. Η επιλογή γίνεται κατά την έκδοση παραστατικού.</p>";
    return;
  }
  wrap.innerHTML = `<table class="data"><tr><th>Πακέτο</th><th>Διάστημα</th><th>Ποσό</th><th>Κατάσταση</th></tr>${
    rows.map((row) => `
      <tr>
        <td>${Office.escapeHtml(row.plan_name || "")}</td>
        <td>${Office.escapeHtml(billingDate(row.starts_on))} – ${Office.escapeHtml(billingDate(row.ends_on))}</td>
        <td>${Office.escapeHtml(String(row.amount_net || "0"))} €</td>
        <td>${row.billed ? "Τιμολογήθηκε" : Office.escapeHtml(row.status || "")}</td>
      </tr>
    `).join("")
  }</table>`;
  Office.enhanceResponsiveTable?.(wrap.querySelector("table"));
}

function billingDate(iso) {
  if (Office.formatDateGr) return Office.formatDateGr(iso) || "";
  const parts = String(iso || "").slice(0, 10).split("-");
  if (parts.length === 3 && parts[0].length === 4) return `${parts[2]}/${parts[1]}/${parts[0]}`;
  return String(iso || "");
}

function renderDocuments(rows) {
  const wrap = document.getElementById("custDocsWrap");
  if (!wrap) return;
  if (!rows.length) {
    wrap.innerHTML = "<p style='color:var(--muted);'>Δεν υπάρχουν παραστατικά.</p>";
    return;
  }
  wrap.innerHTML = `<table class="data"><tr><th>Ημ/νία</th><th>Τύπος</th><th>Αριθμός</th><th>Σύνολο</th><th>Έντυπο</th><th>MARK</th><th></th></tr>${
    rows.map((row) => `
      <tr>
        <td>${Office.escapeHtml(billingDate(row.issued_on))}</td>
        <td>${Office.escapeHtml(row.doc_type_label || row.doc_type || "")}${row.related_label ? ` · για ${Office.escapeHtml(row.related_label)}` : ""}</td>
        <td>${row.number ? `${Office.escapeHtml(row.series || "")}-${row.number}` : "—"}</td>
        <td>${Office.escapeHtml(String(row.total_gross || "0"))} €</td>
        <td>${row.form_url ? `<a class="btn btn-icon-only" href="${Office.escapeHtml(row.form_url)}" target="_blank" rel="noopener" title="Έντυπο" aria-label="Έντυπο">${Office.icon("file-earmark-text")}</a>` : "—"}</td>
        <td>${row.qr_url ? `<a href="${Office.escapeHtml(row.qr_url)}" target="_blank" rel="noopener">${Office.escapeHtml(row.mark || "PDF")}</a>` : Office.escapeHtml(row.mark || "—")}</td>
        <td>${row.can_credit ? `<button type="button" class="btn btn-secondary" data-credit="${row.id}">Πιστωτικό</button>` : row.credit_label ? Office.escapeHtml(row.credit_label) : "—"}</td>
      </tr>
    `).join("")
  }</table>`;
  Office.enhanceResponsiveTable?.(wrap.querySelector("table"));
  wrap.querySelectorAll("[data-credit]").forEach((btn) => {
    btn.addEventListener("click", () => issueCustomerCredit(Number(btn.dataset.credit)));
  });
}

async function issueCustomerCredit(documentId) {
  if (!documentId) return;
  if (!await Office.confirm("Έκδοση πιστωτικού μέσω Oxygen για αυτό το παραστατικό;", {
    title: "Πιστωτικό",
    confirmText: "Έκδοση",
  })) return;
  const res = await fetch(`/api/billing/documents/${documentId}/credit`, { method: "POST" });
  const data = await res.json();
  if (!res.ok) {
    Office.showMsg("billingCustMsg", data.error || "Αποτυχία πιστωτικού", false);
    return;
  }
  Office.showMsg("billingCustMsg", data.document?.mark ? `Πιστωτικό · MARK ${data.document.mark}` : "Εκδόθηκε πιστωτικό.", true);
  if (data.document?.form_url) window.open(data.document.form_url, "_blank", "noopener");
  if (billingState.id) loadCustomer();
}

async function addStore() {
  const sid = Number(document.getElementById("custStorePick")?.value || 0);
  if (!sid) {
    document.getElementById("custStoreInput")?.closest(".ac-wrap")?.classList.add("field-err");
    return;
  }
  const ids = billingState.assigned.map((s) => Number(s.store_id));
  if (!ids.includes(sid)) ids.push(sid);
  await saveStores(ids);
  billingStoreAc?.clearValue();
}

async function removeStore(storeId) {
  const ids = billingState.assigned.map((s) => Number(s.store_id)).filter((id) => id !== storeId);
  await saveStores(ids);
}
