/**
 * Επιλογή ημερομηνίας / διαστήματος — ελληνικό φορμάτ ηη/μμ/εεεε + popup ημερολόγιο.
 */
(function () {
  const MONTHS_GR = [
    "Ιανουάριος",
    "Φεβρουάριος",
    "Μάρτιος",
    "Απρίλιος",
    "Μάιος",
    "Ιούνιος",
    "Ιούλιος",
    "Αύγουστος",
    "Σεπτέμβριος",
    "Οκτώβριος",
    "Νοέμβριος",
    "Δεκέμβριος",
  ];
  const DAYS_GR = ["Δε", "Τρ", "Τε", "Πε", "Πα", "Σα", "Κυ"];

  let openPopup = null;

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
    const [y, m, d] = String(s || "").split("-").map(Number);
    if (!y || !m || !d) return null;
    return new Date(y, m - 1, d);
  }

  function addDays(iso, n) {
    const d = parseIso(iso);
    if (!d) return iso;
    d.setDate(d.getDate() + n);
    return toIso(d);
  }

  function isoToGr(iso) {
    if (!iso || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) return "";
    const [y, m, d] = iso.split("-");
    return `${d}/${m}/${y}`;
  }

  function grToIso(text) {
    const m = String(text || "")
      .trim()
      .match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    if (!m) return null;
    const day = parseInt(m[1], 10);
    const month = parseInt(m[2], 10);
    const year = parseInt(m[3], 10);
    if (month < 1 || month > 12 || day < 1 || day > 31 || year < 1900) return null;
    const d = new Date(year, month - 1, day);
    if (d.getFullYear() !== year || d.getMonth() !== month - 1 || d.getDate() !== day) {
      return null;
    }
    return toIso(d);
  }

  function closeOpenPopup() {
    if (openPopup) {
      openPopup.classList.add("hidden");
      openPopup = null;
    }
  }

  document.addEventListener("click", (e) => {
    if (!e.target.closest(".dp-date-field")) closeOpenPopup();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeOpenPopup();
  });

  function clampIso(iso, minIso, maxIso) {
    let v = iso;
    if (minIso && v < minIso) v = minIso;
    if (maxIso && v > maxIso) v = maxIso;
    return v;
  }

  function resolveBound(raw) {
    if (!raw) return null;
    if (raw === "today") return isoToday();
    if (raw === "yesterday") return addDays(isoToday(), -1);
    return String(raw).slice(0, 10);
  }

  function inRange(iso, startIso, endIso) {
    if (!iso || !startIso || !endIso) return false;
    return iso >= startIso && iso <= endIso;
  }

  function renderCalendar(popup, viewIso, selectedIso, ctx) {
    const {
      minIso,
      maxIso,
      rangeStart,
      rangeEnd,
      onPick,
    } = ctx;
    const view = parseIso(viewIso) || new Date();
    const year = view.getFullYear();
    const month = view.getMonth();
    const first = new Date(year, month, 1);
    const startPad = (first.getDay() + 6) % 7;
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const prevMonthDays = new Date(year, month, 0).getDate();

    popup.innerHTML = `
      <div class="dp-cal-head">
        <button type="button" class="dp-cal-nav" data-nav="-1" aria-label="Προηγούμενος μήνας">‹</button>
        <div class="dp-cal-title">${MONTHS_GR[month]} ${year}</div>
        <button type="button" class="dp-cal-nav" data-nav="1" aria-label="Επόμενος μήνας">›</button>
      </div>
      <div class="dp-cal-weekdays">${DAYS_GR.map((d) => `<span>${d}</span>`).join("")}</div>
      <div class="dp-cal-grid"></div>`;

    const grid = popup.querySelector(".dp-cal-grid");
    const cells = [];

    for (let i = 0; i < startPad; i += 1) {
      const day = prevMonthDays - startPad + i + 1;
      cells.push({ day, outside: true, iso: null });
    }
    for (let day = 1; day <= daysInMonth; day += 1) {
      const iso = toIso(new Date(year, month, day));
      cells.push({ day, outside: false, iso });
    }
    while (cells.length % 7 !== 0) {
      const day = cells.length - startPad - daysInMonth + 1;
      cells.push({ day, outside: true, iso: null });
    }

    cells.forEach((cell) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "dp-cal-day";
      btn.textContent = String(cell.day);
      if (cell.outside) {
        btn.classList.add("outside");
        btn.disabled = true;
      } else {
        const disabled =
          (minIso && cell.iso < minIso) || (maxIso && cell.iso > maxIso);
        if (disabled) btn.disabled = true;
        if (cell.iso === selectedIso) btn.classList.add("selected");
        if (rangeStart && rangeEnd && inRange(cell.iso, rangeStart, rangeEnd)) {
          btn.classList.add("in-range");
          if (cell.iso === rangeStart) btn.classList.add("range-start");
          if (cell.iso === rangeEnd) btn.classList.add("range-end");
        }
        btn.addEventListener("click", (e) => {
          e.stopPropagation();
          onPick(cell.iso);
        });
      }
      grid.appendChild(btn);
    });

    popup.querySelectorAll(".dp-cal-nav").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const delta = parseInt(btn.dataset.nav, 10);
        const next = new Date(year, month + delta, 1);
        renderCalendar(popup, toIso(next), selectedIso, ctx);
      });
    });
  }

  function openCalendar(fieldEl, ctx) {
    const popup = fieldEl.querySelector(".dp-cal-popup");
    if (!popup) return;
    closeOpenPopup();
    renderCalendar(popup, ctx.viewIso || ctx.selectedIso || isoToday(), ctx.selectedIso, {
      ...ctx,
      onPick(iso) {
        ctx.onPick(iso);
        closeOpenPopup();
      },
    });
    popup.classList.remove("hidden");
    openPopup = popup;
  }

  function bindGreekDateField(fieldEl, opts) {
    const textInput = fieldEl.querySelector(".dp-text");
    const calBtn = fieldEl.querySelector(".dp-cal-btn");
    const popup = fieldEl.querySelector(".dp-cal-popup");
    if (!textInput || !popup) return null;

    let iso = opts.initialIso || isoToday();
    const minIso = opts.minIso || null;
    const maxIso = opts.maxIso || null;

    function setIso(next, silent) {
      const prev = iso;
      iso = clampIso(next || isoToday(), minIso, maxIso);
      textInput.value = isoToGr(iso);
      textInput.dataset.iso = iso;
      if (!silent && iso !== prev && typeof opts.onChange === "function") {
        opts.onChange(iso);
      }
    }

    function readText() {
      const parsed = grToIso(textInput.value);
      if (parsed) {
        if (parsed !== iso) setIso(parsed);
        else textInput.value = isoToGr(iso);
      } else {
        textInput.value = isoToGr(iso);
      }
    }

    function refreshBounds() {
      if (opts.getRangeHighlight) {
        const h = opts.getRangeHighlight();
        fieldEl._rangeStart = h?.start || null;
        fieldEl._rangeEnd = h?.end || null;
      }
    }

    let skipBlurRead = false;

    calBtn?.addEventListener("mousedown", (e) => {
      e.preventDefault();
      skipBlurRead = true;
    });

    calBtn?.addEventListener("click", (e) => {
      e.stopPropagation();
      if (textInput.disabled) return;
      refreshBounds();
      openCalendar(fieldEl, {
        selectedIso: iso,
        viewIso: iso,
        minIso,
        maxIso,
        rangeStart: fieldEl._rangeStart,
        rangeEnd: fieldEl._rangeEnd,
        onPick: (picked) => setIso(picked),
      });
    });

    textInput.addEventListener("focus", () => {
      textInput.select();
    });
    textInput.addEventListener("blur", () => {
      if (skipBlurRead) {
        skipBlurRead = false;
        return;
      }
      readText();
    });
    textInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        readText();
        textInput.blur();
      }
    });

    setIso(iso, true);

    return {
      getIso: () => iso,
      setIso,
      setDisabled(disabled) {
        textInput.disabled = Boolean(disabled);
        if (calBtn) calBtn.disabled = Boolean(disabled);
      },
      setBounds(min, max) {
        opts.minIso = min;
        opts.maxIso = max;
        setIso(iso);
      },
    };
  }

  function buildDateFieldHtml(label, ariaLabel, singleLabel) {
    const fieldLabel = label || (singleLabel ? "Ημερομηνία" : "Από");
    return `
      <label class="dp-field">
        <span class="dp-field-label">${fieldLabel}</span>
        <div class="dp-date-field">
          <div class="dp-date-control">
            <button type="button" class="dp-cal-btn" aria-label="Άνοιγμα ημερολογίου">
              <i class="bi bi-calendar3" aria-hidden="true"></i>
            </button>
            <input type="text" class="dp-text" inputmode="numeric" autocomplete="off"
              placeholder="ηη/μμ/εεεε" aria-label="${ariaLabel || fieldLabel}">
          </div>
          <div class="dp-cal-popup hidden" role="dialog" aria-label="Ημερολόγιο"></div>
        </div>
      </label>`;
  }

  Office.formatDateGr = isoToGr;
  Office.parseDateGr = grToIso;

  Office.attachGreekDateField = function (opts) {
    const input = opts.inputEl || document.getElementById(opts.inputId);
    if (!input) return null;

    let fieldEl = input.closest(".dp-date-field");
    if (!fieldEl) {
      const parent = input.parentNode;
      fieldEl = document.createElement("div");
      fieldEl.className = "dp-date-field";
      const control = document.createElement("div");
      control.className = "dp-date-control";
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "dp-cal-btn";
      btn.setAttribute("aria-label", "Άνοιγμα ημερολογίου");
      btn.innerHTML = '<i class="bi bi-calendar3" aria-hidden="true"></i>';
      const popup = document.createElement("div");
      popup.className = "dp-cal-popup hidden";
      popup.setAttribute("role", "dialog");
      popup.setAttribute("aria-label", "Ημερολόγιο");
      input.classList.add("dp-text");
      input.type = "text";
      input.inputMode = "numeric";
      input.autocomplete = "off";
      if (!input.placeholder) input.placeholder = "ηη/μμ/εεεε";
      control.appendChild(btn);
      control.appendChild(input);
      fieldEl.appendChild(control);
      fieldEl.appendChild(popup);
      parent.appendChild(fieldEl);
    }

    const initial =
      opts.initialIso ||
      grToIso(input.value) ||
      (input.type === "date" ? input.value : null) ||
      isoToday();

    return bindGreekDateField(fieldEl, {
      initialIso: initial,
      minIso: resolveBound(opts.minDate),
      maxIso: resolveBound(opts.maxDate),
      onChange: opts.onChange,
      getRangeHighlight: opts.getRangeHighlight,
    });
  };

  Office.createDatePicker = function (opts) {
    const mount = document.getElementById(opts.mountId);
    if (!mount) return null;

    const singleDay = opts.mode === "single";
    const autoApply = opts.autoApply !== false;
    const inlineLayout = opts.layout === "inline";
    const onApply = opts.onApply || (() => {});

    const ALL_QUICK = [
      { id: "today", label: "Σήμερα" },
      { id: "yesterday", label: "Χθες" },
      { id: "last7", label: "7 ημέρες" },
      { id: "last30", label: "30 ημέρες" },
    ];
    const quickLabels = opts.quickLabels || {};
    const quickIds =
      Array.isArray(opts.quickPresets) && opts.quickPresets.length
        ? opts.quickPresets
        : ALL_QUICK.map((p) => p.id);
    const QUICK = ALL_QUICK.filter((p) => quickIds.includes(p.id)).map((p) => ({
      ...p,
      label: quickLabels[p.id] || p.label,
    }));

    let start = isoToday();
    let end = isoToday();
    let startField = null;
    let endField = null;

    mount.className = singleDay ? "dp-mount dp-single" : "dp-mount";
    if (inlineLayout) mount.classList.add("dp-mount--inline");
    mount.innerHTML = `
      <div class="dp-bar${inlineLayout ? " dp-bar--inline" : ""}">
        <div class="dp-quick" role="group" aria-label="Γρήγορη επιλογή"></div>
        <div class="dp-period">
          ${singleDay ? "" : '<span class="dp-period-label">Περίοδος:</span>'}
          <div class="dp-fields">
            ${buildDateFieldHtml(singleDay ? "Ημερομηνία" : "Από", singleDay ? "Ημερομηνία" : "Από", singleDay)}
            <span class="dp-sep" ${singleDay ? "hidden" : ""}>–</span>
            ${singleDay ? "" : buildDateFieldHtml("Έως", "Έως")}
          </div>
        </div>
      </div>`;

    const quickEl = mount.querySelector(".dp-quick");
    const startEl = mount.querySelector(".dp-date-field");
    const endEl = singleDay ? null : mount.querySelectorAll(".dp-date-field")[1];

    function getBounds() {
      return {
        minIso: resolveBound(opts.minDate),
        maxIso: resolveBound(opts.maxDate),
      };
    }

    let lastNotified = { start: "", end: "" };

    function notify(preset) {
      if (!autoApply) return;
      if (start === lastNotified.start && end === lastNotified.end) return;
      lastNotified = { start, end };
      onApply({ start, end, preset: preset || "custom", singleDay });
    }

    function syncRangeFields() {
      if (singleDay) end = start;
      if (start > end) [start, end] = [end, start];
      startField?.setIso(start, true);
      if (!singleDay) endField?.setIso(end, true);
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
      syncRangeFields();
      highlightQuick(id);
      if (!skipNotify) notify(id);
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

    const bounds = getBounds();
    startField = bindGreekDateField(startEl, {
      initialIso: start,
      ...bounds,
      getRangeHighlight: () => ({ start, end }),
      onChange(iso) {
        start = iso;
        if (singleDay) end = start;
        else if (start > end) end = start;
        syncRangeFields();
        highlightQuick(null);
        notify("custom");
      },
    });
    if (!singleDay && endEl) {
      endField = bindGreekDateField(endEl, {
        initialIso: end,
        ...bounds,
        getRangeHighlight: () => ({ start, end }),
        onChange(iso) {
          end = iso;
          if (start > end) start = end;
          syncRangeFields();
          highlightQuick(null);
          notify("custom");
        },
      });
    }

    renderQuick();
    applyPreset(quickIds.includes("today") ? "today" : quickIds[0], true);
    lastNotified = { start, end };

    return {
      getRange: () => ({ start, end }),
      applyPreset: (id) => applyPreset(id, false),
      setRange(s, e) {
        start = s;
        end = e || s;
        syncRangeFields();
        highlightQuick(null);
      },
    };
  };
})();
