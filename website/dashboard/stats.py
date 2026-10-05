"""Numbers shown on the learner dashboard: streak, XP, level, daily goal."""

from datetime import timedelta

from django.utils import timezone

from courses.models import LessonCompletion

from .labs import LEVEL_NAMES, lab_count, XP_PER_LAB, XP_PER_LESSON, XP_PER_LEVEL
from .models import LabCompletion


def activity_days(user):
    """Set of dates on which the learner finished a lesson or a lab."""
    lessons = LessonCompletion.objects.filter(enrollment__learner=user).values_list("completed_at", flat=True)
    labs = LabCompletion.objects.filter(learner=user).values_list("completed_at", flat=True)
    return {dt.date() for dt in list(lessons) + list(labs)}


def streak_from_days(days):
    """Consecutive active days ending today (or yesterday, so the streak isn't lost until a day is missed)."""
    day = timezone.now().date()
    if day not in days:
        day -= timedelta(days=1)
    streak = 0
    while day in days:
        streak += 1
        day -= timedelta(days=1)
    return streak


def learning_streak(user):
    return streak_from_days(activity_days(user))


def learner_stats(user):
    days = activity_days(user)
    today = timezone.now().date()
    lessons_done = LessonCompletion.objects.filter(enrollment__learner=user).count()
    labs_done = LabCompletion.objects.filter(learner=user).count()
    xp = lessons_done * XP_PER_LESSON + labs_done * XP_PER_LAB
    level = xp // XP_PER_LEVEL + 1
    week = []
    for offset in range(6, -1, -1):
        d = today - timedelta(days=offset)
        week.append({"label": d.strftime("%a")[0], "active": d in days, "today": offset == 0})
    return {
        "streak": streak_from_days(days),
        "week": week,
        "lessons_done": lessons_done,
        "labs_done": labs_done,
        "labs_total": lab_count(),
        "xp": xp,
        "level": level,
        "level_name": LEVEL_NAMES[min(level - 1, len(LEVEL_NAMES) - 1)],
        "xp_in_level": xp % XP_PER_LEVEL,
        "xp_per_level": XP_PER_LEVEL,
        "goal_done": today in days,
    }
