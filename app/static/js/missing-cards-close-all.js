let closeAllState = {
  plan: [],
  skipped: [],
  running: false,
};

document.addEventListener("DOMContentLoaded", async () => {
  Office.setActiveNav("missingcards");
  const activeData = await Office.fetchActiveStore();
  Office.applyActiveStoreChrome(activeData);
  document.getElementById("closeAllConfirm")?.addEventListener("click", () => {
    runCloseAllPunches().catch((e) => {
      Office.showMsg("closeAllMsg", String(e), false);
    });
  });
  await loadCloseAllPlan();
});

async function loadCloseAllPlan() {
  const wrap = document.getElementById("closeAllPlanWrap");
  const desc = document.getElementById("closeAllDesc");
  const confirmBtn = document.getElementById("closeAllConfirm");
  Office.showTableLoading(wrap);
  try {
    const res = await fetch("/api/work-log/missing-cards/close-all-plan", {
      cache: "no-store",
    });
    const data = await Office.parseJson(res);
    if (!res.ok) {
      wrap.innerHTML = `<p style="color:var(--err);">${Office.escapeHtml(data.error || "Σφάλμα")}</p>`;
      if (desc) desc.textContent = "";
      return;
    }
    const rows = data.work_log || [];
    const summary = Office.summarizeMissingCardCloseAll(rows);
    closeAllState.plan = summary.plan;
    closeAllState.skipped = summary.skipped;

    const storeName = data.store?.name ? Office.escapeHtml(data.store.name) : "";
    const pending = data.total_pending || rows.length;
    const planN = summary.plan.length;
    const skipN = summary.skipped.length;
    let descText = storeName
      ? `${storeName} · ${pending} εκκρεμείς εγγραφές πριν από ${data.exclude_date || "σήμερα"}`
      : `${pending} εκκρεμείς εγγραφές`;
    descText += ` · ${planN} προς υποβολή (ταξινόμηση: παλαιότερες πρώτα)`;
    if (skipN) descText += ` · ${skipN} εκτός`;
    if (data.truncated) {
      descText += ` · προειδοποίηση: εμφανίζονται οι πρώτες ${rows.length} από ${pending}`;
    }
    if (desc) desc.textContent = descText;

    wrap.innerHTML = Office.renderCloseAllPlanPageHtml(summary.plan, summary.skipped);
    Office.bindCloseAllPlanPage(closeAllState.plan);
    if (confirmBtn) confirmBtn.disabled = planN === 0;
  } catch (e) {
    wrap.innerHTML = `<p style="color:var(--err);">${Office.escapeHtml(String(e))}</p>`;
    if (desc) desc.textContent = "";
  }
}

async function runCloseAllPunches() {
  const plan = closeAllState.plan || [];
  const progress = document.getElementById("closeAllProgress");
  const confirmBtn = document.getElementById("closeAllConfirm");
  if (!plan.length || closeAllState.running) return;

  Office.syncCloseAllPlanTimes(plan);
  const validation = Office.validateCloseAllPlanTimes(plan);
  if (!validation.ok) {
    Office.showMsg(
      "closeAllMsg",
      validation.message || "Συμπληρώστε όλες τις ώρες χτυπήματος πριν την αποστολή.",
      false
    );
    return;
  }

  closeAllState.running = true;
  if (confirmBtn) confirmBtn.disabled = true;
  progress?.classList.remove("hidden");

  let ok = 0;
  const failures = [];

  for (let i = 0; i < plan.length; i += 1) {
    const punch = plan[i];
    const label =
      `${punch.employee_name || punch.employee_afm} · ${punch.event_label} · ${punch.retro_time}`;
    if (progress) {
      progress.textContent = `Αποστολή ${i + 1}/${plan.length}: ${label}…`;
    }
    const res = await Office.submitRetroWorkCardPunch(punch, {
      source: "close_all",
      batch_index: i + 1,
      batch_total: plan.length,
    });
    if (res.ok) {
      ok += 1;
      if (progress) {
        progress.textContent = `Ολοκληρώθηκε ${i + 1}/${plan.length}: ${label}`;
      }
    } else {
      failures.push(`${label} — ${res.error || "σφάλμα"}`);
      if (progress) {
        progress.textContent = `Αποτυχία ${i + 1}/${plan.length}: ${label}`;
      }
    }
  }

  closeAllState.running = false;

  if (failures.length) {
    Office.showMsg(
      "closeAllMsg",
      `Ολοκληρώθηκαν ${ok}/${plan.length}. Αποτυχίες: ${failures.join(" · ")}`,
      ok > 0
    );
    if (confirmBtn) confirmBtn.disabled = false;
    await loadCloseAllPlan();
    return;
  }

  Office.showMsg(
    "closeAllMsg",
    `Επιτυχής υποβολή ${ok} χτυπημάτων (WRKCardSE). Δείτε Καταγραφές → Χτυπήματα κάρτας. Επιστροφή στη λίστα…`,
    true
  );
  window.setTimeout(() => {
    window.location.href = "/ui/missing-cards";
  }, 1200);
}
