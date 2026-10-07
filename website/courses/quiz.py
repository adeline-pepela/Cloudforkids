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
MARK = "<!--quiz-questions-->"


def _shuffle_options(body):
    """The lessons list the right answer first, so show the options in a random order on every attempt.
    Each button keeps its original data-index, which is what the browser sends back."""

    def mix(match):
        buttons = BUTTON.findall(match.group(2))
        random.shuffle(buttons)
        return match.group(1) + "".join(buttons) + match.group(3)

    return OPTIONS.sub(mix, body, count=1)


def public_html(content, qids=None):
    """The lesson HTML that is safe to send to the browser: no answers, no explanations.

    Only the questions in `qids` are shown (all of them when it is None), in that order, each tagged with its
    `data-qid` (its position in the lesson), and with the answer options in a random order."""
    picked, seen = {}, []

    def clean(match):
        qid = len(seen)
        seen.append(qid)
        if qids is not None and qid not in qids:
            return ""
        attrs = CORRECT.sub("", match.group("attrs"))
        picked[qid] = f'<div class="mcq-question"{attrs} data-qid="{qid}">{_shuffle_options(match.group("body"))}</div>'
        return MARK if len(picked) == 1 else ""

    html = QUESTION.sub(clean, content or "")
    order = list(qids) if qids is not None else sorted(picked)
    return html.replace(MARK, "".join(picked[q] for q in order if q in picked))


def quiz_question_count(lesson):
    """Number of multiple-choice questions written into a lesson (or exam): the size of its question pool."""
    return len(parse_questions(lesson.content))


def questions_per_attempt(lesson, pool):
    """How many questions one attempt asks. A lesson can hold a bigger pool and ask only some of it each time."""
    size = 0 if lesson.is_exam else lesson.quiz_size
    return size if 0 < size < pool else pool


def quiz_status(user, lesson):
    """(total_questions, passed, best_score_percent) for this learner and lesson."""
    pool = quiz_question_count(lesson)
    if not pool:
        return 0, True, None
    total = questions_per_attempt(lesson, pool)
    result = QuizResult.objects.filter(learner=user, lesson=lesson).first()
    return total, bool(result and result.passed), (result.score_percent if result else None)


# ---- per-attempt questions and answers, kept in the learner's session (never trusted from the browser) ----

def _key(lesson):
    return f"quiz-{lesson.pk}"


def new_attempt(request, lesson):
    """Start a fresh attempt: pick the questions and shuffle their order, avoiding the previous attempt's
    questions and order where there is a choice. Returns the question ids (positions in the lesson) to show."""
    pool = len(parse_questions(lesson.display_content))
    size = questions_per_attempt(lesson, pool)
    previous = (request.session.get(_key(lesson)) or {}).get("qids", [])
    fresh = [q for q in range(pool) if q not in previous]
    random.shuffle(fresh)
    qids = fresh[:size]
    if len(qids) < size:
        repeats = [q for q in range(pool) if q in previous]
        random.shuffle(repeats)
        qids += repeats[: size - len(qids)]
    for _ in range(5):
        random.shuffle(qids)
        if len(qids) < 2 or qids != previous:
            break
    request.session[_key(lesson)] = {"qids": qids, "answers": {}}
    return qids


def attempt(request, lesson):
    """The current attempt ({'qids': [...], 'answers': {qid: choice}}), or None if the page has not started one."""
    return request.session.get(_key(lesson))


def end_attempt(request, lesson):
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
