let usersState = {
  users: [],
  roles: [],
  rolePermissions: {},
  permissions: [],
  stores: [],
  selected: null,
  selectedStoreIds: new Set(),
  storeQuery: "",
  permissionQuery: "",
};

let userStoreAc = null;

const PERMISSION_COMPONENTS = {
  "*": {
    label: "Όλα",
    type: "Καθολικό",
    description: "Πλήρης πρόσβαση σε όλες τις σελίδες, ενέργειες και καταστήματα.",
  },
  dashboard: {
    label: "Dashboard",
    type: "Προβολή",
    description: "Αρχική εικόνα του γραφείου με συνοπτικά στοιχεία και καταστάσεις.",
  },
  employees: {
    label: "Εργαζόμενοι",
    type: "Μητρώο",
    description: "Λίστα εργαζομένων, στοιχεία απασχόλησης και εξαγωγές προσωπικού.",
  },
  schedule: {
    label: "Ψηφιακό ωράριο",
    type: "ΕΡΓΑΝΗ",
    description: "Προβολή, συγχρονισμός και υποβολές ωραρίων, αδειών και WΤΟ.",
  },
  work_log: {
    label: "Πραγματική απασχόληση",
    type: "ΕΡΓΑΝΗ",
    description: "Πραγματικές κινήσεις εργασίας, ιστορικό και συγχρονισμός παρουσιών.",
  },
  missing_cards: {
    label: "Ελλειπή χτυπήματα",
    type: "Έλεγχος",
    description: "Έλεγχος και κλείσιμο εκκρεμοτήτων από ελλιπείς κινήσεις κάρτας.",
  },
  work_card: {
    label: "Ψηφιακή κάρτα",
    type: "ΕΡΓΑΝΗ",
    description: "Live/αναδρομικές υποβολές ψηφιακής κάρτας και ιστορικό κινήσεων.",
  },
  sync: {
    label: "Συγχρονισμός",
    type: "Λειτουργία",
    description: "Χειροκίνητοι συγχρονισμοί ανά κατάστημα ή περίοδο και παρακολούθηση προόδου.",
  },
  monthly_status: {
    label: "Μηνιαία κατάσταση",
    type: "Έλεγχος",
    description: "Μηνιαία εικόνα/συγχρονισμός κατάστασης για έλεγχο εκκρεμοτήτων.",
  },
  notifications: {
    label: "Ειδοποιήσεις",
    type: "Επικοινωνία",
    description: "Προβολή, κανόνες, παραλήπτες και δοκιμαστικές αποστολές ειδοποιήσεων.",
  },
  logs: {
    label: "Καταγραφές",
    type: "Audit",
    description: "Ιστορικό συγχρονισμών, ειδοποιήσεων, σφαλμάτων και ενεργειών.",
  },
  stores: {
    label: "Καταστήματα",
    type: "Scope",
    description: "Πρόσβαση σε καταστήματα, επιλογή ενεργού καταστήματος και διαχείριση στοιχείων/API.",
  },
  users: {
    label: "Χρήστες",
    type: "Admin",
    description: "Δημιουργία χρηστών, αλλαγές ρόλων, permissions, passwords και πρόσβαση καταστημάτων.",
  },
  settings: {
    label: "Ρυθμίσεις",
    type: "Admin",
    description: "Ρυθμίσεις συστήματος, scheduler και ευαίσθητα secrets.",
  },
  ergani: {
    label: "Κατάλογοι ΕΡΓΑΝΗ",
    type: "Βοηθητικό",
    description: "Κατάλογοι/λεξικά ΕΡΓΑΝΗ, παραρτήματα, ειδικότητες και αναζητήσεις.",
  },
};

