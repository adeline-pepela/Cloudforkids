/* Live class room (LiveKit). The server decides who may speak or share; this script shows the room and the controls. */
(function () {
  'use strict';
  var LK = window.LivekitClient;
  var cfg = JSON.parse(document.getElementById('lv-config').textContent);
  var csrf = (document.querySelector('[name=csrfmiddlewaretoken]') || {}).value || '';
  var isHost = cfg.role === 'host';
  var EMOJIS = ['👍', '👏', '😂', '😕', '🎉'];
  var room = null, settings = {}, tiles = new Map(), leaving = false, lastReact = 0, unreadChat = 0;
  var canSpeakBefore = false;

  var $ = function (id) { return document.getElementById(id); };
  function S(key) {
    var el = document.querySelector('#lv-strings [data-k="' + key + '"]');
    return el ? el.textContent.trim() : key;
  }
  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }
  function initials(name) {
    return (name || '?').split(/\s+/).filter(Boolean).slice(0, 2).map(function (w) { return w[0]; }).join('').toUpperCase();
  }
  function post(url, data) {
    return fetch(url, {
      method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': csrf }, body: new URLSearchParams(data || {})
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) {
        if (!r.ok || !d.ok) throw new Error(d.error || S('actionFailed'));
        return d;
      });
    });
  }
  var bannerTimer;
  function banner(text, sticky) {
    var b = $('lv-banner');
    b.textContent = text;
    b.hidden = !text;
    clearTimeout(bannerTimer);
    if (text && !sticky) bannerTimer = setTimeout(function () { b.hidden = true; }, 4500);
  }

  /* ---------- Joining ---------- */
  $('lv-join').addEventListener('click', function () {
    var btn = this, err = $('lv-join-error');
    btn.disabled = true;
    err.hidden = true;
    post(cfg.tokenUrl).then(function (d) {
      settings = d.settings || {};
      room = new LK.Room({
        adaptiveStream: true, dynacast: true,
        videoCaptureDefaults: { resolution: LK.VideoPresets.h540.resolution },
        publishDefaults: { simulcast: true }
      });
      wire(room);
      return room.connect(d.url, d.token).then(function () {
        readSettings();
        $('lv-prejoin').hidden = true;
        $('lv-app').hidden = false;
        room.startAudio().catch(function () {});
        canSpeakBefore = canSpeak();
        sync();
        if (isHost) {
          room.localParticipant.enableCameraAndMicrophone().catch(function () { banner(S('noMedia')); }).then(sync);
        }
      });
    }).catch(function (e) {
      btn.disabled = false;
      err.textContent = (e && e.message && e.message !== 'Failed to fetch') ? e.message : S('joinFailed');
      err.hidden = false;
    });
  });

  function wire(r) {
    var E = LK.RoomEvent;
    [E.ParticipantConnected, E.ParticipantDisconnected, E.TrackSubscribed, E.TrackUnsubscribed, E.TrackMuted,
      E.TrackUnmuted, E.LocalTrackPublished, E.LocalTrackUnpublished, E.ActiveSpeakersChanged,
      E.ParticipantAttributesChanged].forEach(function (ev) { r.on(ev, sync); });

    r.on(E.TrackSubscribed, function (track) {
      if (track.kind === 'audio') $('lv-audio').appendChild(track.attach());
    });
    r.on(E.TrackUnsubscribed, function (track) {
      if (track.kind === 'audio') track.detach().forEach(function (n) { n.remove(); });
    });
    r.on(E.ParticipantPermissionsChanged, function (prev, participant) {
      if (participant && participant !== r.localParticipant) { sync(); return; }
      var now = canSpeak();
      if (!isHost && now && !canSpeakBefore) banner(S('canSpeak'));
      if (!isHost && !now && canSpeakBefore) banner(S('muted'));
      canSpeakBefore = now;
      sync();
    });
    r.on(E.RoomMetadataChanged, function () { readSettings(); sync(); });
    r.on(E.DataReceived, function (payload, participant, kind, topic) { onData(payload, participant, topic); });
    r.on(E.ConnectionQualityChanged, function (quality, participant) {
      if (participant === r.localParticipant) $('lv-net').hidden = quality !== LK.ConnectionQuality.Poor;
    });
    r.on(E.Reconnecting, function () { banner(S('reconnecting'), true); });
    r.on(E.Reconnected, function () { banner(''); });
    r.on(E.Disconnected, onDisconnected);
  }

  function onDisconnected(reason) {
    var R = LK.DisconnectReason || {};
    $('lv-app').hidden = true;
    if (reason === R.ROOM_DELETED) {
      $('lv-ended').hidden = false;
    } else if (reason === R.PARTICIPANT_REMOVED) {
      $('lv-ended-title').textContent = S('removedTitle');
      $('lv-ended-text').textContent = S('removedText');
      $('lv-ended').hidden = false;
    } else if (leaving) {
      window.location.href = cfg.exitUrl;
    } else {
      window.location.reload();  // lost the connection for good: the page shows the class again, or that it ended
    }
  }

  function readSettings() {
    try { settings = Object.assign({}, settings, JSON.parse(room.metadata || '{}')); } catch (e) { /* keep the last settings */ }
  }

  /* ---------- Who may do what ---------- */
  function perms() { return (room && room.localParticipant.permissions) || {}; }
  function canSpeak() { return isHost || !!perms().canPublish; }
  function canCamera() { return isHost || (canSpeak() && !!settings.video); }
  function canChat() { return isHost || !!settings.chat; }
  function handOf(p) { return (p.attributes && p.attributes.hand) || ''; }
  function isTeacher(p) { return p.identity === cfg.host; }
  function label(p) {
    var name = p.name || p.identity;
    if (p === room.localParticipant) return name + ' (' + S('you') + ')';
    return isTeacher(p) ? name + ' (' + S('teacher') + ')' : name;
  }

  /* ---------- Video tiles ---------- */
  function tileFor(p) {
    var t = tiles.get(p.identity);
    if (t) return t;
    var node = el('div', 'lv-tile' + (isTeacher(p) ? ' teacher' : ''));
    var video = el('video');
    video.autoplay = true; video.playsInline = true; video.muted = true;
    var avatar = el('div', 'lv-avatar', initials(p.name || p.identity));
    var name = el('div', 'lv-name');
    var handIco = el('div', 'lv-tile-hand', '✋');
    node.append(video, avatar, name, handIco);
    t = { el: node, video: video, name: name };
    tiles.set(p.identity, t);
    return t;
  }

  function attach(video, track) {
    if (video._track === track) return;
    if (video._track) video._track.detach(video);
    video._track = track || null;
    if (track) track.attach(video);
  }

  function participants() {
    return [room.localParticipant].concat(Array.from(room.remoteParticipants.values()));
  }

  var spotVideo;
  function sync() {
    if (!room) return;
    var all = participants(), seen = {}, screen = null, S_ = LK.Track.Source;
    all.forEach(function (p) {
      seen[p.identity] = true;
      var t = tileFor(p);
      var cam = p.getTrackPublication(S_.Camera);
      var camTrack = cam && cam.track && !cam.isMuted ? cam.track : null;
      attach(t.video, camTrack);
      t.el.classList.toggle('has-video', !!camTrack);
      t.el.classList.toggle('mine', p === room.localParticipant);
      t.el.classList.toggle('speaking', !!p.isSpeaking);
      t.el.classList.toggle('hand', !!handOf(p));
      t.name.textContent = '';
      t.name.append(el('i', 'bi ' + (p.isMicrophoneEnabled ? 'bi-mic-fill' : 'bi-mic-mute-fill')), document.createTextNode(' ' + label(p)));
      var ss = p.getTrackPublication(S_.ScreenShare);
      if (ss && ss.track && !ss.isMuted) screen = { p: p, track: ss.track };
    });
    tiles.forEach(function (t, id) { if (!seen[id]) { attach(t.video, null); t.el.remove(); tiles.delete(id); } });

    // Stage: a shared screen fills the spotlight, otherwise the teacher does. Everyone else sits in the strip.
    var spot = $('lv-spot'), grid = $('lv-grid');
    var teacher = all.filter(isTeacher)[0];
    if (screen) {
      if (!spotVideo) { spotVideo = el('video', 'lv-screen'); spotVideo.autoplay = true; spotVideo.playsInline = true; spotVideo.muted = true; }
      attach(spotVideo, screen.track);
      if (spotVideo.parentNode !== spot) { spot.textContent = ''; spot.append(spotVideo, el('div', 'lv-name')); }
      spot.lastChild.textContent = (screen.p.name || '') + ' ' + S('screenSharing');
    } else {
      if (spotVideo) attach(spotVideo, null);
      var want = teacher ? tiles.get(teacher.identity).el : null;
      if (!want) spot.textContent = '';
      else if (want.parentNode !== spot) { spot.textContent = ''; spot.append(want); }
    }
    spot.classList.toggle('empty', !screen && !teacher);
    var order = all.slice().sort(function (a, b) {
      var rank = function (p) { return isTeacher(p) ? 0 : (p === room.localParticipant ? 1 : 2); };
      return rank(a) - rank(b) || (a.name || '').localeCompare(b.name || '');
    });
    var i = 0;
    order.forEach(function (p) {
      if (!screen && p === teacher) return;
      var node = tiles.get(p.identity).el;
      if (grid.children[i] !== node) grid.insertBefore(node, grid.children[i] || null);
      i += 1;
    });
    if (all.length === 1) {
      if (!$('lv-alone')) { var alone = el('p', 'lv-alone', S('nobody')); alone.id = 'lv-alone'; grid.appendChild(alone); }
    } else if ($('lv-alone')) $('lv-alone').remove();

    $('lv-count').querySelector('b').textContent = all.length;
    renderPeople(all);
    renderControls();
  }

  /* ---------- People list and hands ---------- */
  function control(action, extra) {
    return post(cfg.controlUrl, Object.assign({ action: action }, extra || {})).then(function (d) {
      if (d.settings) { settings = Object.assign(settings, d.settings); renderControls(); }
    }).catch(function (e) { banner(e.message); });
  }

  function personRow(p, inHands) {
    var li = el('li', 'lv-person');
    var av = el('span', 'lv-mini', initials(p.name || p.identity));
    var info = el('span', 'lv-person-name', label(p));
    var icons = el('span', 'lv-person-icons');
    if (handOf(p)) icons.append(el('span', 'lv-hand-ico', '✋'));
    icons.append(el('i', 'bi ' + (p.isMicrophoneEnabled ? 'bi-mic-fill text-on' : 'bi-mic-mute-fill')));
    li.append(av, info, icons);
    if (isHost && !isTeacher(p) && p !== room.localParticipant) {
      var actions = el('span', 'lv-person-actions');
      var speaking = settings.open_mic ? p.isMicrophoneEnabled : !!(p.permissions && p.permissions.canPublish);
      var b;
      if (speaking) {
        b = el('button', 'lv-mini-btn', S('stopSpeak'));
        b.onclick = function () {
          if (settings.open_mic) {
            var mic = p.getTrackPublication(LK.Track.Source.Microphone);
            control('mute_mic', { identity: p.identity, track: mic ? mic.trackSid : '' });
          } else control('stop_speak', { identity: p.identity });
        };
        actions.append(b);
      } else if (!settings.open_mic) {
        b = el('button', 'lv-mini-btn go', S('allow'));
        b.onclick = function () { control('allow_speak', { identity: p.identity }); };
        actions.append(b);
      }
      if (handOf(p) && !speaking) {
        b = el('button', 'lv-mini-btn', S('lowerHand'));
        b.onclick = function () { control('lower_hand', { identity: p.identity }); };
        actions.append(b);
      }
      if (!inHands) {
        b = el('button', 'lv-mini-btn danger', S('remove'));
        b.onclick = function () { if (window.confirm(S('confirmRemove'))) control('remove', { identity: p.identity }); };
        actions.append(b);
      }
      li.append(actions);
    }
    return li;
  }

  function renderPeople(all) {
    var hands = all.filter(handOf).sort(function (a, b) { return Number(handOf(a)) - Number(handOf(b)); });
    var list = $('lv-hands');
    list.textContent = '';
    hands.forEach(function (p) { list.append(personRow(p, true)); });
    $('lv-hands-title').hidden = !hands.length;
    var badge = $('lv-hand-badge');
    badge.textContent = hands.length;
    badge.hidden = !hands.length;
    var people = $('lv-people');
    people.textContent = '';
    all.slice().sort(function (a, b) { return (isTeacher(b) - isTeacher(a)) || (a.name || '').localeCompare(b.name || ''); })
      .forEach(function (p) { people.append(personRow(p, false)); });
  }

  /* ---------- Buttons ---------- */
  function setCtl(btn, on, icon, text, disabled) {
    if (!btn) return;
    btn.classList.toggle('on', !!on);
    btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    btn.disabled = !!disabled;
    btn.querySelector('i').className = 'bi ' + icon;
    btn.querySelector('span').textContent = text;
  }

  function renderControls() {
    if (!room) return;
    var me = room.localParticipant;
    setCtl($('lv-mic'), me.isMicrophoneEnabled, me.isMicrophoneEnabled ? 'bi-mic-fill' : 'bi-mic-mute-fill', S('mic'), !canSpeak());
    setCtl($('lv-cam'), me.isCameraEnabled, me.isCameraEnabled ? 'bi-camera-video-fill' : 'bi-camera-video-off-fill', S('camera'), !canCamera());
    $('lv-cam').hidden = !canCamera() && !me.isCameraEnabled;
    if (isHost) {
      setCtl($('lv-screen'), me.isScreenShareEnabled, 'bi-display', me.isScreenShareEnabled ? S('stopShare') : S('share'));
      if (!(navigator.mediaDevices && navigator.mediaDevices.getDisplayMedia)) $('lv-screen').hidden = true;
      document.querySelectorAll('[data-setting]').forEach(function (box) { box.checked = !!settings[box.dataset.setting]; });
    } else {
      var up = !!handOf(me);
      setCtl($('lv-hand'), up, up ? 'bi-hand-index-thumb-fill' : 'bi-hand-index-thumb', up ? S('lower') : S('raise'), settings.open_mic);
    }
    $('lv-locked-chip').hidden = !settings.locked;
    var chat = canChat();
    $('lv-chat-form').hidden = !chat;
    $('lv-chat-off').hidden = chat;
    $('lv-reacts').classList.toggle('off', !chat);
  }

  $('lv-mic').addEventListener('click', function () {
    var me = room.localParticipant;
    me.setMicrophoneEnabled(!me.isMicrophoneEnabled).catch(function () { banner(S('noMedia')); }).then(sync);
  });
  $('lv-cam').addEventListener('click', function () {
    var me = room.localParticipant;
    me.setCameraEnabled(!me.isCameraEnabled).catch(function () { banner(S('noMedia')); }).then(sync);
  });
  if ($('lv-screen')) $('lv-screen').addEventListener('click', function () {
    var me = room.localParticipant;
    me.setScreenShareEnabled(!me.isScreenShareEnabled, { audio: true }).catch(function () {}).then(sync);
  });
  if ($('lv-hand')) $('lv-hand').addEventListener('click', function () {
    var up = !handOf(room.localParticipant);
    post(cfg.handUrl, { up: up ? '1' : '0' }).then(function () { if (up) banner(S('handUp')); }).catch(function (e) { banner(e.message); });
  });
  document.querySelectorAll('[data-setting]').forEach(function (box) {
    box.addEventListener('change', function () {
      control('set', { setting: box.dataset.setting, value: box.checked ? '1' : '0' });
    });
  });
  document.querySelectorAll('[data-action]').forEach(function (btn) {
    btn.addEventListener('click', function () { control(btn.dataset.action); });
  });
  if ($('lv-share')) $('lv-share').addEventListener('click', function () {
    if (navigator.clipboard) navigator.clipboard.writeText(cfg.shareUrl).then(function () { banner(S('copied')); }, function () { banner(cfg.shareUrl, true); });
    else banner(cfg.shareUrl, true);
  });
  $('lv-leave').addEventListener('click', function () {
    if (isHost && !window.confirm(S('confirmLeave'))) return;
    leaving = true;
    room.disconnect();
  });
  if ($('lv-end')) $('lv-end').addEventListener('click', function () {
    if (window.confirm(S('confirmEnd'))) control('end');
  });

  /* ---------- Chat and reactions ---------- */
  var encoder = new TextEncoder(), decoder = new TextDecoder();
  function send(obj, topic) {
    return room.localParticipant.publishData(encoder.encode(JSON.stringify(obj)), { reliable: true, topic: topic });
  }
  function addChat(p, text) {
    var box = $('lv-chat');
    var msg = el('div', 'lv-msg' + (p && isTeacher(p) ? ' teacher' : '') + (p === room.localParticipant ? ' mine' : ''));
    msg.append(el('b', null, p ? label(p) : ''), el('span', null, text));
    box.append(msg);
    box.scrollTop = box.scrollHeight;
    var panel = $('lv-panel');
    var visible = panel.dataset.tab === 'chat' && (window.innerWidth >= 900 || panel.classList.contains('open'));
    if (!visible && p !== room.localParticipant) {
      unreadChat += 1;
      $('lv-chat-badge').textContent = unreadChat;
      $('lv-chat-badge').hidden = false;
    }
  }
  function floatEmoji(emoji) {
    var f = el('span', 'lv-float', emoji);
    f.style.left = (10 + Math.random() * 70) + '%';
    $('lv-floats').append(f);
    setTimeout(function () { f.remove(); }, 2600);
  }
  function onData(payload, participant, topic) {
    var data;
    try { data = JSON.parse(decoder.decode(payload)); } catch (e) { return; }
    if (topic === 'chat' && typeof data.text === 'string') addChat(participant, data.text.slice(0, 300));
    if (topic === 'react' && EMOJIS.indexOf(data.e) !== -1) floatEmoji(data.e);
  }
  $('lv-chat-form').addEventListener('submit', function (e) {
    e.preventDefault();
    var input = $('lv-chat-input'), text = input.value.trim().slice(0, 300);
    if (!text || !canChat()) return;
    send({ text: text }, 'chat').then(function () { addChat(room.localParticipant, text); input.value = ''; })
      .catch(function () { banner(S('actionFailed')); });
  });
  document.querySelectorAll('.lv-react').forEach(function (btn) {
    btn.addEventListener('click', function () {
      if (!canChat() || Date.now() - lastReact < 1200) return;
      lastReact = Date.now();
      send({ e: btn.dataset.emoji }, 'react').then(function () { floatEmoji(btn.dataset.emoji); }).catch(function () {});
    });
  });

  /* ---------- Panel tabs (a drawer on phones) ---------- */
  function showTab(name, open) {
    var panel = $('lv-panel');
    panel.dataset.tab = name;
    document.querySelectorAll('.lv-tab').forEach(function (t) {
      var on = t.dataset.tab === name;
      t.classList.toggle('active', on);
      t.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    document.querySelectorAll('.lv-pane').forEach(function (p) { p.hidden = p.dataset.pane !== name; });
    if (name === 'chat') { unreadChat = 0; $('lv-chat-badge').hidden = true; }
    if (open) panel.classList.add('open');
  }
  $('lv-panel').dataset.tab = 'people';
  document.querySelectorAll('.lv-tab').forEach(function (t) { t.addEventListener('click', function () { showTab(t.dataset.tab); }); });
  $('lv-open-people').addEventListener('click', function () { showTab('people', true); });
  $('lv-open-chat').addEventListener('click', function () { showTab('chat', true); });
  $('lv-panel-close').addEventListener('click', function () { $('lv-panel').classList.remove('open'); });

  /* ---------- Clock ---------- */
  var started = new Date(cfg.startedAt).getTime();
  setInterval(function () {
    var s = Math.max(0, Math.floor((Date.now() - started) / 1000));
    var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    $('lv-timer').textContent = (h ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(sec).padStart(2, '0');
  }, 1000);

  var audio = el('div');
  audio.id = 'lv-audio';
  audio.hidden = true;
  document.body.append(audio);
})();
