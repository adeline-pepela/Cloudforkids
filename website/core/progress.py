"""Admin learner progress: a searchable list of every learner and a full report for each one."""

import csv
from collections import defaultdict
from datetime import timedelta

from django.contrib import admin
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.utils import timezone

from accounts.models import ClassMembership, Classroom, ParentLink, User
from courses.models import Course, Enrollment, LearnerBadge, Lesson, LessonCompletion, QuizResult, Tier
from dashboard.labs import XP_PER_LAB, XP_PER_LESSON, XP_PER_LIVE_CLASS, XP_PER_LEVEL, LEVEL_NAMES
from dashboard.models import Lab, LabCompletion
from dashboard.stats import streak_from_days

PAGE_SIZE = 25
IDLE_DAYS = 14
SORTS = {
    "name": ("first_name", "last_name"),
    "-lessons": ("-lessons_done", "first_name"),
    "lessons": ("lessons_done", "first_name"),
    "-joined": ("-date_joined",),
    "joined": ("date_joined",),
    "-login": ("-last_login",),
}


def _activity_by_learner(ids):
    """{learner id: sorted list of datetimes} for lessons, labs and live classes."""
    from live.models import LiveAttendance

    events = defaultdict(list)
    for uid, when in LessonCompletion.objects.filter(enrollment__learner_id__in=ids).values_list("enrollment__learner_id", "completed_at"):
        events[uid].append(when)
    for uid, when in LabCompletion.objects.filter(learner_id__in=ids).values_list("learner_id", "completed_at"):
        events[uid].append(when)
    for uid, when in LiveAttendance.objects.filter(user_id__in=ids, is_host=False, removed=False).values_list("user_id", "first_joined_at"):
        events[uid].append(when)
    return events


def _last_seen(user, events):
    """Latest sign of life: finishing something, or signing in."""
    times = list(events)
    if user.last_login:
        times.append(user.last_login)
    return max(times) if times else None


def _learners(request):
    qs = User.objects.filter(role=User.Role.LEARNER).select_related("learner_profile", "learner_profile__tier")
    g = request.GET
    q = g.get("q", "").strip()
    if q:
        qs = qs.filter(
            Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(username__icontains=q) | Q(email__icontains=q)
            | Q(learner_profile__school_name__icontains=q) | Q(learner_profile__parent_guardian_name__icontains=q)
        )
    if g.get("tier", "").isdigit():
        qs = qs.filter(learner_profile__tier_id=int(g["tier"]))
    if g.get("classroom", "").isdigit():
        qs = qs.filter(id__in=ClassMembership.objects.filter(classroom_id=int(g["classroom"])).values("learner_id"))
    if g.get("course", "").isdigit():
        qs = qs.filter(id__in=Enrollment.objects.filter(course_id=int(g["course"])).values("learner_id"))
    cutoff = timezone.now() - timedelta(days=IDLE_DAYS)
    recent = Q(last_login__gte=cutoff) | Q(id__in=LessonCompletion.objects.filter(completed_at__gte=cutoff).values("enrollment__learner_id")) \
        | Q(id__in=LabCompletion.objects.filter(completed_at__gte=cutoff).values("learner_id"))
    status = g.get("status", "")
    if status == "idle":
        qs = qs.exclude(recent)
    elif status == "active":
        qs = qs.filter(recent)
    elif status == "not_started":
        qs = qs.exclude(id__in=LessonCompletion.objects.values("enrollment__learner_id"))
    elif status == "finished":
        qs = qs.filter(id__in=LessonCompletion.objects.filter(lesson__lesson_type=Lesson.LessonType.EXAM).values("enrollment__learner_id"))
    qs = qs.annotate(lessons_done=Count("enrollments__completions", distinct=True), n_courses=Count("enrollments", distinct=True))
    sort = g.get("sort", "name")
    return qs.order_by(*SORTS.get(sort, SORTS["name"]), "id"), sort