const PERMISSION_ACTIONS = {
  view: "Βλέπει τη σελίδα ή τα δεδομένα.",
  sync: "Τρέχει συγχρονισμό με ΕΡΓΑΝΗ ή ενημέρωση τοπικών δεδομένων.",
  export: "Κάνει εξαγωγή αρχείων ή αναφορών.",
  select: "Επιλέγει ενεργό κατάστημα εργασίας.",
  catalog: "Διαβάζει βοηθητικούς καταλόγους.",
  run_store: "Τρέχει συγχρονισμό για συγκεκριμένο κατάστημα.",
  run_period: "Τρέχει συγχρονισμό για περίοδο.",
  run_all: "Τρέχει συνολικό συγχρονισμό.",
  view_progress: "Βλέπει πρόοδο εργασίας ή background job.",
  view_sync: "Βλέπει logs συγχρονισμών.",
  view_work_cards: "Βλέπει logs κινήσεων κάρτας.",
  view_notifications: "Βλέπει logs ειδοποιήσεων.",
  view_errors: "Βλέπει σφάλματα συστήματος.",
  view_sensitive: "Βλέπει ευαίσθητα στοιχεία καταστημάτων.",
  submit_live: "Υποβάλλει live κίνηση.",
  submit_retro: "Υποβάλλει αναδρομική κίνηση.",
  submit_leave: "Υποβάλλει άδεια.",
  submit_daily: "Υποβάλλει ημερήσιο πρόγραμμα.",
  submit_weekly: "Υποβάλλει εβδομαδιαίο πρόγραμμα.",
  view_history: "Βλέπει ιστορικό κινήσεων.",
  sync_refresh: "Ανανεώνει δεδομένα με συγχρονισμό.",
  close_one: "Κλείνει μία εκκρεμότητα.",
  close_all: "Κλείνει μαζικά εκκρεμότητες.",
  snooze: "Αναβάλει ειδοποίηση.",
  send_test: "Στέλνει δοκιμαστική ειδοποίηση.",
  manage: "Διαχειρίζεται ρυθμίσεις ή εγγραφές.",
  create: "Δημιουργεί νέα εγγραφή.",
  edit: "Επεξεργάζεται υπάρχουσα εγγραφή.",
  disable: "Απενεργοποιεί χρήστη ή εγγραφή.",
  delete: "Διαγράφει οριστικά χρήστη και συσχετίσεις.",
  reset_password: "Αλλάζει password χρήστη.",
  manage_permissions: "Αλλάζει granular δικαιώματα χρήστη.",
  manage_store_access: "Αλλάζει πρόσβαση χρήστη σε καταστήματα.",
};

const ROLE_LABELS = {
  admin: "admin",
  backoffice_admin: "backoffice",
  notifications_manager: "notif.",
  office: "office",
  office_manager: "manager",
  store_viewer: "store view",
  super_admin: "super",
  viewer: "viewer",
};

document.addEventListener("DOMContentLoaded", () => {
  Office.setActiveNav("users");
  initStoreAutocomplete();
  document.getElementById("btnNewUser")?.addEventListener("click", () => selectUser(null));
  document.getElementById("userRole")?.addEventListener("change", applyRoleTemplate);
  document.getElementById("btnSaveUser")?.addEventListener("click", saveUser);
  document.getElementById("btnResetPassword")?.addEventListener("click", resetPassword);
  document.getElementById("btnRoleTemplate")?.addEventListener("click", applyRoleTemplate);
  document.getElementById("btnClearPerms")?.addEventListener("click", () => setCheckedPermissions([]));
  document.getElementById("btnAddStore")?.addEventListener("click", addStoreFromSearch);
  document.getElementById("userStoreSearch")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      addStoreFromSearch();
    }
  });
  document.getElementById("permissionCompareSearch")?.addEventListener("input", (event) => {
    usersState.permissionQuery = String(event.target.value || "");
    renderPermissionComparison();
  });
  document.getElementById("userActivityClose")?.addEventListener("click", closeUserActivityModal);
  document.getElementById("userActivityModal")?.querySelectorAll("[data-user-activity-close]").forEach((el) => {
    el.addEventListener("click", closeUserActivityModal);
  });
  document.getElementById("userActivityLoadMore")?.addEventListener("click", () => loadUserActivityMore());
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    const modal = document.getElementById("userActivityModal");
    if (modal && !modal.classList.contains("hidden")) closeUserActivityModal();
  });
  loadUsers();
});

async function loadUsers() {
  try {
    const res = await fetch("/api/users");
    const data = await Office.parseJson(res);
    if (!res.ok) {
      const hint = data.db_setup ? ` Εκτελέστε: ${data.db_setup}` : "";
      throw new Error((data.error || `HTTP ${res.status}`) + hint);
    }
    usersState = {
      users: data.users || [],
      roles: data.roles || [],
      rolePermissions: data.role_permissions || {},
      permissions: data.permissions || [],
      stores: data.stores || [],
      selected: usersState.selected,
      selectedStoreIds: usersState.selectedStoreIds || new Set(),
      storeQuery: usersState.storeQuery || "",
      permissionQuery: usersState.permissionQuery || "",
    };
    renderRoleOptions();
    renderStoreSuggestions();
    renderUsersList();
    renderPermissionComparison();
    usersState.selectedStoreIds = new Set();
    renderStores();
    renderPermissions([]);
    if (usersState.selected) await selectUser(usersState.selected.id);
    else selectUser(null);
  } catch (e) {
    document.getElementById("usersListWrap").innerHTML =
      `<p style="color:var(--err);">${Office.formatMultilineHtml(String(e))}</p>`;
  }
}

