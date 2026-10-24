"""The facilitator / teacher portal: classes, rosters, assignments and learner reports."""

import csv
from datetime import datetime, timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import Assignment, ClassMembership, Classroom, ClassSession, User
from core import notify
from core.forms import BootstrapFormMixin
from courses.models import Tier
from courses.quiz import quiz_question_count
from live.models import LiveRoom
from live.views import live_summary

from .family import child_report
from .teach import class_report, learner_in_class, teacher_overview, teacher_tips


def teacher_only(view):
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.role != User.Role.FACILITATOR:
            return redirect("dashboard:home")
        if request.user.awaiting_approval:
            return render(request, "teach/pending.html")
        return view(request, *args, **kwargs)

    wrapper.__name__ = view.__name__
    return wrapper


class ClassroomForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Classroom
        fields = ["name", "description", "tier", "school_name", "location", "meeting_link", "discussion_enabled"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. Grade 6 Cloud Club"}),
            "description": forms.TextInput(attrs={"placeholder": "Optional: when and where you meet"}),
            "school_name": forms.TextInput(attrs={"placeholder": "School or hub name"}),
            "location": forms.TextInput(attrs={"placeholder": "e.g. Computer lab, Room 4"}),
            "meeting_link": forms.URLInput(attrs={"placeholder": "https://meet.google.com/... (online classes)"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tier"].empty_label = "All tiers"


class AssignmentForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Assignment
        fields = ["course", "due_date", "note"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "note": forms.TextInput(attrs={"placeholder": "e.g. Finish this before our next session"}),
        }


class SessionForm(BootstrapFormMixin, forms.Form):
    """Adds one session, or a weekly run of sessions, to a class calendar. Times are Kenyan time."""

    title = forms.CharField(max_length=150, required=False, widget=forms.TextInput(attrs={"placeholder": "Topic (optional)"}))
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    time = forms.TimeField(widget=forms.TimeInput(attrs={"type": "time"}))
    duration_minutes = forms.IntegerField(min_value=10, max_value=480, initial=60, label="Minutes")
    repeat_weeks = forms.IntegerField(min_value=1, max_value=40, initial=1, label="Number of weekly sessions")
    location = forms.CharField(max_length=150, required=False, widget=forms.TextInput(attrs={"placeholder": "Room (blank = class venue)"}))
    meeting_link = forms.URLField(required=False, widget=forms.URLInput(attrs={"placeholder": "Online link (blank = class link)"}))
    notes = forms.CharField(max_length=300, required=False, widget=forms.TextInput(attrs={"placeholder": "e.g. Bring your laptop"}))
    is_live = forms.BooleanField(required=False, label="Live online class on Cloud for Kids")
    # Live classes only: a meeting of its own (new link, optional passcode) or the class's permanent link
    live_link = forms.ChoiceField(
        choices=[("own", "Its own new link"), ("class", "The class's permanent link")], initial="own", required=False,
        label="Link",
    )
    passcode = forms.CharField(max_length=20, required=False, label="Passcode (optional)",
                               widget=forms.TextInput(attrs={"placeholder": "e.g. cloud42", "autocomplete": "off"}))
    waiting_room = forms.BooleanField(required=False, label="Waiting room: I let each person in")
    audience = forms.ChoiceField(choices=LiveRoom.Audience.choices, initial=LiveRoom.Audience.CLASS, required=False, label="Who can join")
    student_video = forms.BooleanField(required=False, label="Learners may turn on their cameras")
    chat_enabled = forms.BooleanField(required=False, initial=True, label="Chat and reactions on")

    def clean_passcode(self):
        return clean_passcode(self.cleaned_data.get("passcode", ""))

    def clean_date(self):
        date = self.cleaned_data["date"]
        if date < timezone.localdate() - timedelta(days=1):
            raise forms.ValidationError("Pick today or a future date.")
        return date

    def save(self, classroom):
        data = self.cleaned_data
        meeting = None
        if data["is_live"]:
            if data["live_link"] == "class":
                LiveRoom.objects.get_or_create(classroom=classroom, is_main=True)
            else:
                meeting = LiveRoom.objects.create(
                    classroom=classroom, is_main=False, title=data["title"] or f"{classroom.name} live class",
                    passcode=data["passcode"], waiting_room=data["waiting_room"],
                    audience=data["audience"] or LiveRoom.Audience.CLASS, student_video=data["student_video"],
                    chat_enabled=data["chat_enabled"],
                )
        first = datetime.combine(data["date"], data["time"])
        made = []
        for week in range(data["repeat_weeks"]):
            starts = timezone.make_aware(first + timedelta(weeks=week))
            made.append(ClassSession(
                classroom=classroom, title=data["title"], starts_at=starts, duration_minutes=data["duration_minutes"],
                location=data["location"], meeting_link="" if data["is_live"] else data["meeting_link"], notes=data["notes"],
                is_live=data["is_live"], meeting=meeting,
            ))
        return ClassSession.objects.bulk_create(made)


def clean_passcode(value):
    value = (value or "").strip()
    if value and not (4 <= len(value) <= 20 and value.replace("-", "").isalnum()):
        raise forms.ValidationError("Use 4 to 20 letters or numbers.")
    return value


class MeetingForm(BootstrapFormMixin, forms.ModelForm):
    """A live meeting with its own link: name, passcode and the rules learners join with."""

    class Meta:
        model = LiveRoom
        fields = ["title", "passcode", "waiting_room", "audience", "student_video", "chat_enabled"]
        labels = {"title": "Meeting name", "waiting_room": "Waiting room: I let each person in",
                  "student_video": "Learners may turn on their cameras", "chat_enabled": "Chat and reactions on"}
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "e.g. Revision before the exam"}),
            "passcode": forms.TextInput(attrs={"placeholder": "Leave blank for no passcode", "autocomplete": "off"}),
        }

    def clean_passcode(self):
        return clean_passcode(self.cleaned_data.get("passcode", ""))


