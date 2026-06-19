document.addEventListener("DOMContentLoaded", async () => {
  Office.setActiveNav("worklog");
  await Office.loadActiveStore();

  const params = new URLSearchParams(window.location.search);
  const afm = (params.get("employee_afm") || params.get("afm") || "").trim();
  const name = (params.get("employee_name") || "").trim();
  const from = (params.get("from") || "").trim();

  configureWorkLogHistoryBack(from, afm, name);

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

function configureWorkLogHistoryBack(from, afm, name) {
  const btn = document.querySelector("main.main .page-back-btn");
  if (!btn) return;

  const workCardUrl = () => {
    const p = new URLSearchParams();
    if (afm) p.set("employee_afm", afm);
    if (name) p.set("employee_name", name);
    const qs = p.toString();
    return qs ? `/ui/work-card?${qs}` : "/ui/work-card";
  };

  const routes = {
    employees: {
      href: "/ui/employees",
      label: "Πίσω στους εργαζομένους",
    },
    "work-card": {
      href: workCardUrl(),
      label: "Πίσω στην ψηφιακή κάρτα",
    },
    worklog: {
      href: "/ui/work-log",
      label: "Πίσω στην πραγματική απασχόληση",
    },
  };

  const route = routes[from];
  if (route) {
    btn.title = route.label;
    btn.setAttribute("aria-label", route.label);
    btn.onclick = () => {
      window.location.href = route.href;
    };
  }
}