function renderRoleOptions() {
  const sel = document.getElementById("userRole");
  sel.innerHTML = usersState.roles
    .map((role) => `<option value="${Office.escapeHtml(role)}">${Office.escapeHtml(role)}</option>`)
    .join("");
}

function renderUsersList() {
  const wrap = document.getElementById("usersListWrap");
  if (!usersState.users.length) {
    wrap.innerHTML = `<p style="color:var(--muted);">Δεν υπάρχουν χρήστες.</p>`;
    return;
  }
  const rows = usersState.users.map((u) => {
    const active = u.is_active ? "Ενεργός" : "Ανενεργός";
    const activeCls = u.is_active ? "ok" : "err";
    const selected = usersState.selected && Number(usersState.selected.id) === Number(u.id);
    const label = Office.escapeHtml(u.username || "");
    const actions =
      `<span class="user-row-actions">` +
      (
        (u.email || "").trim()
          ? (
            `<button type="button" class="user-row-icon-btn" data-resend-user-id="${u.id}" ` +
            `title="Επαναποστολή email επιβεβαίωσης" ` +
            `aria-label="Επαναποστολή email επιβεβαίωσης για ${label}">` +
            `<i class="bi bi-envelope" aria-hidden="true"></i>` +
            `</button>`
          )
          : ""
      ) +
      `<button type="button" class="user-row-icon-btn" data-activity-user-id="${u.id}" ` +
      `title="Καταγραφές ενεργειών" ` +
      `aria-label="Καταγραφές ενεργειών για ${label}">` +
      `<i class="bi bi-journal-text" aria-hidden="true"></i>` +
      `</button>` +
      `<button type="button" class="user-row-icon-btn user-row-icon-btn--danger" data-delete-user-id="${u.id}" ` +
      `title="Διαγραφή χρήστη" ` +
      `aria-label="Διαγραφή χρήστη ${label}">` +
      `<i class="bi bi-trash" aria-hidden="true"></i>` +
      `</button>` +
      `</span>`;
    const emailLine = (u.email || "").trim()
      ? (
        `<span class="user-row-email-line">` +
        `<small>${Office.escapeHtml(u.email)}</small>` +
        `${actions}` +
        `</span>`
      )
      : (
        `<span class="user-row-email-line">` +
        `<small>${Office.escapeHtml(u.full_name || "")}</small>` +
        `${actions}` +
        `</span>`
      );
    return (
      `<div class="user-row${selected ? " is-selected" : ""}" data-user-id="${u.id}" role="button" tabindex="0">` +
      `<span class="user-row-main">` +
      `<strong>${label}</strong>` +
      `${emailLine}` +
      `</span>` +
      `<span class="user-row-meta">` +
      `<code>${Office.escapeHtml(u.role || "")}</code>` +
      `<span class="${activeCls}">${active}</span>` +
      `</span>` +
      `</div>`
    );
  }).join("");
  wrap.innerHTML = `<div class="users-list-items">${rows}</div>`;
  wrap.querySelectorAll("[data-user-id]").forEach((row) => {
    row.addEventListener("click", () => selectUser(Number(row.dataset.userId)));
    row.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      selectUser(Number(row.dataset.userId));
    });
  });
  wrap.querySelectorAll("[data-resend-user-id]").forEach((btn) => {
    btn.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      resendVerificationEmail(Number(btn.dataset.resendUserId), btn);
    });
  });
  wrap.querySelectorAll("[data-activity-user-id]").forEach((btn) => {
    btn.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      openUserActivityModal(Number(btn.dataset.activityUserId));
    });
  });
  wrap.querySelectorAll("[data-delete-user-id]").forEach((btn) => {
    btn.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      deleteUser(Number(btn.dataset.deleteUserId), btn);
    });
  });
}

