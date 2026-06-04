/**
 * Autocomplete με πλήκτρα ↑/↓, Enter και Tab για επιλογή.
 */
Office.createAutocomplete = function (opts) {
  const input = document.getElementById(opts.inputId);
  const list = document.getElementById(opts.listId);
  const hidden = opts.hiddenId ? document.getElementById(opts.hiddenId) : null;
  if (!input || !list) return null;

  let allItems = [];
  let filtered = [];
  let hi = -1;
  let debounceTimer = null;
  const maxItems = opts.maxItems ?? 30;
  const minChars = opts.minChars ?? 0;

  const labelOf = (item) => {
    if (opts.labelFn) return opts.labelFn(item);
    const d = item.description || item.desc || "";
    return d ? `${item.value} — ${d}` : String(item.value ?? "");
  };

  const valueOf = (item) => String(item.value ?? item.code ?? "");

  function filterLocal(q) {
    const s = q.trim().toLowerCase();
    let pool = allItems;
    if (s) {
      pool = allItems.filter((item) => {
        const lbl = labelOf(item).toLowerCase();
        const val = valueOf(item).toLowerCase();
        return lbl.includes(s) || val.startsWith(s);
      });
    }
    return pool.slice(0, maxItems);
  }

  function render(items) {
    filtered = items;
    hi = items.length ? 0 : -1;
    list.innerHTML = "";
    items.forEach((item, i) => {
      const li = document.createElement("li");
      li.textContent = labelOf(item);
      li.setAttribute("role", "option");
      li.id = `${opts.listId}-opt-${i}`;
      if (i === hi) {
        li.classList.add("highlighted");
        li.setAttribute("aria-selected", "true");
      }
      li.addEventListener("mousedown", (e) => {
        e.preventDefault();
        pick(i);
      });
      list.appendChild(li);
    });
    const open = items.length > 0;
    list.classList.toggle("show", open);
    input.setAttribute("aria-expanded", open ? "true" : "false");
    if (open && hi >= 0) {
      input.setAttribute("aria-activedescendant", `${opts.listId}-opt-${hi}`);
    } else {
      input.removeAttribute("aria-activedescendant");
    }
  }

  function setHighlight(idx) {
    if (!filtered.length) return;
    hi = Math.max(0, Math.min(idx, filtered.length - 1));
    [...list.children].forEach((li, i) => {
      const on = i === hi;
      li.classList.toggle("highlighted", on);
      if (on) {
        li.setAttribute("aria-selected", "true");
        li.scrollIntoView({ block: "nearest" });
        input.setAttribute("aria-activedescendant", li.id);
      } else {
        li.removeAttribute("aria-selected");
      }
    });
  }

  function pick(idx) {
    const item = filtered[idx];
    if (!item) return;
    input.value = labelOf(item);
    if (hidden) hidden.value = valueOf(item);
    list.classList.remove("show");
    list.innerHTML = "";
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
    opts.onSelect?.(item);
  }

  function openList() {
    if (opts.searchFn) return;
    render(filterLocal(input.value));
  }

  function scheduleSearch() {
    clearTimeout(debounceTimer);
    const q = input.value.trim();
    if (!opts.searchFn) {
      render(filterLocal(input.value));
      return;
    }
    if (q.length < minChars) {
      render([]);
      return;
    }
    debounceTimer = setTimeout(async () => {
      try {
        const items = await opts.searchFn(q);
        render(Array.isArray(items) ? items.slice(0, maxItems) : []);
      } catch (e) {
        console.error(e);
        render([]);
      }
    }, opts.debounce ?? 280);
  }

  input.addEventListener("input", scheduleSearch);

  input.addEventListener("focus", () => {
    if (!opts.searchFn) openList();
  });

  input.addEventListener("keydown", (e) => {
    const open = list.classList.contains("show") && filtered.length > 0;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (!open) {
        if (opts.searchFn) scheduleSearch();
        else openList();
        return;
      }
      setHighlight(hi < 0 ? 0 : hi + 1);
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      if (!open) {
        if (!opts.searchFn) openList();
        return;
      }
      setHighlight(hi <= 0 ? filtered.length - 1 : hi - 1);
      return;
    }
    if (e.key === "Enter") {
      if (open && hi >= 0) {
        e.preventDefault();
        pick(hi);
      }
      return;
    }
    if (e.key === "Tab") {
      if (open) {
        const idx = hi >= 0 ? hi : filtered.length === 1 ? 0 : -1;
        if (idx >= 0) pick(idx);
      }
      return;
    }
    if (e.key === "Escape") {
      list.classList.remove("show");
      input.setAttribute("aria-expanded", "false");
    }
  });

  document.addEventListener("click", (e) => {
    if (!e.target.closest(`#${opts.inputId}`) && !e.target.closest(`#${opts.listId}`)) {
      list.classList.remove("show");
      input.setAttribute("aria-expanded", "false");
    }
  });

  return {
    setItems(items) {
      allItems = items || [];
    },
    setValue(code, desc) {
      if (!code) return;
      const item = allItems.find((x) => valueOf(x) === String(code));
      input.value = item ? labelOf(item) : desc || code;
      if (hidden) hidden.value = String(code);
    },
    getValue() {
      return { code: hidden ? hidden.value : "", label: input.value };
    },
  };
};
