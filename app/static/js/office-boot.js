document.addEventListener("DOMContentLoaded", () => {
  const path = window.location.pathname || "";
  const recipientFlow =
    path.startsWith("/ui/landing") ||
    path.startsWith("/ui/telegram-hit") ||
    path.startsWith("/ui/retro-hit") ||
    path.startsWith("/ui/today-hit") ||
    path.startsWith("/ui/today-action");

  window.Office.installFetchAuthGuard();
  if (!recipientFlow) {
    window.Office.initChrome();
    window.Office.initPageBackButton();
    window.Office.initResponsiveTables();
    window.Office.ensureLogoutLink();
    window.Office.loadActiveStore();
  }
});