def _row(user, events, lesson_totals, enrolled):
    total = sum(lesson_totals.get(cid, 0) for cid in enrolled.get(user.pk, []))
    days = {w.date() for w in events}
    seen = _last_seen(user, events)
    return {
        "user": user,
        "profile": getattr(user, "learner_profile", None),
        "done": user.lessons_done,
        "total": total,
        "percent": round(user.lessons_done / total * 100) if total else 0,
        "courses": user.n_courses,
        "active_days": len(days),
        "streak": streak_from_days(days),
        "last_seen": seen,
        "idle": seen is None or seen < timezone.now() - timedelta(days=IDLE_DAYS),
    }


def _rows(users):
    users = list(users)
    ids = [u.pk for u in users]
    events = _activity_by_learner(ids)
    lesson_totals = dict(Lesson.objects.values_list("course_id").annotate(n=Count("id")))
    enrolled = defaultdict(list)
    for uid, cid in Enrollment.objects.filter(learner_id__in=ids).values_list("learner_id", "course_id"):
        enrolled[uid].append(cid)
    return [_row(u, events.get(u.pk, []), lesson_totals, enrolled) for u in users]


def learner_list(request):
    qs, sort = _learners(request)
    if request.GET.get("format") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="learner-progress.csv"'
        w = csv.writer(response)
        w.writerow(["Name", "Username", "Grade", "School", "County", "Tier", "Joined", "Courses", "Lessons done", "Lessons total", "Progress %", "Days active", "Streak", "Last seen"])
        for r in _rows(qs[:5000]):
            u, p = r["user"], r["profile"]
            w.writerow([u.get_full_name() or u.username, u.username, p.grade if p else "", p.school_name if p else "", p.county if p else "",
                        p.tier.name if p and p.tier else "", f"{u.date_joined:%Y-%m-%d}", r["courses"], r["done"], r["total"], r["percent"],
                        r["active_days"], r["streak"], f"{r['last_seen']:%Y-%m-%d}" if r["last_seen"] else ""])
        return response
    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get("page"))
    rows = _rows(page.object_list)
    params = request.GET.copy()
    params.pop("page", None)
    context = {
        **admin.site.each_context(request), "title": "Learner progress", "rows": rows, "page": page, "sort": sort,
        "total": page.paginator.count, "query": params.urlencode(), "g": request.GET,
        "tiers": Tier.objects.all(), "courses": Course.objects.all(), "classrooms": Classroom.objects.filter(archived=False),
        "idle_days": IDLE_DAYS,
    }
    return render(request, "admin/learner_list.html", context)


# ---------------------------------------------------------------- one learner

