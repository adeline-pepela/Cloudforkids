"""Facilitator portal tools. They use the portal's own forms (ClassroomForm, SessionForm, AssignmentForm, MeetingForm,
ComposeForm), its reports and its email helpers, and every lookup is limited to the facilitator's own classes,
exactly as the /teach/ pages are."""

from datetime import timedelta

from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from accounts.models import Assignment, ClassMembership, Classroom, ClassPost, ClassSession, Message, User
from core import notify

from . import ToolError, Result, changed_since, form_data, form_errors, fresh_snapshot, iso, json_arg, restore, short, snapshot, tool

AREA = "teach"


def _teacher(ctx):
    user = ctx.user
    if not user.is_active or user.role != User.Role.FACILITATOR:
        raise ToolError("Only facilitators can use the portal assistant.")
    if user.awaiting_approval:
        raise ToolError("Your facilitator account is still waiting for an admin's approval, so classes are not open yet.")
    return user


def _class(ctx, class_id):
    user = _teacher(ctx)
    classroom = Classroom.objects.filter(pk=_int(class_id, "class_id"), facilitator=user).select_related("tier").first()
    if classroom is None:
        raise ToolError(f"None of your classes has id {class_id}. Use list_my_classes.")
    return classroom


def _int(value, name):
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ToolError(f"{name} must be a number id.")


def _abs(ctx, path):
    try:
        return ctx.request.build_absolute_uri(path)
    except Exception:
        return notify.absolute(path)


def _class_name(ctx, args):
    try:
        return _class(ctx, args.get("class_id")).name
    except ToolError:
        return f"class {args.get('class_id')}"


# ---------------------------------------------------------------- reading

@tool(AREA, "my_overview",
      "The facilitator's home page in numbers: each class with learner count and average progress, learners who need "
      "attention (inactive, stuck, not started), open assignments.")
def my_overview(ctx, args):
    from dashboard.teach import teacher_overview

    data = teacher_overview(_teacher(ctx))
    return Result({
        "learners": data["learners"], "active_this_week": data["active_week"], "open_assignments": data["assignments_open"],
        "classes": [{"class_id": r["classroom"].pk, "name": r["classroom"].name, "learners": r["count"],
                     "average_progress": r["avg_progress"], "average_quiz_score": r["avg_score"]} for r in data["reports"]],
        "needs_attention": [{"class": c.name, "learner_id": row["user"].pk, "name": row["name"], "status": row["status_label"],
                             "last_active": row["last_text"]} for c, row in data["attention"]],
        "needs_attention_total": data["attention_total"],
    })


@tool(AREA, "list_my_classes", "Your classes with id, join code, tier, venue, learner count and whether the discussion board is on.",
      {"include_archived": {"type": "boolean"}})
def list_my_classes(ctx, args):
    user = _teacher(ctx)
    qs = user.classrooms.select_related("tier")
    if not args.get("include_archived"):
        qs = qs.filter(archived=False)
    return Result([{
        "class_id": c.pk, "name": c.name, "join_code": c.join_code, "tier": c.tier.name if c.tier else "All tiers",
        "school": c.school_name, "location": c.location, "learners": c.memberships.count(), "archived": c.archived,
        "discussion_on": c.discussion_enabled, "page": reverse("teach:class", args=[c.pk]),
    } for c in qs])


@tool(AREA, "class_report",
      "One class in full, as its class page shows it: every learner with progress %, lessons done, quiz average, labs, "
      "streak, last active and status; the hardest lessons; assignments with how many finished; suggestions.",
      {"class_id": {"type": "integer"}}, ["class_id"])
def class_report(ctx, args):
    from dashboard.teach import class_report as report, teacher_tips

    classroom = _class(ctx, args.get("class_id"))
    r = report(classroom)
    return Result({
        "class": classroom.name, "class_id": classroom.pk, "join_code": classroom.join_code, "learners": r["count"],
        "average_progress": r["avg_progress"], "average_quiz_score": r["avg_score"], "active_this_week": r["active_week"],
        "lessons_in_tier": r["lessons_total"],
        "roster": [{"learner_id": row["user"].pk, "name": row["name"], "username": row["user"].username, "progress": row["percent"],
                    "lessons_done": row["done"], "quiz_average": row["avg_score"], "labs": row["labs"], "streak_days": row["streak"],
                    "last_active": row["last_text"], "status": row["status_label"]} for row in r["roster"][:80]],
        "hardest_lessons": [{"lesson": h["lesson"].title, "course": h["course"].title, "average": h["avg"], "failed": h["failed"]} for h in r["hard"]],
        "assignments": [{"assignment_id": a["a"].pk, "course": a["a"].course.title, "due": iso(a["a"].due_date), "note": a["a"].note,
                         "finished": a["finished"], "average_progress": a["avg"], "overdue": a["overdue"]} for a in r["assignments"]],
        "suggestions": teacher_tips(r),
    }, link=reverse("teach:class", args=[classroom.pk]))