def _classroom(request, class_id):
    return get_object_or_404(Classroom, pk=class_id, facilitator=request.user)


def _ctx(request, **extra):
    extra.setdefault("classes", list(request.user.classrooms.filter(archived=False)))
    return extra


@teacher_only
def home(request):
    data = teacher_overview(request.user)
    return render(request, "teach/home.html", _ctx(request, nav="home", **data))


@teacher_only
def classes(request):
    """All the teacher's classes in one place (the sidebar shows a single "My classes" link, not one per class)."""
    show_archived = request.GET.get("archived") == "1"
    rows = request.user.classrooms.filter(archived=show_archived).select_related("tier")
    reports = [class_report(c) for c in rows]
    archived_count = request.user.classrooms.filter(archived=True).count()
    return render(request, "teach/classes.html", _ctx(request, nav="classes", reports=reports, show_archived=show_archived,
                                                       archived_count=archived_count))


@teacher_only
def discussion(request, class_id):
    from .classroom import discussion as class_discussion

    classroom = _classroom(request, class_id)
    posts = class_discussion(classroom, teacher_view=True)
    blocked = classroom.posts.filter(flagged=True, hidden=False).count()
    return render(request, "teach/discussion.html", _ctx(request, nav="classes", classroom=classroom, posts=posts, blocked=blocked))


@teacher_only
def class_new(request):
    form = ClassroomForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        classroom = form.save(commit=False)
        classroom.facilitator = request.user
        classroom.save()
        messages.success(request, f"{classroom.name} is ready. Share the join code {classroom.join_code} with your learners.")
        return redirect("teach:class", class_id=classroom.pk)
    return render(request, "teach/class_form.html", _ctx(request, form=form, nav="classes", editing=None))


@teacher_only
def class_edit(request, class_id):
    classroom = _classroom(request, class_id)
    form = ClassroomForm(request.POST or None, instance=classroom)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Class updated.")
        return redirect("teach:class", class_id=classroom.pk)
    return render(request, "teach/class_form.html", _ctx(request, form=form, nav="classes", editing=classroom))


