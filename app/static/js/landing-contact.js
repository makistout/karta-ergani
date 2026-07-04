(function () {
  const form = document.getElementById("landingContactForm");
  if (!form) return;

  const submitBtn = document.getElementById("landingContactSubmit");
  const msgId = "landingContactMsg";

  function value(name) {
    return String(form.elements[name]?.value || "").trim();
  }

  function setLoading(loading) {
    if (!submitBtn) return;
    submitBtn.disabled = loading;
    submitBtn.classList.toggle("is-loading", loading);
    const label = submitBtn.querySelector("span");
    if (label) label.textContent = loading ? "Αποστολή..." : "Αποστολή";
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = {
      name: value("name"),
      email: value("email"),
      phone: value("phone"),
      employees: value("employees"),
      company: value("company"),
      message: value("message"),
      website: value("website"),
    };
    if (!payload.name || !payload.email || !payload.message) {
      Office.showMsg(msgId, "Συμπληρώστε όνομα, email και μήνυμα.", false);
      return;
    }

    setLoading(true);
    try {
      const res = await fetch("/api/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify(payload),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.success === false) {
        throw new Error(data.error || "Δεν ήταν δυνατή η αποστολή.");
      }
      Office.showMsg(msgId, data.message || "Το μήνυμα στάλθηκε.", true);
      form.reset();
    } catch (error) {
      Office.showMsg(msgId, String(error.message || error), false);
    } finally {
      setLoading(false);
    }
  });
})();
