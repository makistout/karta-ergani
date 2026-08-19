const qs = new URLSearchParams(location.search);
const weekFrom = qs.get("week_from") || "";
let timekeepingData = null;

function esc(value) { return Office.escapeHtml(String(value ?? "")); }
function duration(minutes) {
  const value = Math.max(0, Number(minutes || 0));
  return `${String(Math.floor(value / 60)).padStart(2, "0")}:${String(value % 60).padStart(2, "0")}`;
}
function displayDate(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value || ""));
  return match ? `${match[3]}/${match[2]}/${match[1]}` : String(value || "");
}

document.addEventListener("DOMContentLoaded", async () => {
  Office.setActiveNav("apologistic");
  document.getElementById("timekeepingBack").href = `/ui/apologistic${weekFrom ? `?week_from=${encodeURIComponent(weekFrom)}` : ""}`;
  document.getElementById("timekeepingExport").addEventListener("click", downloadExcel);
  try {
    const active = await Office.fetchActiveStore();
    Office.applyActiveStoreChrome(active);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(weekFrom)) throw new Error("Λείπει έγκυρη εβδομάδα ωρομέτρησης.");
    await loadTimekeeping();
  } catch (error) {
    document.getElementById("timekeepingWrap").innerHTML = `<p style="color:var(--err);">${esc(error.message || error)}</p>`;
  }
});

async function loadTimekeeping() {
  const res = await fetch("/api/apologistic/timekeeping/preview", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ week_from: weekFrom }),
  });
  const data = await Office.parseJson(res);
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  timekeepingData = data;
  document.getElementById("timekeepingMeta").textContent =
    `${data.store?.name || "Κατάστημα"} · ${displayDate(data.week_from)} – ${displayDate(data.week_to)} · ${data.calculation_version}`;
  document.getElementById("timekeepingSummary").innerHTML =
    `<div class="card apologistic-kpi"><span>Εργαζόμενοι</span><strong>${data.counts?.employees || 0}</strong></div>` +
    `<div class="card apologistic-kpi"><span>Ημέρες</span><strong>${data.counts?.days || 0}</strong></div>` +
    `<div class="card apologistic-kpi apologistic-kpi--ok"><span>Κατάσταση</span><strong>Σ / Μ</strong></div>`;
  renderRows(data.employees || []);
}

function renderRows(rows) {
  document.getElementById("timekeepingWrap").innerHTML =
    `<table class="data apologistic-timekeeping-table"><thead><tr>` +
    `<th>Εργαζόμενος</th><th>Βάση</th><th>Ημέρα</th><th>Νύχτα 25%</th>` +
    `<th>Κυρ/Αργία 75%</th><th>Νύχτα + Κυρ/Αργία</th><th>Μερική 12%</th>` +
    `<th>6η ημέρα 30%</th><th>Υπερωρία 40%</th><th>Υπερωρία 60%</th><th>120%</th>` +
    `</tr></thead><tbody>${rows.map((row) => `<tr>` +
      `<td>${esc(`${row.eponymo || ""} ${row.onoma || ""}`.trim())}<br><small>${esc(row.employee_afm)}</small></td>` +
      `<td>${duration(row.recognized_work_minutes)}</td><td>${duration(row.day)}</td>` +
      `<td>${duration(row.night)}</td><td>${duration(row.sunday_holiday)}</td>` +
      `<td>${duration(row.night_sunday_holiday)}</td><td>${duration(row.partial_additional_12)}</td>` +
      `<td>${duration(row.sixth_day_minutes)}</td><td>${duration(row.overtime_40)}</td>` +
      `<td>${duration(row.overtime_60)}</td><td>${duration((row.overtime_120 || 0) + (row.partial_120 || 0))}</td></tr>`
    ).join("")}</tbody></table>`;
}

async function downloadExcel() {
  const button = document.getElementById("timekeepingExport");
  Office.setButtonLoading(button, true);
  try {
    const res = await fetch("/api/apologistic/timekeeping/export", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ week_from: weekFrom }),
    });
    if (!res.ok) {
      const data = await Office.parseJson(res);
      throw new Error(data.error || `HTTP ${res.status}`);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `orometrisi_${weekFrom.replaceAll("-", "")}.xlsx`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (error) {
    Office.showMsg("timekeepingMsg", error.message || String(error), false);
  } finally {
    Office.setButtonLoading(button, false);
  }
}
