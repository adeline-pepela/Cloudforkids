"""Numbers for the facilitator / teacher dashboard: roster, hardest lessons, activity, assignments."""

from collections import Counter, defaultdict
from datetime import timedelta

from django.utils import timezone

from courses.models import Course, Enrollment, Lesson, LessonCompletion, QuizResult
from .models import LabCompletion
from .stats import streak_from_days

IDLE_DAYS = 5
LOW_SCORE = 60


def _ago(dt, today):
    if dt is None:
        return "never"
    days = (today - dt.date()).days
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    return f"{days} days ago" if days < 14 else f"{days // 7} weeks ago"


def class_report(classroom):
    now = timezone.now()
    today = now.date()
    members = [m.learner for m in classroom.memberships.select_related("learner")]
    ids = [u.id for u in members]

    if classroom.tier_id:
        courses = list(Course.objects.filter(tier_id=classroom.tier_id).prefetch_related("lessons"))
    else:
        courses = list(Course.objects.prefetch_related("lessons"))
    lessons = [l for c in courses for l in c.lessons.all()]
    lesson_ids = {l.id for l in lessons}
    total = len(lessons)

    comps = LessonCompletion.objects.filter(enrollment__learner_id__in=ids).select_related("enrollment")
    quizzes = QuizResult.objects.filter(learner_id__in=ids)
    labs = LabCompletion.objects.filter(learner_id__in=ids)

    done_by = defaultdict(set)  # learner -> lesson ids
    dates_by = defaultdict(set)
    last_by = {}
    for c in comps:
        uid = c.enrollment.learner_id
        if c.lesson_id in lesson_ids:
            done_by[uid].add(c.lesson_id)
        dates_by[uid].add(c.completed_at.date())
        last_by[uid] = max(last_by.get(uid, c.completed_at), c.completed_at)
    labs_by = Counter()
    for row in labs:
        labs_by[row.learner_id] += 1
        dates_by[row.learner_id].add(row.completed_at.date())
        last_by[row.learner_id] = max(last_by.get(row.learner_id, row.completed_at), row.completed_at)
    scores_by = defaultdict(list)
    quiz_by_lesson = defaultdict(list)
    for q in quizzes:
        if q.lesson_id in lesson_ids:
            scores_by[q.learner_id].append(q.score_percent)
            quiz_by_lesson[q.lesson_id].append(q)
        last_by[q.learner_id] = max(last_by.get(q.learner_id, q.updated_at), q.updated_at)

    roster = []
    for u in members:
        done = len(done_by[u.id])
        percent = round(done / total * 100) if total else 0
        scores = scores_by[u.id]
        avg = round(sum(scores) / len(scores)) if scores else None
        last = last_by.get(u.id)
        idle = (today - last.date()).days if last else None
        streak = streak_from_days(dates_by[u.id])
        if last is None:
            status, label = "new", "Not started"
        elif percent >= 100:
            status, label = "great", "Finished"
        elif idle is not None and idle >= IDLE_DAYS:
            status, label = "nudge", "Inactive"
        elif avg is not None and avg < LOW_SCORE and len(scores) >= 2:
            status, label = "help", "Needs help"
        else:
            status, label = "good", "On track"
        roster.append({
            "user": u, "name": u.get_full_name() or u.username, "percent": percent, "done": done,
            "avg_score": avg, "streak": streak, "labs": labs_by[u.id], "last": last,
            "last_text": _ago(last, today), "idle": idle, "status": status, "status_label": label,
        })
    roster.sort(key=lambda r: r["name"].lower())

    # ---- lesson funnel and hardest lessons
    funnel, hard = [], []
    n = len(members)
    for course in courses:
        for l in course.lessons.all():
            count = sum(1 for u in members if l.id in done_by[u.id])
            results = quiz_by_lesson.get(l.id, [])
            avg = round(sum(q.score_percent for q in results) / len(results)) if results else None
            failed = sum(1 for q in results if not q.passed)
            funnel.append({
                "lesson": l, "course": course, "done": count,
                "percent": round(count / n * 100) if n else 0, "avg": avg, "attempts": len(results), "failed": failed,
            })
            if results and (avg < 75 or failed):
                hard.append(funnel[-1])
    hard.sort(key=lambda f: (f["avg"], -f["failed"]))

    # ---- class-wide activity, last 14 days
    counts = Counter()
    for uid, days in dates_by.items():
        for d in days:
            counts[d] += 1  # learners active that day
    series = []
    for offset in range(13, -1, -1):
        day = today - timedelta(days=offset)
        series.append({"label": day.strftime("%a")[0], "date": day, "count": counts.get(day, 0), "today": offset == 0})
    peak = max([d["count"] for d in series] + [1])
    for d in series:
        d["height"] = max(8, round(d["count"] / peak * 100)) if d["count"] else 0
    active_week = sum(1 for r in roster if r["idle"] is not None and r["idle"] < 7)

    # ---- assignments
    assignments = []
    for a in classroom.assignments.select_related("course"):
        course_lessons = [l.id for l in a.course.lessons.all()]
        full = 0
        sum_percent = 0
        for u in members:
            enrollment_done = len(set(course_lessons) & done_by[u.id]) if a.course in courses else None
            if enrollment_done is None:
                enrollment_done = LessonCompletion.objects.filter(enrollment__learner=u, lesson_id__in=course_lessons).count()
            pct = round(enrollment_done / len(course_lessons) * 100) if course_lessons else 0
            sum_percent += pct
            if pct >= 100:
                full += 1
        overdue = bool(a.due_date and a.due_date < today)
        assignments.append({
            "a": a, "finished": full, "avg": round(sum_percent / n) if n else 0, "overdue": overdue,
            "days_left": (a.due_date - today).days if a.due_date else None,
        })

    attention = [r for r in roster if r["status"] in ("nudge", "help", "new")]
    avg_progress = round(sum(r["percent"] for r in roster) / n) if n else 0
    scored = [r["avg_score"] for r in roster if r["avg_score"] is not None]
    return {
        "classroom": classroom,
        "roster": roster,
        "count": n,
        "avg_progress": avg_progress,
        "avg_score": round(sum(scored) / len(scored)) if scored else None,
        "active_week": active_week,
        "attention": attention,
        "funnel": funnel,
        "hard": hard[:5],
        "series": series,
        "assignments": assignments,
        "lessons_total": total,
        "courses": courses,
    }


