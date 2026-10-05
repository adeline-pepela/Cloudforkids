"""Everything the parent portal shows about a child: journey 0-100%, strengths, weak points, activity."""

from collections import Counter
from datetime import timedelta

from django.utils import timezone

from courses.tiers import suggested_tier
from courses.models import Badge, Enrollment, LessonCompletion, QuizResult, Tier

from .labs import get_labs
from .models import LabCompletion
from .stats import learner_stats

STAGES = [
    (0, "Not started yet", "bi-hourglass-top"),
    (1, "Just taking off", "bi-rocket-takeoff-fill"),
    (25, "Getting the hang of it", "bi-lightning-charge-fill"),
    (50, "Halfway there", "bi-signpost-2-fill"),
    (75, "Nearly there", "bi-flag-fill"),
    (100, "Cloud graduate", "bi-mortarboard-fill"),
]
STRONG_SCORE = 80


def _stage(percent):
    label, icon = STAGES[0][1], STAGES[0][2]
    for floor, name, ico in STAGES:
        if percent >= floor:
            label, icon = name, ico
    return label, icon


def _ago(dt, now):
    """'today', 'yesterday', '3 days ago' ..."""
    days = (now.date() - dt.date()).days
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 14:
        return f"{days} days ago"
    return f"{days // 7} weeks ago"


