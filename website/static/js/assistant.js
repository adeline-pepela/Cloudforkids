/* Cloud for Kids assistant panel. Reads the page as text (plus anything typed into its forms) when you send,
   streams the reply by polling the chat, and shows each proposed change as one sentence with Approve / Decline.
   Any page can add a line of context the screen can't show: <div data-assistant-hint="Editing the Term 2 timetable">,
   or window.C4KAssistant.setContext("..."). */
(function () {
  'use strict';
  var root = document.getElementById('c4ka');
  if (!root) return;

  var $ = function (id) { return document.getElementById(id); };
  var fab = $('c4ka-fab'), log = $('c4ka-log'), form = $('c4ka-form'), input = $('c4ka-input'), sendBtn = $('c4ka-send'),
      stopBtn = $('c4ka-stop'), modelSel = $('c4ka-model'), threadsBox = $('c4ka-threads'), historyBtn = $('c4ka-history-btn'),
      foot = $('c4ka-foot');
  var area = root.dataset.area;
  var STORE = 'c4ka-' + area + '-';
  var state = { thread: null, busy: false, polling: null, rendered: {}, loaded: false, extra: '', info: null, files: [] };

  var SUGGEST = {
    admin: [
      'What needs my attention today?',
      'Summarise this page for me.',
      'Which facilitators are waiting for approval?',
      'How did sign-ups and lesson completions go this month?'
    ],
    teach: [
      'Who in my classes needs a nudge this week?',
      'Summarise this page for me.',
      'Which lessons is my class finding hardest?',
      'Add a session next Tuesday at 4pm to my class.'
    ],
    learn: [
      'What should I learn next?',
      'Explain this lesson in simple words.',
      'Give me a hint for this quiz, not the answer.',
      'How am I doing?'
    ],
    family: [
      'How is my child doing this week?',
      'What can we practise together at home?',
      'Do I have messages from the teacher?',
      'What does my child\'s plan include?'
    ]
  };
  var WORDS = {
    admin: { hello: 'I can see this page, and I work with your permissions.', place: 'Ask about this page, or ask me to do something', foot: 'Reads this page when you send. Changes wait for your approval.' },
    teach: { hello: 'I can see this page, and I work only with your classes.', place: 'Ask about your classes, or ask me to do something', foot: 'Reads this page when you send. Changes wait for your approval.' },
    learn: { hello: 'I am Nimbus. I can explain your lessons and help you practise. I give hints, not quiz answers.', place: 'Ask Nimbus about a lesson', foot: 'Nimbus can make mistakes. Ask your teacher if unsure, and never share personal details.' },
    family: { hello: 'Ask me about your child\'s learning, and how to help at home.', place: 'Ask about your child\'s progress', foot: 'Only your own linked children. Replies to teachers wait for your approval.' }
  }[area] || {};
  input.placeholder = WORDS.place || input.placeholder;

  function store(key, value) {
    try {
      if (value === undefined) return localStorage.getItem(STORE + key);
      if (value === null) localStorage.removeItem(STORE + key); else localStorage.setItem(STORE + key, String(value));
    } catch (e) { return null; }
  }
  function url(name, id) { return root.dataset[name].replace('/0/', '/' + id + '/'); }

  function api(method, path, body) {
    var opts = { method: method, credentials: 'same-origin', headers: { 'Accept': 'application/json' } };
    if (body !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.headers['X-CSRFToken'] = csrf();
      opts.body = JSON.stringify(body);
    }
    return fetch(path, opts).then(function (res) {
      return res.json().catch(function () { return { ok: false, error: 'The server answered in a way we did not expect (' + res.status + ').' }; })
        .then(function (data) { data._status = res.status; return data; });
    }).catch(function () { return { ok: false, error: 'No connection. Check your internet and try again.' }; });
  }
  function csrf() {
    var m = document.cookie.match(/(?:^|;\s*)c4k_csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : root.dataset.csrf;
  }

  // ---------------------------------------------------------------- reading the screen

  function labelFor(el) {
    var text = '';
    if (el.id) {
      var lab = document.querySelector('label[for="' + (window.CSS && CSS.escape ? CSS.escape(el.id) : el.id) + '"]');
      if (lab) text = lab.innerText;
    }
    if (!text) { var wrap = el.closest('label'); if (wrap) text = wrap.innerText; }
    text = text || el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.name || '';
    return text.replace(/\s+/g, ' ').replace(/[:*]\s*$/, '').trim().slice(0, 80);
  }

  function captureScreen() {
    var main = document.getElementById('content-start') || document.querySelector('main') || document.body;
    var text = (main.innerText || '').replace(/\n{3,}/g, '\n\n').trim();
    var fields = [];
    main.querySelectorAll('input, textarea, select').forEach(function (el) {
      if (el.closest('#c4ka')) return;
      var type = (el.type || '').toLowerCase();
      if (['hidden', 'password', 'submit', 'button', 'reset', 'file', 'image'].indexOf(type) !== -1) return;
      if (el.name === 'csrfmiddlewaretoken' || el.disabled) return;
      if (el.offsetParent === null && type !== 'checkbox' && type !== 'radio') return; // not visible
      var value;
      if (type === 'checkbox') value = el.checked ? 'yes' : 'no';
      else if (type === 'radio') { if (!el.checked) return; value = el.value; }
      else if (el.tagName === 'SELECT') {
        value = Array.prototype.filter.call(el.options, function (o) { return o.selected && o.value !== ''; })
          .map(function (o) { return o.text.trim(); }).join(', ');
      } else value = (el.value || '').trim();
      if (!value) return;
      fields.push(labelFor(el) + ': ' + value.slice(0, 1500));
    });
    var hints = [];
    document.querySelectorAll('[data-assistant-hint]').forEach(function (el) { hints.push(el.getAttribute('data-assistant-hint')); });
    if (state.extra) hints.push(state.extra);
    var out = text.slice(0, 4200);
    if (fields.length) out += '\n\nForm values on the page:\n' + fields.join('\n');
    return {
      path: location.pathname + location.search, title: document.title,
      text: out.slice(0, 6000), hint: hints.join(' ').slice(0, 400)
    };
  }

  // ---------------------------------------------------------------- a little markdown, safely

  function esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  function inline(s) {
    return s
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/\[([^\]]+)\]\(((?:https?:\/\/|\/)[^\s)]+)\)/g, function (_m, label, href) {
        var ext = /^https?:/.test(href) && href.indexOf(location.origin) !== 0;
        return '<a href="' + href + '"' + (ext ? ' target="_blank" rel="noopener"' : '') + '>' + label + '</a>';
      });
  }
  function markdown(src) {
    var parts = esc(src || '').split(/```/);
    var html = '';
    parts.forEach(function (chunk, i) {
      if (i % 2 === 1) { html += '<pre><code>' + chunk.replace(/^\w*\n/, '') + '</code></pre>'; return; }
      chunk.split(/\n{2,}/).forEach(function (block) {
        var lines = block.split('\n').filter(function (l) { return l.trim() !== ''; });
        if (!lines.length) return;
        var bullets = lines.every(function (l) { return /^\s*[-*•]\s+/.test(l); });
        var numbers = lines.every(function (l) { return /^\s*\d+[.)]\s+/.test(l); });
        if (bullets || numbers) {
          var tag = bullets ? 'ul' : 'ol';
          html += '<' + tag + '>' + lines.map(function (l) {
            return '<li>' + inline(l.replace(/^\s*(?:[-*•]|\d+[.)])\s+/, '')) + '</li>';
          }).join('') + '</' + tag + '>';
          return;
        }
        html += '<p>' + lines.map(function (l) {
          var h = l.match(/^#{1,4}\s+(.*)$/);
          return h ? '<span class="c4ka-h">' + inline(h[1]) + '</span>' : inline(l);
        }).join('<br>') + '</p>';
      });
    });
    return html;
  }

  // ---------------------------------------------------------------- drawing the conversation

  function nearBottom() { return log.scrollHeight - log.scrollTop - log.clientHeight < 80; }
  function toBottom() { log.scrollTop = log.scrollHeight; }

  function hello() {
    var box = document.createElement('div');
    box.className = 'c4ka-hello';
    var extra = area === 'learn' ? '' : (state.info && state.info.read_only ? ' Read-only mode is on, so I will only look and answer.' : ' I ask before I change anything.');
    box.innerHTML = '<h3>' + (area === 'learn' ? 'Habari! How can I help?' : 'How can I help?') + '</h3><p>' + esc(WORDS.hello || '') + esc(extra) +
      '</p><div class="c4ka-suggest"></div>';
    var list = box.querySelector('.c4ka-suggest');
    (SUGGEST[area] || []).forEach(function (text) {
      var b = document.createElement('button');
      b.type = 'button'; b.textContent = text;
      b.addEventListener('click', function () { input.value = text; send(); });
      list.appendChild(b);
    });
    return box;
  }

  var READ_ICON = 'bi-search';
  function toolName(t) { return t.replace(/_/g, ' '); }

  function actionsHtml(actions) {
    var chips = [], cards = [];
    actions.forEach(function (a) {
      if (!a.writes && a.status !== 'pending') {
        chips.push('<span class="c4ka-chip' + (a.status === 'failed' ? ' failed' : '') + '" title="' + esc(a.error || '') + '"><i class="bi ' +
          (a.status === 'failed' ? 'bi-exclamation-circle' : READ_ICON) + '" aria-hidden="true"></i>' + esc(toolName(a.tool)) + '</span>');
        return;
      }
      var icon = { pending: 'bi-hand-index', done: 'bi-check-circle-fill', failed: 'bi-x-circle-fill', declined: 'bi-slash-circle', undone: 'bi-arrow-counterclockwise' }[a.status];
      var note = { pending: '', done: '', failed: a.error, declined: 'Declined. Nothing was changed.', undone: 'Undone.' }[a.status];
      var buttons = '';
      if (a.status === 'pending') {
        buttons = '<button type="button" class="approve" data-act="approve" data-id="' + a.id + '"><i class="bi bi-check-lg" aria-hidden="true"></i> Approve</button>' +
          '<button type="button" data-act="decline" data-id="' + a.id + '">Decline</button>';
      } else if (a.status === 'done') {
        if (a.link) buttons += '<a href="' + esc(a.link) + '"><i class="bi bi-box-arrow-up-right" aria-hidden="true"></i> Open</a>';
        if (a.can_undo) buttons += '<button type="button" data-act="undo" data-id="' + a.id + '"><i class="bi bi-arrow-counterclockwise" aria-hidden="true"></i> ' + esc(a.undo_label) + '</button>';
      }
      cards.push('<div class="c4ka-card ' + a.status + '"><p><i class="bi ' + icon + '" aria-hidden="true"></i><span>' + esc(a.summary) + '</span></p>' +
        (note ? '<small>' + esc(note) + '</small>' : '') + (buttons ? '<div class="c4ka-card-actions">' + buttons + '</div>' : '') + '</div>');
    });
    return (chips.length ? '<div class="c4ka-chips">' + chips.join('') + '</div>' : '') + cards.join('');
  }

  function turnHtml(t) {
    if (t.role === 'user') return esc(t.text);
    var html = '';
    if (t.reasoning) {
      var thinking = t.streaming && !t.text;
      html += '<details class="c4ka-think"' + (thinking ? ' open' : '') + '><summary><i class="bi bi-lightbulb" aria-hidden="true"></i> ' +
        (thinking ? 'Thinking…' : 'How I worked it out') + '</summary><div>' + esc(t.reasoning.slice(-4000)) + '</div></details>';
    }
    if (t.text) html += '<div class="c4ka-text' + (t.streaming ? ' c4ka-caret' : '') + '">' + markdown(t.text) + '</div>';
    else if (t.streaming && !t.reasoning) html += '<div class="c4ka-dots" aria-label="Working"><span></span><span></span><span></span></div>';
    if (t.failed && t.error) html += '<div class="c4ka-error">' + esc(t.error) + '</div>';
    if (t.actions && t.actions.length) html += actionsHtml(t.actions);
    return html;
  }

  function render(data) {
    if (!data || !data.ok) return;
    state.thread = data.id;
    state.busy = data.busy;
    store('thread', data.id);
    if (data.connection_id && modelSel.querySelector('option[value="' + data.connection_id + '"]')) modelSel.value = data.connection_id;
    var stick = nearBottom();
    var hi = log.querySelector('.c4ka-hello');
    if (hi && data.turns.length) hi.remove();
    var seen = {};
    data.turns.forEach(function (t) {
      seen[t.id] = true;
      var key = JSON.stringify(t);
      var el = state.rendered[t.id];
      if (!el) {
        el = document.createElement('div');
        el.className = 'c4ka-msg ' + t.role;
        el.dataset.id = t.id;
        log.appendChild(el);
        state.rendered[t.id] = el;
      }
      if (el.dataset.key !== key) {
        el.dataset.key = key;
        if (t.role === 'user') {
          el.textContent = t.text;
          if (t.files && t.files.length) {
            var sent = document.createElement('span');
            sent.className = 'c4ka-sent-files';
            sent.textContent = 'Attached: ' + t.files.join(', ');
            el.appendChild(sent);
          }
        } else el.innerHTML = turnHtml(t);
      }
    });
    Object.keys(state.rendered).forEach(function (id) {
      if (!seen[id]) { state.rendered[id].remove(); delete state.rendered[id]; }
    });
    if (!data.turns.length && !log.querySelector('.c4ka-hello')) log.appendChild(hello());
    setBusy(data.busy || data.turns.some(function (t) { return t.streaming; }));
    if (stick) toBottom();
  }

  function setBusy(busy) {
    state.busy = busy;
    sendBtn.hidden = busy;
    stopBtn.hidden = !busy;
    foot.textContent = busy ? 'Working… you can keep reading the page.' :
      (state.info && state.info.read_only && area !== 'learn' ? 'Read-only mode: nothing will be changed.' : (WORDS.foot || ''));
    if (busy) poll(); else stopPolling();
  }

  function poll() {
    if (state.polling) return;
    state.polling = setInterval(function () {
      if (!state.thread) return stopPolling();
      api('GET', url('thread', state.thread)).then(function (data) {
        if (data.ok) render(data);
        else { stopPolling(); setBusy(false); }
      });
    }, 450);
  }
  function stopPolling() { if (state.polling) { clearInterval(state.polling); state.polling = null; } }

  function showError(message) {
    var el = document.createElement('div');
    el.className = 'c4ka-error';
    el.setAttribute('role', 'alert');
    el.textContent = message;
    log.appendChild(el);
    toBottom();
    setTimeout(function () { el.remove(); }, 9000);
  }

  // ---------------------------------------------------------------- actions

  function send() {
    var text = input.value.trim();
    if (!text || state.busy) return;
    if (!modelSel.value && !(state.info && state.info.default_connection)) { showError('No AI model is set up yet. ' + (root.dataset.settings ? 'Add one in Settings.' : 'Ask an admin to add one.')); return; }
    var files = state.files.slice();
    input.value = ''; grow();
    state.files = []; drawFiles();
    setBusy(true);
    stopPolling();
    var hi = log.querySelector('.c4ka-hello'); if (hi) hi.remove();
    var temp = document.createElement('div');
    temp.className = 'c4ka-msg user'; temp.textContent = text;
    log.appendChild(temp); toBottom();
    api('POST', root.dataset.send, {
      area: area, text: text, thread: state.thread, connection: modelSel.value || null, screen: captureScreen(), files: files
    }).then(function (data) {
      temp.remove();
      if (!data.ok) { input.value = text; state.files = files; drawFiles(); setBusy(false); showError(data.error); return; }
      render(data);
    });
  }

  log.addEventListener('click', function (e) {
    var btn = e.target.closest('button[data-act]');
    if (!btn) return;
    var id = btn.dataset.id, act = btn.dataset.act;
    btn.closest('.c4ka-card-actions').querySelectorAll('button').forEach(function (b) { b.disabled = true; });
    var req = act === 'undo' ? api('POST', url('undo', id), {}) : api('POST', url('decide', id), { approve: act === 'approve' });
    req.then(function (data) {
      if (!data.ok) { showError(data.error); refresh(); return; }
      render(data);
      if (act !== 'undo') { setBusy(true); }
    });
  });

  stopBtn.addEventListener('click', function () {
    if (state.thread) api('POST', url('stop', state.thread), {});
  });

  function refresh() {
    if (!state.thread) return;
    api('GET', url('thread', state.thread)).then(function (data) {
      if (data.ok) render(data);
      else { store('thread', null); newChat(); }
    });
  }

  function newChat() {
    stopPolling();
    state.thread = null; state.rendered = {};
    store('thread', null);
    log.innerHTML = '';
    log.appendChild(hello());
    setBusy(false);
    showThreads(false);
    input.focus();
  }

  function showThreads(open) {
    threadsBox.hidden = !open;
    log.hidden = open;
    historyBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (!open) return;
    threadsBox.innerHTML = '<p class="c4ka-empty">Loading…</p>';
    api('GET', root.dataset.state + '?area=' + encodeURIComponent(area)).then(function (data) {
      if (!data.ok) { threadsBox.innerHTML = '<p class="c4ka-empty">' + esc(data.error) + '</p>'; return; }
      if (!data.threads.length) { threadsBox.innerHTML = '<p class="c4ka-empty">No chats yet.</p>'; return; }
      threadsBox.innerHTML = data.threads.map(function (t) {
        return '<div class="c4ka-thread-row"><button type="button" class="c4ka-thread-open" data-thread="' + t.id + '"><span>' + esc(t.title) +
          '</span><small>' + esc(t.when) + '</small></button><button type="button" class="c4ka-btn-icon" data-forget="' + t.id +
          '" title="Delete this chat" aria-label="Delete this chat"><i class="bi bi-trash3" aria-hidden="true"></i></button></div>';
      }).join('');
    });
  }

  threadsBox.addEventListener('click', function (e) {
    var open = e.target.closest('[data-thread]'), forget = e.target.closest('[data-forget]');
    if (open) {
      stopPolling();
      state.thread = +open.dataset.thread; state.rendered = {};
      log.innerHTML = '';
      showThreads(false);
      refresh();
    } else if (forget) {
      api('POST', url('delete', forget.dataset.forget), {}).then(function () {
        if (+forget.dataset.forget === state.thread) { state.thread = null; store('thread', null); log.innerHTML = ''; log.appendChild(hello()); }
        showThreads(true);
      });
    }
  });

  historyBtn.addEventListener('click', function () { showThreads(threadsBox.hidden); });
  $('c4ka-new').addEventListener('click', newChat);
  modelSel.addEventListener('change', function () { store('model', modelSel.value); });

  // ---------------------------------------------------------------- attachments (admin and facilitator areas)

  var fileInput = $('c4ka-file'), filesBox = $('c4ka-files');
  var TEXT_EXT = /\.(txt|md|csv|tsv|json|xml|html?)$/i, MAX_FILES = 4, MAX_TEXT = 300000, MAX_BINARY = 1500000;

  function drawFiles() {
    if (!filesBox) return;
    filesBox.hidden = !state.files.length;
    filesBox.innerHTML = state.files.map(function (f, i) {
      return '<span class="c4ka-file"><i class="bi ' + (f.kind === 'image' ? 'bi-image' : f.kind === 'pdf' ? 'bi-file-earmark-pdf' : 'bi-file-earmark-text') +
        '" aria-hidden="true"></i><span>' + esc(f.name) + '</span><button type="button" data-drop="' + i + '" aria-label="Remove ' + esc(f.name) + '">&times;</button></span>';
    }).join('');
  }
  if (filesBox) filesBox.addEventListener('click', function (e) {
    var b = e.target.closest('[data-drop]');
    if (b) { state.files.splice(+b.dataset.drop, 1); drawFiles(); }
  });

  function shrinkImage(file) {
    // Big photos are scaled down in the browser (longest side 1600px), which keeps them well under the upload limit.
    return new Promise(function (resolve, reject) {
      var img = new Image(), url = URL.createObjectURL(file);
      img.onload = function () {
        var scale = Math.min(1, 1600 / Math.max(img.width, img.height));
        var canvas = document.createElement('canvas');
        canvas.width = Math.round(img.width * scale); canvas.height = Math.round(img.height * scale);
        canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
        URL.revokeObjectURL(url);
        resolve(canvas.toDataURL('image/jpeg', 0.85));
      };
      img.onerror = function () { URL.revokeObjectURL(url); reject(new Error('Could not read ' + file.name + '.')); };
      img.src = url;
    });
  }
  function readAs(file, how) {
    return new Promise(function (resolve, reject) {
      var r = new FileReader();
      r.onload = function () { resolve(r.result); };
      r.onerror = reject;
      if (how === 'text') r.readAsText(file); else r.readAsDataURL(file);
    });
  }

  function addFiles(list) {
    Array.prototype.forEach.call(list, function (file) {
      if (state.files.length >= MAX_FILES) { showError('Attach up to ' + MAX_FILES + ' files.'); return; }
      // A pasted screenshot has no useful name of its own: name it by the time it arrived.
      var name = file.name && file.name !== 'image.png' ? file.name : 'pasted ' + new Date().toTimeString().slice(0, 8).replace(/:/g, '.') + '.png';
      var job;
      if (/^image\//.test(file.type)) {
        job = shrinkImage(file).then(function (url) { return { name: name.replace(/\.\w+$/, '') + '.jpg', type: 'image/jpeg', kind: 'image', data: url.split(',')[1] }; });
      } else if (file.type === 'application/pdf' || /\.pdf$/i.test(name)) {
        if (file.size > MAX_BINARY) { showError(name + ' is too big. Attach a PDF under 1.5 MB.'); return; }
        job = readAs(file, 'url').then(function (url) { return { name: name, type: 'application/pdf', kind: 'pdf', data: url.split(',')[1] }; });
      } else if (/^text\//.test(file.type) || TEXT_EXT.test(name) || file.type === 'application/json') {
        job = readAs(file, 'text').then(function (text) {
          if (text.length > MAX_TEXT) throw new Error(name + ' is too long. Attach a smaller file.');
          return { name: name, type: file.type || 'text/plain', kind: 'text', text: text };
        });
      } else { showError(name + ': attach text, CSV, JSON, an image or a PDF.'); return; }
      job.then(function (f) {
        if (f.data && f.data.length > MAX_BINARY * 4 / 3) { showError(f.name + ' is too big.'); return; }
        if (state.files.length < MAX_FILES) { state.files.push(f); drawFiles(); }
      }).catch(function (err) { showError((err && err.message) || ('Could not read ' + name + '.')); });
    });
  }

  if (fileInput) {
    $('c4ka-attach').addEventListener('click', function () { fileInput.click(); });
    fileInput.addEventListener('change', function () { addFiles(fileInput.files); fileInput.value = ''; });
    root.addEventListener('dragover', function (e) {
      if (e.dataTransfer && Array.prototype.indexOf.call(e.dataTransfer.types, 'Files') !== -1) { e.preventDefault(); root.classList.add('is-drop'); }
    });
    root.addEventListener('dragleave', function (e) { if (!root.contains(e.relatedTarget)) root.classList.remove('is-drop'); });
    root.addEventListener('drop', function (e) {
      root.classList.remove('is-drop');
      if (e.dataTransfer && e.dataTransfer.files.length) { e.preventDefault(); addFiles(e.dataTransfer.files); }
    });
    input.addEventListener('paste', function (e) {
      var pasted = (e.clipboardData && e.clipboardData.files) || [];
      if (pasted.length) { e.preventDefault(); addFiles(pasted); }
    });
  }

  // ---------------------------------------------------------------- open, close, type

  function load() {
    if (state.loaded) return;
    state.loaded = true;
    api('GET', root.dataset.state + '?area=' + encodeURIComponent(area)).then(function (data) {
      if (!data.ok) { showError(data.error); return; }
      state.info = data;
      modelSel.innerHTML = data.connections.map(function (c) { return '<option value="' + c.id + '">' + esc(c.name) + '</option>'; }).join('');
      if (!data.connections.length) modelSel.innerHTML = '<option value="">No model set up</option>';
      var saved = store('model');
      modelSel.value = (saved && modelSel.querySelector('option[value="' + saved + '"]')) ? saved : (data.default_connection || '');
      var last = +store('thread');
      if (last) { state.thread = last; refresh(); } else { log.innerHTML = ''; log.appendChild(hello()); setBusy(false); }
    });
  }

  function open() {
    root.hidden = false;
    document.body.classList.add('c4ka-open');
    fab.setAttribute('aria-expanded', 'true');
    store('open', '1');
    load();
    setTimeout(function () { input.focus(); toBottom(); }, 30);
  }
  function close() {
    root.hidden = true;
    document.body.classList.remove('c4ka-open');
    fab.setAttribute('aria-expanded', 'false');
    store('open', null);
    stopPolling();
    fab.focus();
  }
  fab.addEventListener('click', open);
  $('c4ka-close').addEventListener('click', close);
  document.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key === '/') { e.preventDefault(); if (root.hidden) open(); else close(); }
    else if (e.key === 'Escape' && !root.hidden && root.contains(document.activeElement)) close();
  });

  function grow() { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 160) + 'px'; }
  input.addEventListener('input', grow);
  input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); }
  });
  form.addEventListener('submit', function (e) { e.preventDefault(); send(); });

  window.C4KAssistant = {
    open: open, close: close,
    setContext: function (text) { state.extra = String(text || '').slice(0, 400); },
    ask: function (text) { open(); input.value = text; grow(); input.focus(); }
  };

  // Stay open across page loads on wide screens, so a task can carry on from page to page.
  if (store('open') && window.matchMedia('(min-width: 1100px)').matches) open();
})();
