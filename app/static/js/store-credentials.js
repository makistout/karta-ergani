const MASKED = "********";
let notifyRecipients = [];

document.addEventListener("DOMContentLoaded", async () => {
  Office.setActiveNav("stores");
  const params = new URLSearchParams(location.search);
  const draft = Office.getDraft();
  const editStoreId = parseInt(params.get("id") || "", 10) || draft.id;
  initNotifyRecipientButtons();
  if (params.get("edit") === "1" && editStoreId) {
    document.querySelector(".page-title").textContent = "Επεξεργασία καταστήματος";
    await loadStoreIntoForm(editStoreId);
  } else {
    fillFormFromDraft(draft);
    if (Array.isArray(draft.notifyRecipients) && draft.notifyRecipients.length) {
      notifyRecipients = draft.notifyRecipients.map((r) => ({
        name: r.name || "",
        mobile: r.mobile || "",
        telegram_chat_id: r.telegram_chat_id || "",
        notify_pin: r.notify_pin || "",
        has_notify_pin: Boolean(r.has_notify_pin),
      }));
      renderNotifyRecipients();
    } else {
      renderNotifyRecipients();
    }
    updateNotifyUiState();
  }
  document.getElementById("btnStep1Next").onclick = onStep1Next;
});

function cleanSecret(value) {
  const s = (value || "").trim();
  return s === MASKED ? "" : s;
}

function fillFormFromDraft(draft) {
  document.getElementById("storeName").value = draft.name || "";
  document.getElementById("storeAdminUser").value = draft.username || "";
  document.getElementById("storeAdminPass").value = cleanSecret(draft.password);
  document.getElementById("storeAdminUtype").value = draft.usertype || "01";
  document.getElementById("storeWebUser").value = draft.web_username || "";
  document.getElementById("storeWebPass").value = cleanSecret(draft.web_password);
  document.getElementById("storeEnv").value = draft.ergani_env || "production";
}

function updateNotifyUiState() {
  const draft = Office.getDraft();
  const hasId = Boolean(draft.id);
  setNotifyButtonsEnabled(hasId);
  document.getElementById("notifyRecipientsPendingHint")?.classList.toggle("hidden", hasId);
}

function initNotifyRecipientButtons() {
  document.getElementById("btnAddNotifyRecipient").onclick = () => {
    notifyRecipients.push({ name: "", mobile: "", telegram_chat_id: "", notify_pin: "" });
    renderNotifyRecipients();
  };
  document.getElementById("btnSaveNotifyRecipients").onclick = () => saveNotifyRecipients();
  document.getElementById("btnTestNotify").onclick = () => testNotifyRecipients();
}

function setNotifyButtonsEnabled(enabled) {
  const saveBtn = document.getElementById("btnSaveNotifyRecipients");
  const testBtn = document.getElementById("btnTestNotify");
  if (saveBtn) saveBtn.disabled = !enabled;
  if (testBtn) testBtn.disabled = !enabled;
}

function renderNotifyRecipients() {
  const body = document.getElementById("notifyRecipientsBody");
  const empty = document.getElementById("notifyRecipientsEmpty");
  if (!body) return;
  body.innerHTML = "";
  if (!notifyRecipients.length) {
    if (empty) empty.style.display = "";
    return;
  }
  if (empty) empty.style.display = "none";
  notifyRecipients.forEach((row, idx) => {
    const tr = document.createElement("tr");
    const pinVal = row.notify_pin || (row.has_notify_pin ? MASKED : "");
    tr.innerHTML =
      `<td><input type="text" class="notify-input-name" data-idx="${idx}" value="${Office.escapeHtml(row.name || "")}" placeholder="Όνομα"></td>` +
      `<td><input type="text" class="notify-input-mobile" data-idx="${idx}" value="${Office.escapeHtml(row.mobile || "")}" placeholder="69XXXXXXXX"></td>` +
      `<td><input type="text" class="notify-input-chat" data-idx="${idx}" value="${Office.escapeHtml(row.telegram_chat_id || "")}" placeholder="αυτόματα" readonly title="Συμπληρώνεται με /start στο bot"></td>` +
      `<td><input type="password" class="notify-input-pin" data-idx="${idx}" value="${Office.escapeHtml(pinVal)}" placeholder="PIN" inputmode="numeric" maxlength="8" title="Προσωπικός κωδικός για αυτόματο χτύπημα"></td>` +
      `<td class="table-actions"><button type="button" class="btn btn-danger btn-sm notify-remove" data-idx="${idx}">${Office.icon("trash3")}</button></td>`;
    body.appendChild(tr);
  });
  body.querySelectorAll(".notify-input-name, .notify-input-mobile, .notify-input-pin").forEach((inp) => {
    inp.addEventListener("input", (e) => {
      const i = parseInt(e.target.getAttribute("data-idx"), 10);
      let field = "mobile";
      if (e.target.classList.contains("notify-input-name")) field = "name";
      else if (e.target.classList.contains("notify-input-pin")) field = "notify_pin";
      if (notifyRecipients[i]) notifyRecipients[i][field] = e.target.value;
    });
  });
  body.querySelectorAll(".notify-remove").forEach((btn) => {
    btn.addEventListener("click", () => {
      const i = parseInt(btn.getAttribute("data-idx"), 10);
      notifyRecipients.splice(i, 1);
      renderNotifyRecipients();
    });
  });
}

