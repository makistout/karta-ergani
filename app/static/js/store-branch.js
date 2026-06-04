document.addEventListener("DOMContentLoaded", () => {
  Office.setActiveNav("stores");
  const draft = Office.getDraft();
  if (!draft.accessToken || !draft.branches) {
    window.location.href = "/ui/stores/credentials";
    return;
  }
  document.getElementById("employerHint").textContent =
    `ΑΦΜ εργοδότη: ${draft.employer_afm || "—"} · Σημείο: ${draft.name || "—"}`;
  const sel = document.getElementById("branchSelect");
  sel.innerHTML = "";
  (draft.branches || []).forEach((b) => {
    const opt = document.createElement("option");
    opt.value = b.aa;
    opt.textContent = `${b.aa} — ${b.description}`;
    sel.appendChild(opt);
  });
  if (draft.branch_aa) {
    sel.value = String(draft.branch_aa);
  }
  document.getElementById("btnStep2Next").onclick = onStep2Next;
});

function onStep2Next() {
  const branch_aa = document.getElementById("branchSelect").value;
  const draft = Office.getDraft();
  Office.setDraft({ ...draft, branch_aa });
  window.location.href = "/ui/stores/mappings";
}
