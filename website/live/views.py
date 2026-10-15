"""Live classes: the teacher starts the room, learners in the class join from the short link.

Safety rules: only the class teacher and learners who joined the class (with its join code) get in. Learners arrive with
their microphone and camera off and can only talk when the teacher allows it (or turns on open mic, or in a breakout
group). Every permission is decided here and signed into the LiveKit token, so a learner cannot give themselves more
rights from the browser. Chat, reactions and poll votes go through this server (filtered and saved), never straight
from one child's browser to another.
"""

import json
import logging
import random
import re
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.models import ClassMembership, Classroom, User
from billing.access import can_join_live

from . import livekit, moderation, services
from .models import LiveAttendance, LiveChatMessage, LiveLaunch, LivePoll, LivePollVote, LiveRecording, LiveRoom, LiveSession

logger = logging.getLogger(__name__)

TOGGLES = {
    "chat": "chat_enabled", "open_mic": "open_mic", "video": "student_video", "locked": "locked",
    "board": "board", "board_draw": "board_draw",
}
PERMISSION_SETTINGS = {"open_mic", "video", "board_draw"}
REACTIONS = {"👍", "👏", "😂", "😕", "🎉"}
MAX_GROUPS = 8
ROOM_NAME = re.compile(r"^c4k-[A-Z0-9]+-(\d+)(?:-g(\d+))?$")


def identity(user):
    return f"u{user.pk}"


def user_id_from(identity_text):
    try:
        return int(identity_text[1:]) if identity_text.startswith("u") else None
    except ValueError:
        return None


def display_name(user, host=False):
    """Teachers show their full name. Learners show first name and an initial, so classmates never see a full name."""
    if host:
        return user.get_full_name() or user.username
    if user.first_name:
        return f"{user.first_name} {user.last_name[:1]}." if user.last_name else user.first_name
    return user.username


def in_group(session, attendance):
    return bool(session.groups and 0 < attendance.group <= session.groups)


def room_for(session, attendance):
    """The LiveKit room this person belongs in right now: their breakout group, or the main room."""
    return session.room_name(attendance.group) if in_group(session, attendance) else session.livekit_name


def learner_permission(room, attendance, session=None):
    """What a learner may do right now, in LiveKit's server API format. Breakout groups are open-mic."""
    sources = ["MICROPHONE"] + (["CAMERA"] if room.student_video else [])
    grouped = session is not None and in_group(session, attendance)
    return {
        "can_subscribe": True,
        "can_publish": grouped or room.open_mic or attendance.can_speak,
        "can_publish_data": room.board_draw,  # only used for the whiteboard; chat goes through the server
        "can_publish_sources": sources,
        "can_update_metadata": False,
    }


def _room_for_code(code):
    return get_object_or_404(LiveRoom.objects.select_related("classroom__facilitator", "classroom__tier"), code=code.strip().upper())


def _role(user, room):
    """'host', 'learner' or None (not allowed in)."""
    classroom = room.classroom
    if user.pk == classroom.facilitator_id and user.role == User.Role.FACILITATOR and not user.awaiting_approval:
        return "host"
    if user.role == User.Role.LEARNER and (
        (not room.is_main and room.audience == LiveRoom.Audience.ANYONE)
        or ClassMembership.objects.filter(classroom=classroom, learner=user).exists()
    ):
        return "learner"
    return None


def _passcode_ok(request, room, role):
    return role == "host" or not room.passcode or request.session.get(f"live-pass-{room.pk}") == room.passcode


def _gate(request, room, reason, status=200, **extra):
    base = "teach/base.html" if request.user.role == User.Role.FACILITATOR else "learner/base.html"
    ctx = {"room": room, "reason": reason, "base_tpl": base, "nav": "classes", **extra}
    if request.user.role == User.Role.FACILITATOR:
        ctx["classes"] = list(request.user.classrooms.filter(archived=False))
        ctx["nav"] = "classes"
    return render(request, "live/gate.html", ctx, status=status)


def _json_error(message, status=400):
    return JsonResponse({"ok": False, "error": message}, status=status)


def _throttled(key, seconds):
    """True if this action happened less than `seconds` ago (and remembers it otherwise)."""
    return not cache.add(key, 1, seconds)


def _run_all(func, items):
    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(func, items))


def broadcast(session, payload, rooms=None, to=None):
    """Send a server message to every room of the class (main room and breakout groups), or to some of them."""
    def push(name):
        try:
            livekit.send_data(name, payload, to=to)
        except livekit.LiveKitError:
            pass  # an empty breakout room may already be closed

    _run_all(push, rooms or session.room_names())