@tool(AREA, "learner_report",
      "One learner in one of your classes, as their report shows it: progress, courses, strengths, weak lessons, quiz "
      "average, labs, recent activity and tips.",
      {"class_id": {"type": "integer"}, "learner_id": {"type": "integer"}}, ["class_id", "learner_id"])
def learner_report(ctx, args):
    from dashboard.family import child_report

    classroom = _class(ctx, args.get("class_id"))
    member = ClassMembership.objects.filter(classroom=classroom, learner_id=_int(args.get("learner_id"), "learner_id")).select_related("learner").first()
    if member is None:
        raise ToolError(f"No learner with id {args.get('learner_id')} in {classroom.name}.")
    r = child_report(member.learner)
    return Result({
        "name": r["name"], "progress": r["percent"], "stage": r["stage"], "tier": str(r["tier"] or ""),
        "lessons_done": r["lessons_done"], "lessons_total": r["lessons_total"], "quiz_average": r["avg_score"],
        "labs_done": r["labs_done"], "last_active": r["last_active_text"], "finished_this_week": r["this_week"],
        "finished_last_week": r["last_week"], "streak_days": r["stats"].get("streak") if isinstance(r["stats"], dict) else None,
        "courses": [{"course": c["course"].title, "progress": c["percent"], "done": c["done"], "total": c["total"],
                     "quiz_average": c["avg_score"]} for c in r["courses"]],
        "strengths": [q.lesson.title for q in r["strengths"]],
        "weak_lessons": [{"lesson": q.lesson.title, "best_score": q.score_percent} for q in r["weak"]],
        "insights": [text for _tone, _icon, text in r["insights"]],
        "badges": r["badge_total"],
    }, link=reverse("teach:learner", args=[classroom.pk, member.learner_id]))


@tool(AREA, "list_sessions", "The calendar of one class: session id, title, start (Kenyan time), minutes, venue or link, live or not.",
      {"class_id": {"type": "integer"}, "include_past": {"type": "boolean"}}, ["class_id"])
def list_sessions(ctx, args):
    classroom = _class(ctx, args.get("class_id"))
    qs = classroom.sessions.select_related("meeting")
    if not args.get("include_past"):
        qs = qs.filter(starts_at__gte=timezone.now() - timedelta(hours=2))
    return Result([{
        "session_id": s.pk, "title": s.display_title, "starts": iso(s.starts_at), "minutes": s.duration_minutes,
        "where": s.where, "live_on_cloud_for_kids": s.is_live, "link": s.link, "notes": s.notes,
    } for s in qs[:60]])


@tool(AREA, "list_courses", "Courses you can assign (id, title, tier, number of lessons). Optionally only one tier.",
      {"tier": {"type": "string", "description": "Tier name, e.g. Foundational"}})
def list_courses(ctx, args):
    from courses.models import Course

    _teacher(ctx)
    qs = Course.objects.select_related("tier").order_by("tier__order", "order")
    if args.get("tier"):
        qs = qs.filter(tier__name__icontains=args["tier"])
    return Result([{"course_id": c.pk, "title": c.title, "tier": c.tier.name, "tier_id": c.tier_id, "lessons": c.lessons.count()} for c in qs])


@tool(AREA, "list_meetings", "The live links of one class: the permanent class link and meetings made for later, with passcodes.",
      {"class_id": {"type": "integer"}}, ["class_id"])
def list_meetings(ctx, args):
    classroom = _class(ctx, args.get("class_id"))
    return Result([{
        "meeting_id": r.pk, "title": r.title or ("Class link" if r.is_main else "Meeting"), "permanent_class_link": r.is_main,
        "link": _abs(ctx, reverse("live_short", args=[r.code])), "passcode": r.passcode, "waiting_room": r.waiting_room,
        "who_can_join": r.get_audience_display(), "learner_cameras": r.student_video, "chat": r.chat_enabled,
    } for r in classroom.live_rooms.order_by("-is_main", "-created_at")])


@tool(AREA, "class_discussion",
      "Recent posts on a class discussion board with their replies, including posts the filter blocked (only you see those).",
      {"class_id": {"type": "integer"}, "limit": {"type": "integer"}}, ["class_id"])
