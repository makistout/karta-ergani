(function () {
  const slider = document.querySelector("[data-screen-slider]");
  if (!slider) return;

  const slides = Array.from(slider.querySelectorAll("[data-screen-slide]"));
  const dots = Array.from(slider.querySelectorAll("[data-screen-dot]"));
  const prev = slider.querySelector("[data-screen-prev]");
  const next = slider.querySelector("[data-screen-next]");
  let active = 0;
  let timer = null;

  function show(index) {
    active = (index + slides.length) % slides.length;
    slides.forEach((slide, i) => {
      slide.classList.toggle("is-active", i === active);
    });
    dots.forEach((dot, i) => {
      dot.classList.toggle("is-active", i === active);
      dot.setAttribute("aria-current", i === active ? "true" : "false");
    });
  }

  function start() {
    stop();
    timer = window.setInterval(() => show(active + 1), 6500);
  }

  function stop() {
    if (timer) window.clearInterval(timer);
    timer = null;
  }

  prev?.addEventListener("click", () => {
    show(active - 1);
    start();
  });
  next?.addEventListener("click", () => {
    show(active + 1);
    start();
  });
  dots.forEach((dot, index) => {
    dot.addEventListener("click", () => {
      show(index);
      start();
    });
  });
  slider.addEventListener("mouseenter", stop);
  slider.addEventListener("mouseleave", start);
  show(0);
  start();
})();