def push_settings(room, session):
    def push(name):
        try:
            livekit.update_room_metadata(name, room.settings_json())
        except livekit.LiveKitError:
            pass

    _run_all(push, session.room_names())


def live_summary(classroom):
    """For the teacher's class page: the room (made on first visit, so the link can be shared early) and recent classes."""
    room, _ = LiveRoom.objects.get_or_create(classroom=classroom, is_main=True)
    recent = list(
        room.sessions.filter(ended_at__isnull=False).prefetch_related("attendance", "recordings")[:5]
    )
    return {"room": room, "current": room.current_session, "recent": recent}


def class_recordings(classroom):
    return LiveRecording.objects.filter(session__room__classroom=classroom, status=LiveRecording.Status.READY).select_related("session")


def _chat_item(msg):
    host = msg.user_id == msg.session.room.classroom.facilitator_id
    return {
        "id": msg.pk, "from": identity(msg.user), "name": display_name(msg.user, host=host), "role": "host" if host else "learner",
        "text": msg.text, "announce": msg.announce,
    }


def _lesson_choices(classroom):
    """Lessons a teacher can open for the class: the class's programme, or every programme when the class has none."""
    from courses.models import Course
    from courses.quiz import quiz_question_count

    courses = Course.objects.prefetch_related("lessons").select_related("tier")
    if classroom.tier_id:
        courses = courses.filter(tier_id=classroom.tier_id)
    return [
        {"course": c.display_title, "lessons": [{"id": l.pk, "title": l.display_title, "quiz": quiz_question_count(l) > 0} for l in c.lessons.all()]}
        for c in courses
    ]


def _launch_item(launch):
    if launch is None:
        return None
    lesson = launch.lesson
    return {"id": launch.pk, "title": lesson.display_title, "url": lesson.get_absolute_url()}


def _groups_info(session):
    if not session.groups:
        return None
    members = {g: [] for g in range(1, session.groups + 1)}
    for att in session.attendance.select_related("user").filter(is_host=False, removed=False, group__gt=0):
        if att.group in members:
            members[att.group].append(display_name(att.user))
    return {"count": session.groups, "members": {str(g): names for g, names in members.items()}}


def short_link(request, code):
    return redirect("live:room", code=code.strip().upper())


@login_required
@require_POST
def start(request, class_id):
    """Start the class's main live room."""
    classroom = get_object_or_404(Classroom, pk=class_id, facilitator=request.user)
    room, _ = LiveRoom.objects.get_or_create(classroom=classroom, is_main=True)
    return _start(request, room)


@login_required
@require_POST
def start_room(request, code):
    """Start one meeting (or the main room) by its link code."""
    return _start(request, _room_for_code(code))


def _start(request, room):
    classroom = room.classroom
    if _role(request.user, room) != "host":
        raise Http404
    if not livekit.configured():
        return _gate(request, room, "not_set_up")
    if room.current_session is None:
        # A fresh start: nobody can talk yet, the room is open and nothing is recording; chat and video choices stay.
        room.open_mic = room.locked = room.recording = room.board = room.board_draw = False
        room.save(update_fields=["open_mic", "locked", "recording", "board", "board_draw"])
        session = LiveSession.objects.create(room=room, started_by=request.user)
        try:
            livekit.create_room(session.livekit_name, room.settings_json(), settings.LIVE_MAX_PARTICIPANTS)
        except livekit.LiveKitError as exc:
            session.delete()
            messages.error(request, f"The live class could not be started: {exc}")
            return redirect("teach:class", class_id=classroom.pk)
    return redirect("live:room", code=room.code)


