const MASKED = "********";

document.addEventListener("DOMContentLoaded", async () => {
  Office.setActiveNav("stores");
  const params = new URLSearchParams(location.search);
  const draft = Office.getDraft();
  if (params.get("edit") === "1" && draft.id) {
    document.querySelector(".page-title").textContent = "Επεξεργασία καταστήματος";
    await loadStoreIntoForm(draft.id);
  } else {
    fillFormFromDraft(draft);
  }
  document.getElementById("btnStep1Next").onclick = onStep1Next;
  document.getElementById("btnSaveSyncSettings")?.addEventListener("click", saveSyncSettingsOnly);
  if (params.get("edit") === "1" && draft.id) {
    document.getElementById("btnSaveSyncSettings")?.classList.remove("hidden");
  }
});

function cleanSecret(value) {
  const s = (value || "").trim();
  return s === MASKED ? "" : s;
}

function readSyncIntervalMinutes() {
  const raw = parseInt(document.getElementById("workLogSyncInterval")?.value || "30", 10);
  if (!Number.isFinite(raw)) return 30;
  return Math.max(5, Math.min(raw, 24 * 60));
}

function fillFormFromDraft(draft) {
  document.getElementById("storeName").value = draft.name || "";
  document.getElementById("storeAdminUser").value = draft.username || "";
  document.getElementById("storeAdminPass").value = cleanSecret(draft.password);
  document.getElementById("storeAdminUtype").value = draft.usertype || "01";
  document.getElementById("storeWebUser").value = draft.web_username || "";
  document.getElementById("storeWebPass").value = cleanSecret(draft.web_password);
  document.getElementById("storeEnv").value = draft.ergani_env || "production";
  const intervalEl = document.getElementById("workLogSyncInterval");
  if (intervalEl) {
    intervalEl.value = String(draft.work_log_sync_interval_minutes || 30);
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
    Office.setDraft({ ...Office.getDraft(), ...store, accessToken: "", branches: null });
    document.getElementById("btnSaveSyncSettings")?.classList.remove("hidden");
  } catch (e) {
    Office.showMsg("stepMsg", String(e), false);
  }
}

async function saveSyncSettingsOnly() {
  const draft = Office.getDraft();
  if (!draft.id) {
    Office.showMsg("stepMsg", "Αποθηκεύστε πρώτα το κατάστημα.", false);
    return;
  }
  const btn = document.getElementById("btnSaveSyncSettings");
  const mins = readSyncIntervalMinutes();
  Office.setButtonLoading(btn, true);
  try {
    const res = await fetch(`/api/store/${draft.id}/sync-settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ work_log_sync_interval_minutes: mins }),
    });
    const data = await Office.parseJson(res);
    if (!res.ok || !data.success) {
      Office.showMsg("stepMsg", data.error || "Αποτυχία αποθήκευσης", false);
      return;
    }
    Office.setDraft({
      ...draft,
      work_log_sync_interval_minutes: data.work_log_sync_interval_minutes || mins,
    });
    if (document.getElementById("workLogSyncInterval")) {
      document.getElementById("workLogSyncInterval").value = String(
        data.work_log_sync_interval_minutes || mins
      );
    }
    Office.showMsg(
      "stepMsg",
      `Αποθηκεύτηκε διάστημα auto-sync: ${data.work_log_sync_interval_minutes || mins} λεπτά.`,
      true
    );
  } catch (e) {
    Office.showMsg("stepMsg", String(e), false);
  } finally {
    Office.setButtonLoading(btn, false);
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
    const work_log_sync_interval_minutes = readSyncIntervalMinutes();
    if (storeId) {
      try {
        await fetch(`/api/store/${storeId}/sync-settings`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ work_log_sync_interval_minutes }),
        });
      } catch {
        /* draft κρατά την τιμή για τελική αποθήκευση */
      }
    }
    Office.setDraft({
      ...draft,
      id: storeId,
      ...fields,
      ergani_env,
      work_log_sync_interval_minutes,
      accessToken: token,
      employer_afm,
      branches: branchesData.branches || [],
    });
    window.location.href = "/ui/stores/branch";
  } catch (e) {
    Office.showMsg("stepMsg", String(e), false);
  } finally {
    btn.disabled = false;
  }
}
