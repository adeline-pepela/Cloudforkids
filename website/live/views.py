"""Live classes: the teacher starts the room, learners in the class join from the short link.

Safety rules: only the class teacher and learners who joined the class (with its join code) get in. Learners arrive with
their microphone and camera off and can only talk when the teacher allows it (or turns on open mic). Every permission
is decided here and signed into the LiveKit token, so a learner cannot give themselves more rights from the browser.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.models import ClassMembership, Classroom, User

from . import livekit
from .models import LiveAttendance, LiveRoom, LiveSession

logger = logging.getLogger(__name__)

TOGGLES = {"chat": "chat_enabled", "open_mic": "open_mic", "video": "student_video", "locked": "locked"}


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
        return f"{user.first_name} {user.last_name[:1]}.".strip(" .") if user.last_name else user.first_name
    return user.username


def learner_permission(room, attendance):
    """What a learner may do right now, in LiveKit's server API format."""
    sources = ["MICROPHONE"] + (["CAMERA"] if room.student_video else [])
    return {
        "can_subscribe": True,
        "can_publish": room.open_mic or attendance.can_speak,
        "can_publish_data": room.chat_enabled,
        "can_publish_sources": sources,
        "can_update_metadata": False,
    }


def _room_for(code):
    return get_object_or_404(LiveRoom.objects.select_related("classroom__facilitator"), code=code.strip().upper())


def _role(user, room):
    """'host', 'learner' or None (not allowed in)."""
    classroom = room.classroom
    if user.pk == classroom.facilitator_id and user.role == User.Role.FACILITATOR and not user.awaiting_approval:
        return "host"
    if user.role == User.Role.LEARNER and ClassMembership.objects.filter(classroom=classroom, learner=user).exists():
        return "learner"
    return None


def _gate(request, room, reason, status=200, **extra):
    base = "teach/base.html" if request.user.role == User.Role.FACILITATOR else "learner/base.html"
    ctx = {"room": room, "reason": reason, "base_tpl": base, "nav": "classes", **extra}
    if request.user.role == User.Role.FACILITATOR:
        ctx["classes"] = list(request.user.classrooms.filter(archived=False))
        ctx["nav"] = room.classroom.pk if room else None
    return render(request, "live/gate.html", ctx, status=status)


def _json_error(message, status=400):
    return JsonResponse({"ok": False, "error": message}, status=status)


def live_summary(classroom):
    """For the teacher's class page: the room (made on first visit, so the link can be shared early) and recent classes."""
    room, _ = LiveRoom.objects.get_or_create(classroom=classroom)
    return {
        "room": room,
        "current": room.current_session,
        "recent": list(room.sessions.filter(ended_at__isnull=False).prefetch_related("attendance")[:5]),
    }


def short_link(request, code):
    return redirect("live:room", code=code.strip().upper())


@login_required
@require_POST
def start(request, class_id):
    classroom = get_object_or_404(Classroom, pk=class_id, facilitator=request.user)
    room, _ = LiveRoom.objects.get_or_create(classroom=classroom)
    if _role(request.user, room) != "host":
        raise Http404
    if not livekit.configured():
        return _gate(request, room, "not_set_up")
    if room.current_session is None:
        # A fresh start: nobody can talk yet and the room is open, but the teacher's chat and video choices stay.
        room.open_mic = room.locked = False
        room.save(update_fields=["open_mic", "locked"])
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
    room = _room_for(code)
    role = _role(request.user, room)
    if role is None:
        return _gate(request, room, "not_member", status=403)
    if not livekit.configured():
        return _gate(request, room, "not_set_up")
    session = room.current_session
    if session is None:
        return _gate(request, room, "host_start" if role == "host" else "waiting")
    if role == "learner":
        attendance = LiveAttendance.objects.filter(session=session, user=request.user).first()
        if attendance and attendance.removed:
            return _gate(request, room, "removed", status=403)
        if room.locked and attendance is None:
            return _gate(request, room, "locked", status=403)
    config = {
        "role": role,
        "me": identity(request.user),
        "host": identity(room.classroom.facilitator),
        "startedAt": session.started_at.isoformat(),
        "tokenUrl": reverse("live:token", args=[room.code]),
        "statusUrl": reverse("live:status", args=[room.code]),
        "controlUrl": reverse("live:control", args=[room.code]),
        "handUrl": reverse("live:hand", args=[room.code]),
        "shareUrl": request.build_absolute_uri(reverse("live_short", args=[room.code])),
        "exitUrl": reverse("teach:class", args=[room.classroom.pk]) if role == "host" else reverse("dashboard:classes"),
    }
    return render(request, "live/room.html", {"room": room, "session": session, "role": role, "config": config})


@login_required
@require_POST
def token(request, code):
    room = _room_for(code)
    role = _role(request.user, room)
    if role is None:
        return _json_error("You are not in this class.", 403)
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
        attendance = LiveAttendance.objects.create(session=session, user=request.user, is_host=role == "host")

    if role == "host":
        grant = {"room": session.livekit_name, "roomAdmin": True, "canPublish": True, "canSubscribe": True,
                 "canPublishData": True, "canUpdateOwnMetadata": False}
    else:
        permission = learner_permission(room, attendance)
        grant = {
            "room": session.livekit_name, "canSubscribe": True, "canPublish": permission["can_publish"],
            "canPublishData": permission["can_publish_data"], "canUpdateOwnMetadata": False,
            "canPublishSources": [s.lower() for s in permission["can_publish_sources"]],
        }
    jwt = livekit.join_token(
        identity(request.user), display_name(request.user, host=role == "host"), grant, metadata=json.dumps({"role": role}),
    )
    return JsonResponse({"ok": True, "url": settings.LIVEKIT_URL, "token": jwt, "settings": json.loads(room.settings_json())})


