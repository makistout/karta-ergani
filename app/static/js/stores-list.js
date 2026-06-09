document.addEventListener("DOMContentLoaded", () => {
  Office.setActiveNav("stores");
  document.getElementById("btnNewStore")?.addEventListener("click", (e) => {
    Office.clearDraft();
  });
  loadStoresList();
});

async function loadStoresList() {
  const wrap = document.getElementById("storesListWrap");
  if (!wrap) return;
  try {
    const res = await fetch("/api/store/list");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const stores = await res.json();
    if (!stores.length) {
      wrap.innerHTML =
        "<p style='color:var(--muted);'>Δεν υπάρχουν καταστήματα. Πατήστε «Νέο κατάστημα».</p>";
      return;
    }
    const t = document.createElement("table");
    t.className = "data";
    const hr = document.createElement("tr");
    ["Όνομα", "API", "ΑΦΜ", "Παράρτημα", "ΚΑΔ / ΤΕΕΣ / ΟΑΕΔ", "Ενέργειες"].forEach((h) => {
      const th = document.createElement("th");
      th.textContent = h;
      hr.appendChild(th);
    });
    t.appendChild(hr);
    stores.forEach((store) => {
      const tr = document.createElement("tr");
      const tdName = document.createElement("td");
      tdName.innerHTML =
        `<strong>${Office.escapeHtml(store.name)}</strong><br>` +
        `<span style="font-size:0.75rem;color:var(--muted);">${Office.escapeHtml(store.username)}</span>`;
      tr.appendChild(tdName);
      const tdEnv = document.createElement("td");
      const env = (store.ergani_env || "production").toLowerCase();
      const envLabel = env === "trial" ? "Δοκιμαστικό" : "Παραγωγή";
      tdEnv.innerHTML = `<span class="env-badge env-${env}">${Office.escapeHtml(envLabel)}</span>`;
      tr.appendChild(tdEnv);
      const tdAfm = document.createElement("td");
      tdAfm.textContent = store.employer_afm || "";
      tr.appendChild(tdAfm);
      const tdAa = document.createElement("td");
      tdAa.textContent = store.branch_aa || "0";
      tr.appendChild(tdAa);
      const tdDet = document.createElement("td");
      tdDet.style.fontSize = "0.75rem";
      tdDet.style.color = "var(--muted)";
      tdDet.innerHTML =
        `<span class="meta-line">${Office.icon("tag")}<span>KAD: ${Office.escapeHtml(store.kad_code || "-")}</span></span>` +
        `<span class="meta-line">${Office.icon("building")}<span>ΤΕΕΣ: ${Office.escapeHtml(store.sepe_code || "-")}</span></span>` +
        `<span class="meta-line">${Office.icon("people")}<span>ΟΑΕΔ: ${Office.escapeHtml(store.oaed_code || "-")}</span></span>`;
      tr.appendChild(tdDet);
      const tdAct = document.createElement("td");
      tdAct.className = "table-actions";
      tdAct.appendChild(mkBtn("Επιλογή", "btn btn-select btn-sm", "check-circle", () => selectStore(store.id)));
      tdAct.appendChild(mkBtn("Επεξεργασία", "btn btn-sm", "pencil-square", () => editStore(store.id)));
      tdAct.appendChild(mkBtn("Διαγραφή", "btn btn-danger btn-sm", "trash3", () => deleteStore(store.id)));
      tr.appendChild(tdAct);
      t.appendChild(tr);
    });
    wrap.innerHTML = "";
    wrap.appendChild(t);
  } catch (e) {
    wrap.innerHTML = `<p style="color:var(--err);">Σφάλμα: ${Office.escapeHtml(String(e))}</p>`;
  }
}

function mkBtn(label, cls, iconName, fn) {
  const b = document.createElement("button");
  b.className = cls;
  b.innerHTML = `${Office.icon(iconName)}<span>${label}</span>`;
  b.onclick = fn;
  return b;
}

async function selectStore(id) {
  Office.showLoading("listMsg", "Επιλογή και συγχρονισμός Ergani… Παρακαλώ περιμένετε.");
  try {
    const res = await fetch("/api/store/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    });
    const data = await res.json();
    if (res.ok && data.success) {
      const emp = data.sync?.sync_results?.employees;
      let msg = `Ενεργό: ${data.store.name}`;
      const sched = data.sync?.sync_results?.schedule;
      if (emp?.success) {
        msg += ` — ${emp.count ?? 0} εργαζόμενοι`;
      }
      if (sched?.success) {
        msg += `, ${sched.count ?? 0} ωράριο`;
      }
      const wl = data.sync?.sync_results?.work_log;
      if (wl?.success) {
        msg += `, ${wl.count ?? 0} πραγμ. απασχόληση`;
      }
      if (!emp?.success && emp?.detail) {
        msg += ` — προειδοποίηση: ${emp.detail}`;
      }
      Office.showMsg("listMsg", msg, Boolean(emp?.success ?? true));
      await Office.loadActiveStore();
    } else {
      Office.showMsg("listMsg", data.error || "Αποτυχία επιλογής", false);
    }
  } catch (e) {
    Office.showMsg("listMsg", String(e), false);
  }
}

async function editStore(id) {
  try {
    const res = await fetch(`/api/store/${id}`);
    const store = await res.json();
    if (!res.ok) {
      Office.showMsg("listMsg", store.error || "Σφάλμα", false);
      return;
    }
    Office.setDraft({
      id: store.id,
      name: store.name,
      username: store.username,
      password: store.password || "",
      usertype: store.usertype || "01",
      web_username: store.web_username || "",
      web_password: store.web_password || "",
      ergani_env: store.ergani_env || "production",
      employer_afm: store.employer_afm,
      branch_aa: store.branch_aa,
      sepe_code: store.sepe_code,
      sepe_desc: store.sepe_desc,
      oaed_code: store.oaed_code,
      oaed_desc: store.oaed_desc,
      kad_code: store.kad_code,
      kad_desc: store.kad_desc,
      kallikratis_code: store.kallikratis_code,
      kallikratis_desc: store.kallikratis_desc,
      accessToken: "",
      branches: null,
    });
    window.location.href = "/ui/stores/credentials?edit=1";
  } catch (e) {
    Office.showMsg("listMsg", String(e), false);
  }
}

async function deleteStore(id) {
  if (!confirm("Διαγραφή καταστήματος;")) return;
  try {
    const res = await fetch(`/api/store/${id}`, { method: "DELETE" });
    if (res.ok) {
      Office.showMsg("listMsg", "Διαγράφηκε.", true);
      await Office.loadActiveStore();
      loadStoresList();
    } else {
      const data = await res.json();
      Office.showMsg("listMsg", data.error || "Αποτυχία", false);
    }
  } catch (e) {
    Office.showMsg("listMsg", String(e), false);
  }
}