def class_discussion(ctx, args):
    from dashboard.classroom import discussion, short_name

    classroom = _class(ctx, args.get("class_id"))
    posts = discussion(classroom, teacher_view=True)[: max(1, min(40, int(args.get("limit") or 15)))]
    return Result({"discussion_on": classroom.discussion_enabled, "posts": [{
        "post_id": p.pk, "author": short_name(p.author), "teacher": p.author_id == classroom.facilitator_id, "when": iso(p.created_at),
        "text": short(p.body, 500), "pinned": p.pinned, "blocked_by_filter": p.flagged,
        "replies": [{"post_id": r.pk, "author": short_name(r.author), "text": short(r.body, 300), "blocked_by_filter": r.flagged}
                    for r in p.visible_replies[:10]],
    } for p in posts]})


@tool(AREA, "list_messages", "Your inbox (or sent box): message id, from/to, subject, date, unread, first words.",
      {"box": {"type": "string", "enum": ["in", "sent"]}, "limit": {"type": "integer"}})
def list_messages(ctx, args):
    user = _teacher(ctx)
    limit = max(1, min(40, int(args.get("limit") or 15)))
    if args.get("box") == "sent":
        qs = Message.objects.filter(sender=user).select_related("recipient")
        rows = [{"message_id": m.pk, "to": str(m.recipient), "subject": m.subject, "when": iso(m.created_at), "text": short(m.body, 160)} for m in qs[:limit]]
    else:
        qs = Message.objects.filter(recipient=user).select_related("sender")
        rows = [{"message_id": m.pk, "from": str(m.sender), "from_role": m.sender.get_role_display(), "subject": m.subject,
                 "when": iso(m.created_at), "unread": m.read_at is None, "text": short(m.body, 160)} for m in qs[:limit]]
    return Result(rows)


@tool(AREA, "read_message", "One conversation in full, oldest first. Reading it marks it read, as opening it does.",
      {"message_id": {"type": "integer"}}, ["message_id"])
def read_message(ctx, args):
    from dashboard.messaging_views import _thread

    user = _teacher(ctx)
    msg = Message.objects.filter(pk=_int(args.get("message_id"), "message_id")).select_related("sender", "recipient").first()
    if msg is None or user not in (msg.sender, msg.recipient):
        raise ToolError("That message isn't in your inbox.")
    thread = _thread(msg)
    Message.objects.filter(pk__in=[m.pk for m in thread], recipient=user, read_at__isnull=True).update(read_at=timezone.now())
    return Result([{"message_id": m.pk, "from": str(m.sender), "to": str(m.recipient), "when": iso(m.created_at),
                    "subject": m.subject, "text": m.body} for m in thread], link=reverse("messaging:detail", args=[msg.pk]))


# ---------------------------------------------------------------- classes

def _classroom_form():
    from dashboard.teach_views import ClassroomForm

    return ClassroomForm


CLASS_FIELDS = {
    "name": {"type": "string"}, "description": {"type": "string"}, "tier": {"type": "integer", "description": "Tier id, empty for all tiers"},
    "school_name": {"type": "string"}, "location": {"type": "string"}, "meeting_link": {"type": "string"},
    "discussion_enabled": {"type": "boolean"},
}


def _undo_class_archive(ctx, info):
    classroom = _class(ctx, info["class_id"])
    classroom.archived = info["archived"]
    classroom.save(update_fields=["archived"])
    return f"{classroom.name} {'archived' if classroom.archived else 'restored'}."


@tool(AREA, "create_class", "Create a class, as on New class. Learners join it with the join code it gets.",
      {**CLASS_FIELDS}, ["name"], writes=True,
      describe=lambda ctx, a: f"Create the class \"{a.get('name')}\"" + (f" at {a['school_name']}" if a.get("school_name") else ""),
      undo=_undo_class_archive)
def create_class(ctx, args):
    user = _teacher(ctx)
    form_class = _classroom_form()
    values = {k: v for k, v in args.items() if k in CLASS_FIELDS}
    values.setdefault("discussion_enabled", True)
    form = form_class(data=form_data(form_class, values=values))
    if not form.is_valid():
        raise ToolError(f"Not created. {form_errors(form)}")
    classroom = form.save(commit=False)
    classroom.facilitator = user
    classroom.save()
    return Result({"class_id": classroom.pk, "message": f"{classroom.name} is ready. Share the join code {classroom.join_code} with your learners."},
                  undo={"class_id": classroom.pk, "archived": True}, undo_label="Archive it", link=reverse("teach:class", args=[classroom.pk]))


