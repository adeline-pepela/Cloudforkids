from django.contrib import messages
import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .badges import check_and_award_badges
from .models import Course, Enrollment, Lesson, LessonCompletion, QuizResult, Tier
from .quiz import quiz_question_count, quiz_status


def programs(request):
    tiers = Tier.objects.prefetch_related("courses").all()
    return render(request, "courses/programs.html", {"tiers": tiers})


def course_detail(request, slug):
    course = get_object_or_404(Course, slug=slug)
    lessons = course.lessons.filter(lesson_type=Lesson.LessonType.LESSON)
    exam = course.lessons.filter(lesson_type=Lesson.LessonType.EXAM).first()
    enrollment = None
    completed_ids = set()
    if request.user.is_authenticated:
        enrollment = Enrollment.objects.filter(learner=request.user, course=course).first()
        if enrollment:
            completed_ids = enrollment.completed_lesson_ids
    lessons_unlocked = not lessons.exists() or all(lesson.id in completed_ids for lesson in lessons)
    return render(
        request,
        "courses/course_detail.html",
        {
            "course": course,
            "lessons": lessons,
            "exam": exam,
            "enrollment": enrollment,
            "completed_ids": completed_ids,
            "lessons_unlocked": lessons_unlocked,
        },
    )


@login_required
def enroll(request, slug):
    course = get_object_or_404(Course, slug=slug)
    Enrollment.objects.get_or_create(learner=request.user, course=course)
    messages.success(request, f"You're enrolled in {course.title}! Let's get started.")
    return redirect("courses:course_detail", slug=course.slug)


@login_required
def lesson_detail(request, course_slug, lesson_slug):
    course = get_object_or_404(Course, slug=course_slug)
    lesson = get_object_or_404(Lesson, course=course, slug=lesson_slug)
    enrollment, _ = Enrollment.objects.get_or_create(learner=request.user, course=course)
    is_complete = lesson.id in enrollment.completed_lesson_ids
    quiz_total, quiz_passed, quiz_score = quiz_status(request.user, lesson)
    return render(
        request,
        "courses/lesson_detail.html",
        {
            "course": course,
            "lesson": lesson,
            "enrollment": enrollment,
            "is_complete": is_complete,
            "quiz_total": quiz_total,
            "quiz_passed": quiz_passed,
            "quiz_score": quiz_score,
            "side_quiz": bool(quiz_total) and not lesson.is_exam,
            "next_lesson": lesson.next_lesson(),
            "previous_lesson": lesson.previous_lesson(),
        },
    )


@login_required
def mark_lesson_complete(request, course_slug, lesson_slug):
    course = get_object_or_404(Course, slug=course_slug)
    lesson = get_object_or_404(Lesson, course=course, slug=lesson_slug)
    enrollment, _ = Enrollment.objects.get_or_create(learner=request.user, course=course)

    total, passed, score = quiz_status(request.user, lesson)
    if total and not passed:
        messages.error(request, "Finish the quiz first. You need to pass it before you can mark this complete.")
        return redirect("courses:lesson_detail", course_slug=course.slug, lesson_slug=lesson.slug)

    _, created = LessonCompletion.objects.get_or_create(
        enrollment=enrollment, lesson=lesson, defaults={"score_percent": score if total else None}
    )

    if created:
        new_badges = check_and_award_badges(request.user)
        for badge in new_badges:
            messages.success(request, f"Badge earned: {badge.name}!")
        messages.success(request, f"Nice work! You completed \u201c{lesson.title}\u201d.")

    next_lesson = lesson.next_lesson()
    if next_lesson:
        return redirect("courses:lesson_detail", course_slug=course.slug, lesson_slug=next_lesson.slug)
    return redirect("courses:course_detail", slug=course.slug)


@login_required
@require_POST
def quiz_result(request, course_slug, lesson_slug):
    """Record the learner's quiz score (sent by the lesson page) and say whether it passed."""
    course = get_object_or_404(Course, slug=course_slug)
    lesson = get_object_or_404(Lesson, course=course, slug=lesson_slug)
    try:
        data = json.loads(request.body or b"{}")
        correct, total = int(data["correct"]), int(data["total"])
    except (ValueError, KeyError, TypeError):
        return JsonResponse({"error": "Bad quiz result"}, status=400)

    expected = quiz_question_count(lesson)
    if not expected or total != expected or not 0 <= correct <= total:
        return JsonResponse({"error": "Quiz does not match this lesson"}, status=400)

    percent = round(correct / total * 100)
    passed = percent >= lesson.pass_score_percent
    result, _ = QuizResult.objects.get_or_create(learner=request.user, lesson=lesson)
    # Keep the best attempt, and never un-pass a lesson the learner already passed.
    if percent >= result.score_percent:
        result.score_percent = percent
    result.passed = result.passed or passed
    result.save()
    return JsonResponse(
        {"score_percent": percent, "passed": passed, "unlocked": result.passed, "needed": lesson.pass_score_percent}
    )
