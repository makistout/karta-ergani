const BRANCH_DETAIL_FIELDS = [
  { key: "aa", label: "Α/Α Παραρτήματος" },
  { key: "address", label: "Διεύθυνση" },
  { key: "ypiresia_sepe", label: "Υπηρεσία ΣΕΠΕ" },
  { key: "ypiresia_oaed", label: "Υπηρεσία ΟΑΕΔ" },
  { key: "kad", label: "ΚΑΔ" },
  { key: "kallikratis", label: "Καλλικράτης" },
  { key: "status_description", label: "Κατάσταση" },
];

function renderBranchDetails(branch) {
  const dl = document.getElementById("branchDetails");
  dl.innerHTML = "";
  if (!branch) {
    return;
  }
  BRANCH_DETAIL_FIELDS.forEach(({ key, label }) => {
    const val = (branch[key] || "").trim();
    if (!val) {
      return;
    }
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.textContent = val;
    dl.appendChild(dt);
    dl.appendChild(dd);
  });
}

function branchMappingPatch(branch) {
  if (!branch) {
    return {};
  }
  const patch = { branch_aa: String(branch.aa ?? "0") };
  if (branch.ypiresia_sepe) patch.sepe_code = branch.ypiresia_sepe;
  if (branch.ypiresia_oaed) patch.oaed_code = branch.ypiresia_oaed;
  if (branch.kad) patch.kad_code = branch.kad;
  if (branch.kallikratis) patch.kallikratis_code = branch.kallikratis;
  return patch;
}

function getSelectedBranch(draft) {
  const branches = draft.branches || [];
  if (!branches.length) {
    return null;
  }
  const sel = document.getElementById("branchSelect");
  const pickerVisible = !document.getElementById("branchPickerWrap").classList.contains("hidden");
  if (pickerVisible && sel.value !== "") {
    return branches.find((b) => String(b.aa) === String(sel.value)) || branches[0];
  }
  return branches[0];
}

function initBranchStep(draft) {
  const branches = draft.branches || [];
  const pickerWrap = document.getElementById("branchPickerWrap");
  const sel = document.getElementById("branchSelect");

  if (branches.length > 1) {
    pickerWrap.classList.remove("hidden");
    sel.innerHTML = "";
    branches.forEach((b) => {
      const opt = document.createElement("option");
      opt.value = b.aa;
      const addr = (b.address || b.description || "").trim();
      opt.textContent = addr ? `${b.aa} — ${addr}` : String(b.aa);
      sel.appendChild(opt);
    });
    if (draft.branch_aa !== undefined && draft.branch_aa !== null && draft.branch_aa !== "") {
      sel.value = String(draft.branch_aa);
    }
    sel.onchange = () => renderBranchDetails(getSelectedBranch(draft));
  } else {
    pickerWrap.classList.add("hidden");
  }

  renderBranchDetails(getSelectedBranch(draft));
}

document.addEventListener("DOMContentLoaded", () => {
  Office.setActiveNav("stores");
  const draft = Office.getDraft();
  if (!draft.accessToken || !draft.branches) {
    window.location.href = "/ui/stores/credentials";
    return;
  }
  document.getElementById("employerHint").textContent =
    `ΑΦΜ εργοδότη: ${draft.employer_afm || "—"} · Σημείο: ${draft.name || "—"}`;
  initBranchStep(draft);
  document.getElementById("btnStep2Next").onclick = onStep2Next;
});

function onStep2Next() {
  const draft = Office.getDraft();
  const branch = getSelectedBranch(draft);
  if (!branch) {
    Office.showMsg("stepMsg", "Δεν βρέθηκαν στοιχεία παραρτήματος από EX_BASE_02.", false);
    return;
  }
  Office.setDraft({ ...draft, ...branchMappingPatch(branch) });
  window.location.href = "/ui/stores/mappings";
}
