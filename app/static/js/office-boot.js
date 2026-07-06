document.addEventListener("DOMContentLoaded", () => {
  const path = window.location.pathname || "";
  const publicLanding =
    path.startsWith("/psifiaki-karta-ergasias") ||
    path.startsWith("/psifiaki-karta-logistika-grafeia") ||
    path.startsWith("/ti-einai-i-psifiaki-karta-ergasias") ||
    path.startsWith("/chttypimata-kartas-ergasias") ||
    path.startsWith("/apokliseis-psifiakis-kartas") ||
    path.startsWith("/psifiako-orario-ergani") ||
    path.startsWith("/ui/landing");
  const recipientFlow =
    publicLanding ||
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
