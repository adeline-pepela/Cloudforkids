"""Admin learner progress: a searchable list of every learner and a full report for each one."""

import csv
from collections import Counter, defaultdict
from datetime import timedelta

from django.contrib import admin
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Q, Sum
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from accounts.models import ClassMembership, Classroom, ParentLink, User
from courses.models import Course, Enrollment, LearnerBadge, Lesson, LessonCompletion, LessonTime, QuizAttempt, QuizResult, Tier
from courses.quiz import parse_questions
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
    done = getattr(user, "lessons_done", None)
    if done is None:
        done = LessonCompletion.objects.filter(enrollment__learner=user).count()
    return {
        "user": user,
        "profile": getattr(user, "learner_profile", None),
        "done": done,
        "total": total,
        "percent": round(done / total * 100) if total else 0,
        "courses": getattr(user, "n_courses", len(enrolled.get(user.pk, []))),
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
    if request.method == "POST" and request.POST.get("action") == "nudge":
        from django.contrib import messages

        from . import notify

        from django.utils.http import url_has_allowed_host_and_scheme

        ids = [int(i) for i in request.POST.getlist("learner") if i.isdigit()][:100]
        sent = sum(notify.send_manual_nudge(u) for u in User.objects.filter(pk__in=ids, role=User.Role.LEARNER))
        if ids:
            messages.success(request, f"Sent {sent} reminder email{'s' if sent != 1 else ''} for {len(ids)} learner{'s' if len(ids) != 1 else ''}.")
        else:
            messages.warning(request, "Tick at least one learner first.")
        back = request.POST.get("next", "")
        return redirect(back if back and url_has_allowed_host_and_scheme(back, {request.get_host()}) else request.get_full_path())
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
        "idle_days": IDLE_DAYS, "idle_on_page": [r for r in rows if r["idle"]],
    }
    return render(request, "admin/learner_list.html", context)


# ---------------------------------------------------------------- one learner

RUSH_SECONDS = 120   # a lesson finished after less than 2 minutes on the page was probably skimmed
STRONG_SCORE = 85
WEAK_SCORE = 70


def _questions(lesson, cache):
    if lesson.pk not in cache:
        cache[lesson.pk] = parse_questions(lesson.content)
    return cache[lesson.pk]


def attempt_stats(user):
    """Every quiz attempt: per-lesson counts, attempts needed to pass, the questions missed most and the score trend."""
    attempts = list(QuizAttempt.objects.filter(learner=user).select_related("lesson", "lesson__course").order_by("created_at", "id"))
    by_lesson = defaultdict(list)
    for a in attempts:
        by_lesson[a.lesson_id].append(a)
    per_lesson = {}
    for lid, rows in by_lesson.items():
        per_lesson[lid] = {
            "lesson": rows[0].lesson, "count": len(rows), "first": rows[0].score_percent, "last": rows[-1].score_percent,
            "best": max(a.score_percent for a in rows), "to_pass": next((i + 1 for i, a in enumerate(rows) if a.passed), None),
        }
    missed, parsed = Counter(), {}
    for a in attempts:
        for q in a.wrong or []:
            missed[(a.lesson_id, q)] += 1
    top_missed = []
    for (lid, q), n in missed.most_common(8):
        lesson = by_lesson[lid][0].lesson
        questions = _questions(lesson, parsed)
        text = questions[q]["text"] if q < len(questions) else ""
        top_missed.append({"lesson": lesson, "number": q + 1, "text": text or f"Question {q + 1}", "times": n, "of": len(by_lesson[lid])})
    trend = [{"label": f"{a.created_at:%d %b}", "value": a.score_percent, "lesson": a.lesson.title} for a in attempts[-30:]]
    return {"per_lesson": per_lesson, "missed": top_missed, "trend": trend, "count": len(attempts),
            "retried": sorted((v for v in per_lesson.values() if v["count"] > 1), key=lambda v: -v["count"])[:8]}


