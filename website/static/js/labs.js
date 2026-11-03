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

  /* ================================================================== */
  /* Shared helpers for the labs below                                   */
  function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function shuffled(a) { var b = a.slice(); for (var i = b.length - 1; i > 0; i--) { var j = Math.floor(Math.random() * (i + 1)), t = b[i]; b[i] = b[j]; b[j] = t; } return b; }
  function tick(listSel, rule) {
    var li = $(listSel + ' li[data-rule="' + rule + '"]'); if (!li || li.classList.contains('ok')) return;
    li.classList.add('ok'); li.querySelector('i').className = 'bi bi-check-circle-fill';
  }
  function allTicked(listSel) { return $all(listSel + ' li').every(function (li) { return li.classList.contains('ok'); }); }

  /* Sort cards into bins: tap a card, then tap the bin it belongs in. */
  function sorter(bins, items, doneText) {
    var box = $('#sorter'), chosen = null, left = items.length;
    box.innerHTML = '<div class="sort-pool" id="sort-pool"></div><div class="sort-bins" id="sort-bins"></div><p class="fw-bold mt-3 mb-0" id="sort-msg" aria-live="polite">Tap a card to pick it up.</p>';
    var pool = $('#sort-pool'), binsEl = $('#sort-bins'), msg = $('#sort-msg');
    shuffled(items).forEach(function (it, n) {
      pool.insertAdjacentHTML('beforeend', '<button type="button" class="sm-item sort-card" data-n="' + items.indexOf(it) + '"><i class="bi bi-' + it.icon + '" aria-hidden="true"></i>' + esc(it.label) + '</button>');
    });
    bins.forEach(function (b) {
      binsEl.insertAdjacentHTML('beforeend', '<button type="button" class="sort-bin" data-bin="' + b.id + '"><span class="sort-bin-head"><i class="bi bi-' + b.icon + '" aria-hidden="true"></i> ' + esc(b.label) +
        ' <span class="sort-count">0</span></span><span class="sort-bin-items"></span></button>');
    });
    box.addEventListener('click', function (e) {
      var card = e.target.closest('.sort-card');
      if (card) {
        $all('.sort-card', box).forEach(function (x) { x.classList.remove('sel'); });
        card.classList.add('sel'); chosen = card; msg.textContent = 'Now tap where "' + items[card.getAttribute('data-n')].label + '" belongs.'; return;
      }
      var bin = e.target.closest('.sort-bin'); if (!bin) return;
      if (!chosen) { msg.textContent = 'Tap a card first.'; return; }
      var it = items[chosen.getAttribute('data-n')];
      if (it.bin === bin.getAttribute('data-bin')) {
        var chip = document.createElement('span'); chip.className = 'sort-chip'; chip.textContent = it.label;
        bin.querySelector('.sort-bin-items').appendChild(chip);
        var count = bin.querySelector('.sort-count'); count.textContent = +count.textContent + 1;
        chosen.remove(); chosen = null; left--;
        msg.textContent = 'Correct! ' + it.why + (left ? ' (' + left + ' to go)' : '');
        if (!left) { msg.textContent = doneText; complete(); }
      } else {
        bin.classList.add('bad'); setTimeout(function () { bin.classList.remove('bad'); }, 400);
        msg.textContent = 'Not quite. ' + (it.hint || 'Think again about what "' + it.label + '" is.');
      }
    });
  }

  /* Put steps in the right order: tap the step that comes next. Calls onDone when every step is placed. */
  function sequence(steps, onDone) {
    var tray = $('#seq-tray'), slots = $('#seq-slots'), msg = $('#seq-msg'), next = 0;
    steps.forEach(function (s, i) { slots.insertAdjacentHTML('beforeend', '<li class="seq-slot" data-i="' + i + '"><span class="text-secondary">Empty</span></li>'); });
    shuffled(steps).forEach(function (s) {
      tray.insertAdjacentHTML('beforeend', '<button type="button" class="sm-item seq-part" data-i="' + steps.indexOf(s) + '"><i class="bi bi-' + s.icon + '" aria-hidden="true"></i>' + esc(s.label) + '</button>');
    });
    tray.addEventListener('click', function (e) {
      var b = e.target.closest('.seq-part'); if (!b) return;
      var i = +b.getAttribute('data-i'), s = steps[i];
      if (i === next) {
        var slot = $('.seq-slot[data-i="' + i + '"]', slots);
        slot.classList.add('on');
        slot.innerHTML = '<i class="bi bi-' + s.icon + '" aria-hidden="true"></i><span><strong>' + esc(s.label) + '</strong><br><small>' + esc(s.job) + '</small></span>';
        b.remove(); next++;
        msg.textContent = next < steps.length ? 'Yes! ' + s.job + ' What comes next?' : 'All in place!';
        if (next === steps.length && onDone) onDone();
      } else {
        b.classList.add('bad'); setTimeout(function () { b.classList.remove('bad'); }, 400);
        msg.textContent = 'Not yet! ' + s.needs;
      }
    });
  }

  /* ------------------------------------------------------------------ */
  labs['build-a-computer-lab'] = function () {
    sequence([
      { label: 'Power Supply', icon: 'lightning-charge-fill', job: 'It turns electricity from the wall socket into power for every part.', needs: '' },
      { label: 'Motherboard', icon: 'motherboard-fill', job: 'The main circuit board: every other part plugs into it.', needs: 'The motherboard gets its power from the power supply, so the power supply goes in first.' },
      { label: 'CPU', icon: 'cpu-fill', job: 'The brain of the computer: it runs every instruction.', needs: 'The CPU plugs into a socket on the motherboard, so the motherboard must go in first.' },
      { label: 'Cooling Fan', icon: 'fan', job: 'It sits on the CPU and stops it from overheating.', needs: 'The fan sits on top of the CPU, so the CPU must go in first.' },
      { label: 'RAM', icon: 'memory', job: 'Fast, temporary memory where the CPU does its work.', needs: 'RAM clicks into the motherboard right next to the CPU. Finish the CPU and its fan first.' },
      { label: 'Storage (SSD)', icon: 'device-ssd-fill', job: 'It keeps the operating system, programs and files, even when the power is off.', needs: 'Storage goes in once the parts around the CPU (fan and RAM) are in place.' },
      { label: 'Monitor, Keyboard & Mouse', icon: 'plug-fill', job: 'Plug in the output device (monitor) and the input devices (keyboard and mouse).', needs: 'Plug in the outside devices last, once everything inside the case is in place.' }
    ], function () {
      $('#seq-msg').textContent = 'Your computer is built! Now switch it on.';
      $('#bc-power-wrap').classList.remove('d-none');
    });
    var power = $('#bc-power'), screen = $('#bc-screen');
    power.addEventListener('click', async function () {
      power.disabled = true;
      var lines = ['The power supply sends electricity to every part...', 'The CPU wakes up and runs its startup instructions from ROM (the BIOS)...',
        'The operating system loads from storage into RAM...', 'Desktop ready! You press the K key (input)...',
        'The CPU processes the key press (process)...', 'The monitor shows "K" (output). Input, process, output: your computer works!'];
      screen.innerHTML = '';
      for (var i = 0; i < lines.length; i++) {
        await wait(1100);
        screen.insertAdjacentHTML('beforeend', '<div>&gt; ' + esc(lines[i]) + '</div>');
      }
      complete();
    });
  };

  /* ------------------------------------------------------------------ */
  labs['hardware-software-lab'] = function () {
    var H = function (label, icon, why) { return { label: label, icon: icon, bin: 'hw', why: why, hint: label + ' is a physical thing you can touch.' }; };
    var S = function (label, icon, why) { return { label: label, icon: icon, bin: 'sw', why: why, hint: label + ' is made of instructions: you cannot touch it.' }; };
    sorter([{ id: 'hw', label: 'Hardware', icon: 'motherboard-fill' }, { id: 'sw', label: 'Software', icon: 'window-stack' }], [
      H('CPU', 'cpu-fill', 'The CPU is a chip you can hold: hardware.'), H('RAM', 'memory', 'RAM is a memory chip: hardware.'),
      H('Monitor', 'display', 'A monitor is a physical output device: hardware.'), H('Keyboard', 'keyboard-fill', 'A keyboard is a physical input device: hardware.'),
      H('Mouse', 'mouse-fill', 'A mouse is a physical input device: hardware.'), H('Motherboard', 'motherboard-fill', 'The motherboard is a circuit board: hardware.'),
      H('Speaker', 'speaker-fill', 'A speaker is a physical output device: hardware.'), H('Storage drive', 'device-ssd-fill', 'A storage drive is a device you can touch: hardware.'),
      H('Screen', 'phone-fill', 'A screen is a physical part: hardware.'),
      S('WhatsApp', 'chat-dots-fill', 'WhatsApp is an app: software.'), S('Facebook app', 'people-fill', 'Facebook is an app and website running on servers: software.'),
      S('Python', 'code-slash', 'Python is a programming language for writing software.'), S('Chrome browser', 'globe2', 'A browser is a program: software.'),
      S('Video game', 'controller', 'A game is a program: software.'), S('Email program', 'envelope-fill', 'An email program is software.'),
      S('Calculator app', 'calculator-fill', 'A calculator app is software.'), S('Antivirus', 'shield-fill-check', 'Antivirus is utility software.'),
      S('TikTok app', 'music-note-beamed', 'TikTok is a mobile app: software.')
    ], 'All sorted! Hardware is what you can touch; software is the instructions that tell it what to do.');
  };

  /* ------------------------------------------------------------------ */
  labs['file-organizer-lab'] = function () {
    var path = function (folder, name) { return 'Its path is C: > Users > You > ' + folder + ' > ' + name; };
    var F = function (name, icon, bin, kind, folder) { return { label: name, icon: icon, bin: bin, why: '"' + name.slice(name.lastIndexOf('.')) + '" means ' + kind + '. ' + path(folder, name) + '.', hint: 'Look at the extension: "' + name.slice(name.lastIndexOf('.')) + '" is ' + kind + '.' }; };
    sorter([
      { id: 'doc', label: 'Documents', icon: 'file-earmark-text-fill' }, { id: 'pic', label: 'Pictures', icon: 'image-fill' },
      { id: 'mus', label: 'Music', icon: 'music-note-beamed' }, { id: 'vid', label: 'Videos', icon: 'film' }
    ], [
      F('essay.docx', 'file-earmark-word-fill', 'doc', 'a Word document', 'Documents'), F('notes.txt', 'file-earmark-text-fill', 'doc', 'a plain text file', 'Documents'),
      F('report.pdf', 'file-earmark-pdf-fill', 'doc', 'a PDF document', 'Documents'), F('grades.xlsx', 'file-earmark-spreadsheet-fill', 'doc', 'an Excel spreadsheet', 'Documents'),
      F('photo.jpg', 'file-earmark-image-fill', 'pic', 'a photograph', 'Pictures'), F('drawing.png', 'file-earmark-image-fill', 'pic', 'an image', 'Pictures'),
      F('dance.gif', 'file-earmark-image-fill', 'pic', 'an animated image', 'Pictures'), F('song.mp3', 'file-earmark-music-fill', 'mus', 'a music file', 'Music'),
      F('voice-note.wav', 'file-earmark-music-fill', 'mus', 'a sound file', 'Music'), F('birthday.mp4', 'file-earmark-play-fill', 'vid', 'a video', 'Videos'),
      F('old-film.avi', 'file-earmark-play-fill', 'vid', 'an older kind of video', 'Videos'), F('trip.mov', 'file-earmark-play-fill', 'vid', 'a video', 'Videos')
    ], 'The desktop is tidy! Every file is in the right folder, so you can find it in seconds.');
  };

  /* ------------------------------------------------------------------ */
  labs['service-model-lab'] = function () {
    var I = 'You manage the operating system and apps on rented infrastructure.', P = 'You bring the code; the platform runs it.', S = 'The whole app is ready to use in a browser.';
    sorter([{ id: 'iaas', label: 'IaaS', icon: 'hdd-rack-fill' }, { id: 'paas', label: 'PaaS', icon: 'code-slash' }, { id: 'saas', label: 'SaaS', icon: 'window' }], [
      { label: 'A bank wants to choose and manage its own operating system on rented servers', icon: 'bank', bin: 'iaas', why: 'That is IaaS. ' + I, hint: 'Who manages the operating system here?' },
      { label: 'A startup rents virtual machines (like AWS EC2) and installs its own software', icon: 'pc-display', bin: 'iaas', why: 'That is IaaS. ' + I, hint: 'Virtual machines are infrastructure.' },
      { label: 'A game studio needs full control of servers, storage and networking', icon: 'controller', bin: 'iaas', why: 'That is IaaS. ' + I, hint: 'Full control means the most work for the customer.' },
      { label: 'A student uploads code and wants it to run without managing any servers', icon: 'code-slash', bin: 'paas', why: 'That is PaaS (like Google App Engine). ' + P, hint: 'They only want to write code.' },
      { label: 'A shop runs a small function every time a photo is uploaded (like AWS Lambda)', icon: 'lightning-charge-fill', bin: 'paas', why: 'That is PaaS. ' + P, hint: 'The shop writes the function; the cloud runs it.' },
      { label: 'A team deploys its web app to Heroku so it can focus on coding', icon: 'rocket-takeoff-fill', bin: 'paas', why: 'That is PaaS. ' + P, hint: 'Focusing on coding is the clue.' },
      { label: 'A school wants email for every teacher, ready today (like Gmail)', icon: 'envelope-fill', bin: 'saas', why: 'That is SaaS. ' + S, hint: 'Nothing to build: they just want to use it.' },
      { label: 'A class needs video lessons with no setup (like Zoom)', icon: 'camera-video-fill', bin: 'saas', why: 'That is SaaS. ' + S, hint: 'A ready-made app.' },
      { label: 'A family stores and shares documents online (like Google Drive)', icon: 'folder-fill', bin: 'saas', why: 'That is SaaS. ' + S, hint: 'They use the app in a browser.' }
    ], 'All matched! More control means more work (IaaS); less control means less work (SaaS).');
  };

  /* ------------------------------------------------------------------ */
  labs['deploy-scale-lab'] = function () {
    sequence([
      { label: 'Write the code', icon: 'code-slash', job: 'You write the app in a language like Python or JavaScript.', needs: '' },
      { label: 'Test it locally', icon: 'check2-circle', job: 'Run it on your own computer first, so bugs never reach users.', needs: 'You need some code before there is anything to test.' },
      { label: 'Containerize it', icon: 'box-seam-fill', job: 'Pack the app and everything it needs into a Docker container.', needs: 'Test it first: never package code you have not checked.' },
      { label: 'Deploy to the cloud', icon: 'cloud-upload-fill', job: 'Upload the container to the cloud platform. Your app gets a live URL!', needs: 'The cloud runs containers, so containerize the app first.' },
      { label: 'Monitor it', icon: 'bar-chart-fill', job: 'Watch the logs, errors and speed on the dashboard.', needs: 'You cannot monitor an app that is not running yet. Deploy it first.' },
      { label: 'Update it', icon: 'arrow-repeat', job: 'Deploy a new version without any downtime, then the cycle starts again.', needs: 'Monitoring tells you what to improve, so monitor before you update.' }
    ], function () {
      $('#seq-msg').textContent = 'Your app is live! Now see what happens when it gets popular.';
      $('#ds-part2').classList.remove('d-none');
      draw();
    });
    var LEVELS = [100, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000, 200000, 500000], PER = 1000;
    var range = $('#ds-users'), auto = $('#ds-auto');
    function draw() {
      var users = LEVELS[+range.value], scaled = auto.checked, servers = scaled ? Math.max(1, Math.ceil(users / PER)) : 1;
      var load = users / (servers * PER), crashed = !scaled && load >= 20;
      var ms = Math.round(load <= 1 ? 80 : 80 * Math.pow(load, 1.3));
      $('#ds-users-text').textContent = users.toLocaleString();
      var icons = '', show = Math.min(servers, 14);
      for (var i = 0; i < show; i++) icons += '<i class="bi bi-hdd-rack-fill' + (crashed ? ' text-danger' : '') + '" aria-hidden="true"></i>';
      $('#ds-servers').innerHTML = icons + (servers > show ? ' <span class="small fw-bold">+' + (servers - show).toLocaleString() + ' more</span>' : '') + '<span class="visually-hidden">' + servers + ' servers</span>';
      var status = crashed ? 'Crashed! Users see errors' : ms <= 250 ? 'Fast' : ms <= 1500 ? 'Slow' : 'Very slow';
      $('#ds-time').textContent = crashed ? '-' : ms.toLocaleString() + ' ms';
      $('#ds-status').textContent = status;
      $('#ds-status').className = crashed || ms > 1500 ? 'text-danger' : ms > 250 ? 'text-warning' : 'text-success';
      if (!scaled && (crashed || ms > 250)) tick('#ds-checks', 'slow');
      if (scaled && users >= 50000 && ms <= 250) tick('#ds-checks', 'fast');
      if (allTicked('#ds-checks')) complete();
    }
    range.addEventListener('input', draw); auto.addEventListener('change', draw);
  };

  /* ------------------------------------------------------------------ */
  labs['sql-query-lab'] = function () {
    var COLS = ['name', 'grade', 'math', 'english', 'science', 'days_absent'], SUBJECTS = ['math', 'english', 'science'];
    var rows = [
      ['Amani', 9, 88, 72, 91, 2], ['Baraka', 8, 64, 80, 70, 12], ['Chebet', 9, 95, 85, 89, 0], ['Daudi', 7, 70, 60, 75, 15], ['Esther', 9, 79, 91, 84, 4],
      ['Faraji', 8, 91, 77, 68, 1], ['Gathoni', 7, 58, 88, 73, 11], ['Hamisi', 9, 66, 70, 62, 7], ['Imani', 8, 82, 94, 90, 3], ['Jabari', 7, 73, 65, 80, 0]
    ].map(function (r) { var o = {}; COLS.forEach(function (c, i) { o[c] = r[i]; }); return o; });
    var mode = $('#sq-mode'), colsBox = $('#sq-cols'), wcol = $('#sq-wcol'), op = $('#sq-op'), val = $('#sq-val');
    var ocol = $('#sq-ocol'), dir = $('#sq-dir'), limit = $('#sq-limit'), sqlEl = $('#sq-sql'), msg = $('#sq-msg'), out = $('#sq-result');
    COLS.forEach(function (c) {
      colsBox.insertAdjacentHTML('beforeend', '<label class="sq-col"><input type="checkbox" value="' + c + '"' + (c === 'name' ? ' checked' : '') + '> ' + c + '</label>');
    });
    wcol.innerHTML = '<option value="">(no filter)</option>' + COLS.slice(1).map(function (c) { return '<option>' + c + '</option>'; }).join('');
    ocol.innerHTML = '<option value="">(no order)</option>' + COLS.slice(1).map(function (c) { return '<option>' + c + '</option>'; }).join('');
    wcol.setAttribute('aria-label', 'Column to filter'); ocol.setAttribute('aria-label', 'Column to sort by');

    function picked() { return $all('#sq-cols input').filter(function (x) { return x.checked && !x.disabled; }).map(function (x) { return x.value; }); }
    function query() {
      var avg = mode.value === 'avg', cols = picked(), q = { avg: avg, cols: cols, wcol: wcol.value, op: op.value, val: +val.value, ocol: avg ? '' : ocol.value, dir: dir.value, limit: avg ? '' : limit.value };
      var sql = 'SELECT ' + (cols.length ? cols.map(function (c) { return avg ? 'AVG(' + c + ')' : c; }).join(', ') : '?') + '\nFROM students';
      if (q.wcol) sql += '\nWHERE ' + q.wcol + ' ' + q.op + ' ' + q.val;
      if (q.ocol) sql += '\nORDER BY ' + q.ocol + ' ' + q.dir;
      if (q.limit) sql += '\nLIMIT ' + q.limit;
      sqlEl.textContent = sql + ';';
      return q;
    }
    function sync() {
      var avg = mode.value === 'avg';
      $all('#sq-cols input').forEach(function (x) { var ok = !avg || SUBJECTS.indexOf(x.value) !== -1; x.disabled = !ok; x.parentNode.classList.toggle('off', !ok); });
      [ocol, dir, limit].forEach(function (x) { x.disabled = avg; });
      query();
    }
    function table(cols, data) {
      if (!data.length) return '<p class="text-secondary">No rows matched.</p>';
      return '<table class="table table-sm mb-0"><thead><tr>' + cols.map(function (c) { return '<th>' + esc(c) + '</th>'; }).join('') + '</tr></thead><tbody>' +
        data.map(function (r) { return '<tr>' + cols.map(function (c) { return '<td>' + esc(r[c]) + '</td>'; }).join('') + '</tr>'; }).join('') + '</tbody></table>';
    }
    function names(list) { return list.map(function (r) { return r.name; }); }
    function same(a, b) { return a.length === b.length && a.slice().sort().join() === b.slice().sort().join(); }
    $('#sq-cols').addEventListener('change', query);
    [wcol, op, val, ocol, dir, limit].forEach(function (x) { x.addEventListener('input', query); x.addEventListener('change', query); });
    mode.addEventListener('change', sync);
    out.innerHTML = table(COLS, rows);
    sync();

    $('#sq-run').addEventListener('click', function () {
      var q = query();
      if (!q.cols.length) { msg.textContent = 'Pick at least one column to SELECT.'; return; }
      var data = rows.filter(function (r) {
        if (!q.wcol) return true;
        return q.op === '=' ? r[q.wcol] === q.val : q.op === '>' ? r[q.wcol] > q.val : r[q.wcol] < q.val;
      });
      if (q.avg) {
        var line = {};
        q.cols.forEach(function (c) { line['AVG(' + c + ')'] = data.length ? Math.round(data.reduce(function (s, r) { return s + r[c]; }, 0) / data.length * 10) / 10 : '-'; });
        out.innerHTML = table(Object.keys(line), [line]);
        msg.textContent = 'The database worked out ' + q.cols.length + ' average' + (q.cols.length > 1 ? 's' : '') + ' from ' + data.length + ' rows.';
        if (!q.wcol && SUBJECTS.every(function (s) { return q.cols.indexOf(s) !== -1; })) tick('#sq-checks', 'avg');
      } else {
        if (q.ocol) data.sort(function (a, b) { return q.dir === 'DESC' ? b[q.ocol] - a[q.ocol] : a[q.ocol] - b[q.ocol]; });
        if (q.limit) data = data.slice(0, +q.limit);
        out.innerHTML = table(q.cols, data);
        msg.textContent = data.length + ' row' + (data.length === 1 ? '' : 's') + ' returned.';
        if (q.cols.indexOf('name') !== -1) {
          var got = names(data);
          if (same(got, ['Amani', 'Chebet', 'Esther', 'Hamisi'])) tick('#sq-checks', 'g9');
          if (same(got, ['Baraka', 'Daudi', 'Gathoni'])) tick('#sq-checks', 'absent');
          if (got.join() === 'Chebet,Faraji,Amani') tick('#sq-checks', 'top');
        } else {
          msg.textContent += ' Tip: include the name column so you can see who is who.';
        }
      }
      if (allTicked('#sq-checks')) { msg.textContent = 'Every mission done: you can ask a database real questions with SQL!'; complete(); }
    });
  };

  /* ------------------------------------------------------------------ */
  labs['api-explorer-lab'] = function () {
    var db = [{ id: 1, name: 'Amani', grade: 85 }, { id: 2, name: 'Baraka', grade: 72 }, { id: 3, name: 'Chebet', grade: 90 }], nextId = 4;
    var method = $('#api-method'), path = $('#api-path'), body = $('#api-body'), send = $('#api-send'), out = $('#api-response'), status = $('#api-status');
    function drawDb() {
      $('#api-db').innerHTML = db.length ? '<table class="table table-sm mb-0"><thead><tr><th>id</th><th>name</th><th>grade</th></tr></thead><tbody>' +
        db.map(function (s) { return '<tr><td>' + s.id + '</td><td>' + esc(s.name) + '</td><td>' + s.grade + '</td></tr>'; }).join('') + '</tbody></table>' : '<p class="text-secondary">The table is empty.</p>';
    }
    function find(id) { for (var i = 0; i < db.length; i++) if (db[i].id === id) return i; return -1; }
    function readBody() { try { var b = JSON.parse(body.value); return b && typeof b === 'object' && !Array.isArray(b) ? b : null; } catch (e) { return null; } }
    function check(b, needAll) {
      if (!b) return 'The body must be JSON, like { "name": "Zawadi", "grade": 78 }';
      if (needAll && (b.name === undefined || b.grade === undefined)) return 'A new student needs both a "name" and a "grade".';
      if (b.name !== undefined && (typeof b.name !== 'string' || !b.name.trim() || b.name.length > 30)) return '"name" must be some text (up to 30 letters).';
      if (b.grade !== undefined && (typeof b.grade !== 'number' || b.grade < 0 || b.grade > 100)) return '"grade" must be a number from 0 to 100.';
      return '';
    }
    function handle(m, p) {
      p = p.trim().split('?')[0].replace(/\/+$/, '') || '/';
      var one = p.match(/^\/students\/(\d+)$/), id = one ? +one[1] : null, i = one ? find(id) : -1, b, err;
      if (p === '/hello') return m === 'GET' ? [200, { message: 'Hello, Cloud!' }, 'hello'] : [405, { error: 'Use GET for /hello' }];
      if (p === '/students') {
        if (m === 'GET') return [200, db, 'list'];
        if (m === 'POST') {
          b = readBody(); err = check(b, true); if (err) return [400, { error: err }];
          var s = { id: nextId++, name: b.name.trim(), grade: b.grade }; db.push(s); return [201, s, 'create'];
        }
        return [405, { error: m + ' needs one student, e.g. /students/2' }];
      }
      if (one) {
        if (i === -1) return [404, { error: 'There is no student with id ' + id }];
        if (m === 'GET') return [200, db[i]];
        if (m === 'PUT') {
          b = readBody(); err = check(b, false); if (err) return [400, { error: err }];
          if (b.name !== undefined) db[i].name = b.name.trim();
          if (b.grade !== undefined) db[i].grade = b.grade;
          return [200, db[i], 'update'];
        }
        if (m === 'DELETE') { db.splice(i, 1); return [200, { deleted: id }, 'delete']; }
        return [405, { error: 'Use GET, PUT or DELETE for one student' }];
      }
      return [404, { error: 'Not found. Try /hello or /students' }];
    }
    method.addEventListener('change', function () {
      if (method.value === 'POST') { path.value = '/students'; body.value = '{ "name": "Zawadi", "grade": 78 }'; }
      if (method.value === 'PUT') { path.value = '/students/2'; body.value = '{ "grade": 95 }'; }
      if (method.value === 'DELETE') path.value = '/students/3';
      if (method.value === 'GET' && !/^\/(hello|students)/.test(path.value)) path.value = '/students';
    });
    send.addEventListener('click', async function () {
      send.disabled = true; status.textContent = ''; out.textContent = method.value + ' ' + path.value + ' ... sending to the cloud';
      await wait(500);
      var r = handle(method.value, path.value);
      status.textContent = r[0] + ' ' + ({ 200: 'OK', 201: 'Created', 400: 'Bad Request', 404: 'Not Found', 405: 'Method Not Allowed' })[r[0]];
      status.className = 'api-status ' + (r[0] < 300 ? 'ok' : 'err');
      out.textContent = JSON.stringify(r[1], null, 2);
      drawDb(); send.disabled = false;
      if (r[2]) tick('#api-checks', r[2]);
      if (allTicked('#api-checks')) complete();
    });
    drawDb();
  };

  /* ------------------------------------------------------------------ */
  labs['security-audit-lab'] = function () {
    var checks = [
      { id: 'https', title: 'Does the app use HTTPS?', found: 'No! The address starts with http:// and there is no lock, so passwords travel as plain text anyone on the WiFi can read.',
        fixes: [['Turn on HTTPS with an SSL/TLS certificate', ''], ['Make the password box bigger', 'A bigger box does not hide the password on its journey.'], ['Ask users to sign in only at night', 'Attackers work at night too!']],
        fixed: 'HTTPS now encrypts everything between the browser and the server. Look at what the WiFi snooper sees now.' },
      { id: 'admin', title: 'Can anyone open /admin without signing in?', found: 'Yes: typing school-notes.app/admin shows every user\'s notes with no login at all.',
        fixes: [['Require sign-in, and let only admin accounts open /admin', ''], ['Hide the link to /admin so nobody finds it', 'Hiding is not protecting: anyone can still type the address.'], ['Rename it to /secret-admin', 'A secret name can still be guessed or shared.']],
        fixed: 'Now the app checks who you are (authentication) and what you may do (authorization).' },
      { id: 'store', title: 'Are passwords stored safely?', found: 'No: the database keeps passwords exactly as typed, like "sunflower123". One leak would expose everyone.',
        fixes: [['Store only a hashed (scrambled, one-way) version of each password', ''], ['Keep them in a file called passwords.txt', 'That is still plain text, just in a different place.'], ['Email users their password every week', 'Emailing passwords spreads them even further.']],
        fixed: 'Hashed passwords cannot be turned back into the real password, even by someone who steals the database.' },
      { id: 'errors', title: 'Do error messages leak secrets?', found: 'Yes: a broken page shows "Error: database password = Kenya2024 on server db-01".',
        fixes: [['Show users a friendly message and keep the details in private logs', ''], ['Make the error text red', 'Red text still shows the secret.'], ['Only show the error on phones', 'Phone users could read the secret too.']],
        fixed: 'Users now see "Something went wrong, please try again" and the details stay where only the team can read them.' },
      { id: 'idor', title: 'Can a user see or change someone else\'s notes?', found: 'Yes: changing the address from /notes/12 to /notes/13 opens another student\'s notes.',
        fixes: [['Check that each note belongs to the signed-in user before showing or changing it', ''], ['Use bigger note numbers so they are hard to guess', 'Hard to guess is not the same as protected.'], ['Ask users politely not to change the address', 'Attackers do not follow polite requests.']],
        fixed: 'Each request is now checked, so you can only open your own notes.' }
    ];
    var box = $('#sa-checks'), msg = $('#sa-msg'), wire = $('#sa-wire'), fixedCount = 0;
    function plain() { wire.textContent = 'POST /login\nusername=amani&password=sunflower123'; }
    function scrambled() { var h = ''; for (var i = 0; i < 48; i++) h += '0123456789abcdef'[Math.floor(Math.random() * 16)] + (i % 4 === 3 ? ' ' : ''); wire.textContent = h + '\n(encrypted: unreadable without the key)'; }
    plain();
    checks.forEach(function (c, n) {
      box.insertAdjacentHTML('beforeend', '<div class="audit-card" data-n="' + n + '"><div class="d-flex justify-content-between align-items-center gap-2"><strong>' + (n + 1) + '. ' + esc(c.title) + '</strong>' +
        '<button type="button" class="btn btn-sm btn-outline-cloud audit-run">Run check</button></div><div class="audit-body"></div></div>');
    });
    box.addEventListener('click', function (e) {
      var card = e.target.closest('.audit-card'); if (!card || card.classList.contains('ok')) return;
      var c = checks[+card.getAttribute('data-n')], bodyEl = card.querySelector('.audit-body');
      if (e.target.closest('.audit-run')) {
        e.target.closest('.audit-run').remove(); card.classList.add('found');
        bodyEl.innerHTML = '<p class="mb-2 mt-2"><i class="bi bi-exclamation-triangle-fill text-danger" aria-hidden="true"></i> ' + esc(c.found) + '</p><p class="small fw-bold mb-1">Pick the best fix:</p>' +
          shuffled(c.fixes).map(function (f) { return '<button type="button" class="sm-item audit-fix" data-fix="' + c.fixes.indexOf(f) + '">' + esc(f[0]) + '</button>'; }).join('') + '<p class="small mb-0 audit-hint"></p>';
        return;
      }
      var fix = e.target.closest('.audit-fix'); if (!fix) return;
      var k = +fix.getAttribute('data-fix');
      if (k === 0) {
        card.classList.remove('found'); card.classList.add('ok'); fixedCount++;
        bodyEl.innerHTML = '<p class="mb-0 mt-2"><i class="bi bi-check-circle-fill text-success" aria-hidden="true"></i> Fixed: ' + esc(c.fixes[0][0]) + '. ' + esc(c.fixed) + '</p>';
        if (c.id === 'https') { $('#sa-url').textContent = 'https://school-notes.app/login'; $('#sa-lock').className = 'bi bi-lock-fill text-success'; scrambled(); }
        msg.textContent = 'Fixed ' + fixedCount + ' of ' + checks.length + ' problems.';
        if (fixedCount === checks.length) { msg.textContent = 'All 5 fixed! Security is many layers working together: encryption, sign-in, safe storage, careful errors and permission checks.'; complete(); }
      } else {
        fix.classList.add('bad'); setTimeout(function () { fix.classList.remove('bad'); }, 400);
        card.querySelector('.audit-hint').textContent = 'Not that one: ' + c.fixes[k][1];
      }
    });
  };

  if (labs[slug]) labs[slug]();
})();