def build_learner_report(user):
    profile = getattr(user, "learner_profile", None)
    completions = LessonCompletion.objects.filter(enrollment__learner=user).select_related("lesson", "enrollment")
    done_at = {c.lesson_id: c for c in completions}
    quizzes = {q.lesson_id: q for q in QuizResult.objects.filter(learner=user)}

    courses = []
    for enrollment in Enrollment.objects.filter(learner=user).select_related("course", "course__tier"):
        lessons = list(enrollment.course.lessons.all())
        rows, next_up = [], None
        for lesson in lessons:
            c, quiz = done_at.get(lesson.pk), quizzes.get(lesson.pk)
            if c is None and next_up is None:
                next_up = lesson
            rows.append({"lesson": lesson, "done_at": c.completed_at if c else None, "score": c.score_percent if c else None,
                         "best": quiz.score_percent if quiz else None, "passed": quiz.passed if quiz else None})
        finished = sum(1 for r in rows if r["done_at"])
        courses.append({
            "enrollment": enrollment, "course": enrollment.course, "rows": rows, "done": finished, "total": len(rows),
            "percent": round(finished / len(rows) * 100) if rows else 0, "next": next_up,
            "complete": enrollment.is_complete,
            "started": min((r["done_at"] for r in rows if r["done_at"]), default=None),
            "last": max((r["done_at"] for r in rows if r["done_at"]), default=None),
        })

    from live.models import LiveAttendance

    live = list(LiveAttendance.objects.filter(user=user, is_host=False, removed=False).select_related("session").order_by("-first_joined_at"))
    lab_done = {lc.slug: lc.completed_at for lc in LabCompletion.objects.filter(learner=user)}
    labs = [{"lab": lab, "done_at": lab_done.get(lab.slug)} for lab in Lab.objects.filter(published=True)]

    stamps = [c.completed_at for c in completions] + list(lab_done.values()) + [a.first_joined_at for a in live]
    days = {s.date() for s in stamps}
    today = timezone.now().date()
    month_ago = today - timedelta(days=29)
    per_day = defaultdict(int)
    for s in stamps:
        per_day[s.date()] += 1
    chart = [{"label": (month_ago + timedelta(days=i)).strftime("%d %b"), "value": per_day.get(month_ago + timedelta(days=i), 0)} for i in range(30)]
    by_month = defaultdict(int)
    for s in stamps:
        by_month[s.strftime("%Y-%m")] += 1

    lessons_done, labs_done, live_done = len(done_at), len(lab_done), len(live)
    xp = lessons_done * XP_PER_LESSON + labs_done * XP_PER_LAB + live_done * XP_PER_LIVE_CLASS
    level = xp // XP_PER_LEVEL + 1
    scores = [q.score_percent for q in quizzes.values()]
    total = sum(c["total"] for c in courses)
    seen = _last_seen(user, stamps)

    # Which weekdays they learn on, and how their completed lessons have grown over the last 90 days.
    weekdays = [0] * 7
    for s in stamps:
        weekdays[s.weekday()] += 1
    span = 90
    growth_start = today - timedelta(days=span - 1)
    lesson_days = sorted(c.completed_at.date() for c in completions)
    before = sum(1 for d in lesson_days if d < growth_start)
    lesson_per_day = defaultdict(int)
    for d in lesson_days:
        if d >= growth_start:
            lesson_per_day[d] += 1
    growth, running = [], before
    for i in range(span):
        day = growth_start + timedelta(days=i)
        running += lesson_per_day.get(day, 0)
        growth.append({"label": day.strftime("%d %b"), "value": running})

    # Strong and weak areas, from quiz and exam scores.
    results = list(QuizResult.objects.filter(learner=user).select_related("lesson", "lesson__course"))
    by_course = defaultdict(list)
    for q in results:
        by_course[q.lesson.course].append(q.score_percent)
    course_scores = sorted(({"course": c, "avg": round(sum(v) / len(v)), "n": len(v)} for c, v in by_course.items()), key=lambda r: -r["avg"])
    strong = sorted((q for q in results if q.passed and q.score_percent >= 85), key=lambda q: -q.score_percent)[:6]
    weak = sorted((q for q in results if not q.passed or q.score_percent < max(q.lesson.pass_score_percent, 70)), key=lambda q: q.score_percent)[:6]
    stuck = [q for q in weak if q.lesson_id not in done_at]
    names = ["Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays", "Sundays"]
    insights = []
    if course_scores:
        insights.append(f"Strongest course: {course_scores[0]['course'].title} ({course_scores[0]['avg']}% average).")
        if len(course_scores) > 1 and course_scores[-1]["avg"] < course_scores[0]["avg"]:
            insights.append(f"Needs most help in: {course_scores[-1]['course'].title} ({course_scores[-1]['avg']}% average).")
    if stuck:
        insights.append(f"Stuck on {len(stuck)} lesson{'s' if len(stuck) != 1 else ''}: tried the quiz but has not passed yet ({stuck[0].lesson.title}).")
    if stamps:
        insights.append(f"Learns most on {names[weekdays.index(max(weekdays))]}.")
    in_progress = [c for c in courses if c["next"] and c["done"]]
    if in_progress:
        insights.append(f"Currently working on {in_progress[0]['course'].title}: next is {in_progress[0]['next'].title}.")
    if not stamps:
        insights.append("Has not finished any lesson, lab or live class yet.")
    return {
        "user": user, "profile": profile, "courses": courses,
        "labs": labs, "live": live, "labs_done": labs_done, "live_done": live_done, "live_minutes": round(sum(a.seconds for a in live) / 60),
        "badges": LearnerBadge.objects.filter(learner=user).select_related("badge"),
        "classes": ClassMembership.objects.filter(learner=user).select_related("classroom", "classroom__facilitator"),
        "parents": ParentLink.objects.filter(child=user).select_related("parent"),
        "consent": getattr(user, "consent", None),
        "lessons_done": lessons_done, "lessons_total": total, "percent": round(lessons_done / total * 100) if total else 0,
        "courses_finished": sum(1 for c in courses if c["complete"]),
        "active_days": len(days), "activities": len(stamps), "streak": streak_from_days(days),
        "first_activity": min(stamps) if stamps else None, "last_seen": seen,
        "idle": seen is None or seen < timezone.now() - timedelta(days=IDLE_DAYS),
        "quiz_count": len(quizzes), "quiz_passed": sum(1 for q in quizzes.values() if q.passed),
        "quiz_avg": round(sum(scores) / len(scores)) if scores else None,
        "xp": xp, "level": level, "level_name": LEVEL_NAMES[min(level - 1, len(LEVEL_NAMES) - 1)],
        "chart": chart, "months": sorted(by_month.items(), reverse=True)[:6],
        "weekdays": [{"label": n[:3], "value": v} for n, v in zip(names, weekdays)], "growth": growth,
        "course_scores": course_scores, "strong": strong, "weak": weak, "stuck": stuck, "insights": insights,
        "recent": sorted(((c.completed_at, c.lesson, c.score_percent) for c in completions), key=lambda t: t[0], reverse=True)[:8],
        "generated": timezone.now(),
    }


