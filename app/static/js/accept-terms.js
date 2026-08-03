function showAcceptTermsMsg(text, ok) {
  const el = document.getElementById("acceptTermsMsg");
  if (!el) return;
  el.textContent = text || "";
  el.className = ok ? "msg show ok" : "msg show err";
  el.style.display = text ? "flex" : "none";
}

function termsCheckBox() {
  return document.getElementById("termsAcceptBox") || document.querySelector(".terms-accept-check");
}

function setTermsCheckInvalid(invalid) {
  const box = termsCheckBox();
  if (!box) return;
  box.classList.toggle("is-invalid", !!invalid);
  if (invalid) {
    box.style.border = "2px solid #dc2626";
    box.style.background = "#fef2f2";
    box.style.color = "#991b1b";
  } else {
    box.style.border = "2px solid transparent";
    box.style.background = "transparent";
    box.style.color = "#334155";
  }
}

function clearTermsCheckInvalid() {
  setTermsCheckInvalid(false);
}

let termsVersion = "";

async function loadTerms() {
  const res = await fetch("/api/auth/terms", { credentials: "same-origin" });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    showAcceptTermsMsg(data.error || "Αδυναμία φόρτωσης όρων.", false);
    return;
  }
  termsVersion = data.version || "";
  const titleEl = document.getElementById("termsTitle");
  const bodyEl = document.getElementById("termsBody");
  const hintEl = document.getElementById("termsVersionHint");
  const checkLabel = document.getElementById("termsCheckboxLabel");
  if (titleEl) titleEl.textContent = data.title || "Όροι χρήσης";
  if (bodyEl) bodyEl.innerHTML = data.body_html || "";
  if (hintEl) hintEl.textContent = termsVersion ? `Έκδοση όρων: ${termsVersion}` : "";
  if (checkLabel && data.checkbox_label) checkLabel.textContent = data.checkbox_label;
}

async function submitAcceptTerms(ev) {
  if (ev) {
    ev.preventDefault();
    ev.stopPropagation();
  }
  const checked = !!document.getElementById("termsAcceptCheck")?.checked;
  if (!checked) {
    setTermsCheckInvalid(true);
    showAcceptTermsMsg("Πρέπει να τσεκάρετε την αποδοχή των όρων.", false);
    document.getElementById("termsAcceptCheck")?.focus();
    termsCheckBox()?.scrollIntoView({ behavior: "smooth", block: "center" });
    return false;
  }
  clearTermsCheckInvalid();
  const btn = document.getElementById("btnAcceptTerms");
  if (btn) btn.disabled = true;
  try {
    const res = await fetch("/api/auth/accept-terms", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({
        accepted: true,
        terms_version: termsVersion,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.success) {
      if (data.redirect) {
        window.location.href = data.redirect;
        return false;
      }
      showAcceptTermsMsg(data.error || "Αποτυχία αποδοχής όρων.", false);
      return false;
    }
    const ipNote = data.client_ip ? ` (IP: ${data.client_ip})` : "";
    showAcceptTermsMsg((data.message || "Οι όροι αποδεχτήκαν.") + ipNote, true);
    window.setTimeout(() => {
      window.location.href = data.onboarding_redirect || "/ui/";
    }, 700);
  } catch (e) {
    showAcceptTermsMsg(String(e), false);
  } finally {
    if (btn) btn.disabled = false;
  }
  return false;
}

document.addEventListener("DOMContentLoaded", async () => {
  try {
    const res = await fetch("/api/auth/status", { credentials: "same-origin" });
    const data = await res.json();
    if (!data.authenticated) {
      window.location.href = "/ui/login";
      return;
    }
    if (data.must_change_password) {
      window.location.href = "/ui/change-password";
      return;
    }
    if (data.terms_accepted) {
      window.location.href = "/ui/";
      return;
    }
  } catch {
    /* ignore */
  }
  try {
    await loadTerms();
  } catch (e) {
    showAcceptTermsMsg(String(e), false);
  }
  document.getElementById("termsAcceptCheck")?.addEventListener("change", () => {
    if (document.getElementById("termsAcceptCheck")?.checked) {
      clearTermsCheckInvalid();
      showAcceptTermsMsg("", true);
      const msg = document.getElementById("acceptTermsMsg");
      if (msg) {
        msg.className = "msg";
        msg.style.display = "none";
        msg.textContent = "";
      }
    }
  });
  const btn = document.getElementById("btnAcceptTerms");
  if (btn) {
    btn.disabled = false;
    btn.addEventListener("click", submitAcceptTerms);
  }
});