@login_required
def room_page(request, code):
    room = _room_for_code(code)
    role = _role(request.user, room)
    if role is None:
        return _gate(request, room, "not_member", status=403)
    if role == "learner" and not can_join_live(request.user):
        return _gate(request, room, "plan_needed", status=402)
    if not livekit.configured():
        return _gate(request, room, "not_set_up")
    if not _passcode_ok(request, room, role):
        return _gate(request, room, "passcode", wrong=request.GET.get("wrong") == "1")
    session = room.current_session
    if session is None:
        return _gate(request, room, "host_start" if role == "host" else "waiting")
    if role == "learner":
        attendance = LiveAttendance.objects.filter(session=session, user=request.user).first()
        if attendance and attendance.removed:
            return _gate(request, room, "removed", status=403)
        if room.locked and attendance is None:
            return _gate(request, room, "locked", status=403)
    urls = {name: reverse(f"live:{name}", args=[room.code]) for name in ("token", "status", "control", "hand", "chat", "react", "vote", "results", "lobby")}
    config = {
        "role": role,
        "me": identity(request.user),
        "host": identity(room.classroom.facilitator),
        "startedAt": session.started_at.isoformat(),
        "urls": urls,
        "shareUrl": request.build_absolute_uri(reverse("live_short", args=[room.code])),
        "exitUrl": reverse("teach:class", args=[room.classroom.pk]) if role == "host" else reverse("dashboard:classes"),
        "xp": 20,
    }
    if role == "host":
        config["lessons"] = _lesson_choices(room.classroom)
        config["canRecord"] = livekit.recording_configured()
        config["reportUrl"] = reverse("live:report", args=[session.pk])
    title = room.classroom.name if room.is_main else room.display_title
    return render(request, "live/room.html", {"room": room, "session": session, "role": role, "config": config, "title": title})


@login_required
@require_POST
def token(request, code):
    room = _room_for_code(code)
    role = _role(request.user, room)
    if role is None:
        return _json_error("You are not in this class.", 403)
    if role == "learner" and not can_join_live(request.user):
        return _json_error("Live classes need a plan that includes them.", 402)
    if not _passcode_ok(request, room, role):
        return _json_error("Type the passcode first.", 403)
    session = room.current_session
    if session is None or not livekit.configured():
        return _json_error("This class is not live right now.", 409)
    attendance = LiveAttendance.objects.filter(session=session, user=request.user).first()
    if role == "learner":
        if attendance and attendance.removed:
            return _json_error("Your teacher removed you from this class.", 403)
        if room.locked and attendance is None:
            return _json_error("The teacher has locked this class.", 403)
    if attendance is None:
        attendance = LiveAttendance.objects.create(
            session=session, user=request.user, is_host=role == "host", admitted=role == "host" or not room.waiting_room,
        )
        if not attendance.admitted:
            _tell_host_about_lobby(room, session)
    if not attendance.admitted:
        return JsonResponse({"ok": True, "waiting": True})

    room_name = room_for(session, attendance)
    if role == "host":
        grant = {"room": room_name, "roomAdmin": True, "canPublish": True, "canSubscribe": True,
                 "canPublishData": True, "canUpdateOwnMetadata": False}
    else:
        permission = learner_permission(room, attendance, session)
        grant = {
            "room": room_name, "canSubscribe": True, "canPublish": permission["can_publish"],
            "canPublishData": permission["can_publish_data"], "canUpdateOwnMetadata": False,
            "canPublishSources": [s.lower() for s in permission["can_publish_sources"]],
        }
    jwt = livekit.join_token(
        identity(request.user), display_name(request.user, host=role == "host"), grant, metadata=json.dumps({"role": role}),
    )

    group = attendance.group if in_group(session, attendance) else 0
    chat = session.chat.filter(flagged=False, hidden=False).select_related("user", "session__room__classroom")
    chat = [m for m in chat.order_by("-created_at")[:200] if m.announce or m.group == group][:50][::-1]
    poll = session.polls.filter(closed_at__isnull=True).first()
    launch = session.launches.filter(closed_at__isnull=True).first()
    state = {
        "chat": [_chat_item(m) for m in chat],
        "poll": poll.as_dict() if poll else None,
        "myVote": LivePollVote.objects.filter(poll=poll, user=request.user).values_list("choice", flat=True).first() if poll else None,
        "launch": _launch_item(launch),
    }
    if role == "host":
        state["groups"] = _groups_info(session)
        state["recording"] = session.recordings.filter(status=LiveRecording.Status.RECORDING).exists()
    return JsonResponse({
        "ok": True, "url": settings.LIVEKIT_URL, "token": jwt, "settings": json.loads(room.settings_json()),
        "group": group, "state": state,
    })


@login_required
def status(request, code):
    room = _room_for_code(code)
    if _role(request.user, room) is None:
        return _json_error("You are not in this class.", 403)
    session = room.current_session
    return JsonResponse({"ok": True, "live": session is not None, "settings": json.loads(room.settings_json())})