def _undo_restore(model_label, owner_check):
    def undo(ctx, info):
        from django.apps import apps

        model = apps.get_model(model_label)
        owner_check(ctx, info)
        if changed_since(model, info["id"], info.get("after")):
            raise ToolError("It has been changed again since, so undo would overwrite that.")
        obj = restore(info["before"])
        return f"Put \"{short(obj, 60)}\" back as it was."
    return undo


@tool(AREA, "update_class", "Change some details of a class. Only the fields you pass change.",
      {"class_id": {"type": "integer"}, "values": {"type": "object", "description": "Fields to change: " + ", ".join(CLASS_FIELDS)}},
      ["class_id", "values"], writes=True,
      describe=lambda ctx, a: f"Change {_class_name(ctx, a)}: " + ", ".join(f"{k} to {short(v, 40)}" for k, v in json_arg(a.get("values")).items()),
      undo=_undo_restore("accounts.Classroom", lambda ctx, info: _class(ctx, info["id"])))
def update_class(ctx, args):
    classroom = _class(ctx, args.get("class_id"))
    before = snapshot(classroom)
    form_class = _classroom_form()
    form = form_class(data=form_data(form_class, instance=classroom, values=json_arg(args.get("values"), "values")), instance=classroom)
    if not form.is_valid():
        raise ToolError(f"Not saved. {form_errors(form)}")
    form.save()
    return Result({"changed": form.changed_data, "message": "Class updated."},
                  undo={"id": classroom.pk, "before": before, "after": fresh_snapshot(classroom)}, link=reverse("teach:class", args=[classroom.pk]))


@tool(AREA, "archive_class", "Archive a class (it leaves your list; nothing is deleted) or restore an archived one.",
      {"class_id": {"type": "integer"}, "archived": {"type": "boolean", "description": "true to archive, false to restore"}},
      ["class_id", "archived"], writes=True,
      describe=lambda ctx, a: f"{'Archive' if a.get('archived', True) else 'Restore'} {_class_name(ctx, a)}",
      undo=_undo_class_archive)
def archive_class(ctx, args):
    classroom = _class(ctx, args.get("class_id"))
    was = classroom.archived
    classroom.archived = bool(args.get("archived", True))
    classroom.save(update_fields=["archived"])
    return Result({"message": f"{classroom.name} {'archived' if classroom.archived else 'restored'}."},
                  undo={"class_id": classroom.pk, "archived": was})


def _undo_membership(ctx, info):
    classroom = _class(ctx, info["class_id"])
    learner = User.objects.filter(pk=info["learner_id"], is_active=True).first()
    if learner is None:
        raise ToolError("That learner's account no longer exists.")
    ClassMembership.objects.get_or_create(classroom=classroom, learner=learner)
    return f"{learner.get_full_name() or learner.username} is back in {classroom.name}."


def _learner_name(ctx, args):
    member = ClassMembership.objects.filter(classroom_id=args.get("class_id"), classroom__facilitator=ctx.user,
                                            learner_id=args.get("learner_id")).select_related("learner").first()
    return (member.learner.get_full_name() or member.learner.username) if member else f"learner {args.get('learner_id')}"


@tool(AREA, "remove_learner", "Take a learner out of a class. Their account and progress are not deleted.",
      {"class_id": {"type": "integer"}, "learner_id": {"type": "integer"}}, ["class_id", "learner_id"], writes=True,
      describe=lambda ctx, a: f"Remove {_learner_name(ctx, a)} from {_class_name(ctx, a)}", undo=_undo_membership)
def remove_learner(ctx, args):
    classroom = _class(ctx, args.get("class_id"))
    learner_id = _int(args.get("learner_id"), "learner_id")
    removed, _ = ClassMembership.objects.filter(classroom=classroom, learner_id=learner_id).delete()
    if not removed:
        raise ToolError(f"No learner with id {learner_id} in {classroom.name}.")
    return Result({"message": "Learner removed from the class. Their account and progress are not deleted."},
                  undo={"class_id": classroom.pk, "learner_id": learner_id}, undo_label="Add them back")


# ---------------------------------------------------------------- calendar

def _session_sentence(ctx, a):
    weeks = int(a.get("repeat_weeks") or 1)
    what = f"{weeks} weekly sessions" if weeks > 1 else "a session"
    live = " as a live class, and email the learners and their parents the link" if a.get("is_live") else ""
    title = f" \"{a['title']}\"" if a.get("title") else ""
    return f"Add {what}{title} to {_class_name(ctx, a)} starting {a.get('date')} at {a.get('time')}{live}"


def _undo_sessions(ctx, info):
    classroom = _class(ctx, info["class_id"])
    removed = ClassSession.objects.filter(classroom=classroom, pk__in=info["ids"]).delete()[0]
    return f"Removed {removed} session{'s' if removed != 1 else ''} from the calendar. Any emails already sent stay sent."