function collectNotifyRecipientsFromDom() {
  const body = document.getElementById("notifyRecipientsBody");
  if (!body) return notifyRecipients;
  const rows = [];
  body.querySelectorAll("tr").forEach((tr) => {
    const name = (tr.querySelector(".notify-input-name")?.value || "").trim();
    const mobile = (tr.querySelector(".notify-input-mobile")?.value || "").trim();
    const telegram_chat_id = (tr.querySelector(".notify-input-chat")?.value || "").trim();
    const notify_pin = (tr.querySelector(".notify-input-pin")?.value || "").trim();
    if (name || mobile) {
      rows.push({
        name,
        mobile,
        telegram_chat_id: telegram_chat_id || null,
        notify_pin: notify_pin || "",
      });
    }
  });
  notifyRecipients = rows;
  return rows;
}

function persistNotifyRecipientsToDraft() {
  const rows = collectNotifyRecipientsFromDom();
  Office.setDraft({ ...Office.getDraft(), notifyRecipients: rows });
  return rows;
}

async function loadNotifyRecipients(storeId) {
  try {
    const res = await fetch(`/api/store/${storeId}/notify-recipients`);
    const data = await res.json();
    if (!res.ok) {
      Office.showMsg(
        "stepMsg",
        data.error || data.db_setup || `Σφάλμα ληπτών (HTTP ${res.status})`,
        false
      );
      notifyRecipients = [];
      renderNotifyRecipients();
      return;
    }
    notifyRecipients = (data.recipients || []).map((r) => ({
      name: r.name || "",
      mobile: r.mobile || "",
      telegram_chat_id: r.telegram_chat_id || "",
      notify_pin: r.notify_pin || "",
      has_notify_pin: Boolean(r.has_notify_pin),
    }));
    renderNotifyRecipients();
    updateNotifyUiState();
  } catch (e) {
    Office.showMsg("stepMsg", `Σφάλμα φόρτωσης ληπτών: ${e}`, false);
    notifyRecipients = [];
    renderNotifyRecipients();
  }
}

async function saveNotifyRecipients(storeIdOverride) {
  const draft = Office.getDraft();
  const storeId = storeIdOverride || draft.id;
  if (!storeId) {
    Office.showMsg("stepMsg", "Για νέο κατάστημα, οι λήπτες αποθηκεύονται μετά την «Συνέχεια».", false);
    return false;
  }
  const rows = collectNotifyRecipientsFromDom();
  const btn = document.getElementById("btnSaveNotifyRecipients");
  if (btn) btn.disabled = true;
  try {
    const res = await fetch(`/api/store/${storeId}/notify-recipients`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ recipients: rows }),
    });
    const data = await res.json();
    if (!res.ok) {
      Office.showMsg("stepMsg", data.error || "Αποτυχία αποθήκευσης ληπτών", false);
      return false;
    }
    notifyRecipients = (data.recipients || []).map((r) => ({
      name: r.name || "",
      mobile: r.mobile || "",
      telegram_chat_id: r.telegram_chat_id || "",
      notify_pin: r.notify_pin || "",
      has_notify_pin: Boolean(r.has_notify_pin),
    }));
    renderNotifyRecipients();
    Office.setDraft({ ...Office.getDraft(), id: storeId, notifyRecipients });
    Office.showMsg("stepMsg", `Αποθηκεύτηκαν ${data.count || 0} λήπτες.`, true);
    return true;
  } catch (e) {
    Office.showMsg("stepMsg", String(e), false);
    return false;
  } finally {
    updateNotifyUiState();
  }
}

