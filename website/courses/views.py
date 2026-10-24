from django.contrib import messages
import json
from functools import wraps

import time

from django.contrib.auth.decorators import login_required
from django.db.models import F
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from billing import access
from billing.services import issue_certificate

from .badges import check_and_award_badges
from .models import Course, Enrollment, Lesson, LessonCompletion, LessonTime, Tier
from .quiz import attempt, end_attempt, new_attempt, parse_questions, public_html, quiz_status, record_result, without_quiz


def _locked(request, course):
    """Send someone whose plan does not include this course to the plans page."""
    if access.current_plan(request.user) is None:
        messages.info(request, "Choose a plan to open the lessons. Every plan includes this course's reading and videos.")
    else:
        messages.info(request, f"{course.display_title} is not part of your plan. Upgrade to Core to open every course.")
    return redirect(reverse("billing:my_plan") if request.user.role in ("learner", "parent") else reverse("billing:pricing"))


def _no_exam(request, course):
    messages.info(request, "Quizzes and module exams come with the Core and Advanced plans. On Starter, mark each lesson done when you have read it.")
    return redirect("courses:course_detail", slug=course.slug)


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
    signed_in = request.user.is_authenticated
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
            "can_open": signed_in and access.can_open_course(request.user, course),
            "quizzes_on": signed_in and access.can_take_quizzes(request.user),
            "certificate": request.user.certificates.filter(course=course).first() if signed_in else None,
        },
    )


@login_required
def enroll(request, slug):
    course = get_object_or_404(Course, slug=slug)
    if not access.can_open_course(request.user, course):
        return _locked(request, course)
    Enrollment.objects.get_or_create(learner=request.user, course=course)
    messages.success(request, f"You're enrolled in {course.title}! Let's get started.")
    return redirect("courses:course_detail", slug=course.slug)


@login_required
def lesson_detail(request, course_slug, lesson_slug):
    course = get_object_or_404(Course, slug=course_slug)
    lesson = get_object_or_404(Lesson, course=course, slug=lesson_slug)
    if not access.can_open_course(request.user, course):
        return _locked(request, course)
    quizzes_on = access.can_take_quizzes(request.user)
    if lesson.is_exam and not quizzes_on:
        return _no_exam(request, course)
    enrollment, _ = Enrollment.objects.get_or_create(learner=request.user, course=course)
    is_complete = lesson.id in enrollment.completed_lesson_ids
    if quizzes_on:
        quiz_total, quiz_passed, quiz_score = quiz_status(request.user, lesson)
        qids = new_attempt(request, lesson)  # every page load starts a fresh attempt with its own questions and order
        content_html = public_html(lesson.display_content, qids)
    else:
        quiz_total, quiz_passed, quiz_score = 0, True, None
        content_html = without_quiz(lesson.display_content)
    request.session[_clock_key(lesson)] = time.time()  # time on the page counts from here (see lesson_time)
    next_lesson = lesson.next_lesson()
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
            "content_html": content_html,
            "quizzes_on": quizzes_on,
            "side_quiz": bool(quiz_total) and not lesson.is_exam,
            "next_lesson": next_lesson if next_lesson and (quizzes_on or not next_lesson.is_exam) else None,
            "previous_lesson": lesson.previous_lesson(),
        },
    )


@login_required
def mark_lesson_complete(request, course_slug, lesson_slug):
    course = get_object_or_404(Course, slug=course_slug)
    lesson = get_object_or_404(Lesson, course=course, slug=lesson_slug)
    if not access.can_open_course(request.user, course):
        return _locked(request, course)
    quizzes_on = access.can_take_quizzes(request.user)
    if lesson.is_exam and not quizzes_on:
        return _no_exam(request, course)
    enrollment, _ = Enrollment.objects.get_or_create(learner=request.user, course=course)

    total, passed, score = quiz_status(request.user, lesson) if quizzes_on else (0, True, None)
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
        cert = issue_certificate(request.user, enrollment)
        if cert:
            messages.success(request, f"You earned a {cert.get_level_display()} for {course.title}! Find it under My Plan.")

    next_lesson = lesson.next_lesson()
    if next_lesson and (quizzes_on or not next_lesson.is_exam):
        return redirect("courses:lesson_detail", course_slug=course.slug, lesson_slug=next_lesson.slug)
    return redirect("courses:course_detail", slug=course.slug)


