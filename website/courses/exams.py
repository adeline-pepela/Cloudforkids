"""Module exams: every course ends with one "Full Module Exam" built from the quiz questions of its lessons."""

import re

from django.utils.text import slugify

from .models import Lesson

QUESTION = re.compile(r'<div class="mcq-question"[^>]*>.*?<div class="mcq-explain">.*?</div></div>', re.S)
PASS_PERCENT = 70


def course_questions(course):
    """Every quiz question (as HTML) from the course's teaching lessons, in lesson order."""
    questions = []
    for lesson in course.lessons.filter(lesson_type=Lesson.LessonType.LESSON).order_by("order"):
        questions.extend(QUESTION.findall(lesson.content or ""))
    return questions


def build_exam_content(course, questions):
    count = len(questions)
    return (
        '<div class="lesson-content tone-fun">\n'
        '  <div class="exam-wrap">\n'
        f'    <p><i class="bi bi-mortarboard-fill" aria-hidden="true"></i> You have reached the end of <strong>{course.title}</strong>! '
        f'This exam checks everything you learned across every lesson in this module. Answer all {count} questions, then tap '
        f'<strong>Submit Exam</strong> to see your score. You need {PASS_PERCENT}% to pass, and you can always try again.</p>\n'
        f'    <div class="exam-form" data-pass="{PASS_PERCENT}">\n'
        '      <div class="exam-progress-wrap">\n'
        '        <div class="exam-progress-track"><div class="exam-progress-bar"></div></div>\n'
        f'        <span class="exam-progress-label">Answered 0 of {count}</span>\n'
        '      </div>\n'
        f'      <div class="mcq-block">{"".join(questions)}</div>\n'
        '      <div class="exam-submit-row"><button type="button" class="btn btn-cloud btn-lg exam-submit-btn">Submit Exam</button></div>\n'
        '      <div class="exam-result"></div>\n'
        '    </div>\n'
        '  </div>\n'
        '</div>\n'
    )


def ensure_exam(course, refresh=False):
    """Create the course's module exam if it has none; with refresh=True rebuild an existing one.
    Returns (exam, action) where action is "created", "refreshed" or "kept" (None when there is nothing to build from)."""
    questions = course_questions(course)
    exam = course.lessons.filter(lesson_type=Lesson.LessonType.EXAM).first()
    last = course.lessons.exclude(lesson_type=Lesson.LessonType.EXAM).order_by("-order").first()
    next_order = (last.order + 1) if last else 0
    if exam is None:
        if not questions:
            return None, None
        exam = Lesson.objects.create(
            course=course,
            title=f"Full Module Exam: {course.title}",
            slug=slugify(f"full-module-exam-{course.title}")[:100],
            summary=f"Check everything you learned in {course.title}.",
            content=build_exam_content(course, questions),
            duration_minutes=max(10, len(questions) * 2),
            order=next_order,
            lesson_type=Lesson.LessonType.EXAM,
            pass_score_percent=PASS_PERCENT,
        )
        return exam, "created"
    changed = []
    if exam.order <= (last.order if last else -1):
        exam.order = next_order  # the exam always comes last
        changed.append("order")
    if refresh and questions:
        exam.content = build_exam_content(course, questions)
        changed.append("content")
    if changed:
        exam.save(update_fields=changed)
    return exam, "refreshed" if "content" in changed else "kept"