@tool(AREA, "add_sessions",
      "Add one session, or a weekly run, to a class calendar (Kenyan time), as the class page's Add to calendar form does. "
      "is_live=true holds it live on Cloud for Kids and emails learners and parents the date and link.",
      {"class_id": {"type": "integer"}, "date": {"type": "string", "description": "YYYY-MM-DD"}, "time": {"type": "string", "description": "HH:MM, 24-hour"},
       "duration_minutes": {"type": "integer"}, "repeat_weeks": {"type": "integer", "description": "1 for a single session"},
       "title": {"type": "string"}, "location": {"type": "string"}, "meeting_link": {"type": "string"}, "notes": {"type": "string"},
       "is_live": {"type": "boolean"}, "live_link": {"type": "string", "enum": ["own", "class"], "description": "Live only: its own new link, or the class's permanent link"},
       "passcode": {"type": "string"}, "waiting_room": {"type": "boolean"}, "audience": {"type": "string", "enum": ["class", "anyone"]},
       "student_video": {"type": "boolean"}, "chat_enabled": {"type": "boolean"}},
      ["class_id", "date", "time"], writes=True, always_confirm=lambda a: bool(a.get("is_live")), describe=_session_sentence,
      undo=_undo_sessions)
def add_sessions(ctx, args):
    from dashboard.teach_views import SessionForm

    classroom = _class(ctx, args.get("class_id"))
    values = {k: v for k, v in args.items() if k != "class_id"}
    values.setdefault("duration_minutes", 60)
    values.setdefault("repeat_weeks", 1)
    values.setdefault("chat_enabled", True)
    values.setdefault("live_link", "own")
    values.setdefault("audience", "class")
    form = SessionForm(data=form_data(SessionForm, values=values))
    if not form.is_valid():
        raise ToolError(f"Not added. {form_errors(form)}")
    with transaction.atomic():
        made = form.save(classroom)
    note = ""
    if form.cleaned_data["is_live"]:
        notify.notify_live_scheduled(classroom, made)
        room = made[0].live_room_obj
        note = f" Its link is {_abs(ctx, reverse('live_short', args=[room.code]))}"
        note += f" (passcode {room.passcode})." if room.passcode else "."
        note += " We emailed the learners and their parents the date and the link."
    count = len(made)
    return Result({"message": f"Added {count} session{'s' if count != 1 else ''} to the {classroom.name} calendar. Learners in the class can see it now.{note}",
                   "session_ids": [s.pk for s in made]},
                  undo={"class_id": classroom.pk, "ids": [s.pk for s in made]}, undo_label="Remove them",
                  link=reverse("teach:class", args=[classroom.pk]))


def _undo_recreate(ctx, info):
    _class(ctx, info["class_id"])
    obj = restore(info["before"])
    return f"Put \"{short(obj, 60)}\" back."


@tool(AREA, "delete_session", "Remove one session from a class calendar.",
      {"class_id": {"type": "integer"}, "session_id": {"type": "integer"}}, ["class_id", "session_id"], writes=True,
      describe=lambda ctx, a: f"Remove session {a.get('session_id')} from the {_class_name(ctx, a)} calendar", undo=_undo_recreate)
def delete_session(ctx, args):
    classroom = _class(ctx, args.get("class_id"))
    session = ClassSession.objects.filter(pk=_int(args.get("session_id"), "session_id"), classroom=classroom).first()
    if session is None:
        raise ToolError("That session isn't on this class's calendar.")
    before = snapshot(session)
    session.delete()
    return Result({"message": "Session removed from the calendar."}, undo={"class_id": classroom.pk, "before": before}, undo_label="Put it back")


# ---------------------------------------------------------------- assignments

def _assign_sentence(ctx, a):
    from courses.models import Course

    course = Course.objects.filter(pk=a.get("course_id")).first()
    due = f", due {a['due_date']}" if a.get("due_date") else ""
    return f"Assign {course.title if course else 'course ' + str(a.get('course_id'))} to {_class_name(ctx, a)}{due}, and email the class and their parents"


def _undo_assignment(ctx, info):
    classroom = _class(ctx, info["class_id"])
    Assignment.objects.filter(pk=info["id"], classroom=classroom).delete()
    return "Assignment removed. The email about it was already sent."


@tool(AREA, "assign_course", "Assign a course to a class with an optional due date and note. Learners and their parents get an email.",
      {"class_id": {"type": "integer"}, "course_id": {"type": "integer"}, "due_date": {"type": "string", "description": "YYYY-MM-DD"},
       "note": {"type": "string"}}, ["class_id", "course_id"], writes=True, always_confirm=True, describe=_assign_sentence,
      undo=_undo_assignment)
