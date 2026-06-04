/**
 * Επιλογή ημερομηνίας / διαστήματος — inline, χωρίς popup.
 */
Office.createDatePicker = function (opts) {
  const mount = document.getElementById(opts.mountId);
  if (!mount) return null;

  const singleDay = opts.mode === "single";
  const onApply = opts.onApply || (() => {});

  const QUICK = [
    { id: "today", label: "Σήμερα" },
    { id: "yesterday", label: "Χθες" },
    { id: "last7", label: "7 ημέρες" },
    { id: "last30", label: "30 ημέρες" },
  ];

  let start = isoToday();
  let end = isoToday();

  mount.className = "dp-mount";
  mount.innerHTML = `
    <div class="dp-bar">
      <div class="dp-quick" role="group" aria-label="Γρήγορη επιλογή"></div>
      <div class="dp-fields">
        <label class="dp-field">
          <span class="dp-field-label">${singleDay ? "Ημερομηνία" : "Από"}</span>
          <span class="dp-input-wrap">
            <i class="bi bi-calendar-event" aria-hidden="true"></i>
            <input type="date" class="dp-start" aria-label="${singleDay ? "Ημερομηνία" : "Από"}">
          </span>
        </label>
        <span class="dp-sep" ${singleDay ? 'hidden' : ""}>→</span>
        <label class="dp-field dp-field-end" ${singleDay ? 'hidden' : ""}>
          <span class="dp-field-label">Έως</span>
          <span class="dp-input-wrap">
            <i class="bi bi-calendar-event" aria-hidden="true"></i>
            <input type="date" class="dp-end" aria-label="Έως">
          </span>
        </label>
      </div>
    </div>`;

  const quickEl = mount.querySelector(".dp-quick");
  const inpStart = mount.querySelector(".dp-start");
  const inpEnd = mount.querySelector(".dp-end");

  function isoToday() {
    return toIso(new Date());
  }

  function toIso(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  function parseIso(s) {
    const [y, m, d] = s.split("-").map(Number);
    return new Date(y, m - 1, d);
  }

  function addDays(iso, n) {
    const d = parseIso(iso);
    d.setDate(d.getDate() + n);
    return toIso(d);
  }

  function applyPreset(id, skipNotify) {
    const today = isoToday();
    if (id === "today") {
      start = end = today;
    } else if (id === "yesterday") {
      start = end = addDays(today, -1);
    } else if (id === "last7") {
      end = today;
      start = addDays(end, -6);
    } else if (id === "last30") {
      end = today;
      start = addDays(end, -29);
    }
    if (singleDay) end = start;
    syncInputs();
    highlightQuick(id);
    if (!skipNotify) {
      onApply({ start, end, preset: id, singleDay });
    }
  }

  function syncInputs() {
    inpStart.value = start;
    inpEnd.value = end;
  }

  function readInputs() {
    start = inpStart.value || start;
    end = singleDay ? start : inpEnd.value || end;
    if (start > end) [start, end] = [end, start];
    if (singleDay) end = start;
    syncInputs();
    highlightQuick(null);
    onApply({ start, end, preset: "custom", singleDay });
  }

  function highlightQuick(activeId) {
    quickEl.querySelectorAll(".dp-chip").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.preset === activeId);
    });
  }

  function renderQuick() {
    quickEl.innerHTML = "";
    QUICK.forEach((p) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "dp-chip";
      btn.dataset.preset = p.id;
      btn.textContent = p.label;
      btn.onclick = () => applyPreset(p.id);
      quickEl.appendChild(btn);
    });
  }

  inpStart.addEventListener("change", readInputs);
  inpEnd.addEventListener("change", readInputs);

  renderQuick();
  applyPreset("today", true);

  return {
    getRange: () => ({ start, end }),
    applyPreset: (id) => applyPreset(id, false),
    setRange(s, e) {
      start = s;
      end = e || s;
      syncInputs();
      highlightQuick(null);
    },
  };
};
