"""Quizzes and module exams, graded on the server.

A lesson's quiz questions live in its HTML (Lesson.content) as `mcq-question` blocks. The correct answer
(`data-correct`) and the explanation (`mcq-explain`) are stripped before the page is sent, so the browser never
holds the answer key. The browser asks the server to check each answer (or submit the whole exam) instead.
"""

import random
import re

from .models import QuizResult

QUESTION = re.compile(
    r'<div class="mcq-question"(?P<attrs>[^>]*)>(?P<body>.*?)<div class="mcq-explain">(?P<explain>.*?)</div></div>', re.S
)
CORRECT = re.compile(r'\s*data-correct="(\d+)"')
EXPLAIN_BLOCK = re.compile(r'<div class="mcq-explain">.*?</div>', re.S)


def parse_questions(content):
    """[{'correct': int, 'explain': html}] for every question, in page order."""
    questions = []
    for match in QUESTION.finditer(content or ""):
        found = CORRECT.search(match.group("attrs"))
        questions.append({"correct": int(found.group(1)) if found else 0, "explain": match.group("explain")})
    return questions


OPTIONS = re.compile(r'(<div class="mcq-options">)(.*?)(</div>)', re.S)
BUTTON = re.compile(r"<button.*?</button>", re.S)


def _shuffle_options(body):
    """The lessons list the right answer first, so show the options in a random order on every page load.
    Each button keeps its original data-index, which is what the browser sends back."""

    def mix(match):
        buttons = BUTTON.findall(match.group(2))
        random.shuffle(buttons)
        return match.group(1) + "".join(buttons) + match.group(3)

    return OPTIONS.sub(mix, body, count=1)


def public_html(content, shuffle=True):
    """The lesson HTML that is safe to send to the browser: no answers, no explanations, options in random order."""

    def clean(match):
        attrs = CORRECT.sub("", match.group("attrs"))
        body = _shuffle_options(match.group("body")) if shuffle else match.group("body")
        return f'<div class="mcq-question"{attrs}>{body}</div>'

    return QUESTION.sub(clean, content or "")


def quiz_question_count(lesson):
    """Number of graded multiple-choice questions in a lesson (or exam)."""
    return len(parse_questions(lesson.content))


def quiz_status(user, lesson):
    """(total_questions, passed, best_score_percent) for this learner and lesson."""
    total = quiz_question_count(lesson)
    if not total:
        return 0, True, None
    result = QuizResult.objects.filter(learner=user, lesson=lesson).first()
    return total, bool(result and result.passed), (result.score_percent if result else None)


# ---- per-attempt answers, kept in the learner's session (never trusted from the browser) ----

def _key(lesson):
    return f"quiz-{lesson.pk}"


def attempt(request, lesson):
    return request.session.setdefault(_key(lesson), {})


def reset_attempt(request, lesson):
    request.session.pop(_key(lesson), None)


def record_result(user, lesson, correct, total):
    """Save the best score for a finished attempt; returns (percent, passed_now, unlocked)."""
    percent = round(correct / total * 100) if total else 0
    passed = percent >= lesson.pass_score_percent
    result, _ = QuizResult.objects.get_or_create(learner=user, lesson=lesson)
    if percent >= result.score_percent:
        result.score_percent = percent
    result.passed = result.passed or passed  # never un-pass a lesson the learner already passed
    result.save()
    return percent, passed, result.passed
