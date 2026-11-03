"""Module exams: every course ends with one "Full Module Exam" built from the quiz questions of its lessons."""

import re

from django.utils.text import slugify

from .models import Lesson

QUESTION = re.compile(r'<div class="mcq-question"[^>]*>.*?<div class="mcq-explain">.*?</div></div>', re.S)
PASS_PERCENT = 70
EXAM_SIZE = 20  # questions per attempt when the pool is bigger; each attempt deals a different random set

TEXT = {
    "en": dict(
        intro="You have reached the end of <strong>{title}</strong>! This exam checks everything you learned across every lesson in this module. "
              "Answer all <span class=\"exam-count\">{count}</span> questions, then tap <strong>Submit Exam</strong> to see your score. You need {pass_}% to pass, and you can always try again.",
        progress="Answered 0 of {count}", button="Submit Exam &amp; See My Score"),
    "sw": dict(
        intro="Umefika mwisho wa <strong>{title}</strong>! Mtihani huu unapima kila ulichojifunza katika masomo yote ya kozi hii. "
              "Jibu maswali yote <span class=\"exam-count\">{count}</span>, kisha bonyeza <strong>Wasilisha Mtihani</strong> uone alama zako. Unahitaji {pass_}% kufaulu, na unaweza kujaribu tena.",
        progress="Umejibu 0 kati ya {count}", button="Wasilisha Mtihani na Uone Alama"),
}


def course_questions(course):
    """Every quiz question (as HTML) from the course's teaching lessons, in lesson order."""
    questions = []
    for lesson in course.lessons.filter(lesson_type=Lesson.LessonType.LESSON).order_by("order"):
        questions.extend(QUESTION.findall(lesson.content or ""))
    return questions


def asked(questions, size=EXAM_SIZE):
    """How many of these questions one attempt asks."""
    return size if 0 < size < len(questions) else len(questions)


def build_exam_content(course, questions, lang="en", size=EXAM_SIZE, pass_percent=PASS_PERCENT):
    count = asked(questions, size)
    t = TEXT[lang]
    title = (getattr(course, "title_sw", "") or course.title) if lang == "sw" else course.title
    intro = t["intro"].format(title=title, count=count, pass_=pass_percent)
    return (
        '<div class="lesson-content tone-fun">\n'
        '  <div class="exam-wrap">\n'
        f'    <p><i class="bi bi-mortarboard-fill" aria-hidden="true"></i> {intro}</p>\n'
        f'    <div class="exam-form" data-pass="{pass_percent}">\n'
        '      <div class="exam-progress-wrap">\n'
        '        <div class="exam-progress-track"><div class="exam-progress-bar"></div></div>\n'
        f'        <span class="exam-progress-label">{t["progress"].format(count=count)}</span>\n'
        '      </div>\n'
        f'      <div class="mcq-block">{"".join(questions)}</div>\n'
        '      <div class="exam-submit-row"><button type="button" class="exam-submit-btn btn btn-cloud btn-lg">'
        f'<i class="bi bi-clipboard-check-fill" aria-hidden="true"></i> {t["button"]}</button></div>\n'
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
            duration_minutes=max(10, asked(questions) * 2),
            order=next_order,
            lesson_type=Lesson.LessonType.EXAM,
            pass_score_percent=PASS_PERCENT,
            quiz_size=EXAM_SIZE,
        )
        return exam, "created"
    changed = []
    if exam.order <= (last.order if last else -1):
        exam.order = next_order  # the exam always comes last
        changed.append("order")
    if refresh and questions:
        if exam.quiz_size == 0 and len(questions) > EXAM_SIZE:
            exam.quiz_size = EXAM_SIZE  # a pool this big is dealt as a random set each attempt
            changed.append("quiz_size")
        exam.content = build_exam_content(course, questions, size=exam.quiz_size, pass_percent=exam.pass_score_percent)
        exam.duration_minutes = max(10, asked(questions, exam.quiz_size) * 2)
        changed += ["content", "duration_minutes"]
        sw_questions = []
        for lesson in course.lessons.filter(lesson_type=Lesson.LessonType.LESSON).order_by("order"):
            sw_questions.extend(QUESTION.findall(lesson.content_sw or "")) if lesson.content_sw else None
        if exam.content_sw and len(sw_questions) == len(questions):
            exam.content_sw = build_exam_content(course, sw_questions, "sw", size=exam.quiz_size, pass_percent=exam.pass_score_percent)
            changed.append("content_sw")
        elif exam.content_sw:
            exam.content_sw = ""  # the old Swahili exam no longer matches the English questions
            changed.append("content_sw")
    if changed:
        exam.save(update_fields=changed)
    return exam, "refreshed" if "content" in changed else "kept"
