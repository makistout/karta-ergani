const MASKED = "********";

function normalizeNotifyPinInput(value) {
  return String(value || "").replace(/\D/g, "").slice(0, 4);
}

function cleanNotifyPin(value) {
  const v = String(value || "").trim();
  if (!v || v === MASKED) return "";
  return normalizeNotifyPinInput(v);
}

function isValidNotifyPin(value) {
  const pin = cleanNotifyPin(value);
  return !pin || /^\d{4}$/.test(pin);
}

function normalizeNotifyEmail(value) {
  return String(value || "").trim().toLowerCase().slice(0, 254);
}

function isValidNotifyEmail(value) {
  const email = normalizeNotifyEmail(value);
  return !email || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

let notifyRecipients = [];
let currentStoreId = null;
let storeAc = null;

function storeAcLabel(item) {
  return `${item.description || "Κατάστημα"} (ID ${item.value})`;
}

function markStorePickerClearOnClick() {
  const input = document.getElementById("notifyStoreInput");
  if (!input || input.dataset.openAllBound === "1") return;
  input.dataset.openAllBound = "1";

  const openAllStores = () => {
    if (!storeAc || input.disabled) return;
    storeAc.openAll(true);
  };

  input.addEventListener("pointerdown", openAllStores);
  input.addEventListener("focus", openAllStores);
  input.addEventListener("click", openAllStores);
}

document.addEventListener("DOMContentLoaded", async () => {
  Office.setActiveNav("storenotify");
  initNotifyRecipientButtons();
  await initStorePicker();
});

function asNotifyFlag(value, defaultValue = false) {
  if (value === false || value === 0 || value === "0" || value === "false") return false;
  if (value === true || value === 1 || value === "1" || value === "true") return true;
  if (value === undefined || value === null) return defaultValue;
  return Boolean(value);
}

function normalizeNotifyRepeatPolicy(value) {
  const v = String(value || "").trim();
  return v === "repeat_until_action" ? "repeat_until_action" : "once_snooze";
}

function mapRecipientRow(r) {
  return {
    name: r.name || "",
    mobile: r.mobile || "",
    telegram_chat_id: r.telegram_chat_id || "",
    email: normalizeNotifyEmail(r.email),
    notify_pin: cleanNotifyPin(r.notify_pin),
    has_notify_pin: Boolean(r.has_notify_pin),
    active: asNotifyFlag(r.active, true),
    email_active: asNotifyFlag(r.email_active, false),
    notify_repeat_policy: normalizeNotifyRepeatPolicy(r.notify_repeat_policy),
  };
}

function notifyRecipientIsActive(row) {
  if (!row) return true;
  const v = row.active;
  return !(v === false || v === 0 || v === "0");
}

function notifyRecipientEmailIsActive(row) {
  if (!row) return false;
  const v = row.email_active;
  return !(v === false || v === 0 || v === "0");
}

function isNotifyToggleOn(tr, selector) {
  const btn = tr?.querySelector(selector);
  return Boolean(btn?.classList.contains("notify-toggle-btn--on"));
}

function syncNotifyRecipientsFromDom() {
  const body = document.getElementById("notifyRecipientsBody");
  if (!body) return;
  body.querySelectorAll("tr.notify-recipient-main-row").forEach((tr, idx) => {
    const row = notifyRecipients[idx];
    if (!row) return;
    row.name = (tr.querySelector(".notify-input-name")?.value || "").trim();
    row.mobile = (tr.querySelector(".notify-input-mobile")?.value || "").trim();
    row.telegram_chat_id = (tr.querySelector(".notify-input-chat")?.value || "").trim();
    row.email = normalizeNotifyEmail(tr.querySelector(".notify-input-email")?.value || "");
    row.notify_pin = normalizeNotifyPinInput(tr.querySelector(".notify-input-pin")?.value || "");
    row.active = isNotifyToggleOn(tr, ".notify-toggle");
    let emailActive = isNotifyToggleOn(tr, ".notify-email-toggle");
    if (emailActive && !isValidNotifyEmail(row.email)) {
      emailActive = false;
    }
    row.email_active = emailActive;
    row.notify_repeat_policy = normalizeNotifyRepeatPolicy(
      body.querySelector(`input[name="notify-policy-${idx}"]:checked`)?.value ||
        row.notify_repeat_policy
    );
  });
}

function updateNotifyTelegramRowUi(idx) {
  const body = document.getElementById("notifyRecipientsBody");
  const tr = body?.querySelectorAll("tr.notify-recipient-main-row")[idx];
  const row = notifyRecipients[idx];
  if (!tr || !row) return;

  const isActive = notifyRecipientIsActive(row);
  const email = syncNotifyEmailFromDom(idx);
  const effectiveEmailActive = notifyRecipientEmailEffective(row, email);

  const btn = tr.querySelector(".notify-toggle");
  if (btn) {
    const tgTitle = isActive
      ? "Telegram ενεργό — λαμβάνει μηνύματα bot (πατήστε για παύση)"
      : "Telegram παυμένο — δεν λαμβάνει μηνύματα bot (πατήστε για ενεργοποίηση)";
    btn.className = `btn ${isActive ? "notify-toggle-btn notify-toggle-btn--on" : "notify-toggle-btn notify-toggle-btn--off"} notify-toggle`;
    btn.title = tgTitle;
    btn.setAttribute("aria-label", tgTitle);
    btn.innerHTML = Office.icon(isActive ? "play-circle-fill" : "stop-circle-fill");
  }

  tr.classList.toggle("notify-recipient-row--paused", !isActive && !effectiveEmailActive);
}

function syncNotifyEmailFromDom(idx) {
  const body = document.getElementById("notifyRecipientsBody");
  const tr = body?.querySelectorAll("tr.notify-recipient-main-row")[idx];
  const row = notifyRecipients[idx];
  if (!row) return "";
  const email = normalizeNotifyEmail(tr?.querySelector(".notify-input-email")?.value || row.email || "");
  row.email = email;
  return email;
}

function notifyRecipientEmailEffective(row, email) {
  const addr = email ?? row?.email ?? "";
  return notifyRecipientEmailIsActive(row) && isValidNotifyEmail(addr);
}

async function initStorePicker() {
  const input = document.getElementById("notifyStoreInput");
  const card = document.getElementById("notifyRecipientsCard");
  if (!input) return;

  storeAc = Office.createAutocomplete({
    inputId: "notifyStoreInput",
    listId: "notifyStoreList",
    hiddenId: "notifyStoreId",
    maxItems: 50,
    labelFn: storeAcLabel,
    onSelect: async (item) => {
      const id = parseInt(item.value, 10);
      if (!id) return;
      await selectStore(id, true);
    },
  });
  markStorePickerClearOnClick();

  const params = new URLSearchParams(location.search);
  const urlStoreId = parseInt(params.get("id") || "", 10) || null;

  let activeId = null;
  try {
    const activeData = await Office.fetchActiveStore();
    activeId = activeData?.store?.id ?? null;
  } catch {
    /* ignore */
  }

  let stores = [];
  try {
    const res = await fetch("/api/store/list");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    stores = await res.json();
  } catch (e) {
    input.disabled = true;
    input.placeholder = "Σφάλμα φόρτωσης";
    Office.showMsg("stepMsg", String(e), false);
    if (card) card.classList.add("hidden");
    return;
  }

  if (!stores.length) {
    input.disabled = true;
    input.placeholder = "— Δεν υπάρχουν καταστήματα —";
    if (card) card.classList.add("hidden");
    Office.showMsg("stepMsg", "Δημιουργήστε πρώτα κατάστημα από τη λίστα καταστημάτων.", false);
    return;
  }

  storeAc.setItems(
    stores.map((s) => ({
      value: String(s.id),
      description: s.name || "Κατάστημα",
    }))
  );

  const pickId = urlStoreId || activeId || stores[0]?.id || null;
  if (pickId) {
    storeAc.setValue(String(pickId));
    await selectStore(pickId, false);
  } else {
    updateNotifyUiState();
  }
}

async function selectStore(storeId, pushUrl) {
  currentStoreId = storeId;
  if (pushUrl) {
    const url = new URL(location.href);
    url.searchParams.set("id", String(storeId));
    history.replaceState(null, "", url.pathname + url.search);
  }
  await loadNotifyRecipients(storeId);
  updateNotifyUiState();
}

function initNotifyRecipientButtons() {
  document.getElementById("btnAddNotifyRecipient").onclick = () => {
    if (!currentStoreId) return;
    notifyRecipients.push({
      name: "",
      mobile: "",
      telegram_chat_id: "",
      email: "",
      notify_pin: "",
      active: true,
      email_active: false,
      notify_repeat_policy: "once_snooze",
    });
    renderNotifyRecipients();
  };
  document.getElementById("btnSaveNotifyRecipients").onclick = () => saveNotifyRecipients();
  document.getElementById("btnTestNotify").onclick = () => testNotifyRecipients();
}

function updateNotifyUiState() {
  const hasId = Boolean(currentStoreId);
  const saveBtn = document.getElementById("btnSaveNotifyRecipients");
  const testBtn = document.getElementById("btnTestNotify");
  const addBtn = document.getElementById("btnAddNotifyRecipient");
  if (saveBtn) saveBtn.disabled = !hasId;
  if (testBtn) testBtn.disabled = !hasId;
  if (addBtn) addBtn.disabled = !hasId;
}

function buildNotifyToggleBtn(idx, kind, isOn, title) {
  const icon = isOn ? "play-circle-fill" : "stop-circle-fill";
  const cls = isOn
    ? "notify-toggle-btn notify-toggle-btn--on"
    : "notify-toggle-btn notify-toggle-btn--off";
  const toggleClass = kind === "email" ? "notify-email-toggle" : "notify-toggle";
  return (
    `<button type="button" class="btn ${cls} ${toggleClass}" data-idx="${idx}" ` +
    `title="${Office.escapeHtml(title)}" aria-label="${Office.escapeHtml(title)}">` +
    `${Office.icon(icon)}</button>`
  );
}

function buildNotifyPolicyRow(row, idx) {
  const policy = normalizeNotifyRepeatPolicy(row.notify_repeat_policy);
  return (
    `<tr class="notify-recipient-policy-row" data-idx="${idx}">` +
    `<td colspan="6">` +
    `<div class="notify-policy-options" role="radiogroup" aria-label="Ρυθμός ειδοποιήσεων">` +
    `<label class="notify-policy-option">` +
    `<input type="radio" class="notify-policy-radio" name="notify-policy-${idx}" value="once_snooze"${policy === "once_snooze" ? " checked" : ""}>` +
    `<span>Μία φορά και αυτόματο snooze</span>` +
    `</label>` +
    `<label class="notify-policy-option">` +
    `<input type="radio" class="notify-policy-radio" name="notify-policy-${idx}" value="repeat_until_action"${policy === "repeat_until_action" ? " checked" : ""}>` +
    `<span>Συνέχεια κάθε 10 λεπτά μέχρι ενέργεια</span>` +
    `</label>` +
    `</div>` +
    `</td>` +
    `</tr>`
  );
}

function updateNotifyEmailRowUi(idx) {
  const body = document.getElementById("notifyRecipientsBody");
  const tr = body?.querySelectorAll("tr.notify-recipient-main-row")[idx];
  const row = notifyRecipients[idx];
  if (!tr || !row) return;

  const email = syncNotifyEmailFromDom(idx);
  const emailValid = isValidNotifyEmail(email);
  const isEmailActive = notifyRecipientEmailIsActive(row);
  const effectiveEmailActive = notifyRecipientEmailEffective(row, email);

  const emailInp = tr.querySelector(".notify-input-email");
  if (emailInp) {
    emailInp.classList.toggle("notify-input-email--invalid", Boolean(email) && !emailValid);
  }

  const btn = tr.querySelector(".notify-email-toggle");
  if (btn) {
    let emailTitle = effectiveEmailActive
      ? "Email ενεργό — λαμβάνει email ειδοποιήσεις (πατήστε για παύση)"
      : "Email παυμένο — δεν λαμβάνει email ειδοποιήσεις (πατήστε για ενεργοποίηση)";
    if (isEmailActive && !emailValid) {
      emailTitle = "Email παυμένο — μη έγκυρη διεύθυνση (δεν αποστέλλεται τίποτα)";
    }
    const isOn = effectiveEmailActive;
    btn.className = `btn ${isOn ? "notify-toggle-btn notify-toggle-btn--on" : "notify-toggle-btn notify-toggle-btn--off"} notify-email-toggle`;
    btn.title = emailTitle;
    btn.setAttribute("aria-label", emailTitle);
    btn.innerHTML = Office.icon(isOn ? "play-circle-fill" : "stop-circle-fill");
  }

  const isActive = notifyRecipientIsActive(row);
  tr.classList.toggle("notify-recipient-row--paused", !isActive && !effectiveEmailActive);
}

function renderNotifyRecipients() {
  const body = document.getElementById("notifyRecipientsBody");
  const empty = document.getElementById("notifyRecipientsEmpty");
  if (!body) return;
  body.innerHTML = "";
  if (!notifyRecipients.length) {
    if (empty) empty.style.display = currentStoreId ? "" : "none";
    return;
  }
  if (empty) empty.style.display = "none";

  notifyRecipients.forEach((row, idx) => {
    const isActive = notifyRecipientIsActive(row);
    const isEmailActive = notifyRecipientEmailIsActive(row);
    const emailValid = isValidNotifyEmail(row.email);
    const effectiveEmailActive = notifyRecipientEmailEffective(row, row.email);

    const tr = document.createElement("tr");
    tr.className = "notify-recipient-main-row";
    if (!isActive && !effectiveEmailActive) tr.classList.add("notify-recipient-row--paused");

    const pinVal = cleanNotifyPin(row.notify_pin);
    const pinPlaceholder = "4 ψηφία";
    const pinTitle =
      row.has_notify_pin && !pinVal
        ? "Υπάρχει PIN — πληκτρολογήστε ξανά και αποθηκεύστε για εμφάνιση"
        : "4 αριθμητικά ψηφία";

    const tgTitle = isActive
      ? "Telegram ενεργό — λαμβάνει μηνύματα bot (πατήστε για παύση)"
      : "Telegram παυμένο — δεν λαμβάνει μηνύματα bot (πατήστε για ενεργοποίηση)";
    let emailTitle = effectiveEmailActive
      ? "Email ενεργό — λαμβάνει email ειδοποιήσεις (πατήστε για παύση)"
      : "Email παυμένο — δεν λαμβάνει email ειδοποιήσεις (πατήστε για ενεργοποίηση)";
    if (isEmailActive && !emailValid) {
      emailTitle = "Email παυμένο — μη έγκυρη διεύθυνση (δεν αποστέλλεται τίποτα)";
    }

    tr.innerHTML =
      `<td><input type="text" class="notify-input-name" data-idx="${idx}" value="${Office.escapeHtml(row.name || "")}" placeholder="Όνομα"></td>` +
      `<td class="col-notify-field-toggle">` +
      `<div class="notify-field-with-toggle">` +
      `<input type="text" class="notify-input-mobile" data-idx="${idx}" value="${Office.escapeHtml(row.mobile || "")}" placeholder="69XXXXXXXX">` +
      buildNotifyToggleBtn(idx, "telegram", isActive, tgTitle) +
      `</div></td>` +
      `<td><input type="text" class="notify-input-chat" data-idx="${idx}" value="${Office.escapeHtml(row.telegram_chat_id || "")}" placeholder="αυτόματα" readonly title="Συμπληρώνεται με /start στο bot"></td>` +
      `<td class="col-notify-field-toggle">` +
      `<div class="notify-field-with-toggle">` +
      `<input type="email" class="notify-input-email${isEmailActive && !emailValid ? " notify-input-email--invalid" : ""}" data-idx="${idx}" value="${Office.escapeHtml(row.email || "")}" placeholder="user@example.gr">` +
      buildNotifyToggleBtn(idx, "email", effectiveEmailActive, emailTitle) +
      `</div></td>` +
      `<td><input type="text" class="notify-input-pin${row.has_notify_pin && !pinVal ? " notify-input-pin--restored" : ""}" data-idx="${idx}" value="${Office.escapeHtml(pinVal)}" placeholder="${pinPlaceholder}" inputmode="numeric" pattern="[0-9]{4}" maxlength="4" autocomplete="off" title="${Office.escapeHtml(pinTitle)}"></td>` +
      `<td class="col-notify-actions">` +
      `<button type="button" class="btn btn-danger notify-remove" data-idx="${idx}" title="Διαγραφή λήπτη" aria-label="Διαγραφή λήπτη">${Office.icon("trash3")}</button>` +
      `</td>`;
    body.appendChild(tr);
    body.insertAdjacentHTML("beforeend", buildNotifyPolicyRow(row, idx));
  });

  body.querySelectorAll(".notify-input-name, .notify-input-mobile, .notify-input-email, .notify-input-pin").forEach((inp) => {
    inp.addEventListener("input", (e) => {
      const i = parseInt(e.target.getAttribute("data-idx"), 10);
      if (!notifyRecipients[i]) return;
      if (e.target.classList.contains("notify-input-name")) {
        notifyRecipients[i].name = e.target.value;
      } else if (e.target.classList.contains("notify-input-email")) {
        notifyRecipients[i].email = e.target.value;
        updateNotifyEmailRowUi(i);
      } else if (e.target.classList.contains("notify-input-pin")) {
        const cleaned = normalizeNotifyPinInput(e.target.value);
        if (e.target.value !== cleaned) e.target.value = cleaned;
        notifyRecipients[i].notify_pin = cleaned;
      } else {
        notifyRecipients[i].mobile = e.target.value;
      }
    });
  });

  body.querySelectorAll(".notify-toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      const i = parseInt(btn.getAttribute("data-idx"), 10);
      if (!notifyRecipients[i]) return;
      notifyRecipients[i].active = !notifyRecipientIsActive(notifyRecipients[i]);
      updateNotifyTelegramRowUi(i);
      updateNotifyEmailRowUi(i);
    });
  });

  body.querySelectorAll(".notify-email-toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      const i = parseInt(btn.getAttribute("data-idx"), 10);
      const row = notifyRecipients[i];
      if (!row) return;
      const email = syncNotifyEmailFromDom(i);
      const currentlyOn = notifyRecipientEmailEffective(row, email);
      const turningOn = !currentlyOn;
      if (turningOn && !isValidNotifyEmail(email)) {
        Office.showMsg("stepMsg", "Συμπληρώστε έγκυρο email πριν ενεργοποιήσετε την αποστολή.", false);
        return;
      }
      row.email_active = turningOn;
      updateNotifyEmailRowUi(i);
    });
  });

  body.querySelectorAll(".notify-remove").forEach((btn) => {
    btn.addEventListener("click", () => {
      const i = parseInt(btn.getAttribute("data-idx"), 10);
      notifyRecipients.splice(i, 1);
      renderNotifyRecipients();
    });
  });

  body.querySelectorAll(".notify-policy-radio").forEach((radio) => {
    radio.addEventListener("change", () => {
      const tr = radio.closest(".notify-recipient-policy-row");
      const i = parseInt(tr?.getAttribute("data-idx") || "", 10);
      if (!notifyRecipients[i]) return;
      notifyRecipients[i].notify_repeat_policy = normalizeNotifyRepeatPolicy(radio.value);
    });
  });
}

