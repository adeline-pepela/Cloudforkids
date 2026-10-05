"""Quiz gating helpers: how many graded questions a lesson has, and whether the learner passed."""

from .models import QuizResult


def quiz_question_count(lesson):
    """Number of graded multiple-choice questions in a lesson (or exam)."""
    return (lesson.content or "").count('class="mcq-question"')


def quiz_status(user, lesson):
    """(total_questions, passed, best_score_percent) for this learner and lesson."""
    total = quiz_question_count(lesson)
    if not total:
        return 0, True, None
    result = QuizResult.objects.filter(learner=user, lesson=lesson).first()
    return total, bool(result and result.passed), (result.score_percent if result else None)