def time_stats(user):
    """Minutes spent with lessons open: total, per lesson and per day for the last 30 days."""
    today = timezone.localdate()
    per_lesson, per_day = defaultdict(int), defaultdict(int)
    for lid, day, seconds in LessonTime.objects.filter(learner=user).values_list("lesson_id", "day", "seconds"):
        per_lesson[lid] += seconds
        per_day[day] += seconds
    start = today - timedelta(days=29)
    chart = [{"label": f"{start + timedelta(days=i):%d %b}", "value": round(per_day.get(start + timedelta(days=i), 0) / 60)} for i in range(30)]
    total = sum(per_lesson.values())
    week = sum(v for d, v in per_day.items() if d > today - timedelta(days=7))
    return {"per_lesson": per_lesson, "chart": chart, "minutes": round(total / 60), "week_minutes": round(week / 60), "tracked": bool(total)}


def recommendations(user, limit=5):
    """Concrete next steps from the learner's results: redo failed quizzes, re-read weak lessons, carry on, try a lab.
    Each step is {icon, tone, url, text, kind, title}; `kind` and `title` let emails word them in Kiswahili."""
    from django.urls import reverse

    from courses.tiers import suggested_tier
    from dashboard.labs import get_labs

    steps = []
    results = list(QuizResult.objects.filter(learner=user).select_related("lesson", "lesson__course"))
    done = set(LessonCompletion.objects.filter(enrollment__learner=user).values_list("lesson_id", flat=True))
    missed = Counter()
    for lid, wrong in QuizAttempt.objects.filter(learner=user).values_list("lesson_id", "wrong"):
        missed[lid] += len(wrong or [])
    planned = set()
    for q in sorted((q for q in results if not q.passed), key=lambda q: q.score_percent)[:3]:
        extra = f", {missed[q.lesson_id]} wrong answers so far" if missed[q.lesson_id] else ""
        planned.add(q.lesson_id)
        steps.append({"kind": "redo", "lesson": q.lesson, "icon": "bi-arrow-repeat", "tone": "coral", "url": q.lesson.get_absolute_url(),
                      "text": f"Redo the quiz in “{q.lesson.title}” (best {q.score_percent}%, needs {q.lesson.pass_score_percent}%{extra})."})
    for q in sorted((q for q in results if q.passed and q.score_percent < WEAK_SCORE), key=lambda q: q.score_percent)[:2]:
        planned.add(q.lesson_id)
        steps.append({"kind": "reread", "lesson": q.lesson, "icon": "bi-book", "tone": "sun", "url": q.lesson.get_absolute_url(),
                      "text": f"Re-read “{q.lesson.title}”: passed with only {q.score_percent}%."})
    enrollments = list(Enrollment.objects.filter(learner=user).select_related("course").order_by("-enrolled_at"))
    for enrollment in enrollments:
        nxt = next((l for l in enrollment.course.lessons.all() if l.pk not in done), None)
        if nxt and nxt.pk not in planned:
            steps.append({"kind": "next", "lesson": nxt, "icon": "bi-play-circle-fill", "tone": "sky", "url": nxt.get_absolute_url(),
                          "text": f"Carry on with {enrollment.course.title}: next is “{nxt.title}”."})
            break
    if not enrollments:
        profile = getattr(user, "learner_profile", None)
        tier = profile.tier if profile and profile.tier_id else suggested_tier(profile)
        first = tier.courses.first() if tier else None
        if first:
            steps.append({"kind": "start", "course": first, "icon": "bi-flag-fill", "tone": "sky", "url": first.get_absolute_url(),
                          "text": f"Start the first course: {first.title}."})
    labs_done = set(LabCompletion.objects.filter(learner=user).values_list("slug", flat=True))
    lab = next((l for l in get_labs() if l["slug"] not in labs_done), None)
    if lab:
        steps.append({"kind": "lab", "lab": lab, "icon": "bi-joystick", "tone": "grass", "url": reverse("dashboard:lab", args=[lab["slug"]]),
                      "text": f"Try the “{lab['title']}” Practice Lab ({lab['minutes']} min) to practise {lab['skill'][:1].lower()}{lab['skill'][1:]}."})
    return steps[:limit]


