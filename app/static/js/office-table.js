Object.assign(window.Office, {
  paginateSlice(rows, page, pageSize = this.TABLE_PAGE_SIZE) {
    const total = rows.length;
    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    const safePage = Math.min(Math.max(1, page), totalPages);
    const start = (safePage - 1) * pageSize;
    return {
      page: safePage,
      totalPages,
      total,
      items: rows.slice(start, start + pageSize),
    };
  },

  buildTablePager(page, totalPages, totalItems, onPageChange, pageSize = this.TABLE_PAGE_SIZE) {
    const nav = document.createElement("nav");
    nav.className = "table-pager";
    nav.setAttribute("aria-label", "Σελίδες αποτελεσμάτων");

    const from = totalItems ? (page - 1) * pageSize + 1 : 0;
    const to = Math.min(page * pageSize, totalItems);
    const info = document.createElement("span");
    info.className = "table-pager-info";
    info.textContent =
      totalItems > 0
        ? `${from}–${to} από ${totalItems}`
        : "0 αποτελέσματα";

    const mkBtn = (label, disabled, handler, extraClass) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = `table-pager-btn${extraClass ? ` ${extraClass}` : ""}`;
      b.textContent = label;
      b.disabled = disabled;
      if (!disabled) b.onclick = handler;
      return b;
    };

    nav.appendChild(mkBtn("‹", page <= 1, () => onPageChange(page - 1), "prev"));
    const pages = document.createElement("span");
    pages.className = "table-pager-pages";
    pages.textContent = `Σελίδα ${page} / ${totalPages}`;
    nav.appendChild(pages);
    nav.appendChild(mkBtn("›", page >= totalPages, () => onPageChange(page + 1), "next"));
    nav.appendChild(info);
    return nav;
  },

  enhanceResponsiveTable(table) {
    if (!table) return;
    const rows = Array.from(table.querySelectorAll("tr"));
    const headerRow = rows.find((row) => row.querySelector("th"));
    if (!headerRow) return;

    const headers = Array.from(headerRow.children).map((cell) =>
      (cell.textContent.trim() || cell.getAttribute("aria-label") || "").replace(/\s+/g, " ")
    );
    headerRow.classList.add("responsive-table-header");

    rows.forEach((row) => {
      if (row === headerRow) return;
      Array.from(row.children).forEach((cell, index) => {
        if (!cell.dataset.label) cell.dataset.label = headers[index] || "";
      });
    });

    table.classList.add("responsive-data-table");
    table.dataset.responsiveReady = "1";
  },

  enhanceResponsiveTables(root = document) {
    root.querySelectorAll("table.data").forEach((table) => {
      this.enhanceResponsiveTable(table);
    });
  },

  initResponsiveTables() {
    if (this._responsiveTablesObserver) {
      this.enhanceResponsiveTables();
      return;
    }

    this.enhanceResponsiveTables();
    this._responsiveTablesObserver = new MutationObserver((mutations) => {
      let shouldScan = false;
      mutations.forEach((mutation) => {
        mutation.addedNodes.forEach((node) => {
          if (node.nodeType !== Node.ELEMENT_NODE) return;
          if (
            node.matches?.("table.data") ||
            node.querySelector?.("table.data") ||
            node.closest?.("table.data")
          ) {
            shouldScan = true;
          }
        });
      });
      if (shouldScan) this.enhanceResponsiveTables();
    });
    this._responsiveTablesObserver.observe(document.body, {
      childList: true,
      subtree: true,
    });
  },
});