@login_required
@require_POST
def unlock(request, code):
    """Check the meeting passcode. Ten wrong tries lock the learner out of that meeting for 15 minutes."""
    room = _room_for_code(code)
    if _role(request.user, room) is None:
        raise Http404
    key = f"live-pass-tries-{request.user.pk}-{room.pk}"
    tries = cache.get(key, 0)
    if tries >= 10:
        messages.error(request, "Too many wrong passcodes. Wait 15 minutes, or ask your teacher.")
        return redirect(reverse("live:room", args=[room.code]) + "?wrong=1")
    if room.check_passcode(request.POST.get("passcode", "")):
        request.session[f"live-pass-{room.pk}"] = room.passcode
        cache.delete(key)
        return redirect("live:room", code=room.code)
    cache.set(key, tries + 1, 15 * 60)
    return redirect(reverse("live:room", args=[room.code]) + "?wrong=1")


def _tell_host_about_lobby(room, session):
    host_att = session.attendance.filter(is_host=True).first()
    try:
        livekit.send_data(room_for(session, host_att) if host_att else session.livekit_name, {"type": "lobby"},
                          to=[identity(room.classroom.facilitator)])
    except livekit.LiveKitError:
        pass  # the teacher's page also checks the waiting room every few seconds


@login_required
def lobby(request, code):
    """For the teacher: who is in the waiting room."""
    room = _room_for_code(code)
    if _role(request.user, room) != "host":
        return _json_error("Only the teacher can see this.", 403)
    session = room.current_session
    rows = []
    if session:
        members = set(room.classroom.memberships.values_list("learner_id", flat=True))
        rows = [
            {"identity": identity(a.user), "name": display_name(a.user), "member": a.user_id in members}
            for a in session.attendance.filter(admitted=False, removed=False).select_related("user")
        ]
    return JsonResponse({"ok": True, "waiting": rows})


def _learner_context(request, code):
    """(room, session, attendance) for a learner in a running class, or a JsonResponse error."""
    room = _room_for_code(code)
    role = _role(request.user, room)
    if role is None:
        return _json_error("You are not in this class.", 403)
    session = room.current_session
    if session is None:
        return _json_error("This class is not live right now.", 409)
    attendance = LiveAttendance.objects.filter(session=session, user=request.user).first()
    if attendance is None or attendance.removed or not attendance.admitted:
        return _json_error("Join the class first.", 403)
    return room, session, attendance, role


@login_required
@require_POST
def hand(request, code):
    """A learner raises or lowers their hand. Done on the server so learners never need rights to change their own details."""
    ctx = _learner_context(request, code)
    if isinstance(ctx, JsonResponse):
        return ctx
    room, session, attendance, role = ctx
    if role != "learner":
        return _json_error("Only learners raise hands.", 403)
    up = request.POST.get("up") == "1"
    value = str(int(timezone.now().timestamp() * 1000)) if up else ""
    try:
        livekit.update_participant(room_for(session, attendance), identity(request.user), attributes={"hand": value})
    except livekit.LiveKitError as exc:
        return _json_error(str(exc), 502)
    return JsonResponse({"ok": True, "up": up})


@login_required
@require_POST
def chat(request, code):
    """Chat goes through here: filtered, saved for review, then passed to the room."""
    ctx = _learner_context(request, code)
    if isinstance(ctx, JsonResponse):
        return ctx
    room, session, attendance, role = ctx
    host = role == "host"
    text = " ".join(request.POST.get("text", "").split())[:300]
    if not text:
        return _json_error("Type a message first.")
    if not host and not room.chat_enabled:
        return _json_error("The teacher has turned chat off.", 403)
    if not host and _throttled(f"live-chat-{request.user.pk}", 2):
        return _json_error("Slow down a little, then send again.", 429)
    group = attendance.group if in_group(session, attendance) else 0
    reason = moderation.check(text, host=host)
    msg = LiveChatMessage.objects.create(session=session, user=request.user, group=group, text=text, flagged=bool(reason), reason=reason or "")
    if reason:
        try:
            host_att = session.attendance.filter(is_host=True).first()
            host_room = room_for(session, host_att) if host_att else session.livekit_name
            livekit.send_data(host_room, {"type": "flag", "name": display_name(request.user), "reason": reason},
                              to=[identity(room.classroom.facilitator)])
        except livekit.LiveKitError:
            pass
        return _json_error(moderation.REASONS[reason], 400)
    msg.session = session
    broadcast(session, {"type": "chat", "msg": _chat_item(msg)}, rooms=[room_for(session, attendance)])
    return JsonResponse({"ok": True})