def learner_numbers(ids):
    """{learner id: {percent, quiz, days, minutes, lessons}} for a set of learners, in a handful of queries."""
    from django.db.models.functions import TruncDate

    lesson_totals = dict(Lesson.objects.values_list("course_id").annotate(n=Count("id")))
    totals, done = defaultdict(int), defaultdict(int)
    for uid, cid in Enrollment.objects.filter(learner_id__in=ids).values_list("learner_id", "course_id"):
        totals[uid] += lesson_totals.get(cid, 0)
    for row in LessonCompletion.objects.filter(enrollment__learner_id__in=ids).values("enrollment__learner_id").annotate(n=Count("id")):
        done[row["enrollment__learner_id"]] = row["n"]
    quiz = {r["learner_id"]: r["avg"] for r in QuizResult.objects.filter(learner_id__in=ids).values("learner_id").annotate(avg=Avg("score_percent"))}
    days = defaultdict(set)
    for uid, d in LessonCompletion.objects.filter(enrollment__learner_id__in=ids).annotate(d=TruncDate("completed_at")).values_list("enrollment__learner_id", "d"):
        days[uid].add(d)
    for uid, d in LabCompletion.objects.filter(learner_id__in=ids).annotate(d=TruncDate("completed_at")).values_list("learner_id", "d"):
        days[uid].add(d)
    secs = {r["learner_id"]: r["s"] for r in LessonTime.objects.filter(learner_id__in=ids).values("learner_id").annotate(s=Sum("seconds"))}
    return {uid: {"percent": round(done[uid] / totals[uid] * 100) if totals[uid] else 0, "quiz": quiz.get(uid), "days": len(days[uid]),
                  "minutes": round((secs.get(uid) or 0) / 60), "lessons": done[uid]} for uid in ids}


def peer_averages(tier):
    """Averages for learners in the same tier, cached for ten minutes."""
    from django.core.cache import cache

    from accounts.models import LearnerProfile

    def compute():
        ids = list(LearnerProfile.objects.filter(tier=tier).values_list("user_id", flat=True))
        if not ids:
            return None
        numbers = list(learner_numbers(ids).values())
        quiz = [n["quiz"] for n in numbers if n["quiz"] is not None]

        def avg(key):
            return round(sum(n[key] for n in numbers) / len(numbers))

        return {"n": len(ids), "percent": avg("percent"), "days": avg("days"), "minutes": avg("minutes"), "lessons": avg("lessons"),
                "quiz": round(sum(quiz) / len(quiz)) if quiz else None}

    return cache.get_or_set(f"c4k-peer-{tier.pk}", compute, 600)


def _compare(report, tier):
    peers = peer_averages(tier) if tier else None
    if not peers:
        return None
    rows = [("Overall progress", report["percent"], peers["percent"], "%"), ("Lessons completed", report["lessons_done"], peers["lessons"], ""),
            ("Days learned", report["active_days"], peers["days"], ""), ("Minutes learning", report["time"]["minutes"], peers["minutes"], " min")]
    if report["quiz_avg"] is not None and peers["quiz"] is not None:
        rows.insert(1, ("Quiz average", report["quiz_avg"], peers["quiz"], "%"))
    if not (report["time"]["minutes"] or peers["minutes"]):
        rows = [row for row in rows if row[0] != "Minutes learning"]  # nobody has timed lessons yet
    out = []
    for label, mine, avg, unit in rows:
        top = max(mine, avg, 1)
        out.append({"label": label, "mine": mine, "avg": avg, "unit": unit, "diff": mine - avg,
                    "width": round(mine / top * 100), "avg_width": round(avg / top * 100)})
    return {"tier": tier, "n": peers["n"], "rows": out}


