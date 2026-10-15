/* Live class room (LiveKit). The server decides who may speak, share or draw; this script shows the room and the controls.
   Chat, reactions and votes are sent to the server, which filters and saves them and passes them on to the room. */
(function () {
  'use strict';
  var LK = window.LivekitClient;
  var cfg = JSON.parse(document.getElementById('lv-config').textContent);
  var csrf = (document.querySelector('[name=csrfmiddlewaretoken]') || {}).value || '';
  var isHost = cfg.role === 'host';
  var room = null, settings = {}, tiles = new Map(), leaving = false, moving = false, unreadChat = 0, canSpeakBefore = false;
  var myGroup = 0, poll = null, myVote = null, pollHidden = false, launch = null, launchHidden = false, groupsInfo = null;
  var resultsTimer = null, spotVideo = null;
  var DATA_MODES = ['full', 'saver', 'audio'];
  var dataMode = 'full';
  try { dataMode = DATA_MODES.indexOf(localStorage.getItem('c4k-live-data')) !== -1 ? localStorage.getItem('c4k-live-data') : 'full'; } catch (e) { /* private window */ }

  var $ = function (id) { return document.getElementById(id); };
  function S(key) {
    var node = document.querySelector('#lv-strings [data-k="' + key + '"]');
    return node ? node.textContent.trim() : key;
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
  function request(key, data, method) {
    var opts = { method: method || 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': csrf } };
    if ((method || 'POST') === 'POST') {
      var body = new URLSearchParams();
      Object.keys(data || {}).forEach(function (k) {
        [].concat(data[k]).forEach(function (v) { body.append(k, v); });
      });
      opts.body = body;
    }
    return fetch(cfg.urls[key], opts).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) {
        if (!r.ok || !d.ok) throw new Error(d.error || S('actionFailed'));
        return d;
      });
    });
  }
  var bannerTimer;
  function banner(text, sticky) {
    var b = $('lv-banner');
    b.textContent = text || '';
    b.hidden = !text;
    clearTimeout(bannerTimer);
    if (text && !sticky) bannerTimer = setTimeout(function () { b.hidden = true; }, 4500);
  }

  /* ---------- Joining and moving between rooms (breakout groups) ---------- */
  /* With a waiting room, the token request answers "waiting" until the teacher lets this person in. */
  function getToken() {
    return request('token').then(function (d) {
      if (!d.waiting) { $('lv-wait').hidden = true; return d; }
      $('lv-wait').hidden = false;
      return new Promise(function (resolve) { setTimeout(resolve, 4000); }).then(getToken);
    });
  }

  function connect() {
    return getToken().then(function (d) {
      settings = d.settings || {};
      applyState(d);
      var r = new LK.Room({
        adaptiveStream: true, dynacast: true,
        videoCaptureDefaults: { resolution: LK.VideoPresets.h540.resolution },
        publishDefaults: { simulcast: true }
      });
      wire(r);
      return r.connect(d.url, d.token).then(function () {
        room = r;
        readSettings();
        room.startAudio().catch(function () {});
        canSpeakBefore = canSpeak();
        sync();
      });
    });
  }

  $('lv-join').addEventListener('click', function () {
    var btn = this, err = $('lv-join-error');
    btn.disabled = true;
    err.hidden = true;
    connect().then(function () {
      $('lv-prejoin').hidden = true;
      $('lv-app').hidden = false;
      sync();
      if (myGroup) banner(S('youAreInGroup'));
      if (isHost) {
        room.localParticipant.enableCameraAndMicrophone().catch(function () { banner(S('noMedia')); }).then(sync);
        loadLobby();
        setInterval(loadLobby, 8000);
      }
    }).catch(function (e) {
      $('lv-wait').hidden = true;
      btn.disabled = false;
      err.textContent = (e && e.message && e.message !== 'Failed to fetch') ? e.message : S('joinFailed');
      err.hidden = false;
    });
  });

  function resetStage() {
    tiles.forEach(function (t) { attach(t.video, null); t.el.remove(); });
    tiles.clear();
    if (spotVideo) attach(spotVideo, null);
    $('lv-spot').textContent = '';
    $('lv-audio').textContent = '';
  }

  function moveRoom() {
    if (moving || !room) return;
    moving = true;
    banner(S('moving'), true);
    var me = room.localParticipant, wasMic = me.isMicrophoneEnabled, wasCam = me.isCameraEnabled, old = room;
    room = null;
    old.disconnect().catch(function () {}).then(function () {
      resetStage();
      return connect();
    }).then(function () {
      moving = false;
      banner(myGroup ? (isHost ? S('visiting') + ' ' + S('group') + ' ' + myGroup : S('youAreInGroup')) : S('backToMain'));
      if (isHost) {
        var lp = room.localParticipant;
        Promise.all([lp.setMicrophoneEnabled(wasMic), lp.setCameraEnabled(wasCam)]).catch(function () {}).then(sync);
      }
    }).catch(function () {
      window.location.reload();
    });
  }

  function wire(r) {
    var E = LK.RoomEvent;
    [E.ParticipantConnected, E.ParticipantDisconnected, E.TrackSubscribed, E.TrackUnsubscribed, E.TrackMuted,
      E.TrackUnmuted, E.LocalTrackPublished, E.LocalTrackUnpublished, E.ActiveSpeakersChanged, E.TrackPublished,
      E.ParticipantAttributesChanged].forEach(function (ev) { r.on(ev, function () { if (room === r) sync(); }); });

    r.on(E.TrackSubscribed, function (track) {
      if (track.kind === 'audio') $('lv-audio').appendChild(track.attach());
    });
    r.on(E.TrackUnsubscribed, function (track) {
      if (track.kind === 'audio') track.detach().forEach(function (n) { n.remove(); });
    });
    r.on(E.ParticipantConnected, function (p) {
      // The teacher's browser holds the whiteboard and hands it to anyone who arrives late.
      if (isHost && settings.board && window.C4KBoard.hasDrawing()) sendBoardState([p.identity]);
    });
    r.on(E.ParticipantPermissionsChanged, function (prev, participant) {
      if (room !== r) return;
      if (participant && participant !== r.localParticipant) { sync(); return; }
      var now = canSpeak();
      if (!isHost && !myGroup && now && !canSpeakBefore) banner(S('canSpeak'));
      if (!isHost && !now && canSpeakBefore) banner(S('muted'));
      canSpeakBefore = now;
      sync();
    });
    r.on(E.RoomMetadataChanged, function () { if (room === r) { readSettings(); sync(); } });
    r.on(E.DataReceived, function (payload, participant, kind, topic) { onData(payload, participant, topic); });
    r.on(E.ConnectionQualityChanged, function (quality, participant) {
      if (participant === r.localParticipant) $('lv-net').hidden = quality !== LK.ConnectionQuality.Poor || dataMode !== 'full';
    });
    r.on(E.Reconnecting, function () { banner(S('reconnecting'), true); });
    r.on(E.Reconnected, function () { banner(''); });
    r.on(E.Disconnected, function (reason) { if (!moving && room === r) onDisconnected(reason); });
  }

  function onDisconnected(reason) {
    var R = LK.DisconnectReason || {};
    clearInterval(resultsTimer);
    $('lv-app').hidden = true;
    if (reason === R.ROOM_DELETED) {
      $('lv-ended').hidden = false;
    } else if (reason === R.PARTICIPANT_REMOVED) {
      $('lv-ended-title').textContent = S('removedTitle');
      $('lv-ended-text').textContent = S('removedText');
      if ($('lv-ended-xp')) $('lv-ended-xp').hidden = true;
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

  /* ---------- What the server sends: chat, polls, lessons, groups ---------- */
  function applyState(d) {
    var st = d.state || {};
    myGroup = d.group || 0;
    $('lv-chat').textContent = '';
    (st.chat || []).forEach(addChat);
    unreadChat = 0;
    $('lv-chat-badge').hidden = true;
    if (!poll || !st.poll || poll.id !== (st.poll || {}).id) pollHidden = false;
    poll = st.poll || null;
    myVote = st.myVote != null ? st.myVote : null;
    setLaunch(st.launch || null);
    if (isHost) {
      groupsInfo = st.groups || null;
      renderGroups();
    }
    renderPoll();
  }

  function onData(payload, participant, topic) {
    var data;
    try { data = JSON.parse(new TextDecoder().decode(payload)); } catch (e) { return; }
    if (topic === 'wb') {
      if (participant && (participant.identity === cfg.host || settings.board_draw)) window.C4KBoard.receive(data);
      return;
    }
    if (topic !== 'c4k' || participant) return;  // only trust messages from the server
    switch (data.type) {
      case 'chat': addChat(data.msg); break;
      case 'chat_delete':
        var gone = document.querySelector('.lv-msg[data-id="' + Number(data.id) + '"]');
        if (gone) gone.remove();
        break;
      case 'flag': if (isHost) banner(S('flagged') + ' ' + data.name + ' (' + data.reason + ')'); break;
      case 'react': if (['👍', '👏', '😂', '😕', '🎉'].indexOf(data.e) !== -1) floatEmoji(data.e); break;
      case 'poll':
        if (!poll || poll.id !== data.poll.id) { pollHidden = false; myVote = null; }
        poll = data.poll;
        renderPoll();
        break;
      case 'launch': setLaunch(data.launch); break;
      case 'move': moveRoom(); break;
      case 'lobby': if (isHost) loadLobby(); break;
    }
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
    if (room && p === room.localParticipant) return name + ' (' + S('you') + ')';
    return isTeacher(p) ? name + ' (' + S('teacher') + ')' : name;
  }

  /* ---------- Video tiles ---------- */
  function tileFor(p) {
    var t = tiles.get(p.identity);
    if (t) return t;
    var node = el('div', 'lv-tile' + (isTeacher(p) ? ' teacher' : ''));
    var video = el('video');
    video.autoplay = true; video.playsInline = true; video.muted = true;
    node.append(video, el('div', 'lv-avatar', initials(p.name || p.identity)), el('div', 'lv-name'), el('div', 'lv-tile-hand', '✋'));
    t = { el: node, video: video, name: node.querySelector('.lv-name') };
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

  /* Data saver: only the teacher's video (in low quality) and shared screens. Audio only: no video at all. */
  function applyDataMode() {
    var Src = LK.Track.Source;
    room.remoteParticipants.forEach(function (p) {
      p.trackPublications.forEach(function (pub) {
        if (pub.kind !== 'video') return;
        var want = dataMode === 'full' || (dataMode === 'saver' && (isTeacher(p) || pub.source === Src.ScreenShare));
        if (pub._want !== want) { pub._want = want; pub.setSubscribed(want); }
        var q = dataMode === 'saver' && pub.source === Src.Camera ? LK.VideoQuality.LOW : LK.VideoQuality.HIGH;
        if (want && pub._q !== q && pub.setVideoQuality) { pub._q = q; pub.setVideoQuality(q); }
      });
    });
  }

  function sync() {
    if (!room) return;
    applyDataMode();
    var all = participants(), seen = {}, screen = null, Src = LK.Track.Source;
    all.forEach(function (p) {
      seen[p.identity] = true;
      var t = tileFor(p);
      var cam = p.getTrackPublication(Src.Camera);
      var camTrack = cam && cam.track && !cam.isMuted ? cam.track : null;
      attach(t.video, camTrack);
      t.el.classList.toggle('has-video', !!camTrack);
      t.el.classList.toggle('mine', p === room.localParticipant);
      t.el.classList.toggle('speaking', !!p.isSpeaking);
      t.el.classList.toggle('hand', !!handOf(p));
      t.name.textContent = '';
      t.name.append(el('i', 'bi ' + (p.isMicrophoneEnabled ? 'bi-mic-fill' : 'bi-mic-mute-fill')), document.createTextNode(' ' + label(p)));
      var ss = p.getTrackPublication(Src.ScreenShare);
      if (ss && ss.track && !ss.isMuted) screen = { p: p, track: ss.track };
    });
    tiles.forEach(function (t, id) { if (!seen[id]) { attach(t.video, null); t.el.remove(); tiles.delete(id); } });

    // Stage: the whiteboard, else a shared screen, else the teacher fills the spotlight. Everyone else sits in the strip.
    var spot = $('lv-spot'), grid = $('lv-grid'), boardOn = !!settings.board;
    var teacher = all.filter(isTeacher)[0];
    if (boardOn) screen = null;
    if (screen) {
      if (!spotVideo) { spotVideo = el('video', 'lv-screen'); spotVideo.autoplay = true; spotVideo.playsInline = true; spotVideo.muted = true; }
      attach(spotVideo, screen.track);
      if (spotVideo.parentNode !== spot) { spot.textContent = ''; spot.append(spotVideo, el('div', 'lv-name')); }
      spot.lastChild.textContent = (screen.p.name || '') + ' ' + S('screenSharing');
    } else {
      if (spotVideo) attach(spotVideo, null);
      var want = teacher && !boardOn ? tiles.get(teacher.identity).el : null;
      if (!want) { if (spot.firstChild && spot.firstChild.classList && !spot.firstChild.classList.contains('lv-tile')) spot.textContent = ''; }
      else if (want.parentNode !== spot) { spot.textContent = ''; spot.append(want); }
    }
    spot.classList.toggle('empty', boardOn || (!screen && !teacher));
    var order = all.slice().sort(function (a, b) {
      var rank = function (p) { return isTeacher(p) ? 0 : (p === room.localParticipant ? 1 : 2); };
      return rank(a) - rank(b) || (a.name || '').localeCompare(b.name || '');
    });
    var i = 0;
    order.forEach(function (p) {
      if (!screen && !boardOn && p === teacher) return;
      var node = tiles.get(p.identity).el;
      if (grid.children[i] !== node) grid.insertBefore(node, grid.children[i] || null);
      i += 1;
    });
    if (all.length === 1) {
      if (!$('lv-alone')) { var alone = el('p', 'lv-alone', S('nobody')); alone.id = 'lv-alone'; grid.appendChild(alone); }
    } else if ($('lv-alone')) $('lv-alone').remove();

    $('lv-count').querySelector('b').textContent = all.length;
    renderBoard();
    renderPeople(all);
    renderControls();
  }

  /* ---------- People list and hands ---------- */
  function control(action, extra) {
    return request('control', Object.assign({ action: action }, extra || {})).then(function (d) {
      if (d.settings) { settings = Object.assign(settings, d.settings); sync(); }
      return d;
    }).catch(function (e) { banner(e.message); throw e; });
  }
  function quiet(promise) { return promise.catch(function () {}); }

  function personRow(p, inHands) {
    var li = el('li', 'lv-person');
    var icons = el('span', 'lv-person-icons');
    if (handOf(p)) icons.append(el('span', 'lv-hand-ico', '✋'));
    icons.append(el('i', 'bi ' + (p.isMicrophoneEnabled ? 'bi-mic-fill text-on' : 'bi-mic-mute-fill')));
    li.append(el('span', 'lv-mini', initials(p.name || p.identity)), el('span', 'lv-person-name', label(p)), icons);
    if (isHost && !isTeacher(p) && p !== room.localParticipant) {
      var actions = el('span', 'lv-person-actions'), openRoom = settings.open_mic || myGroup > 0;
      var speaking = openRoom ? p.isMicrophoneEnabled : !!(p.permissions && p.permissions.canPublish);
      var b;
      if (speaking) {
        b = el('button', 'lv-mini-btn', S('stopSpeak'));
        b.onclick = function () {
          if (openRoom) {
            var mic = p.getTrackPublication(LK.Track.Source.Microphone);
            quiet(control('mute_mic', { identity: p.identity, track: mic ? mic.trackSid : '' }));
          } else quiet(control('stop_speak', { identity: p.identity }));
        };
        actions.append(b);
      } else if (!openRoom) {
        b = el('button', 'lv-mini-btn go', S('allow'));
        b.onclick = function () { quiet(control('allow_speak', { identity: p.identity })); };
        actions.append(b);
      }
      if (handOf(p) && !speaking) {
        b = el('button', 'lv-mini-btn', S('lowerHand'));
        b.onclick = function () { quiet(control('lower_hand', { identity: p.identity })); };
        actions.append(b);
      }
      if (!inHands) {
        b = el('button', 'lv-mini-btn danger', S('remove'));
        b.onclick = function () { if (window.confirm(S('confirmRemove'))) quiet(control('remove', { identity: p.identity })); };
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
    $('lv-hand-badge').textContent = hands.length;
    $('lv-hand-badge').hidden = !hands.length;
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
    var modeLabel = { full: S('fullVideo'), saver: S('saver'), audio: S('audioOnly') }[dataMode];
    var modeIcon = { full: 'bi-reception-4', saver: 'bi-reception-2', audio: 'bi-headphones' }[dataMode];
    setCtl($('lv-data'), dataMode !== 'full', modeIcon, modeLabel);
    if (isHost) {
      setCtl($('lv-screen'), me.isScreenShareEnabled, 'bi-display', me.isScreenShareEnabled ? S('stopShare') : S('share'));
      if (!(navigator.mediaDevices && navigator.mediaDevices.getDisplayMedia)) $('lv-screen').hidden = true;
      document.querySelectorAll('[data-setting]').forEach(function (box) { box.checked = !!settings[box.dataset.setting]; });
      var rec = $('lv-record');
      if (rec) {
        rec.classList.toggle('lv-btn-danger', !!settings.rec);
        rec.querySelector('span').textContent = settings.rec ? S('stopRec') : S('startRec');
      }
    } else {
      var up = !!handOf(me);
      setCtl($('lv-hand'), up, up ? 'bi-hand-index-thumb-fill' : 'bi-hand-index-thumb', up ? S('lower') : S('raise'), settings.open_mic || myGroup > 0);
    }
    $('lv-locked-chip').hidden = !settings.locked;
    $('lv-rec-chip').hidden = !settings.rec;
    var chip = $('lv-group-chip');
    chip.hidden = !myGroup;
    chip.querySelector('span').textContent = (isHost ? S('visiting') + ' ' : '') + S('group') + ' ' + myGroup;
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
    request('hand', { up: up ? '1' : '0' }).then(function () { if (up) banner(S('handUp')); }).catch(function (e) { banner(e.message); });
  });
  function setDataMode(mode) {
    dataMode = mode;
    try { localStorage.setItem('c4k-live-data', mode); } catch (e) { /* private window */ }
    banner({ full: S('fullOn'), saver: S('saverOn'), audio: S('audioOn') }[mode]);
    $('lv-net').hidden = true;
    sync();
  }
  $('lv-data').addEventListener('click', function () { setDataMode(DATA_MODES[(DATA_MODES.indexOf(dataMode) + 1) % DATA_MODES.length]); });
  $('lv-net').addEventListener('click', function () { setDataMode('saver'); });
  document.querySelectorAll('[data-setting]').forEach(function (box) {
    box.addEventListener('change', function () {
      quiet(control('set', { setting: box.dataset.setting, value: box.checked ? '1' : '0' }).then(function () {
        if (box.dataset.setting === 'board' && box.checked && window.C4KBoard.hasDrawing()) sendBoardState();
      }));
    });
  });
  document.querySelectorAll('[data-action]').forEach(function (btn) {
    btn.addEventListener('click', function () { quiet(control(btn.dataset.action)); });
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
    if (window.confirm(S('confirmEnd'))) quiet(control('end'));
  });

  /* ---------- Chat and reactions (through the server) ---------- */
  function addChat(item) {
    if (!item) return;
    var mine = item.from === cfg.me;
    var msg = el('div', 'lv-msg' + (item.role === 'host' ? ' teacher' : '') + (mine ? ' mine' : '') + (item.announce ? ' announce' : ''));
    msg.dataset.id = item.id;
    var who = item.name + (mine ? ' (' + S('you') + ')' : item.role === 'host' ? ' (' + S('teacher') + ')' : '');
    if (item.announce) who += ' · ' + S('everyGroup');
    msg.append(el('b', null, who), el('span', null, item.text));
    if (isHost && !mine) {
      var del = el('button', 'lv-msg-del');
      del.type = 'button';
      del.title = del.ariaLabel = S('deleteMsg');
      del.append(el('i', 'bi bi-trash3'));
      del.onclick = function () { quiet(control('chat_delete', { id: item.id })); };
      msg.append(del);
    }
    var box = $('lv-chat');
    box.append(msg);
    box.scrollTop = box.scrollHeight;
    var panel = $('lv-panel');
    var visible = panel.dataset.tab === 'chat' && (window.innerWidth >= 900 || panel.classList.contains('open'));
    if (!visible && !mine && !$('lv-app').hidden) {
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
  $('lv-chat-form').addEventListener('submit', function (e) {
    e.preventDefault();
    var input = $('lv-chat-input'), text = input.value.trim().slice(0, 300);
    if (!text || !canChat()) return;
    request('chat', { text: text }).then(function () { input.value = ''; }).catch(function (err) { banner(err.message); });
  });
  document.querySelectorAll('.lv-react').forEach(function (btn) {
    btn.addEventListener('click', function () {
      if (canChat()) request('react', { e: btn.dataset.emoji }).catch(function () {});
    });
  });

  /* ---------- Poll ---------- */
  function renderPoll() {
    var card = $('lv-poll-card');
    if (isHost) {
      $('lv-poll-close').hidden = !(poll && !poll.closed);
    }
    card.hidden = !poll || pollHidden;
    if (!poll) return;
    $('lv-poll-q').textContent = poll.q;
    var total = poll.counts.reduce(function (a, b) { return a + b; }, 0);
    var showBars = isHost || poll.closed || myVote != null;
    var box = $('lv-poll-options');
    box.textContent = '';
    poll.options.forEach(function (text, i) {
      var b = el('button', 'lv-poll-opt' + (myVote === i ? ' chosen' : ''));
      b.type = 'button';
      b.disabled = isHost || poll.closed;
      var pct = total ? Math.round((poll.counts[i] / total) * 100) : 0;
      if (showBars) { var bar = el('span', 'lv-poll-bar'); bar.style.width = pct + '%'; b.append(bar); }
      b.append(el('span', 'lv-poll-text', String.fromCharCode(65 + i) + '. ' + text));
      if (showBars) b.append(el('b', null, poll.counts[i] + ' (' + pct + '%)'));
      b.onclick = function () {
        request('vote', { poll: poll.id, choice: i }).then(function (d) { myVote = d.choice; renderPoll(); }).catch(function (e) { banner(e.message); });
      };
      box.append(b);
    });
    $('lv-poll-note').textContent = poll.closed ? S('pollClosed') + ' ' + total + ' ' + (total === 1 ? S('vote') : S('votes'))
      : isHost ? total + ' ' + (total === 1 ? S('vote') : S('votes')) : (myVote == null ? S('tapAnswer') : S('voted'));
    $('lv-poll-x').hidden = !(isHost || poll.closed);
  }
  $('lv-poll-x').addEventListener('click', function () { pollHidden = true; renderPoll(); });

  /* ---------- Lesson opened in class ---------- */
  function setLaunch(l) {
    if (!launch || !l || launch.id !== l.id) launchHidden = false;
    launch = l;
    var card = $('lv-launch-card');
    card.hidden = isHost || !launch || launchHidden;
    if (launch) {
      $('lv-launch-title').textContent = launch.title;
      $('lv-launch-open').href = launch.url;
    }
    if (isHost) {
      $('lv-results').hidden = !launch;
      clearInterval(resultsTimer);
      if (launch) { loadResults(); resultsTimer = setInterval(loadResults, 6000); }
    }
  }
  $('lv-launch-x').addEventListener('click', function () { launchHidden = true; $('lv-launch-card').hidden = true; });
  $('lv-launch-open').addEventListener('click', function () { launchHidden = true; setTimeout(function () { $('lv-launch-card').hidden = true; }, 300); });

  function loadResults() {
    request('results', null, 'GET').then(function (d) {
      $('lv-results-title').textContent = d.title || '';
      var list = $('lv-results-list');
      list.textContent = '';
      d.rows.forEach(function (r) {
        var li = el('li', 'lv-person');
        li.append(el('span', 'lv-mini', initials(r.name)), el('span', 'lv-person-name', r.name));
        var tag = r.done ? S('finished') : (r.here ? S('notYet') : S('notHere'));
        li.append(el('span', 'lv-result ' + (r.done ? 'done' : r.here ? 'todo' : 'away'), tag + (r.score != null ? ' · ' + r.score + '%' : '')));
        list.append(li);
      });
    }).catch(function () {});
  }

  /* ---------- Teacher activities ---------- */
  if (isHost) {
    var select = $('lv-lesson');
    (cfg.lessons || []).forEach(function (course) {
      var group = el('optgroup');
      group.label = course.course;
      course.lessons.forEach(function (l) {
        var o = el('option', null, l.title + (l.quiz ? ' (quiz)' : ''));
        o.value = l.id;
        group.append(o);
      });
      select.append(group);
    });
    $('lv-launch').addEventListener('click', function () {
      if (select.value) control('launch', { lesson: select.value }).then(function (d) { setLaunch(d.launch); }).catch(function () {});
    });
    $('lv-launch-close').addEventListener('click', function () {
      control('launch_close').then(function () { setLaunch(null); }).catch(function () {});
    });

    $('lv-poll-form').addEventListener('submit', function (e) {
      e.preventDefault();
      var form = e.target;
      var options = Array.prototype.map.call(form.querySelectorAll('[name=options]'), function (i) { return i.value; });
      control('poll_start', { question: form.question.value, options: options }).then(function (d) {
        poll = d.poll; pollHidden = false; renderPoll(); form.reset();
      }).catch(function () {});
    });
    $('lv-poll-close').addEventListener('click', function () {
      control('poll_close').then(function (d) { if (d.poll) { poll = d.poll; renderPoll(); } }).catch(function () {});
    });

    $('lv-groups-start').addEventListener('click', function () {
      control('groups_start', { count: $('lv-group-count').value }).then(function (d) { groupsInfo = d.groups; renderGroups(); }).catch(function () {});
    });
    $('lv-groups-end').addEventListener('click', function () {
      control('groups_end').then(function (d) { groupsInfo = null; renderGroups(); if (d.move) moveRoom(); }).catch(function () {});
    });
    $('lv-announce-send').addEventListener('click', function () {
      var input = $('lv-announce');
      if (input.value.trim()) control('announce', { text: input.value }).then(function () { input.value = ''; }).catch(function () {});
    });

    var recBtn = $('lv-record');
    if (recBtn) recBtn.addEventListener('click', function () {
      if (settings.rec) { quiet(control('record_stop')); return; }
      var me = room.localParticipant, Src = LK.Track.Source;
      var mic = me.getTrackPublication(Src.Microphone);
      var video = me.getTrackPublication(Src.ScreenShare) || me.getTrackPublication(Src.Camera);
      if (!mic || !mic.trackSid) { banner(S('recNeedsMedia')); return; }
      quiet(control('record_start', { audio: mic.trackSid, video: video && video.trackSid ? video.trackSid : '' }));
    });
  }

  function renderGroups() {
    if (!isHost) return;
    $('lv-groups-form').hidden = !!groupsInfo;
    $('lv-groups-live').hidden = !groupsInfo;
    var list = $('lv-groups-list');
    list.textContent = '';
    if (!groupsInfo) return;
    function row(label, names, target) {
      var li = el('li', 'lv-person');
      li.append(el('span', 'lv-mini', target ? String(target) : '★'), el('span', 'lv-person-name', label + (names ? ': ' + names : '')));
      var actions = el('span', 'lv-person-actions');
      var b = el('button', 'lv-mini-btn' + (myGroup === target ? '' : ' go'), myGroup === target ? S('visiting') : S('visit'));
      b.disabled = myGroup === target;
      b.onclick = function () { control('groups_visit', { group: target }).then(function (d) { if (d.move) moveRoom(); }).catch(function () {}); };
      actions.append(b);
      li.append(actions);
      list.append(li);
    }
    row(S('mainRoom'), '', 0);
    for (var g = 1; g <= groupsInfo.count; g++) {
      var names = (groupsInfo.members[String(g)] || []).join(', ') || S('nobodyInGroup');
      row(S('group') + ' ' + g, names, g);
    }
  }

  /* ---------- Waiting room (teacher) ---------- */
  var lobbyCount = 0;
  function loadLobby() {
    if (!isHost) return;
    request('lobby', null, 'GET').then(function (d) {
      var list = $('lv-lobby-list');
      list.textContent = '';
      d.waiting.forEach(function (w) {
        var li = el('li', 'lv-person');
        li.append(el('span', 'lv-mini', initials(w.name)), el('span', 'lv-person-name', w.name + (w.member ? '' : ' (' + S('notInClass') + ')')));
        var actions = el('span', 'lv-person-actions');
        var yes = el('button', 'lv-mini-btn go', S('admit'));
        yes.onclick = function () { control('admit', { identity: w.identity }).then(loadLobby, function () {}); };
        var no = el('button', 'lv-mini-btn danger', S('deny'));
        no.onclick = function () { control('deny', { identity: w.identity }).then(loadLobby, function () {}); };
        actions.append(yes, no);
        li.append(actions);
        list.append(li);
      });
      $('lv-lobby').hidden = !d.waiting.length;
      if (d.waiting.length > lobbyCount) banner(d.waiting[d.waiting.length - 1].name + ' ' + S('isWaiting'));
      lobbyCount = d.waiting.length;
      var badge = $('lv-hand-badge');
      if (d.waiting.length) { badge.hidden = false; badge.textContent = d.waiting.length; }
    }).catch(function () {});
  }
  if ($('lv-admit-all')) $('lv-admit-all').addEventListener('click', function () {
    control('admit_all').then(loadLobby, function () {});
  });

  /* ---------- Whiteboard ---------- */
  function sendBoard(obj, to) {
    if (!room || !(isHost || perms().canPublishData)) return Promise.resolve();
    var opts = { reliable: true, topic: 'wb' };
    if (to) opts.destinationIdentities = to;
    return room.localParticipant.publishData(new TextEncoder().encode(JSON.stringify(obj)), opts).catch(function () {});
  }
  function sendBoardState(to) {
    window.C4KBoard.stateMessages().reduce(function (chain, msg) {
      return chain.then(function () { return sendBoard(msg, to); });
    }, Promise.resolve());
  }
  window.C4KBoard.init({ wrap: $('lv-board'), canvas: $('lv-board-canvas'), send: function (obj) { sendBoard(obj); } });
  var boardWasOn = false;
  function renderBoard() {
    var on = !!settings.board, draw = isHost || (!!settings.board_draw && !!perms().canPublishData);
    $('lv-board').hidden = !on;
    $('lv-board-tools').hidden = !draw;
    window.C4KBoard.allowDraw(on && draw);
    if (on && !boardWasOn) setTimeout(window.C4KBoard.shown, 0);
    boardWasOn = on;
  }
  if ($('lv-board-clear')) $('lv-board-clear').addEventListener('click', function () { window.C4KBoard.clear(true); });

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
  if ($('lv-open-teach')) $('lv-open-teach').addEventListener('click', function () { showTab('teach', true); });
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