@teacher_only
def class_detail(request, class_id, session_form=None):
    classroom = _classroom(request, class_id)
    report = class_report(classroom)
    return render(
        request,
        "teach/class.html",
        _ctx(
            request, r=report, tips=teacher_tips(report), assignment_form=AssignmentForm(), nav="classes",
            session_form=session_form or SessionForm(),
            upcoming=classroom.sessions.filter(starts_at__gte=timezone.now() - timedelta(hours=2))[:12],
            past_count=classroom.sessions.filter(starts_at__lt=timezone.now() - timedelta(hours=2)).count(),
            live=live_summary(classroom),
        ),
    )


@teacher_only
@require_POST
def class_archive(request, class_id):
    classroom = _classroom(request, class_id)
    classroom.archived = not classroom.archived
    classroom.save(update_fields=["archived"])
    messages.success(request, f"{classroom.name} {'archived' if classroom.archived else 'restored'}.")
    return redirect("teach:home")


@teacher_only
@require_POST
def member_remove(request, class_id, learner_id):
    classroom = _classroom(request, class_id)
    ClassMembership.objects.filter(classroom=classroom, learner_id=learner_id).delete()
    messages.success(request, "Learner removed from the class. Their account and progress are not deleted.")
    return redirect("teach:class", class_id=classroom.pk)


@teacher_only
@require_POST
def session_add(request, class_id):
    classroom = _classroom(request, class_id)
    form = SessionForm(request.POST)
    if form.is_valid():
        made = form.save(classroom)
        note = ""
        if form.cleaned_data["is_live"]:
            notify.notify_live_scheduled(classroom, made)
            room = made[0].live_room_obj
            note = f" Its link is {request.build_absolute_uri(reverse('live_short', args=[room.code]))}"
            note += f" (passcode {room.passcode})." if room.passcode else "."
            note += " We emailed the learners and their parents the date and the link."
        messages.success(request, f"Added {len(made)} session{'s' if len(made) != 1 else ''} to the {classroom.name} calendar. Learners in the class can see it now.{note}")
        return redirect("teach:class", class_id=classroom.pk)
    return class_detail(request, class_id, session_form=form)


@teacher_only
def meetings(request, class_id):
    """Every live link of the class: the permanent class room and the meetings made for later."""
    classroom = _classroom(request, class_id)
    form = MeetingForm(request.POST or None, initial={"chat_enabled": True})
    if request.method == "POST" and form.is_valid():
        room = form.save(commit=False)
        room.classroom = classroom
        room.is_main = False
        room.title = room.title or "Live meeting"
        room.save()
        messages.success(request, f"Meeting created. Share its link: {request.build_absolute_uri(reverse('live_short', args=[room.code]))}")
        return redirect("teach:meetings", class_id=classroom.pk)
    LiveRoom.objects.get_or_create(classroom=classroom, is_main=True)
    now = timezone.now()
    rows = []
    for room in classroom.live_rooms.order_by("-is_main", "-created_at"):
        rows.append({
            "room": room,
            "url": request.build_absolute_uri(reverse("live_short", args=[room.code])),
            "live": room.current_session,
            "next": room.scheduled.filter(starts_at__gte=now - timedelta(hours=2)).order_by("starts_at").first() if not room.is_main
            else classroom.sessions.filter(is_live=True, meeting__isnull=True, starts_at__gte=now - timedelta(hours=2)).first(),
            "held": room.sessions.count(),
        })
    return render(request, "teach/meetings.html", _ctx(request, nav="classes", classroom=classroom, rows=rows, form=form))


@teacher_only
def meeting_edit(request, class_id, room_id):
    classroom = _classroom(request, class_id)
    room = get_object_or_404(LiveRoom, pk=room_id, classroom=classroom)
    form = MeetingForm(request.POST or None, instance=room)
    if room.is_main:
        del form.fields["audience"]  # the class link is always for the class
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Meeting saved. Changes apply the next time someone joins.")
        return redirect("teach:meetings", class_id=classroom.pk)
    return render(request, "teach/meeting_form.html", _ctx(request, nav="classes", classroom=classroom, room=room, form=form))


