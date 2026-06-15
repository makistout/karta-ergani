document.addEventListener("DOMContentLoaded", async () => {
  Office.setActiveNav("worklog");
  await Office.loadActiveStore();

  const params = new URLSearchParams(window.location.search);
  const afm = (params.get("employee_afm") || params.get("afm") || "").trim();
  const name = (params.get("employee_name") || "").trim();
  const from = (params.get("from") || "").trim();

  const backWrap = document.getElementById("workLogHistoryBackWrap");
  const backLink = document.getElementById("workLogHistoryBack");
  if (from === "work-card" && backWrap && backLink) {
    backWrap.classList.remove("hidden");
    const returnUrl = new URLSearchParams();
    if (afm) returnUrl.set("employee_afm", afm);
    if (name) returnUrl.set("employee_name", name);
    const qs = returnUrl.toString();
    backLink.href = qs ? `/ui/work-card?${qs}` : "/ui/work-card";
  }

  const wrap = document.getElementById("workLogHistoryPageWrap");
  const sub = document.getElementById("workLogHistoryPageEmployee");
  if (!afm) {
    if (wrap) {
      wrap.innerHTML =
        '<p style="color:var(--err);">Λείπει <code>employee_afm</code> στο URL.</p>';
    }
    return;
  }

  await Office.loadWorkLogHistory({ wrap, sub, afm, name });
});
