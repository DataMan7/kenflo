// KENFLO site behaviour
(function () {
  'use strict';

  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // ---- Mobile navigation -------------------------------------------------
  document.addEventListener('DOMContentLoaded', function () {
    var toggle = document.querySelector('.nav-toggle');
    var nav = document.getElementById('site-nav');
    if (!toggle || !nav) return;

    function setOpen(open) {
      nav.classList.toggle('open', open);
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    }

    toggle.addEventListener('click', function (e) {
      e.stopPropagation();
      setOpen(!nav.classList.contains('open'));
    });

    // Close after choosing a destination.
    nav.addEventListener('click', function (e) {
      if (e.target && e.target.closest && e.target.closest('a')) setOpen(false);
    });

    // Close on Escape and hand focus back to the toggle.
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && nav.classList.contains('open')) {
        setOpen(false);
        toggle.focus();
      }
    });

    // Close when tapping anywhere outside the header.
    document.addEventListener('click', function (e) {
      if (!nav.classList.contains('open')) return;
      if (e.target && e.target.closest && e.target.closest('.site-header')) return;
      setOpen(false);
    });

    // Never leave the menu flagged open once the desktop layout returns.
    window.addEventListener('resize', function () {
      if (window.innerWidth > 1199) setOpen(false);
    });
  });

  // ---- Sticky header depth ----------------------------------------------
  (function () {
    var header = document.querySelector('.site-header');
    if (!header) return;
    var ticking = false;
    function update() {
      header.classList.toggle('is-scrolled', window.scrollY > 8);
      ticking = false;
    }
    window.addEventListener('scroll', function () {
      if (!ticking) {
        ticking = true;
        window.requestAnimationFrame(update);
      }
    }, { passive: true });
    update();
  })();

  // ---- Hero carousel -----------------------------------------------------
  (function () {
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
      if (userAction) start();
    }

    function next() { goTo(current + 1, false); }
    function stop() { if (timer) { clearInterval(timer); timer = null; } }
    // Under prefers-reduced-motion the carousel stays on the first slide: visitors
    // can still move it themselves with the dots or the arrow keys.
    function start() { stop(); if (!reduceMotion) timer = setInterval(next, interval); }

    dots.forEach(function (dot, i) {
      dot.addEventListener('click', function () { goTo(i, true); });
    });

    carousel.addEventListener('mouseenter', stop);
    carousel.addEventListener('mouseleave', start);
    // Only the indicator buttons are focusable inside the carousel, so pausing on
    // their focus is enough to keep the active slide still for keyboard visitors.
    carousel.addEventListener('focusin', stop);
    carousel.addEventListener('focusout', function (e) {
      if (!carousel.contains(e.relatedTarget)) start();
    });
    carousel.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowRight') { goTo(current + 1, true); e.preventDefault(); }
      else if (e.key === 'ArrowLeft') { goTo(current - 1, true); e.preventDefault(); }
    });

    start();
  })();
})();