async function testNotifyRecipients() {
  const draft = Office.getDraft();
  if (!draft.id) {
    Office.showMsg("stepMsg", "Αποθηκεύστε πρώτα τους λήπτες.", false);
    return;
  }
  await saveNotifyRecipients(draft.id);
  const btn = document.getElementById("btnTestNotify");
  if (btn) btn.disabled = true;
  try {
    const res = await fetch(`/api/telegram/test/${draft.id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const data = await res.json();
    if (!res.ok) {
      Office.showMsg("stepMsg", data.error || "Αποτυχία αποστολής", false);
      return;
    }
    const err = (data.errors || []).join(" · ");
    Office.showMsg(
      "stepMsg",
      err
        ? `Στάλθηκαν ${data.sent}/${data.total}. ${err}`
        : `Στάλθηκαν ${data.sent} δοκιμαστικά μηνύματα.`,
      data.sent > 0
    );
  } catch (e) {
    Office.showMsg("stepMsg", String(e), false);
  } finally {
    updateNotifyUiState();
  }
}

async function loadStoreIntoForm(storeId) {
  try {
    const res = await fetch(`/api/store/${storeId}`);
    const store = await res.json();
    if (!res.ok) {
      Office.showMsg("stepMsg", store.error || "Σφάλμα φόρτωσης", false);
      return;
    }
    fillFormFromDraft(store);
    Office.setDraft({
      ...Office.getDraft(),
      ...store,
      id: storeId,
      accessToken: "",
      branches: null,
    });
    await loadNotifyRecipients(storeId);
    updateNotifyUiState();
  } catch (e) {
    Office.showMsg("stepMsg", String(e), false);
  }
}

function readCredentialFields() {
  return {
    name: document.getElementById("storeName").value.trim(),
    username: document.getElementById("storeAdminUser").value.trim(),
    password: cleanSecret(document.getElementById("storeAdminPass").value),
    usertype: document.getElementById("storeAdminUtype").value,
    web_username: document.getElementById("storeWebUser").value.trim(),
    web_password: cleanSecret(document.getElementById("storeWebPass").value),
    ergani_env: document.getElementById("storeEnv").value || "production",
  };
}

async function persistCredentials(draft, fields, employer_afm) {
  const res = await fetch("/api/store/credentials", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      id: draft.id || undefined,
      name: fields.name,
      username: fields.username,
      password: fields.password,
      usertype: fields.usertype,
      web_username: fields.web_username,
      web_password: fields.web_password,
      ergani_env: fields.ergani_env,
      employer_afm: employer_afm || draft.employer_afm,
      branch_aa: draft.branch_aa,
    }),
  });
  const data = await res.json();
  if (!res.ok || !data.success) {
    throw new Error(data.error || "Αποτυχία αποθήκευσης");
  }
  return data.id;
}

function erganiEnvHeaders(ergani_env) {
  return { "X-Ergani-Env": ergani_env };
}

async function onStep1Next() {
  const fields = readCredentialFields();
  const { name, username, password, usertype, web_username, web_password, ergani_env } = fields;
  if (!name || !web_username || !web_password) {
    Office.showMsg("stepMsg", "Συμπληρώστε όνομα και διαπιστευτήρια web (API).", false);
    return;
  }
  if (!username || !password) {
    Office.showMsg("stepMsg", "Συμπληρώστε admin username και password (portal).", false);
    return;
  }
  const btn = document.getElementById("btnStep1Next");
  const draft = Office.getDraft();
  const pendingRecipients = persistNotifyRecipientsToDraft();
  btn.disabled = true;
  Office.showMsg(
    "stepMsg",
    `Έλεγχος: web ${web_username} (API) + admin ${username} (portal)…`,
    true
  );
  try {
    const verifyRes = await fetch("/api/store/verify-wizard", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id: draft.id || undefined,
        web_username,
        web_password,
        username,
        password,
        usertype,
        ergani_env,
      }),
    });
    const verifyData = await Office.parseJson(verifyRes);
    if (verifyData._parseError) {
      Office.showMsg("stepMsg", verifyData._parseError, false);
      return;
    }
    if (!verifyRes.ok || !verifyData.success) {
      Office.showMsg("stepMsg", verifyData.error || "Αποτυχία ελέγχου διαπιστευτηρίων", false);
      return;
    }

    const authRes = await fetch("/api/ergani/auth/authenticate", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...erganiEnvHeaders(ergani_env),
      },
      body: JSON.stringify({
        Username: web_username,
        Password: web_password,
        Usertype: "02",
        ergani_env,
      }),
    });
    const authData = await Office.parseJson(authRes);
    if (authData._parseError) {
      Office.showMsg("stepMsg", authData._parseError, false);
      return;
    }
    if (!authRes.ok || !authData.accessToken) {
      Office.showMsg("stepMsg", authData.error || "Αποτυχία API (web)", false);
      return;
    }
    const token = authData.accessToken;
    const branchesRes = await fetch("/api/ergani/branches", {
      headers: {
        Authorization: `Bearer ${token}`,
        ...erganiEnvHeaders(ergani_env),
      },
    });
    const branchesData = await Office.parseJson(branchesRes);
    if (branchesData._parseError) {
      Office.showMsg("stepMsg", branchesData._parseError, false);
      return;
    }
    if (!branchesRes.ok) {
      Office.showMsg("stepMsg", branchesData.error || "Αποτυχία EX_BASE_02", false);
      return;
    }
    const employer_afm = authData.employer_afm || draft.employer_afm;
    let storeId = draft.id;
    try {
      storeId = await persistCredentials({ ...draft, employer_afm }, fields, employer_afm);
      Office.showMsg(
        "stepMsg",
        `OK — web/API: ${web_username}, portal/admin: ${username}. Μετάβαση σε παράρτημα…`,
        true
      );
    } catch (saveErr) {
      Office.showMsg("stepMsg", String(saveErr), false);
      return;
    }
    if (storeId && pendingRecipients.length) {
      await saveNotifyRecipients(storeId);
    }
    Office.setDraft({
      ...draft,
      id: storeId,
      ...fields,
      ergani_env,
      accessToken: token,
      employer_afm,
      branches: branchesData.branches || [],
      notifyRecipients: pendingRecipients,
    });
    window.location.href = "/ui/stores/branch";
  } catch (e) {
    Office.showMsg("stepMsg", String(e), false);
  } finally {
    btn.disabled = false;
  }
}
