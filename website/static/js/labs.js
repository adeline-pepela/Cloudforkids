/* Cloud for Kids: Practice Lab simulations. Each lab runs in the browser; finishing one tells the server so XP and badges update. */
(function () {
  var root = document.getElementById('lab');
  if (!root) return;
  var slug = root.getAttribute('data-lab');
  var user = root.getAttribute('data-user') || 'me';
  var finished = false;

  function $(sel, ctx) { return (ctx || root).querySelector(sel); }
  function $all(sel, ctx) { return Array.prototype.slice.call((ctx || root).querySelectorAll(sel)); }
  function wait(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
  function csrf() { var el = document.querySelector('input[name=csrfmiddlewaretoken]'); return el ? el.value : ''; }

  function complete() {
    if (finished) return;
    finished = true;
    var banner = document.getElementById('lab-done'), text = document.getElementById('lab-done-text');
    fetch(root.getAttribute('data-complete-url'), {
      method: 'POST', headers: { 'X-CSRFToken': csrf(), 'X-Requested-With': 'XMLHttpRequest' }, credentials: 'same-origin'
    }).then(function (r) { return r.json(); }).then(function (d) {
      var msg;
      if (d.created) {
        msg = 'You earned +' + d.xp_gained + ' XP! You are now level ' + d.level + ' (' + d.level_name + ').';
        if (d.badges && d.badges.length) msg += ' New badge: ' + d.badges.join(', ') + '!';
      } else {
        msg = 'You already finished this lab, so no extra XP this time. Great practice!';
      }
      text.textContent = msg;
    }).catch(function () {
      text.textContent = 'Nice work! (We could not save your progress. Check your internet and try again.)';
    }).then(function () {
      banner.classList.add('show');
      banner.scrollIntoView({ behavior: 'smooth', block: 'center' });
      if (window.c4kConfetti) window.c4kConfetti();
    });
  }

  var labs = {};

  /* ------------------------------------------------------------------ */
  labs['cloud-save-lab'] = function () {
    var sel = null, busy = false;
    var packet = $('#cs-packet'), pIcon = $('#cs-packet-icon'), caption = $('#cs-caption');
    var save = $('#cs-save'), openBtn = $('#cs-open'), copies = $all('.cs-copies .copy');
    var seg1 = $('#cs-seg1'), seg2 = $('#cs-seg2'), trail1 = $('#cs-trail1'), trail2 = $('#cs-trail2');
    var nodes = { d: $('#cs-n-device'), n: $('#cs-n-net'), c: $('#cs-n-cloud') };
    var len1 = seg1.getTotalLength(), len2 = seg2.getTotalLength();
    [trail1, trail2].forEach(function (t, i) { var L = i ? len2 : len1; t.style.strokeDasharray = L; t.style.strokeDashoffset = L; });

    function active(k) { Object.keys(nodes).forEach(function (x) { nodes[x].classList.toggle('active', x === k); }); }
    function place(path, len, f) { var p = path.getPointAtLength(len * f); packet.setAttribute('transform', 'translate(' + p.x + ' ' + p.y + ')'); }
    /* Slide the file along one curved piece of the road, drawing the trail as it goes (reverse = coming back). */
    function travel(path, trail, len, ms, reverse) {
      return new Promise(function (resolve) {
        var t0 = null;
        function frame(ts) {
          if (t0 === null) t0 = ts;
          var raw = Math.min((ts - t0) / ms, 1), e = raw < 0.5 ? 2 * raw * raw : 1 - Math.pow(-2 * raw + 2, 2) / 2;
          var f = reverse ? 1 - e : e;
          place(path, len, f);
          trail.style.strokeDashoffset = len * (1 - f);
          if (raw < 1) requestAnimationFrame(frame); else resolve();
        }
        requestAnimationFrame(frame);
      });
    }
    active('d');

    $('#cs-files').addEventListener('click', function (e) {
      var b = e.target.closest('.pick-file'); if (!b || busy) return;
      $all('.pick-file').forEach(function (x) { x.classList.remove('selected'); });
      b.classList.add('selected'); sel = b.getAttribute('data-name');
      pIcon.textContent = String.fromCharCode(parseInt(b.getAttribute('data-code'), 16));
      save.disabled = false; caption.textContent = 'Ready! Press "Save to the cloud".';
    });
    save.addEventListener('click', async function () {
      if (!sel || busy) return; busy = true; save.disabled = true;
      active('d'); caption.textContent = '1. Your device turns ' + sel + ' into data, like tiny digital envelopes.';
      await wait(1500);
      caption.textContent = '2. The data sets off across the internet, through cables and Wi-Fi.';
      await travel(seg1, trail1, len1, 2200); active('n');
      await wait(500);
      caption.textContent = '3. It keeps travelling, all the way to a data centre...';
      await travel(seg2, trail2, len2, 2400); active('c');
      for (var i = 0; i < copies.length; i++) { copies[i].classList.add('on'); await wait(450); }
      caption.textContent = '4. ...where a cloud server keeps 3 safe copies. Saved! Now try opening it on another device.';
      save.classList.add('d-none'); openBtn.classList.remove('d-none'); busy = false;
    });
    openBtn.addEventListener('click', async function () {
      if (busy) return; busy = true; openBtn.disabled = true;
      caption.textContent = 'On a different device you sign in and ask the cloud for ' + sel + '...';
      await wait(1300);
      await travel(seg2, trail2, len2, 2000, true); active('n');
      await wait(300);
      await travel(seg1, trail1, len1, 1800, true); active('d');
      caption.textContent = 'It is here! The file lives in the cloud, not on one device, so you can reach it from anywhere.';
      busy = false; complete();
    });
  };

  /* ------------------------------------------------------------------ */
  labs['block-coder-lab'] = function () {
    var N = 5;
    var levels = [
      { start: [0, 4], goal: [4, 0], walls: [[2, 1], [2, 2], [2, 3]] },
      { start: [0, 4], goal: [4, 4], walls: [[1, 4], [2, 4], [3, 4]] }
    ];
    var li = 0, prog = [], busy = false;
    var grid = $('#bc-grid'), progEl = $('#bc-prog'), msg = $('#bc-msg');
    var arrows = { up: 'bi-arrow-up', down: 'bi-arrow-down', left: 'bi-arrow-left', right: 'bi-arrow-right' };
    var delta = { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] };

    function isWall(x, y) { return levels[li].walls.some(function (w) { return w[0] === x && w[1] === y; }); }
    function draw(pos) {
      var L = levels[li], html = '';
      for (var y = 0; y < N; y++) for (var x = 0; x < N; x++) {
        var cls = 'bc-cell', inner = '';
        if (isWall(x, y)) { cls += ' wall'; inner = '<i class="bi bi-bricks"></i>'; }
        else if (x === L.goal[0] && y === L.goal[1]) { cls += ' goal'; inner = '<i class="bi bi-cloud-fill"></i>'; }
        if (pos[0] === x && pos[1] === y) inner = '<i class="bi bi-robot bc-robot" style="color:#8B6BE8"></i>';
        html += '<div class="' + cls + '">' + inner + '</div>';
      }
      grid.innerHTML = html;
    }
    function renderProg() {
      progEl.innerHTML = prog.length ? prog.map(function (d) {
        return '<span class="bc-block ' + d + '"><i class="bi ' + arrows[d] + '"></i></span>';
      }).join('') : '<span class="text-secondary small">Tap the blocks above to build your program.</span>';
    }
    function setLevel(i) {
      li = i; prog = []; msg.textContent = '';
      $('#bc-level-text').textContent = 'Level ' + (li + 1) + ' of ' + levels.length;
      draw(levels[li].start); renderProg();
    }
    $('#bc-palette').addEventListener('click', function (e) {
      var b = e.target.closest('[data-dir]'); if (!b || busy || prog.length >= 14) return;
      prog.push(b.getAttribute('data-dir')); renderProg();
    });
    $('#bc-undo').addEventListener('click', function () { if (!busy) { prog.pop(); renderProg(); } });
    $('#bc-clear').addEventListener('click', function () { if (!busy) { prog = []; renderProg(); msg.textContent = ''; draw(levels[li].start); } });
    $('#bc-run').addEventListener('click', async function () {
      if (busy || !prog.length) { if (!prog.length) msg.textContent = 'Add some blocks first!'; return; }
      busy = true; msg.textContent = '';
      var pos = levels[li].start.slice(); draw(pos);
      for (var i = 0; i < prog.length; i++) {
        await wait(450);
        var d = delta[prog[i]], nx = pos[0] + d[0], ny = pos[1] + d[1];
        if (nx < 0 || ny < 0 || nx >= N || ny >= N || isWall(nx, ny)) {
          msg.textContent = 'Bump! The robot hit something. Fix your program and try again.'; await wait(500); draw(levels[li].start); busy = false; return;
        }
        pos = [nx, ny]; draw(pos);
      }
      if (pos[0] === levels[li].goal[0] && pos[1] === levels[li].goal[1]) {
        if (li < levels.length - 1) {
          msg.textContent = 'You made it! On to the next level...'; await wait(1400); setLevel(li + 1);
        } else { msg.textContent = 'The robot reached the cloud!'; complete(); }
      } else {
        msg.textContent = 'Not there yet. Where does the robot need to go?'; await wait(600); draw(levels[li].start);
      }
      busy = false;
    });
    setLevel(0);
  };

  /* ------------------------------------------------------------------ */
  labs['password-lab'] = function () {
    var input = $('#pw-input'), bar = $('#pw-bar'), label = $('#pw-label'), timeEl = $('#pw-time');
    var common = ['password', '123456', 'qwerty', 'letmein', 'iloveyou', 'abc123', 'admin', 'welcome', 'cloud', 'kenya'];
    function human(sec) {
      if (sec < 1) return 'instantly';
      if (sec < 60) return Math.round(sec) + ' seconds';
      if (sec < 3600) return Math.round(sec / 60) + ' minutes';
      if (sec < 86400) return Math.round(sec / 3600) + ' hours';
      if (sec < 31536000) return Math.round(sec / 86400) + ' days';
      var y = sec / 31536000;
      if (y < 1000) return Math.round(y) + ' years';
      if (y < 1e6) return Math.round(y / 1000) + ' thousand years';
      return 'millions of years';
    }
    function check() {
      var v = input.value, ok = {};
      ok.len = v.length >= 10; ok.upper = /[A-Z]/.test(v); ok.lower = /[a-z]/.test(v); ok.digit = /\d/.test(v); ok.symbol = /[^A-Za-z0-9]/.test(v);
      var lc = v.toLowerCase(), nm = user.toLowerCase();
      ok.common = v.length > 0 && !common.some(function (c) { return lc.indexOf(c) !== -1; }) && !(nm.length > 2 && lc.indexOf(nm) !== -1);
      var pool = (ok.lower ? 26 : 0) + (ok.upper ? 26 : 0) + (ok.digit ? 10 : 0) + (ok.symbol ? 32 : 0);
      var seconds = pool ? Math.pow(pool, v.length) / 1e10 : 0;
      if (!ok.common && v.length) seconds = Math.min(seconds, 1);
      var score = Object.keys(ok).filter(function (k) { return ok[k]; }).length;
      var pct = v ? Math.min(100, Math.round((score / 6) * 70 + Math.min(v.length, 16) / 16 * 30)) : 0;
      var strong = Object.keys(ok).every(function (k) { return ok[k]; });
      bar.style.width = pct + '%';
      bar.style.background = strong ? '#2FBF71' : (pct > 55 ? '#FFC93C' : '#FF6B6B');
      label.textContent = !v ? 'Type something to start' : (strong ? 'Strong!' : (pct > 55 ? 'Getting better' : 'Weak'));
      timeEl.textContent = v ? 'A computer could crack it: ' + human(seconds) : 'A computer could crack it: —';
      $all('#pw-checks li').forEach(function (li) {
        var good = ok[li.getAttribute('data-rule')];
        li.classList.toggle('ok', !!good);
        li.querySelector('i').className = 'bi ' + (good ? 'bi-check-circle-fill' : 'bi-circle');
      });
      if (strong) complete();
    }
    input.addEventListener('input', check);
    $('#pw-toggle').addEventListener('click', function () { input.type = input.type === 'text' ? 'password' : 'text'; });
    check();
  };

  /* ------------------------------------------------------------------ */
  labs['service-match-lab'] = function () {
    var pairs = [
      { id: 'storage', job: 'Keep my photos and files safe', icon: 'bi-folder-fill', svc: 'Storage (like Amazon S3)', sicon: 'bi-bucket-fill' },
      { id: 'server', job: 'Run the programs behind my website', icon: 'bi-globe2', svc: 'Servers (like Amazon EC2)', sicon: 'bi-pc-display' },
      { id: 'db', job: 'Remember my customers and orders', icon: 'bi-people-fill', svc: 'Database (like Amazon RDS)', sicon: 'bi-database-fill' },
      { id: 'fn', job: 'Do one small task when something happens', icon: 'bi-lightning-charge-fill', svc: 'Functions (like AWS Lambda)', sicon: 'bi-braces' }
    ];
    var jobsEl = $('#sm-jobs'), svcEl = $('#sm-services'), msg = $('#sm-msg');
    var chosenJob = null, matched = 0;
    function shuffle(a) { return a.slice().sort(function () { return Math.random() - 0.5; }); }
    pairs.forEach(function (p) {
      jobsEl.insertAdjacentHTML('beforeend', '<button type="button" class="sm-item" data-id="' + p.id + '" data-side="job"><i class="bi ' + p.icon + '"></i>' + p.job + '</button>');
    });
    shuffle(pairs).forEach(function (p) {
      svcEl.insertAdjacentHTML('beforeend', '<button type="button" class="sm-item" data-id="' + p.id + '" data-side="svc"><i class="bi ' + p.sicon + '"></i>' + p.svc + '</button>');
    });
    root.addEventListener('click', function (e) {
      var b = e.target.closest('.sm-item'); if (!b || b.classList.contains('ok')) return;
      if (b.getAttribute('data-side') === 'job') {
        $all('#sm-jobs .sm-item').forEach(function (x) { x.classList.remove('sel'); });
        b.classList.add('sel'); chosenJob = b; msg.textContent = 'Now pick the service that does this job.'; return;
      }
      if (!chosenJob) { msg.textContent = 'Tap a job on the left first.'; return; }
      if (chosenJob.getAttribute('data-id') === b.getAttribute('data-id')) {
        chosenJob.classList.remove('sel'); chosenJob.classList.add('ok'); b.classList.add('ok'); chosenJob = null; matched++;
        msg.textContent = 'Yes! That is a match. ' + (pairs.length - matched) + ' to go.';
        if (matched === pairs.length) { msg.textContent = 'You matched them all!'; complete(); }
      } else {
        b.classList.add('bad'); setTimeout(function () { b.classList.remove('bad'); }, 400);
        msg.textContent = 'Not quite. Think about what that service is best at.';
      }
    });
  };

  /* ------------------------------------------------------------------ */
  labs['web-page-lab'] = function () {
    var code = $('#wp-code'), frame = $('#wp-frame'), publish = $('#wp-publish'), status = $('#wp-status');
    var publishing = false;
    function words(s) { return (s || '').trim().split(/\s+/).filter(Boolean).length; }
    function update() {
      var html = code.value;
      frame.srcdoc = '<!doctype html><meta charset="utf-8"><body style="font-family:sans-serif;padding:12px">' + html + '</body>';
      var doc = new DOMParser().parseFromString(html, 'text/html');
      var h1 = doc.querySelector('h1'), p = doc.querySelector('p');
      var ok = {
        h1: !!h1 && h1.textContent.trim().length > 0 && h1.textContent.trim().toLowerCase() !== 'hello!',
        p: !!p && words(p.textContent) >= 5 && p.textContent.indexOf('Write something about yourself') === -1,
        color: /color\s*[:=]/i.test(html)
      };
      $all('#wp-checks li').forEach(function (li) {
        var good = ok[li.getAttribute('data-rule')];
        li.classList.toggle('ok', !!good);
        li.querySelector('i').className = 'bi ' + (good ? 'bi-check-circle-fill' : 'bi-circle');
      });
      publish.disabled = publishing || !(ok.h1 && ok.p && ok.color);
    }
    code.addEventListener('input', update);
    publish.addEventListener('click', async function () {
      publishing = true; publish.disabled = true;
      var name = (user || 'me').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'me';
      status.textContent = '1. Saving your page to cloud storage...'; await wait(1300);
      status.textContent = '2. Starting a web server to share it...'; await wait(1300);
      status.innerHTML = '3. Live! Your page is on the internet (pretend) at: <span class="wp-url">https://' + name + '.cloudforkids.app</span>';
      publishing = false; complete();
    });
    update();
  };

  if (labs[slug]) labs[slug]();
})();
