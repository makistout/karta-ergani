const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

document.addEventListener("DOMContentLoaded", () => {
  Office.setActiveNav("billing-presentations");
  document.getElementById("btnPresentationSend")?.addEventListener("click", sendPresentation);
  document.getElementById("presEmail")?.addEventListener("input", () => {
    document.getElementById("presEmail")?.classList.remove("field-err");
  });
  document.getElementById("presEmail")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      sendPresentation();
    }
  });
});

function presentationEmail() {
  const input = document.getElementById("presEmail");
  const email = input?.value?.trim() || "";
  if (!email) {
    input?.classList.add("field-err");
    input?.focus();
    Office.showMsg("billingPresMsg", "Απαιτείται το email", false);
    return "";
  }
  if (!EMAIL_RE.test(email)) {
    input?.classList.add("field-err");
    input?.focus();
    Office.showMsg("billingPresMsg", "Μη έγκυρο email", false);
    return "";
  }
  input?.classList.remove("field-err");
  return email;
}

async function sendPresentation() {
  const email = presentationEmail();
  if (!email) return;
  const btn = document.getElementById("btnPresentationSend");
  Office.setButtonLoading(btn, true);
  try {
    const res = await fetch("/api/billing/presentation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      Office.showMsg("billingPresMsg", data.error || "Αποτυχία αποστολής παρουσίασης", false);
      return;
    }
    Office.showMsg("billingPresMsg", `Η παρουσίαση στάλθηκε στο ${data.to || email}.`, true);
  } catch (err) {
    Office.showMsg("billingPresMsg", String(err || "Αποτυχία αποστολής παρουσίασης"), false);
  } finally {
    Office.setButtonLoading(btn, false);
  }
}
