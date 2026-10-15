"""The family portal assistant: a parent asks about their own linked children, and can reply to a teacher's message.
Every lookup goes through ParentLink, the same rule the family pages use."""

from django.urls import reverse
from django.utils import timezone

from accounts.models import Message, ParentLink, User

from . import Result, ToolError, iso, short, tool

AREA = "family"


def _parent(ctx):
    user = ctx.user
    if not user.is_active or user.role != User.Role.PARENT:
        raise ToolError("This assistant is for parents and guardians.")
    return user


def _child(ctx, child_id):
    link = ParentLink.objects.filter(parent=_parent(ctx), child_id=child_id).select_related("child").first()
    if link is None:
        raise ToolError("That child isn't linked to your account. Use my_children to see who is.")
    return link.child


@tool(AREA, "my_children", "The children linked to this parent, with their progress, plan and when they were last active.")
def my_children(ctx, args):
    from billing.access import current_plan
    from dashboard.family import child_report

    rows = []
    for link in ParentLink.objects.filter(parent=_parent(ctx)).select_related("child"):
        r = child_report(link.child)
        plan = current_plan(link.child)
        rows.append({"child_id": link.child_id, "name": r["name"], "progress_percent": r["percent"], "stage": r["stage"],
                     "plan": plan.name if plan else "No plan", "last_active": r["last_active_text"]})
    if not rows:
        return Result({"children": [], "note": "No children are linked yet. Ask your child for their family code and add them on the family home page."})
    return Result({"children": rows})


@tool(AREA, "child_progress",
      "One child's full progress report, as on their family page: courses, strengths, lessons to practise, quiz average, "
      "labs, this week's activity, badges and tips for helping at home.",
      {"child_id": {"type": "integer"}}, ["child_id"])
def child_progress(ctx, args):
    from billing.access import current_subscription
    from dashboard.family import child_report

    child = _child(ctx, args.get("child_id"))
    r = child_report(child)
    sub = current_subscription(child)
    return Result({
        "name": r["name"], "programme": str(r["tier"] or ""), "progress_percent": r["percent"], "stage": r["stage"],
        "plan": {"name": sub.plan.name, "ends": iso(sub.ends_at)} if sub else None,
        "lessons_done": r["lessons_done"], "lessons_total": r["lessons_total"], "quiz_average": r["avg_score"],
        "courses": [{"course": c["course"].title, "progress": c["percent"], "quiz_average": c["avg_score"]} for c in r["courses"]],
        "strengths": [q.lesson.title for q in r["strengths"]],
        "practise_again": [{"lesson": q.lesson.title, "best_score": q.score_percent} for q in r["weak"]],
        "labs_done": r["labs_done"], "finished_this_week": r["this_week"], "finished_last_week": r["last_week"],
        "last_active": r["last_active_text"], "insights": [text for _tone, _icon, text in r["insights"]], "tips": r["tips"],
        "badges": r["badge_total"],
    }, link=reverse("family:child", args=[child.pk]))


@tool(AREA, "my_messages", "Messages from your child's teachers (newest first), with message ids for reading or replying.",
      {"limit": {"type": "integer"}})
def my_messages(ctx, args):
    user = _parent(ctx)
    qs = Message.objects.filter(recipient=user).select_related("sender", "about_learner")[: max(1, min(30, int(args.get("limit") or 10)))]
    return Result([{"message_id": m.pk, "from": str(m.sender), "about": str(m.about_learner or ""), "subject": m.subject,
                    "when": iso(m.created_at), "unread": m.read_at is None, "text": short(m.body, 200)} for m in qs])


@tool(AREA, "read_message", "One conversation with a teacher in full, oldest first. Reading it marks it read.",
      {"message_id": {"type": "integer"}}, ["message_id"])
def read_message(ctx, args):
    from dashboard.messaging_views import _thread

    user = _parent(ctx)
    msg = Message.objects.filter(pk=args.get("message_id")).select_related("sender", "recipient").first()
    if msg is None or user not in (msg.sender, msg.recipient):
        raise ToolError("That message isn't in your inbox.")
    thread = _thread(msg)
    Message.objects.filter(pk__in=[m.pk for m in thread], recipient=user, read_at__isnull=True).update(read_at=timezone.now())
    return Result([{"from": str(m.sender), "when": iso(m.created_at), "subject": m.subject, "text": m.body} for m in thread],
                  link=reverse("messaging:detail", args=[msg.pk]))


@tool(AREA, "reply_to_teacher", "Reply to a teacher's message. The teacher also gets it by email.",
      {"message_id": {"type": "integer"}, "body": {"type": "string"}}, ["message_id", "body"], writes=True, always_confirm=True,
      describe=lambda ctx, a: f"Reply to the teacher: \"{short(a.get('body'), 90)}\"")
def reply_to_teacher(ctx, args):
    from dashboard.messaging_views import ComposeForm, _deliver, can_message

    user = _parent(ctx)
    original = Message.objects.filter(pk=args.get("message_id")).select_related("sender", "recipient").first()
    if original is None or user not in (original.sender, original.recipient):
        raise ToolError("That message isn't in your inbox.")
    other = original.sender if original.recipient_id == user.pk else original.recipient
    subject = original.subject if original.subject.lower().startswith("re:") else f"Re: {original.subject}"
    form = ComposeForm({"subject": subject[:150], "body": args.get("body", "")})
    if not form.is_valid() or not can_message(user, other):
        raise ToolError("Please write a message." if form.errors else "You cannot reply to this person.")
    _deliver(user, other, form, reply_to=original, classroom=original.classroom, about_learner=original.about_learner)
    return Result({"message": "Reply sent."})
