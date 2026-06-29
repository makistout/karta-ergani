document.addEventListener("DOMContentLoaded", async () => {
  const params = new URLSearchParams(window.location.search);
  const token = (params.get("t") || params.get("token") || "").trim();
  const hint = document.getElementById("verifyEmailHint");
  if (!token) {
    Office.showMsg("verifyEmailMsg", "Λείπει ο σύνδεσμος επιβεβαίωσης.", false);
    if (hint) hint.textContent = "Ο σύνδεσμος δεν περιέχει token.";
    return;
  }
  try {
    const res = await fetch(`/api/users/verify-email?t=${encodeURIComponent(token)}`);
    const data = await res.json();
    if (!res.ok || !data.success) {
      Office.showMsg("verifyEmailMsg", data.error || "Ο σύνδεσμος δεν είναι πλέον έγκυρος.", false);
      if (hint) hint.textContent = "Ζητήστε νέο email επιβεβαίωσης από διαχειριστή.";
      return;
    }
    Office.showMsg("verifyEmailMsg", data.message || "Το email επιβεβαιώθηκε.", true);
    if (hint) hint.textContent = "Μπορείτε πλέον να συνδεθείτε.";
  } catch (e) {
    Office.showMsg("verifyEmailMsg", String(e), false);
    if (hint) hint.textContent = "Δεν ήταν δυνατή η επιβεβαίωση.";
  }
});