TIME_PING_SECONDS = 30  # the lesson page pings this often while it is open and in front


def _clock_key(lesson):
    return f"lesson-clock-{lesson.pk}"


@login_required
@require_POST
def lesson_time(request, course_slug, lesson_slug):
    """Add the time since the last ping (at most a little over one ping) to today's time on this lesson.
    The server keeps the clock, so a page can never claim more time than really passed. `resume` restarts the clock
    after the tab was in the background, without counting the time away."""
    lesson = get_object_or_404(Lesson, course__slug=course_slug, slug=lesson_slug)
    key, now = _clock_key(lesson), time.time()
    last = request.session.get(key)
    request.session[key] = now
    if last is None or _json_body(request).get("resume"):
        return JsonResponse({"ok": True, "added": 0})
    added = int(min(max(now - last, 0), TIME_PING_SECONDS + 15))
    if added:
        row, _ = LessonTime.objects.get_or_create(learner=request.user, lesson=lesson, day=timezone.localdate())
        LessonTime.objects.filter(pk=row.pk).update(seconds=F("seconds") + added)
    return JsonResponse({"ok": True, "added": added})


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


def quiz_plan_required(view):
    """Quiz and exam answers are only checked for plans that include quizzes."""

    @wraps(view)
    def wrapper(request, course_slug, lesson_slug):
        course = get_object_or_404(Course, slug=course_slug)
        if not (access.can_open_course(request.user, course) and access.can_take_quizzes(request.user)):
            return JsonResponse({"error": "Quizzes are not part of your plan."}, status=403)
        return view(request, course_slug, lesson_slug)

    return wrapper


STALE = {"error": "This quiz was refreshed. Reload the page to continue.", "stale": True}


@login_required
@require_POST
@quiz_plan_required
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
@quiz_plan_required
def quiz_finish(request, course_slug, lesson_slug):
    """Score a finished lesson quiz from the answers the server recorded (not from anything the browser claims)."""
    lesson, questions = _quiz_lesson(request, course_slug, lesson_slug)
    current = attempt(request, lesson)
    if current is None:
        return JsonResponse(STALE, status=409)
    qids = current["qids"]
    if not qids or any(str(q) not in current["answers"] for q in qids):
        return JsonResponse({"error": "Answer every question first"}, status=400)
    wrong = [q for q in qids if current["answers"][str(q)] != questions[q]["correct"]]
    correct = len(qids) - len(wrong)
    percent, passed, unlocked = record_result(request.user, lesson, correct, len(qids), wrong)
    return JsonResponse(
        {"correct": correct, "total": len(qids), "score_percent": percent, "passed": passed,
         "unlocked": unlocked, "needed": lesson.pass_score_percent}
    )


@login_required
@require_POST
@quiz_plan_required
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
    wrong = [q for q in qids if not results[str(q)]["correct"]]
    percent, passed, unlocked = record_result(request.user, lesson, correct, len(qids), wrong)
    end_attempt(request, lesson)
    return JsonResponse(
        {"correct": correct, "total": len(qids), "score_percent": percent, "passed": passed,
         "unlocked": unlocked, "needed": lesson.pass_score_percent, "results": results}
    )


@login_required
@require_POST
@quiz_plan_required
def quiz_reset(request, course_slug, lesson_slug):
    """Start the quiz again with a fresh set and order of questions (the best score is kept)."""
    lesson, _ = _quiz_lesson(request, course_slug, lesson_slug)
    new_attempt(request, lesson)
    return JsonResponse({"ok": True})
