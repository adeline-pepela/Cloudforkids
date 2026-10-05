"""The facilitator / teacher portal: classes, rosters, assignments and learner reports."""

import csv

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import Assignment, ClassMembership, Classroom, User
from core.forms import BootstrapFormMixin
from courses.models import Tier
from courses.quiz import quiz_question_count

from .family import child_report
from .teach import class_report, learner_in_class, teacher_overview, teacher_tips


def teacher_only(view):
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.role != User.Role.FACILITATOR:
            return redirect("dashboard:home")
        return view(request, *args, **kwargs)

    wrapper.__name__ = view.__name__
    return wrapper


class ClassroomForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Classroom
        fields = ["name", "description", "tier", "school_name"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. Grade 6 Cloud Club"}),
            "description": forms.TextInput(attrs={"placeholder": "Optional: when and where you meet"}),
            "school_name": forms.TextInput(attrs={"placeholder": "School or hub name"}),
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
def class_new(request):
    form = ClassroomForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        classroom = form.save(commit=False)
        classroom.facilitator = request.user
        classroom.save()
        messages.success(request, f"{classroom.name} is ready. Share the join code {classroom.join_code} with your learners.")
        return redirect("teach:class", class_id=classroom.pk)
    return render(request, "teach/class_form.html", _ctx(request, form=form, nav="new", editing=None))


@teacher_only
def class_edit(request, class_id):
    classroom = _classroom(request, class_id)
    form = ClassroomForm(request.POST or None, instance=classroom)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Class updated.")
        return redirect("teach:class", class_id=classroom.pk)
    return render(request, "teach/class_form.html", _ctx(request, form=form, nav=classroom.pk, editing=classroom))


@teacher_only
def class_detail(request, class_id):
    classroom = _classroom(request, class_id)
    report = class_report(classroom)
    return render(
        request,
        "teach/class.html",
        _ctx(request, r=report, tips=teacher_tips(report), assignment_form=AssignmentForm(), nav=classroom.pk),
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
def assignment_add(request, class_id):
    classroom = _classroom(request, class_id)
    form = AssignmentForm(request.POST)
    if form.is_valid():
        assignment = form.save(commit=False)
        assignment.classroom = classroom
        assignment.save()
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
    classroom = _classroom(request, class_id)
    membership = get_object_or_404(ClassMembership.objects.select_related("learner"), classroom=classroom, learner_id=learner_id)
    return render(
        request,
        "parent/child.html",
        _ctx(request, r=child_report(membership.learner), viewer="teacher", classroom=classroom, nav=classroom.pk,
             base_tpl="teach/base.html"),
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