def assign_course(ctx, args):
    from dashboard.teach_views import AssignmentForm

    classroom = _class(ctx, args.get("class_id"))
    values = {"course": args.get("course_id"), "due_date": args.get("due_date") or None, "note": args.get("note") or ""}
    form = AssignmentForm(data=form_data(AssignmentForm, values=values))
    if not form.is_valid():
        raise ToolError(f"Not assigned. {form_errors(form)}")
    assignment = form.save(commit=False)
    assignment.classroom = classroom
    assignment.save()
    notify.notify_assignment(assignment)
    return Result({"message": f"Assigned {assignment.course.title} to {classroom.name}.", "assignment_id": assignment.pk},
                  undo={"class_id": classroom.pk, "id": assignment.pk}, undo_label="Remove it")


@tool(AREA, "delete_assignment", "Remove an assignment from a class.",
      {"class_id": {"type": "integer"}, "assignment_id": {"type": "integer"}}, ["class_id", "assignment_id"], writes=True,
      describe=lambda ctx, a: f"Remove assignment {a.get('assignment_id')} from {_class_name(ctx, a)}", undo=_undo_recreate)
def delete_assignment(ctx, args):
    classroom = _class(ctx, args.get("class_id"))
    assignment = Assignment.objects.filter(pk=_int(args.get("assignment_id"), "assignment_id"), classroom=classroom).first()
    if assignment is None:
        raise ToolError("That assignment isn't in this class.")
    before = snapshot(assignment)
    assignment.delete()
    return Result({"message": "Assignment removed."}, undo={"class_id": classroom.pk, "before": before}, undo_label="Put it back")


# ---------------------------------------------------------------- live meetings

MEETING_FIELDS = {"title": {"type": "string"}, "passcode": {"type": "string"}, "waiting_room": {"type": "boolean"},
                  "audience": {"type": "string", "enum": ["class", "anyone"]}, "student_video": {"type": "boolean"},
                  "chat_enabled": {"type": "boolean"}}


def _meeting(ctx, class_id, meeting_id):
    from live.models import LiveRoom

    classroom = _class(ctx, class_id)
    room = LiveRoom.objects.filter(pk=_int(meeting_id, "meeting_id"), classroom=classroom).first()
    if room is None:
        raise ToolError("That meeting isn't in this class.")
    return classroom, room


def _undo_meeting_create(ctx, info):
    classroom, room = _meeting(ctx, info["class_id"], info["id"])
    if room.current_session or room.sessions.exists() or room.scheduled.exists():
        raise ToolError("The meeting has been used or scheduled since, so it was left in place.")
    room.delete()
    return "Meeting deleted. Its link no longer works."


@tool(AREA, "create_meeting", "Make a live meeting for later with its own link, optional passcode and waiting room.",
      {"class_id": {"type": "integer"}, **MEETING_FIELDS}, ["class_id"], writes=True,
      describe=lambda ctx, a: f"Create the live meeting \"{a.get('title') or 'Live meeting'}\" for {_class_name(ctx, a)}"
                              + (f" with passcode {a['passcode']}" if a.get("passcode") else ""),
      undo=_undo_meeting_create)
def create_meeting(ctx, args):
    from dashboard.teach_views import MeetingForm

    classroom = _class(ctx, args.get("class_id"))
    values = {k: v for k, v in args.items() if k in MEETING_FIELDS}
    values.setdefault("chat_enabled", True)
    values.setdefault("audience", "class")
    form = MeetingForm(data=form_data(MeetingForm, values=values))
    if not form.is_valid():
        raise ToolError(f"Not created. {form_errors(form)}")
    room = form.save(commit=False)
    room.classroom, room.is_main = classroom, False
    room.title = room.title or "Live meeting"
    room.save()
    link = _abs(ctx, reverse("live_short", args=[room.code]))
    return Result({"message": f"Meeting created. Share its link: {link}", "meeting_id": room.pk, "link": link},
                  undo={"class_id": classroom.pk, "id": room.pk}, undo_label="Delete it", link=reverse("teach:meetings", args=[classroom.pk]))


def _meeting_owner(ctx, info):
    from live.models import LiveRoom

    room = LiveRoom.objects.filter(pk=info["id"]).first()
    if room is None or room.classroom.facilitator_id != ctx.user.pk:
        raise ToolError("That meeting isn't yours.")