function collectNotifyRecipientsFromDom() {
  syncNotifyRecipientsFromDom();
  const body = document.getElementById("notifyRecipientsBody");
  if (!body) return notifyRecipients;
  const rows = [];
  notifyRecipients.forEach((row) => {
    if (!row.name && !row.mobile && !row.email) return;
    rows.push({
      name: row.name || "",
      mobile: row.mobile || "",
      telegram_chat_id: row.telegram_chat_id || null,
      email: row.email || null,
      notify_pin: row.notify_pin || "",
      active: notifyRecipientIsActive(row),
      email_active: notifyRecipientEmailIsActive(row),
      notify_repeat_policy: normalizeNotifyRepeatPolicy(row.notify_repeat_policy),
    });
  });
  notifyRecipients = rows;
  return rows;
}

async function loadNotifyRecipients(storeId) {
  try {
    const res = await fetch(`/api/store/${storeId}/notify-recipients`, {
      credentials: "same-origin",
    });
    const data = await Office.parseJson(res);
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
    notifyRecipients = (data.recipients || []).map((r) => mapRecipientRow(r));
    renderNotifyRecipients();
  } catch (e) {
    Office.showMsg("stepMsg", `Σφάλμα φόρτωσης ληπτών: ${e}`, false);
    notifyRecipients = [];
    renderNotifyRecipients();
  }
}