@teacher_only
@require_POST
def meeting_delete(request, class_id, room_id):
    classroom = _classroom(request, class_id)
    room = get_object_or_404(LiveRoom, pk=room_id, classroom=classroom, is_main=False)
    if room.current_session:
        messages.error(request, "This meeting is live right now. End it first.")
        return redirect("teach:meetings", class_id=classroom.pk)
    removed = room.scheduled.filter(starts_at__gte=timezone.now()).delete()[0]
    room.scheduled.update(meeting=None, is_live=False)  # past calendar entries stay as history
    room.delete()
    messages.success(request, f"Meeting deleted, with {removed} upcoming session{'s' if removed != 1 else ''}. Its link no longer works.")
    return redirect("teach:meetings", class_id=classroom.pk)


@teacher_only
@require_POST
def session_delete(request, class_id, session_id):
    classroom = _classroom(request, class_id)
    get_object_or_404(ClassSession, pk=session_id, classroom=classroom).delete()
    messages.success(request, "Session removed from the calendar.")
    return redirect("teach:class", class_id=classroom.pk)


@teacher_only
@require_POST
def assignment_add(request, class_id):
    classroom = _classroom(request, class_id)
    form = AssignmentForm(request.POST)
    if form.is_valid():
        assignment = form.save(commit=False)
        assignment.classroom = classroom
        assignment.save()
        notify.notify_assignment(assignment)
        messages.success(request, f"Assigned {assignment.course.title} to {classroom.name}.")
    else:
        messages.error(request, "Please choose a course for the assignment.")
    return redirect("teach:class", class_id=classroom.pk)


@teacher_only
@require_POST
def assignment_delete(request, class_id, assignment_id):
    classroom = _classroom(request, class_id)
    get_object_or_404(Assignment, pk=assignment_id, classroom=classroom).delete()
    messages.success(request, "Assignment removed.")
    return redirect("teach:class", class_id=classroom.pk)


@teacher_only
def learner_report(request, class_id, learner_id):
    from accounts.models import LearnerNote

    classroom = _classroom(request, class_id)
    membership = get_object_or_404(ClassMembership.objects.select_related("learner"), classroom=classroom, learner_id=learner_id)
    learner = membership.learner
    if request.method == "POST":
        # Teaching notes: dated notes about the learner, shared with admins and the learner's other teachers (never the family).
        if request.POST.get("action") == "delete_note":
            LearnerNote.objects.filter(learner=learner, author=request.user, pk=request.POST.get("note")).delete()
            messages.success(request, "Note removed.")
        else:
            body = request.POST.get("body", "").strip()[:2000]
            if body:
                LearnerNote.objects.create(learner=learner, author=request.user, body=body)
                messages.success(request, "Note saved.")
        return redirect("teach:learner", class_id=classroom.pk, learner_id=learner.pk)
    notes = LearnerNote.objects.filter(learner=learner).select_related("author")
    return render(
        request,
        "parent/child.html",
        _ctx(request, r=child_report(learner), viewer="teacher", classroom=classroom, nav="classes",
             base_tpl="teach/base.html", notes=notes),
    )


@teacher_only
def class_export(request, class_id):
    classroom = _classroom(request, class_id)
    report = class_report(classroom)
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{classroom.name.replace(" ", "_")}_progress.csv"'
    writer = csv.writer(response)
    writer.writerow(["Name", "Username", "Progress %", "Lessons done", "Quiz average %", "Practice labs", "Streak (days)", "Last active", "Status"])
    for row in report["roster"]:
        writer.writerow([
            row["name"], row["user"].username, row["percent"], row["done"],
            "" if row["avg_score"] is None else row["avg_score"], row["labs"], row["streak"], row["last_text"], row["status_label"],
        ])
    return response


@teacher_only
def curriculum(request):
    tiers = Tier.objects.prefetch_related("courses__lessons")
    rows = []
    for tier in tiers:
        courses = []
        for course in tier.courses.all():
            lessons = [(l, quiz_question_count(l)) for l in course.lessons.all()]
            courses.append({"course": course, "lessons": lessons})
        rows.append({"tier": tier, "courses": courses})
    return render(request, "teach/curriculum.html", _ctx(request, rows=rows, nav="curriculum"))