async function selectUser(id) {
  usersState.selected = null;
  document.getElementById("userId").value = id || "";
  document.getElementById("userFormTitle").textContent = id ? "Επεξεργασία χρήστη" : "Νέος χρήστης";
  document.getElementById("userUsername").disabled = Boolean(id);
  document.getElementById("userUsername").value = "";
  document.getElementById("userEmail").value = "";
  document.getElementById("userFullName").value = "";
  document.getElementById("userPassword").value = "";
  document.getElementById("userActive").checked = true;
  document.getElementById("userRole").value = usersState.roles.includes("viewer") ? "viewer" : (usersState.roles[0] || "");
  usersState.selectedStoreIds = new Set();
  document.getElementById("userStoreSearch").value = "";
  usersState.storeQuery = "";
  renderStores();
  renderPermissions(usersState.rolePermissions[document.getElementById("userRole").value] || []);
  if (!id) return;
  try {
    const res = await fetch(`/api/users/${id}`);
    const user = await Office.parseJson(res);
    if (!res.ok) throw new Error(user.error || `HTTP ${res.status}`);
    usersState.selected = user;
    document.getElementById("userUsername").value = user.username || "";
    document.getElementById("userEmail").value = user.email || "";
    document.getElementById("userFullName").value = user.full_name || "";
    document.getElementById("userActive").checked = Boolean(user.is_active);
    document.getElementById("userRole").value = user.role || "viewer";
    usersState.selectedStoreIds = new Set((user.store_ids || []).map(Number));
    renderUsersList();
    renderStores();
    renderPermissions(user.permissions || []);
  } catch (e) {
    Office.showMsg("usersMsg", String(e), false);
  }
}

function initStoreAutocomplete() {
  userStoreAc = Office.createAutocomplete({
    inputId: "userStoreSearch",
    listId: "userStoreSuggestions",
    hiddenId: "userStoreSearchId",
    maxItems: 50,
    labelFn: (store) => storeOptionText(store),
    onSelect: () => {
      document.querySelector(".users-store-search .ac-wrap.field-err")?.classList.remove("field-err");
    },
  });
  const input = document.getElementById("userStoreSearch");
  if (!input) return;
  const openAll = () => userStoreAc?.openAll(false);
  input.addEventListener("focus", openAll);
  input.addEventListener("click", openAll);
  input.addEventListener("input", () => {
    document.getElementById("userStoreSearchId").value = "";
    input.closest(".ac-wrap")?.classList.remove("field-err");
  });
}

function renderStoreSuggestions() {
  userStoreAc?.setItems(usersState.stores || []);
}

function storeOptionText(store) {
  const name = store.name || String(store.id || "");
  const afm = store.employer_afm ? `ΑΦΜ ${store.employer_afm}` : "ΑΦΜ -";
  return `${name} · ${afm}`;
}

function storeSearchText(store) {
  return [
    store.name,
    store.employer_afm,
    store.branch_aa,
    String(store.employee_count ?? ""),
  ].join(" ");
}

function normalizeSearchText(value) {
  const map = {
    α: "a", β: "v", γ: "g", δ: "d", ε: "e", ζ: "z", η: "i", θ: "th",
    ι: "i", κ: "k", λ: "l", μ: "m", ν: "n", ξ: "x", ο: "o", π: "p",
    ρ: "r", σ: "s", ς: "s", τ: "t", υ: "y", φ: "f", χ: "ch", ψ: "ps", ω: "o",
  };
  return String(value || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[άέήίόύώϊϋΐΰ]/g, (ch) => ({
      ά: "α", έ: "ε", ή: "η", ί: "ι", ό: "ο", ύ: "υ", ώ: "ω",
      ϊ: "ι", ϋ: "υ", ΐ: "ι", ΰ: "υ",
    })[ch] || ch)
    .replace(/[α-ως]/g, (ch) => map[ch] || ch)
    .replace(/\s+/g, " ")
    .trim();
}

function renderStores() {
  const selected = usersState.selectedStoreIds || new Set();
  const wrap = document.getElementById("userStoresWrap");
  if (!usersState.stores.length) {
    wrap.innerHTML = `<p class="table-meta">Δεν υπάρχουν καταστήματα.</p>`;
    return;
  }
  const stores = usersState.stores.filter((store) => selected.has(Number(store.id)));
  if (!stores.length) {
    wrap.innerHTML = `<p class="table-meta">Δεν έχει προστεθεί κατάστημα.</p>`;
    return;
  }
  wrap.innerHTML = stores.map((store) => {
    const id = Number(store.id);
    return (
      `<div class="users-store-row">` +
      `<span class="users-store-name">${Office.escapeHtml(store.name || String(id))}</span>` +
      `<span class="users-store-afm">ΑΦΜ ${Office.escapeHtml(store.employer_afm || "-")}</span>` +
      `<span class="users-store-count">${Number(store.employee_count || 0)} εργαζ.</span>` +
      `<button type="button" class="users-store-remove" data-remove-store-id="${id}" aria-label="Αφαίρεση καταστήματος">` +
      `<i class="bi bi-x-lg" aria-hidden="true"></i>` +
      `</button>` +
      `</div>`
    );
  }).join("");
  wrap.querySelectorAll("[data-remove-store-id]").forEach((button) => {
    button.addEventListener("click", () => {
      usersState.selectedStoreIds.delete(Number(button.dataset.removeStoreId));
      renderStores();
    });
  });
}

