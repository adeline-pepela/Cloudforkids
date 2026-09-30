from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .badges import check_and_award_badges
from .models import Course, Enrollment, Lesson, LessonCompletion, Tier


def programs(request):
    tiers = Tier.objects.prefetch_related("courses").all()
    return render(request, "courses/programs.html", {"tiers": tiers})


def course_detail(request, slug):
    course = get_object_or_404(Course, slug=slug)
    lessons = course.lessons.all()
    enrollment = None
    completed_ids = set()
    if request.user.is_authenticated:
        enrollment = Enrollment.objects.filter(learner=request.user, course=course).first()
        if enrollment:
            completed_ids = enrollment.completed_lesson_ids
    return render(
        request,
        "courses/course_detail.html",
        {
            "course": course,
            "lessons": lessons,
            "enrollment": enrollment,
            "completed_ids": completed_ids,
        },
    )


@login_required
def enroll(request, slug):
    course = get_object_or_404(Course, slug=slug)
    Enrollment.objects.get_or_create(learner=request.user, course=course)
    messages.success(request, f"You're enrolled in {course.title}\! Let's get started.")
    return redirect("courses:course_detail", slug=course.slug)


@login_required
def lesson_detail(request, course_slug, lesson_slug):
    course = get_object_or_404(Course, slug=course_slug)
    lesson = get_object_or_404(Lesson, course=course, slug=lesson_slug)
    enrollment, _ = Enrollment.objects.get_or_create(learner=request.user, course=course)
    is_complete = lesson.id in enrollment.completed_lesson_ids
    return render(
        request,
        "courses/lesson_detail.html",
        {
            "course": course,
            "lesson": lesson,
            "enrollment": enrollment,
            "is_complete": is_complete,
            "next_lesson": lesson.next_lesson(),
            "previous_lesson": lesson.previous_lesson(),
        },
    )


@login_required
def mark_lesson_complete(request, course_slug, lesson_slug):
    course = get_object_or_404(Course, slug=course_slug)
    lesson = get_object_or_404(Lesson, course=course, slug=lesson_slug)
    enrollment, _ = Enrollment.objects.get_or_create(learner=request.user, course=course)
    _, created = LessonCompletion.objects.get_or_create(enrollment=enrollment, lesson=lesson)

    if created:
        new_badges = check_and_award_badges(request.user)
        for badge in new_badges:
            messages.success(request, f"{badge.icon} Badge earned: {badge.name}\!")
        messages.success(request, f"Nice work\! You completed \u201c{lesson.title}\u201d.")

    next_lesson = lesson.next_lesson()
    if next_lesson:
        return redirect("courses:lesson_detail", course_slug=course.slug, lesson_slug=next_lesson.slug)
    return redirect("courses:course_detail", slug=course.slug)
