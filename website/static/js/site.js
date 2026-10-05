/* Cloud for Kids: site-wide interactivity (theme, accessibility, reveal, counters, confetti). */
(function () {
  var root = document.documentElement;

  function store(k, v) {
    try {
      if (v === undefined) return localStorage.getItem(k);
      localStorage.setItem(k, v);
    } catch (e) { /* storage may be blocked */ }
    return null;
  }

  function applyPrefs() {
    var theme = store('c4k-theme') || 'light';
    root.setAttribute('data-bs-theme', theme);
    root.classList.remove('text-lg', 'text-xl');
    var size = store('c4k-text');
    if (size === 'lg') root.classList.add('text-lg');
    if (size === 'xl') root.classList.add('text-xl');
    root.classList.toggle('easy-read', store('c4k-easy') === '1');
  }
  applyPrefs();

  window.c4kConfetti = function () {
    if (window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    var c = document.createElement('canvas');
    c.id = 'confetti-canvas';
    document.body.appendChild(c);
    var ctx = c.getContext('2d'), w = (c.width = innerWidth), h = (c.height = innerHeight);
    var colors = ['#1CA7EC', '#FFC93C', '#2FBF71', '#FF6B6B', '#8B6BE8'];
    var bits = [];
    for (var i = 0; i < 140; i++) {
      bits.push({
        x: w / 2 + (Math.random() - 0.5) * 200, y: h * 0.35,
        vx: (Math.random() - 0.5) * 14, vy: Math.random() * -12 - 4,
        s: Math.random() * 8 + 4, r: Math.random() * 6, vr: (Math.random() - 0.5) * 0.4, c: colors[i % colors.length]
      });
    }
    var t0 = performance.now();
    (function frame(t) {
      ctx.clearRect(0, 0, w, h);
      bits.forEach(function (b) {
        b.vy += 0.35; b.x += b.vx; b.y += b.vy; b.r += b.vr;
        ctx.save(); ctx.translate(b.x, b.y); ctx.rotate(b.r); ctx.fillStyle = b.c;
        ctx.fillRect(-b.s / 2, -b.s / 4, b.s, b.s / 2); ctx.restore();
      });
      if (t - t0 < 2800) requestAnimationFrame(frame); else c.remove();
    })(t0);
  };

  document.addEventListener('DOMContentLoaded', function () {
    /* ---- Accessibility panel ---- */
    var fab = document.getElementById('a11y-fab'), panel = document.getElementById('a11y-panel');
    if (fab && panel) {
      fab.addEventListener('click', function () {
        var open = panel.classList.toggle('open');
        fab.setAttribute('aria-expanded', open ? 'true' : 'false');
      });
      panel.addEventListener('click', function (e) {
        var b = e.target.closest('[data-pref]');
        if (!b) return;
        var pref = b.getAttribute('data-pref'), val = b.getAttribute('data-value');
        if (pref === 'theme') store('c4k-theme', root.getAttribute('data-bs-theme') === 'dark' ? 'light' : 'dark');
        if (pref === 'text') store('c4k-text', val);
        if (pref === 'easy') store('c4k-easy', store('c4k-easy') === '1' ? '0' : '1');
        applyPrefs();
      });
    }

    /* ---- Scroll reveal ---- */
    var items = document.querySelectorAll('.reveal');
    if ('IntersectionObserver' in window) {
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          if (en.isIntersecting) { en.target.classList.add('in'); io.unobserve(en.target); }
        });
      }, { threshold: 0.12 });
      items.forEach(function (el) { io.observe(el); });
    } else {
      items.forEach(function (el) { el.classList.add('in'); });
    }

    /* ---- Count-up numbers ---- */
    var reduce = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
    document.querySelectorAll('.stat-value').forEach(function (el) {
      var m = el.textContent.trim().match(/^(\d+(?:\.\d+)?)(%?)$/);
      if (!m || reduce || !('IntersectionObserver' in window)) return;
      var target = parseFloat(m[1]), suffix = m[2], dec = (m[1].split('.')[1] || '').length;
      el.textContent = (0).toFixed(dec) + suffix;
      var o = new IntersectionObserver(function (es) {
        es.forEach(function (e) {
          if (!e.isIntersecting) return;
          o.disconnect();
          var t0 = performance.now(), dur = 1200;
          (function tick(t) {
            var p = Math.min((t - t0) / dur, 1), eased = 1 - Math.pow(1 - p, 3);
            el.textContent = (target * eased).toFixed(dec) + suffix;
            if (p < 1) requestAnimationFrame(tick);
          })(t0);
        });
      });
      o.observe(el);
    });

    /* ---- Celebrate success messages ---- */
    document.querySelectorAll('.alert-success').forEach(function (a) {
      if (/Badge earned|Nice work|enrolled/i.test(a.textContent)) window.c4kConfetti();
    });
  });
})();