def learner_detail(request, pk):
    user = User.objects.filter(pk=pk, role=User.Role.LEARNER).select_related("learner_profile", "learner_profile__tier").first()
    if user is None:
        raise Http404("No such learner")
    report = build_learner_report(user)
    if request.GET.get("format") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="progress-{user.username}.csv"'
        w = csv.writer(response)
        p = report["profile"]
        w.writerow(["Cloud for Kids learner report", f"{report['generated']:%Y-%m-%d}"])
        for label, value in [
            ("Name", user.get_full_name() or user.username), ("Username", user.username), ("Grade", p.grade if p else ""), ("School", p.school_name if p else ""),
            ("Tier", p.tier.name if p and p.tier else ""), ("Joined", f"{user.date_joined:%Y-%m-%d}"),
            ("Last seen", f"{report['last_seen']:%Y-%m-%d}" if report["last_seen"] else "Never"),
            ("Lessons completed", f"{report['lessons_done']} of {report['lessons_total']}"), ("Overall progress %", report["percent"]),
            ("Courses finished", report["courses_finished"]), ("Days active", report["active_days"]), ("Current streak (days)", report["streak"]),
            ("Practice labs done", report["labs_done"]), ("Live classes attended", report["live_done"]),
            ("Average quiz score %", "" if report["quiz_avg"] is None else report["quiz_avg"]), ("Badges", report["badges"].count()),
        ]:
            w.writerow([label, value])
        w.writerow([])
        w.writerow(["Course", "Lesson", "Type", "Completed", "Score %", "Best quiz %", "Passed"])
        for c in report["courses"]:
            for r in c["rows"]:
                w.writerow([c["course"].title, r["lesson"].title, r["lesson"].get_lesson_type_display(), f"{r['done_at']:%Y-%m-%d}" if r["done_at"] else "Not yet",
                            "" if r["score"] is None else r["score"], "" if r["best"] is None else r["best"], "" if r["passed"] is None else ("Yes" if r["passed"] else "No")])
        return response
    context = {**admin.site.each_context(request), "title": f"Progress: {user.get_full_name() or user.username}", "r": report, "idle_days": IDLE_DAYS,
               "print": request.GET.get("print") == "1"}
    return render(request, "admin/learner_detail.html", context)