@login_required
@require_POST
def react(request, code):
    ctx = _learner_context(request, code)
    if isinstance(ctx, JsonResponse):
        return ctx
    room, session, attendance, role = ctx
    emoji = request.POST.get("e", "")
    if emoji not in REACTIONS:
        return _json_error("Unknown reaction.")
    if role != "host" and not room.chat_enabled:
        return _json_error("The teacher has turned reactions off.", 403)
    if _throttled(f"live-react-{request.user.pk}", 1):
        return JsonResponse({"ok": True, "skipped": True})
    broadcast(session, {"type": "react", "e": emoji}, rooms=[room_for(session, attendance)])
    return JsonResponse({"ok": True})


@login_required
@require_POST
def vote(request, code):
    ctx = _learner_context(request, code)
    if isinstance(ctx, JsonResponse):
        return ctx
    room, session, attendance, role = ctx
    poll = session.polls.filter(pk=request.POST.get("poll") or 0, closed_at__isnull=True).first()
    if poll is None:
        return _json_error("This poll has closed.", 409)
    try:
        choice = int(request.POST.get("choice", ""))
    except ValueError:
        return _json_error("Pick an answer.")
    if not 0 <= choice < len(poll.options):
        return _json_error("Pick an answer.")
    LivePollVote.objects.update_or_create(poll=poll, user=request.user, defaults={"choice": choice})
    broadcast(session, {"type": "poll", "poll": poll.as_dict()})
    return JsonResponse({"ok": True, "choice": choice})


@login_required
def results(request, code):
    """For the teacher: who has finished the lesson opened in class, and their quiz scores since it was opened."""
    from courses.models import LessonCompletion, QuizResult

    room = _room_for_code(code)
    if _role(request.user, room) != "host":
        return _json_error("Only the teacher can see this.", 403)
    session = room.current_session
    launch = session.launches.select_related("lesson").first() if session else None
    if launch is None:
        return JsonResponse({"ok": True, "rows": []})
    members = list(room.classroom.memberships.select_related("learner"))
    ids = [m.learner_id for m in members]
    done = set(LessonCompletion.objects.filter(lesson=launch.lesson, enrollment__learner_id__in=ids).values_list("enrollment__learner_id", flat=True))
    scores = dict(
        QuizResult.objects.filter(lesson=launch.lesson, learner_id__in=ids, updated_at__gte=launch.created_at)
        .values_list("learner_id", "score_percent")
    )
    here = set(session.attendance.filter(is_host=False, removed=False).values_list("user_id", flat=True))
    rows = [
        {"name": display_name(m.learner), "here": m.learner_id in here, "done": m.learner_id in done, "score": scores.get(m.learner_id)}
        for m in members
    ]
    rows.sort(key=lambda r: (not r["here"], not r["done"], r["name"]))
    return JsonResponse({"ok": True, "title": launch.lesson.display_title, "rows": rows})


def _apply_learner_permissions(room, session):
    """Push the current rules to every learner in every room of the class (in parallel, so a full class updates quickly)."""
    host = identity(room.classroom.facilitator)
    targets = []
    for name in session.room_names():
        try:
            targets += [(name, p["identity"]) for p in livekit.list_participants(name) if p.get("identity") and p["identity"] != host]
        except livekit.LiveKitError:
            continue
    attendance = {
        identity(a.user): a
        for a in session.attendance.select_related("user").filter(user_id__in=[user_id_from(t) for _, t in targets])
    }

    def push(target):
        name, who = target
        att = attendance.get(who)
        if att is None:
            return
        permission = learner_permission(room, att, session)
        attributes = None if permission["can_publish"] else {"hand": ""}
        try:
            livekit.update_participant(name, who, permission=permission, attributes=attributes)
        except livekit.LiveKitError:
            pass  # they may have just left; the next change or their next token will catch up

    _run_all(push, targets)


def _end_groups(session):
    """Everyone back to the main room. Returns True when the teacher was visiting a group (so they move too)."""
    if not session.groups:
        return False
    group_rooms = session.room_names()[1:]
    host_away = session.attendance.filter(is_host=True, group__gt=0).exists()
    session.groups = 0
    session.save(update_fields=["groups"])
    session.attendance.update(group=0)
    broadcast(session, {"type": "move"}, rooms=group_rooms)
    return host_away


