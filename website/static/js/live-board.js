/* Shared whiteboard for live classes. Strokes travel over the LiveKit data channel (topic "wb") as points scaled 0-1,
   so the board looks the same on a phone and a laptop. The teacher's browser keeps the full drawing and sends it to
   anyone who joins late. */
(function () {
  'use strict';
  var canvas, ctx, wrap, send, strokes = [], byId = {}, drawing = null, pending = [], color = '#1F2937', allowed = false, timer;

  function size() {
    if (!canvas) return;
    var r = wrap.getBoundingClientRect(), ratio = window.devicePixelRatio || 1;
    var w = Math.min(r.width, r.height * 1.6), h = w / 1.6;
    canvas.style.width = w + 'px';
    canvas.style.height = h + 'px';
    canvas.width = Math.max(1, Math.round(w * ratio));
    canvas.height = Math.max(1, Math.round(h * ratio));
    redraw();
  }

  function width(stroke) { return (stroke.c === '#FFFFFF' ? 0.03 : 0.004) * canvas.width; }

  function paint(stroke, from) {
    var p = stroke.p;
    if (!p.length) return;
    ctx.strokeStyle = stroke.c;
    ctx.lineWidth = width(stroke);
    ctx.lineCap = ctx.lineJoin = 'round';
    ctx.beginPath();
    var start = Math.max(0, (from || 0) - 1);
    ctx.moveTo(p[start][0] * canvas.width, p[start][1] * canvas.height);
    for (var i = start + 1; i < p.length; i++) ctx.lineTo(p[i][0] * canvas.width, p[i][1] * canvas.height);
    if (p.length === 1) ctx.lineTo(p[0][0] * canvas.width + 0.1, p[0][1] * canvas.height);
    ctx.stroke();
  }

  function redraw() {
    ctx.fillStyle = '#FFFFFF';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    strokes.forEach(function (s) { paint(s, 0); });
  }

  function add(id, c, pts) {
    var s = byId[id];
    if (!s) { s = byId[id] = { id: id, c: c, p: [] }; strokes.push(s); }
    var from = s.p.length;
    s.p = s.p.concat(pts);
    paint(s, from);
    if (strokes.length > 2000) { var old = strokes.shift(); delete byId[old.id]; }
  }

  function point(e) {
    var r = canvas.getBoundingClientRect();
    return [Math.round(((e.clientX - r.left) / r.width) * 1000) / 1000, Math.round(((e.clientY - r.top) / r.height) * 1000) / 1000];
  }

  function flush() {
    if (drawing && pending.length) {
      send({ t: 's', id: drawing.id, c: drawing.c, p: pending });
      pending = [];
    }
  }

  function down(e) {
    if (!allowed) return;
    e.preventDefault();
    canvas.setPointerCapture(e.pointerId);
    drawing = { id: Math.random().toString(36).slice(2, 10), c: color };
    var pt = point(e);
    add(drawing.id, color, [pt]);
    pending = [pt];
    timer = setInterval(flush, 60);
  }
  function move(e) {
    if (!drawing) return;
    var pt = point(e);
    add(drawing.id, drawing.c, [pt]);
    pending.push(pt);
  }
  function up() {
    if (!drawing) return;
    flush();
    clearInterval(timer);
    drawing = null;
  }

  window.C4KBoard = {
    init: function (opts) {
      wrap = opts.wrap;
      canvas = opts.canvas;
      ctx = canvas.getContext('2d');
      send = opts.send;
      canvas.addEventListener('pointerdown', down);
      canvas.addEventListener('pointermove', move);
      canvas.addEventListener('pointerup', up);
      canvas.addEventListener('pointercancel', up);
      window.addEventListener('resize', size);
      document.querySelectorAll('.lv-swatch').forEach(function (b) {
        b.addEventListener('click', function () {
          color = b.dataset.color;
          document.querySelectorAll('.lv-swatch').forEach(function (x) { x.classList.toggle('active', x === b); });
        });
      });
    },
    shown: function () { size(); },
    allowDraw: function (yes) { allowed = !!yes; canvas.classList.toggle('can-draw', allowed); },
    clear: function (broadcast) {
      strokes = []; byId = {};
      if (ctx) redraw();
      if (broadcast) send({ t: 'clear' });
    },
    /* The whole drawing as a few small messages (LiveKit caps one data message at about 15 KB). */
    stateMessages: function () {
      var out = [{ t: 'clear' }], batch = [], len = 0;
      strokes.forEach(function (st) {
        for (var i = 0; i < st.p.length; i += 300) {
          var m = { t: 's', id: st.id, c: st.c, p: st.p.slice(i, i + 300) }, n = JSON.stringify(m).length;
          if (len + n > 12000 && batch.length) { out.push({ t: 'batch', m: batch }); batch = []; len = 0; }
          batch.push(m); len += n;
        }
      });
      if (batch.length) out.push({ t: 'batch', m: batch });
      return out;
    },
    hasDrawing: function () { return strokes.length > 0; },
    receive: function (msg) {
      if (!ctx) return;
      if (msg.t === 's' && msg.id && Array.isArray(msg.p)) {
        add(String(msg.id).slice(0, 16), /^#[0-9A-F]{6}$/i.test(msg.c) ? msg.c : '#1F2937', msg.p.slice(0, 500).filter(function (p) {
          return Array.isArray(p) && p.length === 2 && isFinite(p[0]) && isFinite(p[1]);
        }));
      } else if (msg.t === 'clear') {
        window.C4KBoard.clear(false);
      } else if (msg.t === 'batch' && Array.isArray(msg.m)) {
        msg.m.forEach(function (m) { if (m && m.t === 's') window.C4KBoard.receive(m); });
      }
    }
  };
})();
