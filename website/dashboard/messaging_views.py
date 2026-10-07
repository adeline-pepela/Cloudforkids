"""Messages between facilitators, parents and learners.

Facilitators write to a whole class (learners and their linked parents) or to the parents of one learner in their
class, and can answer any learner in their class. Parents and facilitators can reply to each other. Learners can
write to their teachers and to classmates, but only to people they share a class with, and a conversation is a thread
between the same two people.
"""

from datetime import timedelta

from django import forms
from django.contrib import messages as flash
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import ClassMembership, Classroom, Message, User
from core import notify

LEARNER_MESSAGES_PER_HOUR = 20  # a gentle brake on spam between learners


def _base(request):
    """Template and sidebar data for the person's own area."""
    role = request.user.role
    if role == User.Role.FACILITATOR:
        return "teach/base.html", {"classes": list(request.user.classrooms.filter(archived=False)), "nav": "messages"}
    if role == User.Role.PARENT:
        return "parent/base.html", {"children": [l.child for l in request.user.children_links.select_related("child")], "nav": "messages"}
    return "learner/base.html", {"nav": "messages"}


def _render(request, template, **ctx):
    base, extra = _base(request)
    return render(request, template, {"base_tpl": base, **extra, **ctx})


def _can_write(user):
    return user.role in (User.Role.FACILITATOR, User.Role.PARENT, User.Role.LEARNER) and not user.awaiting_approval


def learner_contacts(learner):
    """The people a learner may write to: the teachers of their classes and the other learners in them.
    Returns (teachers, classmates, class_for) where class_for maps a person's id to a class they share."""
    classes = list(
        Classroom.objects.filter(memberships__learner=learner, archived=False).select_related("facilitator").distinct()
    )
    teachers = {c.facilitator_id: c.facilitator for c in classes if c.facilitator.is_active and c.facilitator.is_approved}
    class_for = {c.facilitator_id: c for c in classes if c.facilitator_id in teachers}
    classmates = {}
    for m in ClassMembership.objects.filter(classroom__in=classes).exclude(learner=learner).select_related("learner", "classroom"):
        if m.learner.is_active and m.learner_id not in classmates:
            classmates[m.learner_id] = m.learner
            class_for[m.learner_id] = m.classroom
    return list(teachers.values()), sorted(classmates.values(), key=lambda u: (u.get_full_name() or u.username).lower()), class_for


def can_message(sender, target):
    """Whether `sender` may write (or reply) to `target`."""
    if not _can_write(sender) or sender.pk == target.pk or not target.is_active:
        return False
    if sender.role == User.Role.LEARNER:
        teachers, classmates, _ = learner_contacts(sender)
        return target in teachers or target in classmates
    if sender.role == User.Role.FACILITATOR:
        if target.role == User.Role.LEARNER:
            return ClassMembership.objects.filter(classroom__facilitator=sender, learner=target).exists()
        return target.role == User.Role.PARENT
    return target.role == User.Role.FACILITATOR  # parents write back to teachers


class ComposeForm(forms.Form):
    subject = forms.CharField(max_length=150, widget=forms.TextInput(attrs={"class": "form-control form-control-lg", "placeholder": "Subject"}))
    body = forms.CharField(max_length=3000, widget=forms.Textarea(attrs={"class": "form-control", "rows": 6, "placeholder": "Write your message"}))


@login_required
def inbox(request):
    box = request.GET.get("box", "in")
    if box == "sent" and _can_write(request.user):
        items = Message.objects.filter(sender=request.user).select_related("recipient", "classroom")
    else:
        box = "in"
        items = Message.objects.filter(recipient=request.user).select_related("sender", "classroom")
    can_compose = request.user.role == User.Role.FACILITATOR
    if request.user.role == User.Role.LEARNER:
        teachers, classmates, _ = learner_contacts(request.user)
        can_compose = bool(teachers or classmates)
    return _render(request, "messaging/inbox.html", items=items[:100], box=box, can_write=_can_write(request.user), can_compose=can_compose)


def _thread(message):
    """The whole conversation a message belongs to: its first message and every reply under it, oldest first."""
    root = message
    while root.reply_to_id:
        root = root.reply_to
    found, frontier = [root], [root.pk]
    while frontier:
        children = list(Message.objects.filter(reply_to_id__in=frontier).select_related("sender", "recipient"))
        found += children
        frontier = [c.pk for c in children]
    return sorted(found, key=lambda m: (m.created_at, m.pk))


