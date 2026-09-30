from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from courses.models import Course, Enrollment, Tier


@login_required
def home(request):
    enrollments = Enrollment.objects.filter(learner=request.user).select_related("course", "course__tier")
    enrolled_course_ids = enrollments.values_list("course_id", flat=True)

    suggested_courses = []
    profile = getattr(request.user, "learner_profile", None)
    if profile and profile.tier:
        suggested_courses = Course.objects.filter(tier=profile.tier).exclude(id__in=enrolled_course_ids)[:3]
    if not suggested_courses:
        suggested_courses = Course.objects.exclude(id__in=enrolled_course_ids)[:3]

    badges = request.user.badges.select_related("badge").all()

    total_lessons_done = sum(len(e.completed_lesson_ids) for e in enrollments)

    return render(
        request,
        "dashboard/dashboard.html",
        {
            "enrollments": enrollments,
            "suggested_courses": suggested_courses,
            "badges": badges,
            "total_lessons_done": total_lessons_done,
            "tiers": Tier.objects.all(),
        },
    )