@login_required
def status(request, code):
    room = _room_for(code)
    if _role(request.user, room) is None:
        return _json_error("You are not in this class.", 403)
    session = room.current_session
    return JsonResponse({"ok": True, "live": session is not None, "settings": json.loads(room.settings_json())})


@login_required
@require_POST
def hand(request, code):
    """A learner raises or lowers their hand. Done on the server so learners never need rights to change their own details."""
    room = _room_for(code)
    if _role(request.user, room) != "learner":
        return _json_error("Only learners raise hands.", 403)
    session = room.current_session
    if session is None:
        return _json_error("This class is not live right now.", 409)
    up = request.POST.get("up") == "1"
    value = str(int(timezone.now().timestamp() * 1000)) if up else ""
    try:
        livekit.update_participant(session.livekit_name, identity(request.user), attributes={"hand": value})
    except livekit.LiveKitError as exc:
        return _json_error(str(exc), 502)
    return JsonResponse({"ok": True, "up": up})


def _apply_learner_permissions(room, session, only=None):
    """Push the current rules to learners in the room (in parallel, so a full class still updates quickly)."""
    participants = livekit.list_participants(session.livekit_name)
    host = identity(room.classroom.facilitator)
    targets = [p["identity"] for p in participants if p.get("identity") and p["identity"] != host]
    if only is not None:
        targets = [t for t in targets if t in only]
    attendance = {
        identity(a.user): a for a in session.attendance.select_related("user").filter(user_id__in=[user_id_from(t) for t in targets])
    }

    def push(target):
        att = attendance.get(target)
        if att is None:
            return
        attributes = None if (room.open_mic or att.can_speak) else {"hand": ""}
        try:
            livekit.update_participant(session.livekit_name, target, permission=learner_permission(room, att), attributes=attributes)
        except livekit.LiveKitError:
            pass  # they may have just left; the next change or their next token will catch up

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(push, targets))


@login_required
@require_POST
def control(request, code):
    """The teacher's buttons: let a learner speak, mute everyone, remove someone, change room settings, end the class."""
    room = _room_for(code)
    if _role(request.user, room) != "host":
        return _json_error("Only the teacher can do that.", 403)
    session = room.current_session
    if session is None:
        return _json_error("This class is not live right now.", 409)
    action = request.POST.get("action", "")
    target = request.POST.get("identity", "")
    name = session.livekit_name

    try:
        if action in ("allow_speak", "stop_speak", "lower_hand", "remove", "mute_mic"):
            user_id = user_id_from(target)
            att = session.attendance.filter(user_id=user_id, is_host=False).first() if user_id else None
            if att is None:
                return _json_error("That learner is not in this class.", 404)
            if action == "lower_hand":
                livekit.update_participant(name, target, attributes={"hand": ""})
            elif action == "mute_mic":  # open mic: switch their microphone off (they may switch it on again)
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
                livekit.update_participant(name, target, permission=learner_permission(room, att), attributes={"hand": ""})
        elif action == "mute_all":
            session.attendance.filter(is_host=False).update(can_speak=False)
            if room.open_mic:
                room.open_mic = False
                room.save(update_fields=["open_mic"])
                livekit.update_room_metadata(name, room.settings_json())
            _apply_learner_permissions(room, session)
        elif action == "lower_all_hands":
            for p in livekit.list_participants(name):
                if (p.get("attributes") or {}).get("hand"):
                    livekit.update_participant(name, p["identity"], attributes={"hand": ""})
        elif action == "set" and request.POST.get("setting") in TOGGLES:
            setting = request.POST["setting"]
            setattr(room, TOGGLES[setting], request.POST.get("value") == "1")
            room.save(update_fields=[TOGGLES[setting]])
            livekit.update_room_metadata(name, room.settings_json())
            if setting != "locked":
                _apply_learner_permissions(room, session)
        elif action == "end":
            session.ended_at = timezone.now()
            session.save(update_fields=["ended_at"])
            try:
                livekit.delete_room(name)  # disconnects everyone
            except livekit.LiveKitError:
                pass  # the class is ended on our side either way
        else:
            return _json_error("Unknown action.")
    except livekit.LiveKitError as exc:
        return _json_error(str(exc), 502)
    return JsonResponse({"ok": True, "settings": json.loads(room.settings_json())})


@csrf_exempt
@require_POST
def webhook(request):
    """LiveKit tells us when people join and leave and when a room closes. Used for attendance and minutes used."""
    if not livekit.configured():
        return HttpResponse(status=404)
    event = livekit.verify_webhook(request.body, request.headers.get("Authorization"))
    if event is None:
        return HttpResponse(status=401)
    kind = event.get("event")
    room_name = (event.get("room") or {}).get("name", "")
    try:
        session_id = int(room_name.rsplit("-", 1)[1]) if room_name.startswith("c4k-") else None
    except (IndexError, ValueError):
        session_id = None
    session = LiveSession.objects.filter(pk=session_id).first() if session_id else None
    if session is None:
        return HttpResponse(status=200)

    now = timezone.now()
    if kind == "room_finished" and session.ended_at is None:
        session.ended_at = now
        session.save(update_fields=["ended_at"])
    elif kind in ("participant_joined", "participant_left"):
        user_id = user_id_from((event.get("participant") or {}).get("identity", ""))
        att = session.attendance.filter(user_id=user_id).first() if user_id else None
        if att is not None:
            if kind == "participant_joined":
                att.last_joined_at = now
                att.left_at = None
            elif att.left_at is None:
                att.seconds += max(0, int((now - att.last_joined_at).total_seconds()))
                att.left_at = now
            att.save(update_fields=["last_joined_at", "left_at", "seconds"])
    return HttpResponse(status=200)
