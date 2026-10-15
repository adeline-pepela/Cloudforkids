"""Live class tools for facilitators. They call the live room's own endpoints (start, and the teacher's control
buttons) as the teacher, so the same host check, filters and LiveKit calls apply as when the teacher clicks."""

import json

from django.http import QueryDict
from django.urls import reverse

from . import Result, ToolError, short, tool
from .teach_tools import _abs, _class, _class_name

AREA = "teach"


def _room(ctx, class_id, meeting_id=None, live_only=False):
    from live.models import LiveRoom

    classroom = _class(ctx, class_id)
    rooms = classroom.live_rooms.all()
    if meeting_id:
        room = rooms.filter(pk=meeting_id).first()
        if room is None:
            raise ToolError("That meeting isn't in this class. Use list_meetings.")
    else:
        room = next((r for r in rooms if r.current_session), None)
        if room is None and not live_only:
            room, _ = LiveRoom.objects.get_or_create(classroom=classroom, is_main=True)
    if room is None or (live_only and room.current_session is None):
        raise ToolError(f"{classroom.name} is not live right now. Start the live class first.")
    return classroom, room


def _post(ctx, view, code, data):
    """Call a live view as the teacher, with form data, and read its JSON answer."""
    request = ctx.request
    request.method = "POST"
    post = QueryDict(mutable=True)
    for key, value in data.items():
        if isinstance(value, (list, tuple)):
            post.setlist(key, [str(v) for v in value])
        else:
            post[key] = str(value)
    request.POST = post
    request._dont_enforce_csrf_checks = True
    response = view(request, code)
    try:
        body = json.loads(response.content or b"{}")
    except ValueError:
        body = {}
    if response.status_code >= 400 or body.get("ok") is False:
        raise ToolError(body.get("error") or f"The live room refused ({response.status_code}).")
    return body


@tool(AREA, "live_status",
      "Whether a class (or any of its meetings) is live right now: who is in the room, how long it has run, any open poll.",
      {"class_id": {"type": "integer"}}, ["class_id"])
def live_status(ctx, args):
    from django.utils import timezone

    classroom = _class(ctx, args.get("class_id"))
    rows = []
    for room in classroom.live_rooms.order_by("-is_main", "-created_at"):
        session = room.current_session
        item = {"meeting_id": room.pk, "title": room.title or ("Class link" if room.is_main else "Meeting"), "live": bool(session),
                "link": _abs(ctx, reverse("live_short", args=[room.code]))}
        if session:
            here = session.attendance.filter(left_at__isnull=True, is_host=False, removed=False)
            item.update(minutes_running=int((timezone.now() - session.started_at).total_seconds() // 60),
                        learners_in_room=here.count(), waiting_room=session.attendance.filter(admitted=False, removed=False).count(),
                        open_poll=(lambda p: p.as_dict() if p else None)(session.polls.filter(closed_at__isnull=True).first()))
        rows.append(item)
    return Result({"class": classroom.name, "rooms": rows})


@tool(AREA, "start_live_class",
      "Start a class's live room (or one of its meetings) so learners can join from its link. You still open the link "
      "yourself to teach.",
      {"class_id": {"type": "integer"}, "meeting_id": {"type": "integer", "description": "Leave out for the class's permanent link"}},
      ["class_id"], writes=True,
      describe=lambda ctx, a: f"Start the live class for {_class_name(ctx, a)} so learners can join")
def start_live_class(ctx, args):
    from live import views as live_views

    from live import livekit

    classroom, room = _room(ctx, args.get("class_id"), args.get("meeting_id"))
    if room.current_session is None and not livekit.configured():
        raise ToolError("Live classes aren't set up on this site yet (the LiveKit keys are missing). An admin can add them.")
    if room.current_session is None:
        ctx.request.method = "POST"
        live_views.start_room(ctx.request, room.code)
        room.refresh_from_db()
        if room.current_session is None:
            notes = " ".join(ctx.notes())
            raise ToolError(notes or "The live class could not be started. Live classes may not be set up on this site yet.")
    link = _abs(ctx, reverse("live_short", args=[room.code]))
    return Result({"message": f"{classroom.name} is live. Open {link} to teach; learners join from the same link.", "link": link},
                  link=reverse("live:room", args=[room.code]))


@tool(AREA, "live_poll", "Ask the class a quick poll while it is live (2 to 4 answers). Any open poll closes first.",
      {"class_id": {"type": "integer"}, "question": {"type": "string"}, "options": {"type": "array", "items": {"type": "string"}}},
      ["class_id", "question", "options"], writes=True,
      describe=lambda ctx, a: f"Ask {_class_name(ctx, a)} the poll \"{short(a.get('question'), 70)}\" ({', '.join(short(o, 20) for o in (a.get('options') or [])[:4])})")
def live_poll(ctx, args):
    from live import views as live_views

    _classroom, room = _room(ctx, args.get("class_id"), live_only=True)
    _post(ctx, live_views.control, room.code, {"action": "poll_start", "question": args.get("question", ""), "options": list(args.get("options") or [])})
    return Result({"message": "Poll sent to the class."})


@tool(AREA, "live_close_poll", "Close the open poll in a live class and get its results.",
      {"class_id": {"type": "integer"}}, ["class_id"], writes=True,
      describe=lambda ctx, a: f"Close the poll in {_class_name(ctx, a)}")
def live_close_poll(ctx, args):
    from live import views as live_views

    _classroom, room = _room(ctx, args.get("class_id"), live_only=True)
    body = _post(ctx, live_views.control, room.code, {"action": "poll_close"})
    return Result({"message": "Poll closed.", "poll": body.get("poll")})


@tool(AREA, "live_announce", "Post a teacher announcement in the chat of a live class (every breakout group sees it).",
      {"class_id": {"type": "integer"}, "text": {"type": "string"}}, ["class_id", "text"], writes=True, always_confirm=True,
      describe=lambda ctx, a: f"Announce in the {_class_name(ctx, a)} live chat: \"{short(a.get('text'), 90)}\"")
def live_announce(ctx, args):
    from live import views as live_views

    _classroom, room = _room(ctx, args.get("class_id"), live_only=True)
    _post(ctx, live_views.control, room.code, {"action": "announce", "text": args.get("text", "")})
    return Result({"message": "Announced."})


@tool(AREA, "end_live_class", "End a live class for everyone in it.",
      {"class_id": {"type": "integer"}}, ["class_id"], writes=True, always_confirm=True,
      describe=lambda ctx, a: f"End the live class for everyone in {_class_name(ctx, a)}")
def end_live_class(ctx, args):
    from live import views as live_views

    _classroom, room = _room(ctx, args.get("class_id"), live_only=True)
    _post(ctx, live_views.control, room.code, {"action": "end"})
    return Result({"message": "The live class has ended."})