def child_report(child):
    now = timezone.now()
    today = now.date()
    profile = getattr(child, "learner_profile", None)
    tier = profile.tier if profile and profile.tier_id else suggested_tier(profile)
    courses = list(tier.courses.prefetch_related("lessons")) if tier else []

    enrollments = {e.course_id: e for e in Enrollment.objects.filter(learner=child)}
    completions = list(LessonCompletion.objects.filter(enrollment__learner=child).select_related("lesson", "enrollment"))
    done_ids = {c.lesson_id for c in completions}
    quizzes = {q.lesson_id: q for q in QuizResult.objects.filter(learner=child).select_related("lesson__course")}
    lab_rows = list(LabCompletion.objects.filter(learner=child))
    lab_done = {row.slug for row in lab_rows}

    # ---- the journey: course by course ----
    course_rows, total_lessons, total_done, current_set = [], 0, 0, False
    for course in courses:
        lessons = list(course.lessons.all())
        done = sum(1 for lesson in lessons if lesson.id in done_ids)
        scores = [quizzes[l.id].score_percent for l in lessons if l.id in quizzes]
        percent = round(done / len(lessons) * 100) if lessons else 0
        if percent >= 100:
            status = "done"
        elif not current_set:
            status, current_set = "current", True
        else:
            status = "todo"
        course_rows.append({
            "course": course,
            "percent": percent,
            "done": done,
            "total": len(lessons),
            "status": status,
            "started": course.id in enrollments,
            "avg_score": round(sum(scores) / len(scores)) if scores else None,
            "lessons": [
                {
                    "title": l.title,
                    "is_exam": l.is_exam,
                    "done": l.id in done_ids,
                    "score": quizzes[l.id].score_percent if l.id in quizzes else None,
                    "passed": quizzes[l.id].passed if l.id in quizzes else None,
                }
                for l in lessons
            ],
        })
        total_lessons += len(lessons)
        total_done += done
    percent = round(total_done / total_lessons * 100) if total_lessons else 0
    stage, stage_icon = _stage(percent)

    # ---- strengths and weak points, from quiz results ----
    tier_lesson_ids = {l.id for course in courses for l in course.lessons.all()}
    tier_quizzes = [q for q in quizzes.values() if q.lesson_id in tier_lesson_ids]
    strengths = sorted((q for q in tier_quizzes if q.passed and q.score_percent >= STRONG_SCORE),
                       key=lambda q: -q.score_percent)[:4]
    weak = sorted((q for q in tier_quizzes if not q.passed), key=lambda q: q.score_percent)[:4]
    scores = [q.score_percent for q in tier_quizzes]
    avg_score = round(sum(scores) / len(scores)) if scores else None
    all_labs = get_labs()
    labs = [dict(lab, done=lab["slug"] in lab_done) for lab in all_labs]
    labs_todo = [lab for lab in labs if not lab["done"]]

    # ---- activity: last 14 days ----
    counts = Counter(c.completed_at.date() for c in completions)
    counts.update(row.completed_at.date() for row in lab_rows)
    series = []
    for offset in range(13, -1, -1):
        day = today - timedelta(days=offset)
        series.append({"date": day, "label": day.strftime("%a")[0], "count": counts.get(day, 0), "today": offset == 0})
    peak = max([d["count"] for d in series] + [1])
    for d in series:
        d["height"] = max(8, round(d["count"] / peak * 100)) if d["count"] else 0
    this_week = sum(d["count"] for d in series[7:])
    last_week = sum(d["count"] for d in series[:7])
    active_days_week = sum(1 for d in series[7:] if d["count"])

    stamps = [c.completed_at for c in completions] + [row.completed_at for row in lab_rows] + [q.updated_at for q in quizzes.values()]
    last_active = max(stamps) if stamps else None
    idle_days = (today - last_active.date()).days if last_active else None

    minutes = sum(c.lesson.duration_minutes for c in completions) + sum(
        lab["minutes"] for lab in all_labs if lab["slug"] in lab_done
    )

    stats = learner_stats(child)

    # ---- overall health ----
    if not stamps:
        health = ("new", "Not started yet", "bi-hourglass-top")
    elif percent >= 100:
        health = ("great", "Completed the programme", "bi-mortarboard-fill")
    elif idle_days is not None and idle_days >= 4:
        health = ("nudge", "Needs a nudge", "bi-bell-fill")
    else:
        health = ("good", "On track", "bi-check-circle-fill")

    name = child.first_name or child.username
    insights = []
    if not stamps:
        insights.append(("sky", "bi-flag-fill", f"{name} hasn't finished a lesson yet. Sit together for the first 10 minutes. A good start makes all the difference."))
    else:
        if idle_days is not None and idle_days >= 4:
            insights.append(("sun", "bi-bell-fill", f"{name} has been away for {idle_days} days. A short, friendly nudge can get the streak going again."))
        if stats["streak"] >= 3:
            insights.append(("grass", "bi-fire", f"{name} is on a {stats['streak']}-day learning streak. Worth celebrating."))
        if avg_score is not None and avg_score >= STRONG_SCORE:
            insights.append(("grass", "bi-stars", f"Quiz average is {avg_score}%. {name} is understanding the lessons well."))
        elif avg_score is not None and avg_score < 60:
            insights.append(("coral", "bi-life-preserver", f"Quiz average is {avg_score}%. Re-reading the lesson together before the quiz will help."))
        if weak:
            insights.append(("coral", "bi-exclamation-triangle-fill", f"{name} hasn't passed \"{weak[0].lesson.title}\" yet. Ask {name} to explain it to you in their own words."))
        if this_week > last_week and last_week:
            insights.append(("grass", "bi-graph-up-arrow", f"More active than last week ({this_week} things finished versus {last_week})."))
        if labs_todo and len(lab_done) == 0:
            insights.append(("sky", "bi-joystick", "No Practice Labs tried yet. They are short, hands-on and a fun way to learn."))

    tips = ["Ask them to show you what they learned today. Teaching you is the best revision."]
    if health[0] == "nudge" or health[0] == "new":
        tips.append("Agree on a regular time, like 20 minutes after homework, so learning becomes a habit.")
    if weak:
        tips.append("Use the quiz retry button together and talk through the answer they got wrong.")
    if labs_todo:
        tips.append(f"Try the \"{labs_todo[0]['title']}\" Practice Lab together. It only takes {labs_todo[0]['minutes']} minutes.")
    tips.append("Praise effort, not only scores. Streaks and badges show effort.")

    earned = list(child.badges.select_related("badge")[:8])

    return {
        "child": child,
        "profile": profile,
        "tier": tier,
        "name": name,
        "percent": percent,
        "stage": stage,
        "stage_icon": stage_icon,
        "markers": [{"at": f, "label": n} for f, n, _ in STAGES[1:]],
        "courses": course_rows,
        "lessons_done": total_done,
        "lessons_total": total_lessons,
        "lessons_remaining": total_lessons - total_done,
        "strong_score": STRONG_SCORE,
        "strengths": strengths,
        "weak": weak,
        "avg_score": avg_score,
        "labs": labs,
        "labs_done": len(lab_done & {l["slug"] for l in all_labs}),
        "labs_todo": labs_todo,
        "series": series,
        "this_week": this_week,
        "last_week": last_week,
        "active_days_week": active_days_week,
        "last_active": last_active,
        "last_active_text": _ago(last_active, now) if last_active else "never",
        "minutes": minutes,
        "stats": stats,
        "health": health,
        "insights": insights,
        "tips": tips[:4],
        "badges": earned,
        "badge_total": child.badges.count(),
        "badges_available": Badge.objects.count(),
    }
