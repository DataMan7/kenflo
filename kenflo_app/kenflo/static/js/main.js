// KENFLO site behaviour: mobile navigation toggle
document.addEventListener("DOMContentLoaded", function () {
  var toggle = document.querySelector(".nav-toggle");
  var nav = document.getElementById("site-nav");
  if (toggle && nav) {
    toggle.addEventListener("click", function () {
      var open = nav.classList.toggle("open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }
});


// KENFLO hero carousel
(function () {
  'use strict';
  var carousel = document.getElementById('hero-carousel');
  if (!carousel) return;
  var slides = carousel.querySelectorAll('.hero-slide');
  var dots = carousel.querySelectorAll('.hero-carousel-indicators button');
  if (!slides.length || slides.length !== dots.length) return;
  var current = 0;
  var timer = null;
  var interval = 5000;

  function goTo(index, userAction) {
    if (index === current && !userAction) return;
    slides[current].classList.remove('active');
    slides[current].setAttribute('aria-hidden', 'true');
    dots[current].classList.remove('active');
    dots[current].setAttribute('aria-selected', 'false');
    current = (index + slides.length) % slides.length;
    slides[current].classList.add('active');
    slides[current].setAttribute('aria-hidden', 'false');
    dots[current].classList.add('active');
    dots[current].setAttribute('aria-selected', 'true');
    if (userAction) restart();
  }

  function next() { goTo(current + 1, false); }
  function restart() { stop(); start(); }
  function start() { timer = setInterval(next, interval); }
  function stop() { if (timer) { clearInterval(timer); timer = null; } }

  dots.forEach(function (dot, i) {
    dot.addEventListener('click', function () { goTo(i, true); });
  });

  carousel.addEventListener('mouseenter', stop);
  carousel.addEventListener('mouseleave', start);
  carousel.addEventListener('focusin', stop);
  carousel.addEventListener('focusout', start);
  carousel.setAttribute('tabindex', '0');
  carousel.setAttribute('role', 'region');
  carousel.addEventListener('keydown', function (e) {
    if (e.key === 'ArrowRight') { goTo(current + 1, true); e.preventDefault(); }
    else if (e.key === 'ArrowLeft') { goTo(current - 1, true); e.preventDefault(); }
  });

  start();
})();
