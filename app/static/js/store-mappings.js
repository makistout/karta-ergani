let catalogsLoaded = false;
let acSepe = null;
let acOaed = null;
let acKad = null;
let acKallikratis = null;

document.addEventListener("DOMContentLoaded", () => {
  Office.setActiveNav("stores");
  const draft = Office.getDraft();
  if (!draft.accessToken) {
    window.location.href = "/ui/stores/credentials";
    return;
  }
  if (!draft.branch_aa && draft.branch_aa !== "0") {
    window.location.href = "/ui/stores/branch";
    return;
  }

  acSepe = Office.createAutocomplete({ inputId: "sepeInput", listId: "sepeList", hiddenId: "sepeCode", maxItems: 40 });
  acOaed = Office.createAutocomplete({ inputId: "oaedInput", listId: "oaedList", hiddenId: "oaedCode", maxItems: 40 });
  acKad = Office.createAutocomplete({ inputId: "kadInput", listId: "kadList", hiddenId: "kadCode", maxItems: 40 });
  acKallikratis = Office.createAutocomplete({
    inputId: "kallikratisInput",
    listId: "kallikratisList",
    hiddenId: "kallikratisCode",
    minChars: 2,
    maxItems: 15,
    labelFn: (row) => row.label || `${row.code} — ${row.name_local || ""}`,
    searchFn: async (q) => {
      const res = await fetch(
        `/api/ergani/kallikratis/search?q=${encodeURIComponent(q)}&limit=15`
      );
      const data = await res.json();
      return (data.results || []).map((row) => ({
        value: row.code,
        code: row.code,
        label: row.label,
        description: row.municipality_name || row.name_local || "",
      }));
    },
  });

  loadCatalogs();
  document.getElementById("btnSaveStore").onclick = onSave;
});

async function loadCatalogs() {
  const draft = Office.getDraft();
  const token = draft.accessToken;
  Office.showMsg("stepMsg", "Φόρτωση καταλόγων EX_BASE_03…", true);
  try {
    const [sepe, oaed, kad] = await Promise.all([
      fetchCatalog("sepe", token),
      fetchCatalog("oaed", token),
      fetchCatalog("kad", token),
    ]);
    acSepe.setItems(sepe);
    acOaed.setItems(oaed);
    acKad.setItems(kad);
    if (draft.sepe_code) acSepe.setValue(draft.sepe_code, draft.sepe_desc);
    if (draft.oaed_code) acOaed.setValue(draft.oaed_code, draft.oaed_desc);
    if (draft.kad_code) acKad.setValue(draft.kad_code, draft.kad_desc);
    if (draft.kallikratis_code) {
      acKallikratis.setValue(draft.kallikratis_code, draft.kallikratis_desc);
      document.getElementById("kallikratisInput").value = draft.kallikratis_desc || draft.kallikratis_code;
      document.getElementById("kallikratisCode").value = draft.kallikratis_code;
    }
    catalogsLoaded = true;
    document.getElementById("stepMsg").classList.remove("show");
  } catch (e) {
    Office.showMsg("stepMsg", String(e), false);
  }
}