@tool(AREA, "update_meeting", "Change a live meeting's name, passcode or joining rules. Only the fields you pass change.",
      {"class_id": {"type": "integer"}, "meeting_id": {"type": "integer"}, "values": {"type": "object", "description": "Fields to change: " + ", ".join(MEETING_FIELDS)}},
      ["class_id", "meeting_id", "values"], writes=True,
      describe=lambda ctx, a: f"Change meeting {a.get('meeting_id')}: " + ", ".join(f"{k} to {short(v, 30)}" for k, v in json_arg(a.get("values")).items()),
      undo=_undo_restore("live.LiveRoom", _meeting_owner))
def update_meeting(ctx, args):
    from dashboard.teach_views import MeetingForm

    classroom, room = _meeting(ctx, args.get("class_id"), args.get("meeting_id"))
    before = snapshot(room)
    form = MeetingForm(data=form_data(MeetingForm, instance=room, values=json_arg(args.get("values"), "values")), instance=room)
    if room.is_main:
        del form.fields["audience"]  # the class link is always for the class
    if not form.is_valid():
        raise ToolError(f"Not saved. {form_errors(form)}")
    form.save()
    return Result({"message": "Meeting saved. Changes apply the next time someone joins.", "changed": form.changed_data},
                  undo={"id": room.pk, "before": before, "after": fresh_snapshot(room)})


@tool(AREA, "delete_meeting", "Delete a meeting made for later (not the permanent class link), with its upcoming sessions. Its link stops working.",
      {"class_id": {"type": "integer"}, "meeting_id": {"type": "integer"}}, ["class_id", "meeting_id"], writes=True, always_confirm=True,
      describe=lambda ctx, a: f"Delete meeting {a.get('meeting_id')} of {_class_name(ctx, a)} and its upcoming sessions; its link will stop working")
def delete_meeting(ctx, args):
    classroom, room = _meeting(ctx, args.get("class_id"), args.get("meeting_id"))
    if room.is_main:
        raise ToolError("The permanent class link can't be deleted.")
    if room.current_session:
        raise ToolError("This meeting is live right now. End it first.")
    removed = room.scheduled.filter(starts_at__gte=timezone.now()).delete()[0]
    room.scheduled.update(meeting=None, is_live=False)
    room.delete()
    return Result({"message": f"Meeting deleted, with {removed} upcoming session{'s' if removed != 1 else ''}. Its link no longer works."})


# ---------------------------------------------------------------- messages and the discussion board

def _message_sentence(ctx, a):
    who = "everyone in " + _class_name(ctx, a) + " and their parents" if str(a.get("to", "class")) == "class" else f"the parents of {_learner_name(ctx, {**a, 'learner_id': a.get('to')})}"
    return f"Send \"{short(a.get('subject'), 60)}\" to {who}"


@tool(AREA, "send_message",
      "Send a message, as Messages > New message does: to a whole class (learners and their linked parents), or to the "
      "parents of one learner in your class (to = that learner's id). They also get it by email.",
      {"class_id": {"type": "integer"}, "to": {"type": "string", "description": "\"class\" or a learner id"},
       "subject": {"type": "string"}, "body": {"type": "string"}}, ["class_id", "subject", "body"],
      writes=True, always_confirm=True, describe=_message_sentence)
def send_message(ctx, args):
    from dashboard.messaging_views import ComposeForm, _deliver

    user = _teacher(ctx)
    classroom = _class(ctx, args.get("class_id"))
    form = ComposeForm({"subject": args.get("subject", ""), "body": args.get("body", "")})
    if not form.is_valid():
        raise ToolError(f"Not sent. {form_errors(form)}")
    target = str(args.get("to") or "class")
    recipients, about = [], None
    if target == "class":
        for member in ClassMembership.objects.filter(classroom=classroom).select_related("learner"):
            recipients.append(member.learner)
            recipients.extend(link.parent for link in member.learner.parent_links.select_related("parent"))
    else:
        member = ClassMembership.objects.filter(classroom=classroom, learner_id=_int(target, "to")).select_related("learner").first()
        if member is None:
            raise ToolError(f"No learner with id {target} in {classroom.name}.")
        about = member.learner
        recipients.extend(link.parent for link in member.learner.parent_links.select_related("parent"))
    unique = {r.pk: r for r in recipients}
    if not unique:
        raise ToolError("Nobody to send to yet. For a single learner, a parent must first link to the child with the family code.")
    for person in unique.values():
        _deliver(user, person, form, classroom=classroom, about_learner=about)
    return Result({"message": f"Message sent to {len(unique)} {'person' if len(unique) == 1 else 'people'}."})