function findStoreBySearchValue(value) {
  const rawQuery = String(value || "").trim();
  if (!rawQuery) return null;
  const query = normalizeSearchText(rawQuery);
  return usersState.stores.find((store) => {
    const id = String(store.id || "");
    const exactValues = [
      storeOptionText(store),
      store.name,
      store.employer_afm,
      id,
    ].map((part) => normalizeSearchText(part));
    return exactValues.some((part) => part === query);
  }) || usersState.stores.find((store) => normalizeSearchText(storeSearchText(store)).includes(query));
}

function addStoreFromSearch() {
  const input = document.getElementById("userStoreSearch");
  const pickedId = document.getElementById("userStoreSearchId")?.value || "";
  const store = usersState.stores.find((item) => String(item.id) === String(pickedId))
    || findStoreBySearchValue(input?.value || "");
  if (!store) {
    Office.showMsg("usersMsg", "Δεν βρέθηκε κατάστημα για προσθήκη.", false);
    input?.focus();
    input?.closest(".ac-wrap")?.classList.add("field-err");
    return;
  }
  usersState.selectedStoreIds.add(Number(store.id));
  if (input) {
    input.value = "";
    input.closest(".ac-wrap")?.classList.remove("field-err");
  }
  document.getElementById("userStoreSearchId").value = "";
  usersState.storeQuery = "";
  renderStores();
}

function renderPermissions(selectedCodes) {
  setCheckedPermissions(selectedCodes || []);
}

function setCheckedPermissions(selectedCodes) {
  const selected = new Set(selectedCodes || []);
  const wrap = document.getElementById("userPermissionsWrap");
  wrap.innerHTML = usersState.permissions.map((permission) => (
    `<label class="users-check-row users-permission-row">` +
    `<input type="checkbox" data-permission="${Office.escapeHtml(permission)}" ${selected.has(permission) ? "checked" : ""}>` +
    `<span><code>${Office.escapeHtml(permission)}</code></span>` +
    `</label>`
  )).join("");
}

function userHasPermission(user, permission) {
  const permissions = new Set(user.permissions || []);
  return permissions.has("*") || permissions.has(permission);
}

function roleHasPermission(role, permission) {
  const permissions = new Set(usersState.rolePermissions[role] || []);
  return permissions.has("*") || permissions.has(permission);
}

function permissionInfo(permission) {
  if (permission === "*") return {
    code: permission,
    component: PERMISSION_COMPONENTS["*"].label,
    type: PERMISSION_COMPONENTS["*"].type,
    action: "Πλήρης πρόσβαση",
    description: PERMISSION_COMPONENTS["*"].description,
  };
  const parts = String(permission || "").split(".");
  const componentKey = parts[0] || "";
  const actionKey = parts.slice(1).join(".");
  const component = PERMISSION_COMPONENTS[componentKey] || {
    label: componentKey || "-",
    type: "Λοιπό",
    description: "Τεχνικό component της εφαρμογής.",
  };
  const action = actionKey || "-";
  const actionDescription = PERMISSION_ACTIONS[action] || PERMISSION_ACTIONS[parts[parts.length - 1]] || "Επιτρέπει την αντίστοιχη λειτουργία του component.";
  return {
    code: permission,
    component: component.label,
    type: component.type,
    action,
    description: `${component.description} ${actionDescription}`,
  };
}