async function saveNotifyRecipients() {
  if (!currentStoreId) {
    Office.showMsg("stepMsg", "Επιλέξτε κατάστημα.", false);
    return false;
  }
  const rows = collectNotifyRecipientsFromDom();
  for (const row of rows) {
    if (row.notify_pin && !isValidNotifyPin(row.notify_pin)) {
      Office.showMsg("stepMsg", "Ο PIN πρέπει να είναι ακριβώς 4 αριθμητικά ψηφία.", false);
      return false;
    }
    if (row.email && !isValidNotifyEmail(row.email)) {
      Office.showMsg("stepMsg", `Μη έγκυρο email για ${row.name || row.mobile || "λήπτη"}.`, false);
      return false;
    }
    if (row.email_active && !isValidNotifyEmail(row.email)) {
      row.email_active = false;
    }
  }
  const seenPins = new Map();
  for (const row of rows) {
    const pin = cleanNotifyPin(row.notify_pin);
    if (!pin) continue;
    if (seenPins.has(pin)) {
      Office.showMsg(
        "stepMsg",
        `Ο PIN ${pin} χρησιμοποιείται ήδη από άλλον λήπτη στο ίδιο κατάστημα. Κάθε PIN πρέπει να είναι μοναδικός.`,
        false
      );
      return false;
    }
    seenPins.set(pin, row.name || row.mobile || "λήπτης");
  }
  const btn = document.getElementById("btnSaveNotifyRecipients");
  if (btn) btn.disabled = true;
  try {
    const res = await fetch(`/api/store/${currentStoreId}/notify-recipients`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ recipients: rows }),
    });
    const data = await Office.parseJson(res);
    if (!res.ok) {
      Office.showMsg("stepMsg", data.error || "Αποτυχία αποθήκευσης ληπτών", false);
      return false;
    }
    notifyRecipients = (data.recipients || []).map((r) => mapRecipientRow(r));
    renderNotifyRecipients();
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
  if (!currentStoreId) {
    Office.showMsg("stepMsg", "Επιλέξτε κατάστημα.", false);
    return;
  }
  await saveNotifyRecipients();
  const btn = document.getElementById("btnTestNotify");
  if (btn) btn.disabled = true;
  try {
    const res = await fetch(`/api/telegram/test/${currentStoreId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({}),
    });
    const data = await Office.parseJson(res);
    if (!res.ok) {
      Office.showMsg("stepMsg", data.error || "Αποτυχία αποστολής", false);
      return;
    }
    const err = (data.errors || []).join(" · ");
    const tg = data.telegram_sent ?? 0;
    const em = data.email_sent ?? 0;
    const parts = [];
    if (tg) parts.push(`Telegram: ${tg}`);
    if (em) parts.push(`Email: ${em}`);
    const summary = parts.length ? parts.join(" · ") : "0 αποστολές";
    Office.showMsg(
      "stepMsg",
      err
        ? `${summary}. Σφάλματα: ${err}`
        : `Δοκιμαστικό μήνυμα — ${summary}.`,
      (tg + em) > 0
    );
  } catch (e) {
    Office.showMsg("stepMsg", String(e), false);
  } finally {
    updateNotifyUiState();
  }
}