@tool(AREA, "reply_to_message", "Reply in an existing conversation. They also get it by email.",
      {"message_id": {"type": "integer"}, "body": {"type": "string"}}, ["message_id", "body"], writes=True, always_confirm=True,
      describe=lambda ctx, a: f"Reply to message {a.get('message_id')}: \"{short(a.get('body'), 80)}\"")
def reply_to_message(ctx, args):
    from dashboard.messaging_views import ComposeForm, _deliver, can_message

    user = _teacher(ctx)
    original = Message.objects.filter(pk=_int(args.get("message_id"), "message_id")).select_related("sender", "recipient").first()
    if original is None or user not in (original.sender, original.recipient):
        raise ToolError("That message isn't in your inbox.")
    other = original.sender if original.recipient_id == user.pk else original.recipient
    subject = original.subject if original.subject.lower().startswith("re:") else f"Re: {original.subject}"
    form = ComposeForm({"subject": subject[:150], "body": args.get("body", "")})
    if not form.is_valid() or not can_message(user, other):
        raise ToolError("Please write a message." if form.errors else "You cannot reply to this person.")
    _deliver(user, other, form, reply_to=original, classroom=original.classroom, about_learner=original.about_learner)
    return Result({"message": "Reply sent."})


def _undo_post(ctx, info):
    post = ClassPost.objects.filter(pk=info["id"], classroom__facilitator=ctx.user).first()
    if post is None:
        raise ToolError("That post is gone.")
    for name, value in info["fields"].items():
        setattr(post, name, value)
    post.save(update_fields=list(info["fields"]))
    return "Done. The post is back as it was."


@tool(AREA, "post_to_discussion", "Post on a class discussion board as the teacher (or reply to a post). The whole class sees it.",
      {"class_id": {"type": "integer"}, "body": {"type": "string"}, "reply_to_post_id": {"type": "integer"}}, ["class_id", "body"],
      writes=True, always_confirm=True, undo=_undo_post,
      describe=lambda ctx, a: f"Post on the {_class_name(ctx, a)} discussion board: \"{short(a.get('body'), 90)}\"")
def post_to_discussion(ctx, args):
    from live import moderation

    user = _teacher(ctx)
    classroom = _class(ctx, args.get("class_id"))
    body = (args.get("body") or "").strip()[:1500]
    if not body:
        raise ToolError("Write something first.")
    parent = None
    if args.get("reply_to_post_id"):
        parent = classroom.posts.filter(pk=args["reply_to_post_id"], parent__isnull=True, hidden=False, flagged=False).first()
        if parent is None:
            raise ToolError("That post is no longer there.")
    reason = moderation.check(body, host=True)
    post = ClassPost.objects.create(classroom=classroom, author=user, parent=parent, body=body, flagged=bool(reason), reason=reason or "")
    if reason:
        raise ToolError(moderation.REASONS[reason].replace("Your message", "Your post"))
    return Result({"message": "Posted.", "post_id": post.pk}, undo={"id": post.pk, "fields": {"hidden": True}},
                  undo_label="Remove the post", link=reverse("teach:discussion", args=[classroom.pk]))


@tool(AREA, "moderate_post",
      "On your class discussion board: 'delete' hides a post, 'pin' pins or unpins a top-level post, 'allow' shows a post "
      "the filter blocked.",
      {"class_id": {"type": "integer"}, "post_id": {"type": "integer"}, "action": {"type": "string", "enum": ["delete", "pin", "allow"]}},
      ["class_id", "post_id", "action"], writes=True, undo=_undo_post,
      describe=lambda ctx, a: {"delete": "Remove", "pin": "Pin or unpin", "allow": "Show the class"}.get(a.get("action"), "Change")
                              + f" post {a.get('post_id')} on the {_class_name(ctx, a)} board")
def moderate_post(ctx, args):
    classroom = _class(ctx, args.get("class_id"))
    post = ClassPost.objects.filter(pk=_int(args.get("post_id"), "post_id"), classroom=classroom).first()
    if post is None:
        raise ToolError("That post isn't on this board.")
    action = args.get("action")
    if action == "delete":
        before, post.hidden, message = {"hidden": post.hidden}, True, "Post removed."
    elif action == "pin" and post.parent_id is None:
        before, post.pinned = {"pinned": post.pinned}, not post.pinned
        message = "Post pinned." if post.pinned else "Post unpinned."
    elif action == "allow" and post.flagged:
        before, post.flagged, message = {"flagged": True}, False, "The post is now visible to the class."
    else:
        raise ToolError("That can't be done to this post (only top-level posts pin; only blocked posts can be allowed).")
    post.save(update_fields=list(before))
    return Result({"message": message}, undo={"id": post.pk, "fields": before})