def build_learner_report(user):
    from live.models import LiveAttendance

    from accounts.models import LearnerNote

    profile = getattr(user, "learner_profile", None)
    completions = list(LessonCompletion.objects.filter(enrollment__learner=user).select_related("lesson", "enrollment"))
    done_at = {c.lesson_id: c for c in completions}
    results = list(QuizResult.objects.filter(learner=user).select_related("lesson", "lesson__course"))
    quizzes = {q.lesson_id: q for q in results}
    tries = attempt_stats(user)
    spent = time_stats(user)

    courses, rushed, long_ones = [], [], []
    for enrollment in Enrollment.objects.filter(learner=user).select_related("course", "course__tier"):
        rows, next_up = [], None
        for lesson in enrollment.course.lessons.all():
            c, quiz = done_at.get(lesson.pk), quizzes.get(lesson.pk)
            if c is None and next_up is None:
                next_up = lesson
            seconds = spent["per_lesson"].get(lesson.pk, 0)
            if c and seconds and seconds < RUSH_SECONDS:
                rushed.append(lesson)
            if seconds > lesson.duration_minutes * 60 * 2:
                long_ones.append(lesson)
            tried = tries["per_lesson"].get(lesson.pk)
            rows.append({"lesson": lesson, "done_at": c.completed_at if c else None, "score": c.score_percent if c else None,
                         "best": quiz.score_percent if quiz else None, "passed": quiz.passed if quiz else None,
                         "attempts": tried["count"] if tried else 0, "to_pass": tried["to_pass"] if tried else None,
                         "minutes": round(seconds / 60) if seconds else None})
        finished = sum(1 for r in rows if r["done_at"])
        courses.append({
            "enrollment": enrollment, "course": enrollment.course, "rows": rows, "done": finished, "total": len(rows),
            "percent": round(finished / len(rows) * 100) if rows else 0, "next": next_up,
            "complete": enrollment.is_complete,
            "started": min((r["done_at"] for r in rows if r["done_at"]), default=None),
            "last": max((r["done_at"] for r in rows if r["done_at"]), default=None),
        })

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
    scores = [q.score_percent for q in results]
    total = sum(c["total"] for c in courses)
    seen = _last_seen(user, stamps)

    # Which weekdays they learn on, and how their completed lessons have grown over the last 90 days.
    weekdays = [0] * 7
    for s in stamps:
        weekdays[s.weekday()] += 1
    span = 90
    growth_start = today - timedelta(days=span - 1)
    lesson_days = sorted(c.completed_at.date() for c in completions)
    lesson_per_day = Counter(d for d in lesson_days if d >= growth_start)
    growth, running = [], sum(1 for d in lesson_days if d < growth_start)
    for i in range(span):
        day = growth_start + timedelta(days=i)
        running += lesson_per_day.get(day, 0)
        growth.append({"label": day.strftime("%d %b"), "value": running})

    # Strong and weak areas, from quiz and exam scores.
    by_course = defaultdict(list)
    for q in results:
        by_course[q.lesson.course].append(q.score_percent)
    course_scores = sorted(({"course": c, "avg": round(sum(v) / len(v)), "n": len(v)} for c, v in by_course.items()), key=lambda r: -r["avg"])
    strong = sorted((q for q in results if q.passed and q.score_percent >= STRONG_SCORE), key=lambda q: -q.score_percent)[:6]
    weak = sorted((q for q in results if not q.passed or q.score_percent < max(q.lesson.pass_score_percent, WEAK_SCORE)), key=lambda q: q.score_percent)[:6]
    stuck = [q for q in weak if q.lesson_id not in done_at]

    names = ["Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays", "Sundays"]
    insights = []
    if course_scores:
        insights.append(f"Strongest course: {course_scores[0]['course'].title} ({course_scores[0]['avg']}% average).")
        if len(course_scores) > 1 and course_scores[-1]["avg"] < course_scores[0]["avg"]:
            insights.append(f"Needs most help in: {course_scores[-1]['course'].title} ({course_scores[-1]['avg']}% average).")
    if stuck:
        insights.append(f"Stuck on {len(stuck)} lesson{'s' if len(stuck) != 1 else ''}: tried the quiz but has not passed yet ({stuck[0].lesson.title}).")
    if tries["retried"]:
        top = tries["retried"][0]
        how = f"passed on try {top['to_pass']}" if top["to_pass"] else "not passed yet"
        insights.append(f"Took {top['count']} tries at “{top['lesson'].title}” ({how}).")
    if tries["missed"]:
        m = tries["missed"][0]
        insights.append(f"Most missed question: “{m['text'][:110]}” ({m['lesson'].title}, wrong {m['times']} time{'s' if m['times'] != 1 else ''}).")
    if rushed:
        insights.append(f"Finished {len(rushed)} lesson{'s' if len(rushed) != 1 else ''} in under 2 minutes, which may mean skimming ({rushed[0].title}).")
    if long_ones:
        insights.append(f"Spent more than twice the expected time on {len(long_ones)} lesson{'s' if len(long_ones) != 1 else ''}, which may mean struggling ({long_ones[0].title}).")
    if spent["tracked"]:
        insights.append(f"{spent['minutes']} minutes learning in total, {spent['week_minutes']} in the last 7 days.")
    if stamps:
        insights.append(f"Learns most on {names[weekdays.index(max(weekdays))]}.")
    in_progress = [c for c in courses if c["next"] and c["done"]]
    if in_progress:
        insights.append(f"Currently working on {in_progress[0]['course'].title}: next is {in_progress[0]['next'].title}.")
    if not stamps:
        insights.append("Has not finished any lesson, lab or live class yet.")

    report = {
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
        "quiz_count": len(results), "quiz_passed": sum(1 for q in results if q.passed),
        "quiz_avg": round(sum(scores) / len(scores)) if scores else None,
        "xp": xp, "level": level, "level_name": LEVEL_NAMES[min(level - 1, len(LEVEL_NAMES) - 1)],
        "chart": chart, "months": sorted(by_month.items(), reverse=True)[:6],
        "weekdays": [{"label": n[:3], "value": v} for n, v in zip(names, weekdays)], "growth": growth,
        "course_scores": course_scores, "strong": strong, "weak": weak, "stuck": stuck, "insights": insights,
        "tries": tries, "time": spent, "rushed": rushed, "long_ones": long_ones,
        "next_steps": recommendations(user),
        "notes": list(LearnerNote.objects.filter(learner=user).select_related("author")),
        "generated": timezone.now(),
    }
    report["compare"] = _compare(report, profile.tier if profile and profile.tier_id else None)
    return report


