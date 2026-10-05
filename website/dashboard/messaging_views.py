"""Messages between facilitators, parents and learners.

Learners can read messages but never send them (child safety). Facilitators write to a whole class (learners and
their linked parents) or to the parents of one learner in their class. Parents and facilitators can reply to each other.
"""

from django import forms
from django.contrib import messages as flash
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import ClassMembership, Classroom, Message, User
from core import notify


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
    return user.role in (User.Role.FACILITATOR, User.Role.PARENT) and not user.awaiting_approval


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
    return _render(request, "messaging/inbox.html", items=items[:100], box=box, can_write=_can_write(request.user))


@login_required
def detail(request, pk):
    message = get_object_or_404(Message.objects.select_related("sender", "recipient", "classroom"), pk=pk)
    if request.user not in (message.sender, message.recipient):
        return redirect("messaging:inbox")
    if message.recipient == request.user and message.read_at is None:
        message.read_at = timezone.now()
        message.save(update_fields=["read_at"])
    thread = Message.objects.filter(reply_to=message).select_related("sender")
    return _render(request, "messaging/detail.html", message=message, thread=thread, can_reply=_can_write(request.user) and message.sender != request.user and message.sender.role != User.Role.LEARNER, form=ComposeForm())


def _deliver(sender, recipient, form, **extra):
    msg = Message.objects.create(sender=sender, recipient=recipient, subject=form.cleaned_data["subject"], body=form.cleaned_data["body"], **extra)
    notify.send_message_email(msg)
    return msg


@login_required
@require_POST
def reply(request, pk):
    original = get_object_or_404(Message, pk=pk, recipient=request.user)
    subject = original.subject if original.subject.lower().startswith("re:") else f"Re: {original.subject}"
    form = ComposeForm({"subject": subject[:150], "body": request.POST.get("body", "")})
    if not _can_write(request.user) or not form.is_valid():
        flash.error(request, "Please write a message.")
        return redirect("messaging:detail", pk=pk)
    _deliver(request.user, original.sender, form, reply_to=original, classroom=original.classroom, about_learner=original.about_learner)
    flash.success(request, "Reply sent.")
    return redirect("messaging:detail", pk=pk)


@login_required
def compose(request):
    """Facilitators only: message a whole class, or the parents of one learner."""
    user = request.user
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
