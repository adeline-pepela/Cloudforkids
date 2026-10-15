"""The learner study helper. Read-only: it explains lessons and progress, and never sees quiz answers. Lessons are
offered only when the learner's plan opens that course, the same rule the lesson pages use."""

import html
import re

from accounts.models import User

from . import Result, ToolError, short, tool

AREA = "learn"
TAGS = re.compile(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>", re.S)
LESSON_LIMIT = 9000


def _learner(ctx):
    user = ctx.user
    if not user.is_active or user.role != User.Role.LEARNER:
        raise ToolError("The study helper is for learners.")
    return user


def lesson_text(content):
    """A lesson's words without its quiz (questions, options, answers and explanations all removed)."""
    from courses.quiz import QUESTION

    text = QUESTION.sub("", content or "")
    text = re.sub(r'<div class="mcq-[^"]*".*?</div>', "", text, flags=re.S)
    text = re.sub(r"<(br|/p|/h\d|/li|/div)[^>]*>", "\n", text)
    text = html.unescape(TAGS.sub("", text))
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


@tool(AREA, "my_progress",
      "How the learner is doing: progress through their programme, courses with their progress, lessons they did well "
      "in, lessons to practise again, Practice Labs, streak and badges.")
def my_progress(ctx, args):
    from billing.access import current_plan
    from dashboard.family import child_report

    user = _learner(ctx)
    r = child_report(user)
    plan = current_plan(user)
    return Result({
        "name": r["name"], "programme": str(r["tier"] or ""), "plan": plan.name if plan else None, "progress_percent": r["percent"],
        "lessons_done": r["lessons_done"], "lessons_total": r["lessons_total"], "quiz_average": r["avg_score"],
        "streak_days": (r["stats"] or {}).get("streak") if isinstance(r["stats"], dict) else None,
        "courses": [{"course_id": c["course"].pk, "course": c["course"].display_title, "progress": c["percent"], "status": c["status"]} for c in r["courses"]],
        "did_well_in": [q.lesson.display_title for q in r["strengths"]],
        "practise_again": [q.lesson.display_title for q in r["weak"]],
        "labs_done": r["labs_done"], "labs_to_try": [lab["title"] for lab in r["labs_todo"][:3]],
        "badges": r["badge_total"],
    })


@tool(AREA, "course_lessons", "The lessons of one course in order, with which ones the learner has finished.",
      {"course_id": {"type": "integer"}}, ["course_id"])
def course_lessons(ctx, args):
    from billing.access import can_open_course
    from courses.models import Course, LessonCompletion

    user = _learner(ctx)
    course = Course.objects.filter(pk=args.get("course_id")).first()
    if course is None:
        raise ToolError("There is no course with that id. Use my_progress to see your courses.")
    if not can_open_course(user, course):
        raise ToolError(f"{course.display_title} is not part of your plan yet.")
    done = set(LessonCompletion.objects.filter(enrollment__learner=user, lesson__course=course).values_list("lesson_id", flat=True))
    return Result({"course": course.display_title, "lessons": [
        {"lesson_id": l.pk, "title": l.display_title, "minutes": l.duration_minutes, "exam": l.is_exam, "done": l.pk in done,
         "page": l.get_absolute_url()} for l in course.lessons.all()
    ]})


@tool(AREA, "read_lesson",
      "The words of one lesson (without its quiz) so you can explain it. Use it before explaining a lesson in detail.",
      {"lesson_id": {"type": "integer"}}, ["lesson_id"])
def read_lesson(ctx, args):
    from billing.access import can_open_course
    from courses.models import Lesson

    user = _learner(ctx)
    lesson = Lesson.objects.select_related("course").filter(pk=args.get("lesson_id")).first()
    if lesson is None:
        raise ToolError("There is no lesson with that id.")
    if not can_open_course(user, lesson.course):
        raise ToolError(f"{lesson.course.display_title} is not part of your plan yet.")
    if lesson.is_exam:
        return Result({"lesson": lesson.display_title, "text": "This is a module exam. I can help you revise the lessons before it, but not with the exam questions."})
    text = lesson_text(lesson.display_content)
    if len(text) > LESSON_LIMIT:
        text = text[:LESSON_LIMIT] + " …"
    return Result({"lesson": lesson.display_title, "course": lesson.course.display_title, "summary": short(lesson.display_summary, 300),
                   "text": text}, link=lesson.get_absolute_url())
