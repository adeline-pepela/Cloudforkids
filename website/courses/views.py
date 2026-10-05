from django.contrib import messages
import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .badges import check_and_award_badges
from .models import Course, Enrollment, Lesson, LessonCompletion, Tier
from .quiz import attempt, parse_questions, public_html, quiz_status, record_result, reset_attempt


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
    reset_attempt(request, lesson)  # every page load starts a fresh quiz attempt
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
            "content_html": public_html(lesson.display_content),
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


def _quiz_lesson(request, course_slug, lesson_slug):
    course = get_object_or_404(Course, slug=course_slug)
    lesson = get_object_or_404(Lesson, course=course, slug=lesson_slug)
    return lesson, parse_questions(lesson.display_content)


def _json_body(request):
    try:
        return json.loads(request.body or b"{}")
    except ValueError:
        return {}


def _int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@login_required
@require_POST
def quiz_check(request, course_slug, lesson_slug):
    """Check one answer. The answer key stays on the server; the first answer to each question in an attempt counts."""
    lesson, questions = _quiz_lesson(request, course_slug, lesson_slug)
    data = _json_body(request)
    q, choice = _int(data.get("q")), _int(data.get("choice"))
    if q is None or choice is None or not 0 <= q < len(questions) or choice < 0 or lesson.is_exam:
        return JsonResponse({"error": "Bad answer"}, status=400)
    answers = attempt(request, lesson)
    if str(q) not in answers:
        answers[str(q)] = choice
        request.session.modified = True
    chosen = answers[str(q)]
    right = questions[q]["correct"]
    return JsonResponse(
        {"correct": chosen == right, "chosen": chosen, "correct_index": right, "explain": questions[q]["explain"],
         "answered": len(answers), "total": len(questions)}
    )


@login_required
@require_POST
def quiz_finish(request, course_slug, lesson_slug):
    """Score a finished lesson quiz from the answers the server recorded (not from anything the browser claims)."""
    lesson, questions = _quiz_lesson(request, course_slug, lesson_slug)
    answers = attempt(request, lesson)
    if not questions or len(answers) < len(questions):
        return JsonResponse({"error": "Answer every question first"}, status=400)
    correct = sum(1 for i, item in enumerate(questions) if answers.get(str(i)) == item["correct"])
    percent, passed, unlocked = record_result(request.user, lesson, correct, len(questions))
    return JsonResponse(
        {"correct": correct, "total": len(questions), "score_percent": percent, "passed": passed,
         "unlocked": unlocked, "needed": lesson.pass_score_percent}
    )


@login_required
@require_POST
def quiz_grade(request, course_slug, lesson_slug):
    """Grade a whole module exam: the browser sends the chosen option for every question."""
    lesson, questions = _quiz_lesson(request, course_slug, lesson_slug)
    chosen = _json_body(request).get("answers")
    if not questions or not isinstance(chosen, list) or len(chosen) != len(questions):
        return JsonResponse({"error": "Exam does not match this lesson"}, status=400)
    chosen = [_int(c, -1) for c in chosen]
    results = [{"correct": chosen[i] == item["correct"], "correct_index": item["correct"], "explain": item["explain"]}
               for i, item in enumerate(questions)]
    correct = sum(1 for r in results if r["correct"])
    percent, passed, unlocked = record_result(request.user, lesson, correct, len(questions))
    return JsonResponse(
        {"correct": correct, "total": len(questions), "score_percent": percent, "passed": passed,
         "unlocked": unlocked, "needed": lesson.pass_score_percent, "results": results}
    )


@login_required
@require_POST
def quiz_reset(request, course_slug, lesson_slug):
    """Start the quiz again (the best score is kept)."""
    lesson, _ = _quiz_lesson(request, course_slug, lesson_slug)
    reset_attempt(request, lesson)
    return JsonResponse({"ok": True})