@login_required
@require_POST
def control(request, code):
    """The teacher's buttons: speaking rights, room settings, polls, lessons, groups, recording and ending the class."""
    room = _room_for_code(code)
    if _role(request.user, room) != "host":
        return _json_error("Only the teacher can do that.", 403)
    session = room.current_session
    if session is None:
        return _json_error("This class is not live right now.", 409)
    action = request.POST.get("action", "")
    target = request.POST.get("identity", "")
    host_att = session.attendance.filter(is_host=True).first()
    extra = {}

    try:
        if action in ("allow_speak", "stop_speak", "lower_hand", "remove", "mute_mic"):
            user_id = user_id_from(target)
            att = session.attendance.filter(user_id=user_id, is_host=False).first() if user_id else None
            if att is None:
                return _json_error("That learner is not in this class.", 404)
            name = room_for(session, att)
            if action == "lower_hand":
                livekit.update_participant(name, target, attributes={"hand": ""})
            elif action == "mute_mic":  # open mic or a group: switch their microphone off (they may switch it on again)
                if not request.POST.get("track"):
                    return _json_error("That learner's microphone is already off.")
                livekit.mute_track(name, target, request.POST["track"])
            elif action == "remove":
                att.removed = True
                att.can_speak = False
                att.save(update_fields=["removed", "can_speak"])
                livekit.remove_participant(name, target)
            else:
                att.can_speak = action == "allow_speak"
                att.save(update_fields=["can_speak"])
                livekit.update_participant(name, target, permission=learner_permission(room, att, session), attributes={"hand": ""})

        elif action in ("admit", "deny", "admit_all"):
            waiting = session.attendance.filter(admitted=False, removed=False, is_host=False)
            if action != "admit_all":
                waiting = waiting.filter(user_id=user_id_from(target) or 0)
            waiting.update(**({"removed": True} if action == "deny" else {"admitted": True}))

        elif action == "mute_all":
            session.attendance.filter(is_host=False).update(can_speak=False)
            if room.open_mic:
                room.open_mic = False
                room.save(update_fields=["open_mic"])
                push_settings(room, session)
            _apply_learner_permissions(room, session)

        elif action == "lower_all_hands":
            for name in session.room_names():
                for p in livekit.list_participants(name):
                    if (p.get("attributes") or {}).get("hand"):
                        livekit.update_participant(name, p["identity"], attributes={"hand": ""})

        elif action == "set" and request.POST.get("setting") in TOGGLES:
            setting = request.POST["setting"]
            setattr(room, TOGGLES[setting], request.POST.get("value") == "1")
            room.save(update_fields=[TOGGLES[setting]])
            push_settings(room, session)
            if setting in PERMISSION_SETTINGS:
                _apply_learner_permissions(room, session)

        elif action == "chat_delete":
            msg = session.chat.filter(pk=request.POST.get("id") or 0).first()
            if msg:
                msg.hidden = True
                msg.save(update_fields=["hidden"])
                broadcast(session, {"type": "chat_delete", "id": msg.pk})

        elif action == "announce":
            text = " ".join(request.POST.get("text", "").split())[:300]
            if not text:
                return _json_error("Type a message first.")
            msg = LiveChatMessage.objects.create(session=session, user=request.user, text=text, announce=True)
            broadcast(session, {"type": "chat", "msg": _chat_item(msg)})

        elif action == "poll_start":
            question = request.POST.get("question", "").strip()[:200]
            options = [o.strip()[:80] for o in request.POST.getlist("options") if o.strip()][:4]
            if not question or len(options) < 2:
                return _json_error("Write a question and at least two answers.")
            session.polls.filter(closed_at__isnull=True).update(closed_at=timezone.now())
            poll = LivePoll.objects.create(session=session, question=question, options=options)
            broadcast(session, {"type": "poll", "poll": poll.as_dict()})
            extra["poll"] = poll.as_dict()

        elif action == "poll_close":
            poll = session.polls.filter(closed_at__isnull=True).first()
            if poll:
                poll.closed_at = timezone.now()
                poll.save(update_fields=["closed_at"])
                broadcast(session, {"type": "poll", "poll": poll.as_dict()})
                extra["poll"] = poll.as_dict()

        elif action == "launch":
            from courses.models import Lesson

            lesson = Lesson.objects.filter(pk=request.POST.get("lesson") or 0).select_related("course").first()
            allowed = {l["id"] for c in _lesson_choices(room.classroom) for l in c["lessons"]}
            if lesson is None or lesson.pk not in allowed:
                return _json_error("Pick a lesson from the class programme.")
            session.launches.filter(closed_at__isnull=True).update(closed_at=timezone.now())
            launch = LiveLaunch.objects.create(session=session, lesson=lesson)
            broadcast(session, {"type": "launch", "launch": _launch_item(launch)})
            extra["launch"] = _launch_item(launch)

        elif action == "launch_close":
            session.launches.filter(closed_at__isnull=True).update(closed_at=timezone.now())
            broadcast(session, {"type": "launch", "launch": None})

        elif action == "groups_start":
            if session.groups:
                return _json_error("Bring everyone back before making new groups.")
            try:
                count = max(2, min(MAX_GROUPS, int(request.POST.get("count", "2"))))
            except ValueError:
                count = 2
            host = identity(room.classroom.facilitator)
            present = [p["identity"] for p in livekit.list_participants(session.livekit_name) if p.get("identity") not in (None, host)]
            ids = [user_id_from(i) for i in present]
            learners = list(session.attendance.filter(user_id__in=ids, is_host=False, removed=False))
            if len(learners) < 2:
                return _json_error("You need at least two learners in the class to make groups.")
            count = min(count, len(learners))
            random.shuffle(learners)
            session.groups = count
            session.save(update_fields=["groups"])
            for i, att in enumerate(learners):
                att.group = i % count + 1
                att.save(update_fields=["group"])
            _run_all(lambda g: livekit.create_room(session.room_name(g), room.settings_json(), settings.LIVE_MAX_PARTICIPANTS, empty_timeout=120),
                     range(1, count + 1))
            livekit.send_data(session.livekit_name, {"type": "move"}, to=[identity(a.user) for a in learners])
            extra["groups"] = _groups_info(session)

        elif action == "groups_visit":
            try:
                group = int(request.POST.get("group", "0"))
            except ValueError:
                group = 0
            if not 0 <= group <= session.groups or host_att is None:
                return _json_error("That group has finished.")
            host_att.group = group
            host_att.save(update_fields=["group"])
            extra["move"] = True

        elif action == "groups_end":
            extra["move"] = _end_groups(session)
            extra["groups"] = None

        elif action == "record_start":
            if not livekit.recording_configured():
                return _json_error("Recording is not set up. Ask the site administrator.")
            if session.recordings.filter(status=LiveRecording.Status.RECORDING).exists():
                return _json_error("Already recording.")
            stamp = timezone.localtime().strftime("%Y%m%d-%H%M")
            path = f"live/class-{room.classroom.pk}/{stamp}-session-{session.pk}.mp4"
            egress = livekit.start_recording(
                room_for(session, host_att) if host_att else session.livekit_name,
                request.POST.get("audio", ""), request.POST.get("video", ""), path,
            )
            LiveRecording.objects.create(session=session, egress_id=egress, filepath=path)
            room.recording = True
            room.save(update_fields=["recording"])
            push_settings(room, session)

        elif action == "record_stop":
            for rec in session.recordings.filter(status=LiveRecording.Status.RECORDING):
                try:
                    livekit.stop_recording(rec.egress_id)
                except livekit.LiveKitError:
                    pass  # LiveKit reports the final state through the webhook
            room.recording = False
            room.save(update_fields=["recording"])
            push_settings(room, session)

        elif action == "end":
            names = session.room_names()
            for rec in session.recordings.filter(status=LiveRecording.Status.RECORDING):
                try:
                    livekit.stop_recording(rec.egress_id)
                except livekit.LiveKitError:
                    pass
            room.recording = False
            room.save(update_fields=["recording"])
            session.ended_at = timezone.now()
            session.groups = 0
            session.save(update_fields=["ended_at", "groups"])
            for name in names:
                try:
                    livekit.delete_room(name)  # disconnects everyone
                except livekit.LiveKitError:
                    pass  # the class is ended on our side either way
            services.finish_session(session)
        else:
            return _json_error("Unknown action.")
    except livekit.LiveKitError as exc:
        return _json_error(str(exc), 502)
    return JsonResponse({"ok": True, "settings": json.loads(room.settings_json()), **extra})