function renderPermissionComparison() {
  const wrap = document.getElementById("permissionCompareWrap");
  if (!wrap) return;
  if (!usersState.roles.length) {
    wrap.innerHTML = `<p class="table-meta">Δεν υπάρχουν ρόλοι.</p>`;
    return;
  }
  const query = normalizeSearchText(usersState.permissionQuery || "");
  const permissions = (usersState.permissions || [])
    .map((permission) => permissionInfo(permission))
    .filter((permission) => (
      !query || normalizeSearchText([
        permission.code,
        permission.type,
        permission.component,
        permission.action,
        permission.description,
      ].join(" ")).includes(query)
    ));
  if (!permissions.length) {
    wrap.innerHTML = `<p class="table-meta">Δεν βρέθηκε δικαίωμα.</p>`;
    return;
  }
  const roleHead = (usersState.roles || []).map((role) => (
    `<th scope="col" class="users-permission-role-head" title="${Office.escapeHtml(role)}">` +
    `<span class="users-matrix-user">${Office.escapeHtml(ROLE_LABELS[role] || role)}</span>` +
    `<small>ρόλος</small>` +
    `</th>`
  )).join("");
  const rows = permissions.map((permission) => {
    const tooltip = `${permission.component}\n${permission.description}\nΚωδικός: ${permission.code}`;
    const roleCells = (usersState.roles || []).map((role) => {
      const hasPermission = roleHasPermission(role, permission.code);
      return (
        `<td class="users-permission-cell users-permission-role-cell ${hasPermission ? "has-permission" : "no-permission"}">` +
        `${hasPermission ? "✓" : "-"}` +
        `</td>`
      );
    }).join("");
    return (
      `<tr>` +
      `<th scope="row"><span class="users-permission-type">${Office.escapeHtml(permission.type)}</span></th>` +
      `<td class="users-permission-action" title="${Office.escapeHtml(tooltip)}">` +
      `<code>${Office.escapeHtml(permission.action)}</code>` +
      `</td>` +
      roleCells +
      `</tr>`
    );
  }).join("");
  wrap.innerHTML = (
    `<table class="users-permission-matrix">` +
    `<thead><tr>` +
    `<th scope="col">Τύπος</th>` +
    `<th scope="col">Ενέργεια</th>` +
    `${roleHead}</tr></thead>` +
    `<tbody>${rows}</tbody>` +
    `</table>`
  );
}

function checkedStores() {
  return Array.from(usersState.selectedStoreIds || []);
}

function checkedPermissions() {
  return Array.from(document.querySelectorAll("#userPermissionsWrap [data-permission]:checked"))
    .map((el) => el.dataset.permission);
}

function applyRoleTemplate() {
  const role = document.getElementById("userRole").value;
  setCheckedPermissions(usersState.rolePermissions[role] || []);
}

function upsertUser(user) {
  if (!user || !user.id) return;
  const id = Number(user.id);
  const idx = usersState.users.findIndex((item) => Number(item.id) === id);
  if (idx >= 0) usersState.users[idx] = user;
  else usersState.users.push(user);
}

function applySavedUser(user) {
  if (!user || !user.id) return;
  upsertUser(user);
  usersState.selected = user;
  document.getElementById("userId").value = user.id;
  document.getElementById("userFormTitle").textContent = "Επεξεργασία χρήστη";
  document.getElementById("userUsername").disabled = true;
  document.getElementById("userUsername").value = user.username || "";
  document.getElementById("userEmail").value = user.email || "";
  document.getElementById("userFullName").value = user.full_name || "";
  document.getElementById("userPassword").value = "";
  document.getElementById("userActive").checked = Boolean(user.is_active);
  document.getElementById("userRole").value = user.role || "viewer";
  usersState.selectedStoreIds = new Set((user.store_ids || []).map(Number));
  renderUsersList();
  renderStores();
  renderPermissions(user.permissions || []);
  renderPermissionComparison();
}

