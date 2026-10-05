from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from courses.badges import check_and_award_badges
from courses.models import Badge, Course, Enrollment, Lesson, Tier

from .labs import XP_PER_LAB, get_lab, get_labs, lab_template_exists
from .models import LabCompletion
from .stats import learner_stats


def _teacher_tasks(user, enrollments):
    """Assignments set by the learner's teachers, with the learner's progress on each course."""
    progress = {e.course_id: e.progress_percent for e in enrollments}
    today = timezone.now().date()
    tasks = []
    for m in user.class_memberships.select_related("classroom__facilitator"):
        for a in m.classroom.assignments.select_related("course"):
            percent = progress.get(a.course_id, 0)
            if percent >= 100:
                continue
            tasks.append({
                "a": a, "percent": percent, "teacher": m.classroom.facilitator, "classroom": m.classroom,
                "overdue": bool(a.due_date and a.due_date < today),
                "days_left": (a.due_date - today).days if a.due_date else None,
            })
    tasks.sort(key=lambda t: (t["a"].due_date is None, t["a"].due_date))
    return tasks


def _enrollments(user):
    return list(Enrollment.objects.filter(learner=user).select_related("course", "course__tier"))


def _continue_lesson(enrollments):
    """First unfinished teaching lesson in the most recently enrolled course."""
    for enrollment in enrollments:
        done = enrollment.completed_lesson_ids
        for lesson in enrollment.course.lessons.filter(lesson_type=Lesson.LessonType.LESSON):
            if lesson.id not in done:
                return lesson
    return None


def _labs_with_status(user):
    done = set(LabCompletion.objects.filter(learner=user).values_list("slug", flat=True))
    return [dict(lab, done=lab["slug"] in done) for lab in get_labs()]


def _path_for(user, enrollments):
    """The learner's tier as a step-by-step path of courses."""
    profile = getattr(user, "learner_profile", None)
    tier = profile.tier if profile and profile.tier_id else Tier.objects.first()
    if tier is None:
        return None, []
    progress = {e.course_id: e.progress_percent for e in enrollments}
    steps, current_set = [], False
    for course in tier.courses.all():
        percent = progress.get(course.id, 0)
        if percent >= 100:
            status = "done"
        elif not current_set:
            status, current_set = "current", True
        else:
            status = "todo"
        steps.append({"course": course, "percent": percent, "status": status, "started": course.id in progress})
    return tier, steps


def _next_lesson_on_path(steps, enrollments):
    """First unfinished lesson of the learner's current path step; falls back to their latest course."""
    for step in steps:
        if step["status"] == "current":
            done = set()
            for enrollment in enrollments:
                if enrollment.course_id == step["course"].id:
                    done = enrollment.completed_lesson_ids
            for lesson in step["course"].lessons.filter(lesson_type=Lesson.LessonType.LESSON):
                if lesson.id not in done:
                    return lesson
    return _continue_lesson(enrollments)


@login_required
def home(request):
    user = request.user
    if user.role == "parent":
        return redirect("family:home")
    if user.role == "facilitator":
        return redirect("teach:home")
    enrollments = _enrollments(user)
    stats = learner_stats(user)
    tier, steps = _path_for(user, enrollments)
    labs = _labs_with_status(user)
    earned = list(user.badges.select_related("badge"))
    earned_ids = {lb.badge_id for lb in earned}
    next_badges = list(Badge.objects.exclude(id__in=earned_ids)[:3])
    return render(
        request,
        "learner/home.html",
        {
            "stats": stats,
            "enrollments": enrollments,
            "continue_lesson": _next_lesson_on_path(steps, enrollments),
            "tier": tier,
            "steps": steps,
            "path_preview": [s for s in steps if s["status"] != "done"][:3],
            "labs": sorted(labs, key=lambda lab: lab["done"])[:3],
            "earned": earned[:6],
            "earned_count": len(earned),
            "next_badges": next_badges,
            "teacher_tasks": _teacher_tasks(user, enrollments),
            "nav": "home",
        },
    )


@login_required
def path(request):
    enrollments = _enrollments(request.user)
    tier, steps = _path_for(request.user, enrollments)
    return render(
        request,
        "learner/path.html",
        {
            "stats": learner_stats(request.user),
            "tier": tier,
            "steps": steps,
            "other_tiers": Tier.objects.exclude(pk=tier.pk) if tier else [],
            "has_profile_tier": bool(getattr(request.user, "learner_profile", None) and request.user.learner_profile.tier_id),
            "nav": "path",
        },
    )


@login_required
def my_courses(request):
    enrollments = _enrollments(request.user)
    enrolled_ids = [e.course_id for e in enrollments]
    return render(
        request,
        "learner/courses.html",
        {
            "stats": learner_stats(request.user),
            "enrollments": enrollments,
            "more_courses": Course.objects.exclude(id__in=enrolled_ids).select_related("tier"),
            "nav": "courses",
        },
    )


@login_required
def achievements(request):
    earned = list(request.user.badges.select_related("badge"))
    earned_ids = {lb.badge_id for lb in earned}
    return render(
        request,
        "learner/achievements.html",
        {
            "stats": learner_stats(request.user),
            "earned": earned,
            "locked": Badge.objects.exclude(id__in=earned_ids),
            "nav": "achievements",
        },
    )


@login_required
def labs(request):
    return render(
        request,
        "learner/labs.html",
        {"stats": learner_stats(request.user), "labs": _labs_with_status(request.user), "nav": "labs"},
    )


@login_required
def lab(request, slug):
    info = get_lab(slug)
    if info is None:
        raise Http404("No such lab")
    done = LabCompletion.objects.filter(learner=request.user, slug=slug).exists()
    return render(
        request,
        "learner/lab_detail.html",
        {
            "stats": learner_stats(request.user), "lab": info, "done": done, "xp": XP_PER_LAB, "nav": "labs",
            "has_template": lab_template_exists(slug),
        },
    )


@login_required
@require_POST
def lab_complete(request, slug):
    if get_lab(slug) is None:
        raise Http404("No such lab")
    _, created = LabCompletion.objects.get_or_create(learner=request.user, slug=slug)
    new_badges = check_and_award_badges(request.user) if created else []
    stats = learner_stats(request.user)
    return JsonResponse(
        {
            "created": created,
            "xp_gained": XP_PER_LAB if created else 0,
            "xp": stats["xp"],
            "level": stats["level"],
            "level_name": stats["level_name"],
            "streak": stats["streak"],
            "badges": [b.name for b in new_badges],
        }
    )