@login_required
def report(request, session_id):
    """The teacher's record of one live class: who came, for how long, the chat (with blocked messages), polls and lessons."""
    session = get_object_or_404(LiveSession.objects.select_related("room__classroom__facilitator"), pk=session_id)
    classroom = session.room.classroom
    if not (request.user.pk == classroom.facilitator_id or request.user.is_staff):
        raise Http404
    attendance = {a.user_id: a for a in session.attendance.select_related("user")}
    roster = []
    for m in classroom.memberships.select_related("learner"):
        att = attendance.get(m.learner_id)
        status = "missed" if att is None else ("removed" if att.removed else "came")
        roster.append({"user": m.learner, "att": att, "status": status, "minutes": round(att.seconds / 60) if att else 0})
    roster.sort(key=lambda r: ({"came": 0, "removed": 1, "missed": 2}[r["status"]], r["user"].first_name or r["user"].username))
    came = sum(1 for r in roster if r["status"] == "came")
    ctx = {
        "s": session, "classroom": classroom, "roster": roster, "came": came, "missed": len(roster) - came,
        "chat": session.chat.select_related("user"), "polls": session.polls.prefetch_related("votes"),
        "launches": session.launches.select_related("lesson"), "recordings": session.recordings.filter(status=LiveRecording.Status.READY),
        "nav": "classes", "classes": list(request.user.classrooms.filter(archived=False)) if request.user.role == User.Role.FACILITATOR else [],
    }
    return render(request, "live/report.html", ctx)