async function fetchCatalog(type, token) {
  const draft = Office.getDraft();
  const res = await fetch(`/api/ergani/catalog/${type}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      "X-Ergani-Env": draft.ergani_env || "production",
    },
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `Κατάλογος ${type}`);
  return data.items || [];
}

async function onSave() {
  if (!catalogsLoaded) {
    Office.showMsg("stepMsg", "Περιμένετε φόρτωση καταλόγων.", false);
    return;
  }
  const draft = Office.getDraft();
  const wasNew = Boolean(draft.wizard_is_new);
  const sepe = acSepe.getValue();
  const oaed = acOaed.getValue();
  const kad = acKad.getValue();
  const kall = acKallikratis.getValue();

  if (!sepe.code || !oaed.code || !kad.code) {
    Office.showMsg("stepMsg", "Επιλέξτε ΤΕΕΣ, ΟΑΕΔ και ΚΑΔ από τη λίστα (↑/↓ + Tab ή Enter).", false);
    return;
  }

  const payload = {
    id: draft.id || undefined,
    name: draft.name,
    username: draft.username,
    password: draft.password,
    usertype: draft.usertype || "01",
    web_username: draft.web_username || null,
    web_password: draft.web_password || null,
    ergani_env: draft.ergani_env || "production",
    employer_afm: draft.employer_afm,
    branch_aa: draft.branch_aa,
    sepe_code: sepe.code,
    sepe_desc: sepe.label,
    oaed_code: oaed.code,
    oaed_desc: oaed.label,
    kad_code: kad.code,
    kad_desc: kad.label,
    kallikratis_code: kall.code,
    kallikratis_desc: kall.label,
  };
  const btn = document.getElementById("btnSaveStore");
  btn.disabled = true;
  try {
    const res = await fetch("/api/store/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (res.ok && data.success) {
      const storeId = data.id;
      Office.clearDraft();
      if (wasNew && storeId) {
        Office.showMsg(
          "stepMsg",
          "Αποθηκεύτηκε. Επιλογή καταστήματος και συγχρονισμός τελευταίου μήνα…",
          true
        );
        try {
          await activateNewStoreWithMonthSync(storeId);
          Office.showMsg("stepMsg", "Ολοκληρώθηκε. Μετάβαση στην αρχική…", true);
        } catch (syncErr) {
          Office.showMsg(
            "stepMsg",
            `Αποθηκεύτηκε ως ενεργό, αλλά ο συγχρονισμός απέτυχε: ${syncErr}`,
            false
          );
        }
        setTimeout(() => {
          window.location.href = "/ui/home";
        }, 900);
        return;
      }
      Office.showMsg("stepMsg", "Αποθηκεύτηκε. Μετάβαση στη λίστα…", true);
      setTimeout(() => {
        window.location.href = "/ui/stores";
      }, 600);
    } else {
      Office.showMsg("stepMsg", data.error || "Αποτυχία αποθήκευσης", false);
    }
  } catch (e) {
    Office.showMsg("stepMsg", String(e), false);
  } finally {
    btn.disabled = false;
  }
}

function isoDaysAgo(days) {
  const d = new Date();
  d.setDate(d.getDate() - Number(days || 0));
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

async function activateNewStoreWithMonthSync(storeId) {
  Office.invalidateActiveStoreCache();
  Office.showLoading("stepMsg", "Επιλογή νέου καταστήματος…", 0, 2);

  const selectRes = await fetch("/api/store/select", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: storeId }),
  });
  const selectData = await Office.parseJson(selectRes);
  if (!selectRes.ok || !selectData.success) {
    throw new Error(selectData.error || selectData._parseError || "Αποτυχία επιλογής καταστήματος");
  }

  if (selectData.job_id) {
    const selectStatus = `/api/store/select/status/${encodeURIComponent(selectData.job_id)}`;
    const polledSelect = await Office.pollSyncJob(selectStatus, "stepMsg");
    if (!polledSelect.success) {
      throw new Error(polledSelect.error || "Αποτυχία συγχρονισμού μετά την επιλογή");
    }
  }

  await Office.loadActiveStore({ refresh: true });

  const to = Office.todayIsoLocal();
  const from = isoDaysAgo(29);
  Office.showLoading(
    "stepMsg",
    `Συγχρονισμός τελευταίου μήνα (${from} → ${to})…`,
    1,
    2
  );

  const periodRes = await fetch("/api/period-sync/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ from, to, async: true }),
  });
  const periodStart = await Office.parseJson(periodRes);
  if (!periodRes.ok || !periodStart.job_id) {
    throw new Error(
      periodStart.error || periodStart._parseError || "Αποτυχία εκκίνησης συγχρονισμού περιόδου"
    );
  }

  const periodStatus = `/api/period-sync/run/status/${encodeURIComponent(periodStart.job_id)}`;
  const polledPeriod = await Office.pollSyncJob(periodStatus, "stepMsg");
  if (!polledPeriod.success) {
    throw new Error(polledPeriod.error || "Αποτυχία συγχρονισμού τελευταίου μήνα");
  }

  await Office.loadActiveStore({ refresh: true });
}
