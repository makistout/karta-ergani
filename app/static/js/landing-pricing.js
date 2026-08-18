(function () {
  const prices = {
    "1-2": "94€",
    "3-5": "112€",
    "6-20": "148€",
    "21-50": "187€",
    "51-100": "274€",
    "101-200": "439€",
  };

  const tabs = Array.from(document.querySelectorAll("[data-pricing-tab]"));
  const amountEl = document.querySelector("[data-pricing-amount]");
  const rangeLabelEl = document.querySelector("[data-pricing-range-label]");

  if (!tabs.length || !amountEl || !rangeLabelEl) return;

  function setActive(range) {
    amountEl.textContent = prices[range] || "";
    rangeLabelEl.textContent = `${range} άτομα`;
    tabs.forEach((tab) => {
      const active = tab.dataset.range === range;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
  }

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => setActive(tab.dataset.range || "1-2"));
  });

  setActive("1-2");
})();