@login_required
def recording(request, recording_id):
    """Plays a recording for the class teacher or a learner in the class, through a private link that lasts an hour."""
    rec = get_object_or_404(LiveRecording.objects.select_related("session__room__classroom"), pk=recording_id, status=LiveRecording.Status.READY)
    room = rec.session.room
    if _role(request.user, room) is None and not request.user.is_staff:
        raise Http404
    if not livekit.recording_configured():
        raise Http404
    return redirect(livekit.recording_url(rec.filepath))


def _get(data, *names):
    for name in names:
        if name in data:
            return data[name]
    return None


@csrf_exempt
@require_POST
def webhook(request):
    """LiveKit tells us when people join and leave, when a room closes and when a recording finishes."""
    if not livekit.configured():
        return HttpResponse(status=404)
    event = livekit.verify_webhook(request.body, request.headers.get("Authorization"))
    if event is None:
        return HttpResponse(status=401)
    kind = event.get("event")
    now = timezone.now()

    if kind in ("egress_ended", "egress_updated"):
        info = _get(event, "egressInfo", "egress_info") or {}
        rec = LiveRecording.objects.filter(egress_id=_get(info, "egressId", "egress_id") or "").select_related("session__room").first()
        status = str(_get(info, "status") or "")
        if rec and rec.status == LiveRecording.Status.RECORDING and status in ("EGRESS_COMPLETE", "EGRESS_FAILED", "EGRESS_ABORTED", "EGRESS_LIMIT_REACHED", "3", "4", "5", "6"):
            files = _get(info, "fileResults", "file_results") or [_get(info, "file") or {}]
            file = files[0] if files else {}
            rec.status = LiveRecording.Status.READY if status in ("EGRESS_COMPLETE", "3", "EGRESS_LIMIT_REACHED", "6") and file else LiveRecording.Status.FAILED
            rec.ended_at = now
            rec.duration_seconds = int(int(_get(file, "duration") or 0) / 1_000_000_000)  # nanoseconds
            rec.size_bytes = int(_get(file, "size") or 0)
            rec.filepath = _get(file, "filename") or rec.filepath
            rec.error = str(_get(info, "error") or "")[:300]
            rec.save()
            room = rec.session.room
            if room.recording and not LiveRecording.objects.filter(session__room=room, status=LiveRecording.Status.RECORDING).exists():
                room.recording = False
                room.save(update_fields=["recording"])
                if rec.session.ended_at is None:
                    push_settings(room, rec.session)
        return HttpResponse(status=200)

    match = ROOM_NAME.match((event.get("room") or {}).get("name", ""))
    session = LiveSession.objects.filter(pk=int(match.group(1))).select_related("room__classroom").first() if match else None
    if session is None:
        return HttpResponse(status=200)
    group = int(match.group(2) or 0)

    if kind == "room_finished" and group == 0:
        if session.ended_at is None:
            session.ended_at = now
            session.save(update_fields=["ended_at"])
        services.finish_session(session)
    elif kind in ("participant_joined", "participant_left"):
        user_id = user_id_from((event.get("participant") or {}).get("identity", ""))
        att = session.attendance.filter(user_id=user_id).first() if user_id else None
        # Moving to or from a breakout group is a leave in one room and a join in another, in either order. Time keeps
        # counting across the move: a join banks the time so far, and a leave only counts in the room they belong in now.
        if att is not None:
            if kind == "participant_joined":
                if att.left_at is None:
                    att.seconds += max(0, int((now - att.last_joined_at).total_seconds()))
                att.last_joined_at = now
                att.left_at = None
            elif att.left_at is None and event["room"]["name"] == room_for(session, att):
                att.seconds += max(0, int((now - att.last_joined_at).total_seconds()))
                att.left_at = now
            att.save(update_fields=["last_joined_at", "left_at", "seconds"])
    return HttpResponse(status=200)