def _learner_or_404(pk):
    user = User.objects.filter(pk=pk, role=User.Role.LEARNER).select_related("learner_profile", "learner_profile__tier").first()
    if user is None:
        raise Http404("No such learner")
    return user


def _post_action(request, user):
    """The buttons on the report: send a reminder, email the report to the family, add or remove a note."""
    from django.contrib import messages

    from accounts.models import LearnerNote

    from . import notify

    action = request.POST.get("action")
    if action == "nudge":
        n = notify.send_manual_nudge(user)
        if n:
            messages.success(request, f"Reminder sent to {n} {'person' if n == 1 else 'people'}.")
        else:
            messages.warning(request, "Nobody to remind: the learner and their parents have no email address, or they turned reminders off.")
    elif action == "email_report":
        n = notify.send_progress_report(user, build_learner_report(user))
        if n:
            messages.success(request, f"Progress report emailed to {n} parent{'s' if n != 1 else ''}.")
        else:
            messages.warning(request, "No parent email found. Link a parent account or add the guardian's email to the learner profile.")
    elif action == "note":
        body = request.POST.get("body", "").strip()[:2000]
        if body:
            LearnerNote.objects.create(learner=user, author=request.user, body=body)
            messages.success(request, "Note added.")
    elif action == "delete_note":
        LearnerNote.objects.filter(learner=user, pk=request.POST.get("note")).delete()
        messages.success(request, "Note removed.")


def learner_detail(request, pk):
    user = _learner_or_404(pk)
    if request.method == "POST":
        _post_action(request, user)
        return redirect(request.path)
    report = build_learner_report(user)
    fmt = request.GET.get("format")
    if fmt == "pdf":
        from .progress_pdf import learner_pdf

        response = HttpResponse(learner_pdf(report), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="progress-{user.username}.pdf"'
        return response
    if fmt == "csv":
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
            ("Minutes learning", report["time"]["minutes"]), ("Quiz attempts", report["tries"]["count"]),
            ("Practice labs done", report["labs_done"]), ("Live classes attended", report["live_done"]),
            ("Average quiz score %", "" if report["quiz_avg"] is None else report["quiz_avg"]), ("Badges", report["badges"].count()),
        ]:
            w.writerow([label, value])
        w.writerow([])
        w.writerow(["Course", "Lesson", "Type", "Completed", "Score %", "Best quiz %", "Passed", "Attempts", "Minutes"])
        for c in report["courses"]:
            for r in c["rows"]:
                w.writerow([c["course"].title, r["lesson"].title, r["lesson"].get_lesson_type_display(), f"{r['done_at']:%Y-%m-%d}" if r["done_at"] else "Not yet",
                            "" if r["score"] is None else r["score"], "" if r["best"] is None else r["best"],
                            "" if r["passed"] is None else ("Yes" if r["passed"] else "No"), r["attempts"], "" if r["minutes"] is None else r["minutes"]])
        w.writerow([])
        w.writerow(["Next steps"])
        for step in report["next_steps"]:
            w.writerow([step["text"]])
        return response
    context = {**admin.site.each_context(request), "title": f"Progress: {user.get_full_name() or user.username}", "r": report, "idle_days": IDLE_DAYS}
    return render(request, "admin/learner_detail.html", context)