async function saveUser() {
  const saveBtn = document.getElementById("btnSaveUser");
  const id = document.getElementById("userId").value;
  const payload = {
    username: document.getElementById("userUsername").value.trim(),
    email: document.getElementById("userEmail").value.trim(),
    full_name: document.getElementById("userFullName").value.trim(),
    role: document.getElementById("userRole").value,
    password: document.getElementById("userPassword").value,
    is_active: document.getElementById("userActive").checked,
    permissions: checkedPermissions(),
    store_ids: checkedStores(),
  };
  if (!id && !payload.password) {
    Office.showMsg("usersMsg", "Συμπληρώστε password για νέο χρήστη.", false);
    return;
  }
  if (!id && (!payload.email || !payload.email.includes("@"))) {
    Office.showMsg("usersMsg", "Συμπληρώστε έγκυρο email για επιβεβαίωση λογαριασμού.", false);
    document.getElementById("userEmail")?.focus();
    return;
  }
  if (payload.role !== "super_admin" && !payload.store_ids.length) {
    Office.showMsg("usersMsg", "Επιλέξτε τουλάχιστον ένα κατάστημα για τον χρήστη.", false);
    document.getElementById("userStoreSearch")?.focus();
    return;
  }
  Office.setButtonLoading(saveBtn, true);
  Office.showMsg("usersMsg", "Αποθήκευση…", true);
  try {
    const res = await fetch(id ? `/api/users/${id}` : "/api/users", {
      method: id ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await Office.parseJson(res);
    if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
    applySavedUser(data.user || { ...payload, id: Number(id || data.id) });
    Office.showMsg(
      "usersMsg",
      data.email_warning ? `Αποθηκεύτηκε, αλλά ${data.email_warning}` : "Αποθηκεύτηκε.",
      !data.email_warning
    );
  } catch (e) {
    Office.showMsg("usersMsg", String(e), false);
  } finally {
    Office.setButtonLoading(saveBtn, false);
  }
}

async function resendVerificationEmail(userId, btn) {
  Office.setButtonLoading(btn, true);
  Office.showMsg("usersMsg", "Αποστολή email…", true);
  try {
    const res = await fetch(`/api/users/${userId}/resend-verification-email`, { method: "POST" });
    const data = await Office.parseJson(res);
    if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
    Office.showMsg("usersMsg", data.message || "Στάλθηκε email επιβεβαίωσης.", true);
  } catch (e) {
    Office.showMsg("usersMsg", String(e), false);
  } finally {
    Office.setButtonLoading(btn, false);
  }
}

async function resetPassword() {
  const id = document.getElementById("userId").value;
  const password = document.getElementById("userPassword").value;
  if (!id) {
    Office.showMsg("usersMsg", "Επιλέξτε υπάρχοντα χρήστη.", false);
    return;
  }
  if (!password) {
    Office.showMsg("usersMsg", "Συμπληρώστε νέο password.", false);
    return;
  }
  try {
    const res = await fetch(`/api/users/${id}/password`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    const data = await Office.parseJson(res);
    if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
    document.getElementById("userPassword").value = "";
    Office.showMsg("usersMsg", "Το password άλλαξε.", true);
  } catch (e) {
    Office.showMsg("usersMsg", String(e), false);
  }
}

function formatActivityWhen(value) {
  if (!value) return "—";
  const text = String(value);
  return text.replace("T", " ").replace(/\.\d+/, "").slice(0, 19);
}

function userActivityLabel(row) {
  const action = String(row.action || "");
  const details = row.details || {};
  const reason = String(details.reason || "");
  if (action === "auth.login_success") return "Σύνδεση";
  if (action === "auth.logout") return "Αποσύνδεση";
  if (action === "auth.login_failed") {
    if (reason === "missing_credentials") return "Αποτυχημένη σύνδεση · λείπουν στοιχεία";
    if (reason === "invalid_credentials") return "Αποτυχημένη σύνδεση · λάθος στοιχεία";
    return "Αποτυχημένη σύνδεση";
  }
  if (action === "auth.terms_accepted") return "Αποδοχή όρων";
  if (action === "auth.password_changed") return "Αλλαγή κωδικού";
  if (action === "auth.password_reset_requested") return "Αίτημα επαναφοράς κωδικού";
  if (action === "auth.password_reset_completed") return "Ολοκλήρωση επαναφοράς κωδικού";
  if (action === "auth.password_reset_failed") return "Αποτυχία επαναφοράς κωδικού";
  if (action === "users.deleted") return "Διαγραφή χρήστη";
  return action || "Ενέργεια";
}

function userActivityExtra(row) {
  const details = row.details || {};
  const bits = [];
  if (details.terms_version) bits.push(`Έκδοση όρων: ${details.terms_version}`);
  if (details.reason) bits.push(`Λόγος: ${details.reason}`);
  if (row.http_status) bits.push(`HTTP ${row.http_status}`);
  if (row.request_path && !String(row.action || "").startsWith("auth.")) {
    bits.push(row.request_path);
  }
  return bits.join(" · ");
}

let userActivityState = {
  userId: null,
  nextBeforeId: null,
  hasMore: false,
  loading: false,
};

function closeUserActivityModal() {
  const modal = document.getElementById("userActivityModal");
  modal?.classList.add("hidden");
  userActivityState = { userId: null, nextBeforeId: null, hasMore: false, loading: false };
}

async function openUserActivityModal(userId) {
  const modal = document.getElementById("userActivityModal");
  const wrap = document.getElementById("userActivityRows");
  const sub = document.getElementById("userActivitySub");
  const moreBtn = document.getElementById("userActivityLoadMore");
  if (!modal || !wrap) return;
  userActivityState = { userId, nextBeforeId: null, hasMore: false, loading: false };
  wrap.innerHTML = `<p style="color:var(--muted);">Φόρτωση…</p>`;
  if (sub) sub.textContent = "";
  if (moreBtn) moreBtn.classList.add("hidden");
  modal.classList.remove("hidden");
  await loadUserActivity(true);
}

async function loadUserActivityMore() {
  await loadUserActivity(false);
}

async function loadUserActivity(reset) {
  const userId = userActivityState.userId;
  const wrap = document.getElementById("userActivityRows");
  const sub = document.getElementById("userActivitySub");
  const moreBtn = document.getElementById("userActivityLoadMore");
  if (!userId || !wrap || userActivityState.loading) return;
  userActivityState.loading = true;
  if (moreBtn) moreBtn.disabled = true;
  try {
    const qs = new URLSearchParams({ limit: "50" });
    if (!reset && userActivityState.nextBeforeId != null) {
      qs.set("before_id", String(userActivityState.nextBeforeId));
    }
    const res = await fetch(`/api/users/${userId}/activity?${qs}`);
    const data = await Office.parseJson(res);
    if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
    const user = data.user || {};
    if (sub) {
      const termsBits = [];
      if (user.terms_accepted_at) {
        termsBits.push(`Όροι: ${formatActivityWhen(user.terms_accepted_at)}`);
        if (user.terms_accepted_ip) termsBits.push(`IP ${user.terms_accepted_ip}`);
        if (user.terms_version) termsBits.push(user.terms_version);
      } else {
        termsBits.push("Όροι: δεν έχουν αποδεχτεί");
      }
      sub.textContent = `${user.username || ""}${user.email ? ` · ${user.email}` : ""} · ${termsBits.join(" · ")}`;
    }
    const rows = data.rows || [];
    const html = rows.map((row) => {
      const ok = row.success === true || row.success === 1;
      const fail = row.success === false || row.success === 0;
      const statusCls = ok ? "ok" : (fail ? "err" : "");
      const extra = userActivityExtra(row);
      return (
        `<div class="user-activity-row">` +
        `<div class="user-activity-when">${Office.escapeHtml(formatActivityWhen(row.created_at))}</div>` +
        `<div class="user-activity-main">` +
        `<strong class="${statusCls}">${Office.escapeHtml(userActivityLabel(row))}</strong>` +
        (extra ? `<small>${Office.escapeHtml(extra)}</small>` : "") +
        `</div>` +
        `<div class="user-activity-ip">` +
        `<code>${Office.escapeHtml(row.client_ip || "—")}</code>` +
        (row.client_device ? `<small title="${Office.escapeHtml(row.client_device)}">${Office.escapeHtml(String(row.client_device).slice(0, 48))}</small>` : "") +
        `</div>` +
        `</div>`
      );
    }).join("");
    if (reset) {
      wrap.innerHTML = html || `<p style="color:var(--muted);">Δεν υπάρχουν καταγεγραμμένες ενέργειες.</p>`;
    } else if (html) {
      wrap.insertAdjacentHTML("beforeend", html);
    }
    userActivityState.hasMore = Boolean(data.has_more);
    userActivityState.nextBeforeId = data.next_before_id ?? null;
    if (moreBtn) {
      moreBtn.classList.toggle("hidden", !userActivityState.hasMore);
      moreBtn.disabled = false;
    }
  } catch (e) {
    if (reset) wrap.innerHTML = `<p style="color:var(--err);">${Office.formatMultilineHtml(String(e))}</p>`;
    else Office.showMsg("usersMsg", String(e), false);
    if (moreBtn) moreBtn.disabled = false;
  } finally {
    userActivityState.loading = false;
  }
}

async function deleteUser(userId, btn) {
  const user = (usersState.users || []).find((u) => Number(u.id) === Number(userId));
  const name = user?.username || `#${userId}`;
  if (!window.confirm(
    `Οριστική διαγραφή του χρήστη «${name}»;\n\nΘα διαγραφούν ρόλος, δικαιώματα, πρόσβαση σε καταστήματα και όλες οι καταγεγραμμένες ενέργειές του.`
  )) {
    return;
  }
  if (btn) btn.disabled = true;
  Office.showMsg("usersMsg", "Διαγραφή…", true);
  try {
    const res = await fetch(`/api/users/${userId}`, { method: "DELETE" });
    const data = await Office.parseJson(res);
    if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
    if (usersState.selected && Number(usersState.selected.id) === Number(userId)) {
      usersState.selected = null;
    }
    Office.showMsg("usersMsg", `Ο χρήστης «${name}» διαγράφηκε.`, true);
    await loadUsers();
  } catch (e) {
    Office.showMsg("usersMsg", String(e), false);
    if (btn) btn.disabled = false;
  }
}