def teacher_tips(report):
    """A few plain suggestions for the facilitator, based on the numbers."""
    tips = []
    if report["attention"]:
        names = ", ".join(r["name"].split()[0] for r in report["attention"][:3])
        tips.append(f"Check in with {names}: they are inactive, stuck or haven't started.")
    if report["hard"]:
        h = report["hard"][0]
        tips.append(f"\"{h['lesson'].title}\" is the hardest topic right now (average {h['avg']}%). Revisit it together in class.")
    if report["count"] and report["active_week"] < report["count"] / 2:
        tips.append("Fewer than half the class studied this week. A short in-class session can restart the habit.")
    if not report["assignments"]:
        tips.append("Set an assignment so the class has a clear goal and a due date.")
    if not tips:
        tips.append("The class is moving well. Celebrate progress and share the next goal.")
    return tips


def teacher_overview(user):
    """Everything on the facilitator home page."""
    classes = list(user.classrooms.filter(archived=False).select_related("tier"))
    reports = [class_report(c) for c in classes]
    learners = sum(r["count"] for r in reports)
    attention = [(r["classroom"], row) for r in reports for row in r["attention"]]
    return {
        "reports": reports,
        "learners": learners,
        "active_week": sum(r["active_week"] for r in reports),
        "attention": attention[:8],
        "attention_total": len(attention),
        "assignments_open": sum(1 for r in reports for a in r["assignments"] if not a["overdue"]),
        "classes": classes,
    }


def learner_in_class(facilitator, learner_id):
    """The classroom (owned by this facilitator) a learner belongs to, or None."""
    from accounts.models import ClassMembership

    m = ClassMembership.objects.filter(classroom__facilitator=facilitator, learner_id=learner_id).select_related("classroom", "learner").first()
    return m