@login_required
def detail(request, pk):
    message = get_object_or_404(Message.objects.select_related("sender", "recipient", "classroom", "reply_to"), pk=pk)
    if request.user not in (message.sender, message.recipient):
        return redirect("messaging:inbox")
    thread = _thread(message)
    Message.objects.filter(pk__in=[m.pk for m in thread], recipient=request.user, read_at__isnull=True).update(read_at=timezone.now())
    first = thread[0]
    other = first.sender if first.recipient_id == request.user.pk else first.recipient
    return _render(
        request, "messaging/detail.html", message=first, thread=thread, other=other, last=thread[-1],
        can_reply=can_message(request.user, other), form=ComposeForm(),
    )


def _deliver(sender, recipient, form, **extra):
    msg = Message.objects.create(sender=sender, recipient=recipient, subject=form.cleaned_data["subject"], body=form.cleaned_data["body"], **extra)
    notify.send_message_email(msg)
    return msg


def _too_many(user):
    if user.role != User.Role.LEARNER:
        return False
    since = timezone.now() - timedelta(hours=1)
    return Message.objects.filter(sender=user, created_at__gte=since).count() >= LEARNER_MESSAGES_PER_HOUR


@login_required
@require_POST
def reply(request, pk):
    original = get_object_or_404(Message.objects.select_related("sender", "recipient"), pk=pk)
    if request.user not in (original.sender, original.recipient):
        return redirect("messaging:inbox")
    other = original.sender if original.recipient_id == request.user.pk else original.recipient
    subject = original.subject if original.subject.lower().startswith("re:") else f"Re: {original.subject}"
    form = ComposeForm({"subject": subject[:150], "body": request.POST.get("body", "")})
    if not can_message(request.user, other) or not form.is_valid():
        flash.error(request, "Please write a message." if form.errors else "You cannot reply to this person.")
        return redirect("messaging:detail", pk=pk)
    if _too_many(request.user):
        flash.error(request, "You have sent a lot of messages. Please wait a little before sending more.")
        return redirect("messaging:detail", pk=pk)
    _deliver(request.user, other, form, reply_to=original, classroom=original.classroom, about_learner=original.about_learner)
    flash.success(request, "Reply sent.")
    return redirect("messaging:detail", pk=pk)


@login_required
def compose(request):
    """Facilitators message a whole class or the parents of one learner. Learners message a teacher or a classmate."""
    user = request.user
    if user.role == User.Role.LEARNER:
        return _compose_learner(request)
    if user.role != User.Role.FACILITATOR or user.awaiting_approval:
        return redirect("messaging:inbox")
    classes = list(user.classrooms.filter(archived=False))
    form = ComposeForm(request.POST or None)
    initial_class = request.GET.get("class")
    if request.method == "POST" and form.is_valid():
        classroom = get_object_or_404(Classroom, pk=request.POST.get("classroom"), facilitator=user)
        target = request.POST.get("to", "class")
        recipients = []
        about = None
        if target == "class":
            for member in ClassMembership.objects.filter(classroom=classroom).select_related("learner"):
                recipients.append(member.learner)
                recipients.extend(link.parent for link in member.learner.parent_links.select_related("parent"))
        else:
            member = get_object_or_404(ClassMembership, classroom=classroom, learner_id=target)
            about = member.learner
            recipients.extend(link.parent for link in member.learner.parent_links.select_related("parent"))
        unique = {r.pk: r for r in recipients}
        if not unique:
            flash.error(request, "Nobody to send to yet. For a single learner, a parent must first link to the child with the family code.")
        else:
            for person in unique.values():
                _deliver(user, person, form, classroom=classroom, about_learner=about)
            flash.success(request, f"Message sent to {len(unique)} {'person' if len(unique) == 1 else 'people'}.")
            return redirect("messaging:inbox")
    members = ClassMembership.objects.filter(classroom__in=classes).select_related("learner", "classroom")
    return _render(request, "messaging/compose.html", form=form, classes=classes, members=members, initial_class=initial_class)


def _compose_learner(request):
    user = request.user
    teachers, classmates, class_for = learner_contacts(user)
    form = ComposeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        target = next((p for p in teachers + classmates if str(p.pk) == request.POST.get("to")), None)
        if target is None:
            flash.error(request, "Choose a teacher or a classmate from your classes.")
        elif _too_many(user):
            flash.error(request, "You have sent a lot of messages. Please wait a little before sending more.")
        else:
            _deliver(user, target, form, classroom=class_for.get(target.pk))
            flash.success(request, f"Message sent to {target.get_full_name() or target.username}.")
            return redirect("messaging:inbox")
    return _render(
        request, "messaging/compose_learner.html", form=form, teachers=teachers, classmates=classmates,
        class_for=class_for, selected=request.POST.get("to") or request.GET.get("to", ""),
    )
