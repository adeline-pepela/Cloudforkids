from django.contrib import messages
import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .badges import check_and_award_badges
from .models import Course, Enrollment, Lesson, LessonCompletion, Tier
from .quiz import attempt, end_attempt, new_attempt, parse_questions, public_html, quiz_status, record_result


def programs(request):
    tiers = Tier.objects.exclude(slug="explorer").prefetch_related("courses__lessons")
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
    qids = new_attempt(request, lesson)  # every page load starts a fresh attempt with its own questions and order
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
            "content_html": public_html(lesson.display_content, qids),
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


STALE = {"error": "This quiz was refreshed. Reload the page to continue.", "stale": True}


@login_required
@require_POST
def quiz_check(request, course_slug, lesson_slug):
    """Check one answer. The answer key stays on the server; the first answer to each question in an attempt counts."""
    lesson, questions = _quiz_lesson(request, course_slug, lesson_slug)
    data = _json_body(request)
    q, choice = _int(data.get("q")), _int(data.get("choice"))
    current = attempt(request, lesson)
    if current is None or lesson.is_exam:
        return JsonResponse(STALE, status=409)
    if q is None or choice is None or q not in current["qids"] or q >= len(questions) or choice < 0:
        return JsonResponse({"error": "Bad answer"}, status=400)
    answers = current["answers"]
    if str(q) not in answers:
        answers[str(q)] = choice
        request.session.modified = True
    chosen = answers[str(q)]
    right = questions[q]["correct"]
    return JsonResponse(
        {"correct": chosen == right, "chosen": chosen, "correct_index": right, "explain": questions[q]["explain"],
         "answered": len(answers), "total": len(current["qids"])}
    )


@login_required
@require_POST
def quiz_finish(request, course_slug, lesson_slug):
    """Score a finished lesson quiz from the answers the server recorded (not from anything the browser claims)."""
    lesson, questions = _quiz_lesson(request, course_slug, lesson_slug)
    current = attempt(request, lesson)
    if current is None:
        return JsonResponse(STALE, status=409)
    qids = current["qids"]
    if not qids or any(str(q) not in current["answers"] for q in qids):
        return JsonResponse({"error": "Answer every question first"}, status=400)
    correct = sum(1 for q in qids if current["answers"][str(q)] == questions[q]["correct"])
    percent, passed, unlocked = record_result(request.user, lesson, correct, len(qids))
    return JsonResponse(
        {"correct": correct, "total": len(qids), "score_percent": percent, "passed": passed,
         "unlocked": unlocked, "needed": lesson.pass_score_percent}
    )


@login_required
@require_POST
def quiz_grade(request, course_slug, lesson_slug):
    """Grade a whole module exam: the browser sends {question id: chosen option} for the questions it was shown.
    An attempt can be graded once; trying again starts from a fresh page with the questions in a new order."""
    lesson, questions = _quiz_lesson(request, course_slug, lesson_slug)
    current = attempt(request, lesson)
    if current is None:
        return JsonResponse(STALE, status=409)
    chosen = _json_body(request).get("answers")
    qids = current["qids"]
    if not qids or not isinstance(chosen, dict):
        return JsonResponse({"error": "Exam does not match this lesson"}, status=400)
    picks = {q: _int(chosen.get(str(q)), -1) for q in qids}
    results = {
        str(q): {"correct": picks[q] == questions[q]["correct"], "correct_index": questions[q]["correct"], "explain": questions[q]["explain"]}
        for q in qids
    }
    correct = sum(1 for r in results.values() if r["correct"])
    percent, passed, unlocked = record_result(request.user, lesson, correct, len(qids))
    end_attempt(request, lesson)
    return JsonResponse(
        {"correct": correct, "total": len(qids), "score_percent": percent, "passed": passed,
         "unlocked": unlocked, "needed": lesson.pass_score_percent, "results": results}
    )


@login_required
@require_POST
def quiz_reset(request, course_slug, lesson_slug):
    """Start the quiz again with a fresh set and order of questions (the best score is kept)."""
    lesson, _ = _quiz_lesson(request, course_slug, lesson_slug)
    new_attempt(request, lesson)
    return JsonResponse({"ok": True})
