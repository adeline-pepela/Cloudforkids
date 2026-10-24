"""Admin reports for groups of learners: a class or a school, and the list of learners who may be falling behind."""

import csv
from collections import Counter, defaultdict
from datetime import timedelta

from django.contrib import admin
from django.core.cache import cache
from django.db.models import Avg, Count, Q
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from accounts.models import ClassMembership, Classroom, LearnerProfile, User
from courses.models import Course, Enrollment, LessonCompletion, QuizAttempt, QuizResult

from .progress import IDLE_DAYS, _activity_by_learner, _questions, _rows, learner_numbers

STUCK_TRIES = 3
LOW_AVERAGE = 60


# ---------------------------------------------------------------- class and school reports

def _group(request):
    """(label, learners queryset, classroom or None, school or '') from ?classroom= or ?school=."""
    learners = User.objects.filter(role=User.Role.LEARNER).select_related("learner_profile", "learner_profile__tier")
    cid, school = request.GET.get("classroom", ""), request.GET.get("school", "").strip()
    if cid.isdigit():
        classroom = Classroom.objects.filter(pk=int(cid)).select_related("facilitator").first()
        if classroom:
            ids = ClassMembership.objects.filter(classroom=classroom).values("learner_id")
            return classroom.name, learners.filter(pk__in=ids), classroom, ""
    if school:
        return school, learners.filter(learner_profile__school_name__iexact=school), None, school
    return "", learners.none(), None, ""


def build_group_report(learners):
    users = list(learners)
    ids = [u.pk for u in users]
    rows = _rows(users)
    numbers = learner_numbers(ids)
    for r in rows:
        r.update(quiz=numbers[r["user"].pk]["quiz"], minutes=numbers[r["user"].pk]["minutes"])
    ranking = sorted(rows, key=lambda r: (-r["percent"], -(r["quiz"] or 0), r["user"].first_name.lower()))
    for i, r in enumerate(ranking, start=1):
        r["rank"] = i

    # Each course the group is enrolled in: how far they got, how they scored, how many finished.
    course_rows = []
    lesson_counts = dict(Course.objects.annotate(n=Count("lessons")).values_list("id", "n"))
    enrollments = Enrollment.objects.filter(learner_id__in=ids)
    done = Counter(LessonCompletion.objects.filter(enrollment__learner_id__in=ids).values_list("enrollment_id", flat=True))
    per_course = defaultdict(list)
    for e in enrollments.select_related("course"):
        per_course[e.course].append(e)
    quiz_by_course = {r["lesson__course"]: r for r in QuizResult.objects.filter(learner_id__in=ids).values("lesson__course")
                      .annotate(avg=Avg("score_percent"), fails=Count("id", filter=Q(passed=False)))}
    for course, items in sorted(per_course.items(), key=lambda kv: (kv[0].tier.order, kv[0].order)):
        total = lesson_counts.get(course.pk) or 0
        percents = [round(done[e.pk] / total * 100) if total else 0 for e in items]
        q = quiz_by_course.get(course.pk, {})
        course_rows.append({"course": course, "enrolled": len(items), "avg_percent": round(sum(percents) / len(percents)),
                            "finished": sum(1 for p in percents if p >= 100), "quiz": round(q["avg"]) if q.get("avg") is not None else None,
                            "fails": q.get("fails", 0)})

    # Lessons the group finds hardest, and the questions most of them get wrong.
    hardest = list(QuizResult.objects.filter(learner_id__in=ids).values("lesson", "lesson__title", "lesson__course__title")
                   .annotate(avg=Avg("score_percent"), n=Count("id"), fails=Count("id", filter=Q(passed=False))).order_by("avg")[:8])
    missed, lessons, parsed = Counter(), {}, {}
    for a in QuizAttempt.objects.filter(learner_id__in=ids).select_related("lesson", "lesson__course"):
        lessons[a.lesson_id] = a.lesson
        for q in a.wrong or []:
            missed[(a.lesson_id, q)] += 1
    missed_rows = []
    for (lid, q), n in missed.most_common(8):
        questions = _questions(lessons[lid], parsed)
        missed_rows.append({"lesson": lessons[lid], "text": (questions[q]["text"] if q < len(questions) else "") or f"Question {q + 1}", "times": n})

    events = _activity_by_learner(ids)
    today = timezone.now().date()
    start = today - timedelta(days=29)
    per_day = Counter(w.date() for ev in events.values() for w in ev if w.date() >= start)
    chart = [{"label": f"{start + timedelta(days=i):%d %b}", "value": per_day.get(start + timedelta(days=i), 0)} for i in range(30)]
    quiz = [r["quiz"] for r in rows if r["quiz"] is not None]
    return {
        "n": len(rows), "ranking": ranking, "courses": course_rows, "hardest": hardest, "missed": missed_rows, "chart": chart,
        "avg_percent": round(sum(r["percent"] for r in rows) / len(rows)) if rows else 0,
        "avg_quiz": round(sum(quiz) / len(quiz)) if quiz else None,
        "active": sum(1 for r in rows if not r["idle"]), "minutes": sum(r["minutes"] for r in rows),
        "not_started": sum(1 for r in rows if not r["done"]),
    }


def group_report(request):
    label, learners, classroom, school = _group(request)
    report = build_group_report(learners) if label else None
    if report and request.GET.get("format") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="group-report-{label[:40].replace(" ", "_")}.csv"'
        w = csv.writer(response)
        w.writerow(["Cloud for Kids group report", label, f"{timezone.now():%Y-%m-%d}"])
        w.writerow([])
        w.writerow(["Rank", "Name", "Username", "Progress %", "Lessons done", "Quiz average %", "Days learned", "Minutes", "Last seen"])
        for r in report["ranking"]:
            w.writerow([r["rank"], r["user"].get_full_name() or r["user"].username, r["user"].username, r["percent"], r["done"],
                        "" if r["quiz"] is None else round(r["quiz"]), r["active_days"], r["minutes"],
                        f"{r['last_seen']:%Y-%m-%d}" if r["last_seen"] else "Never"])
        w.writerow([])
        w.writerow(["Course", "Enrolled", "Average progress %", "Finished", "Quiz average %", "Quizzes not passed"])
        for c in report["courses"]:
            w.writerow([c["course"].title, c["enrolled"], c["avg_percent"], c["finished"], "" if c["quiz"] is None else c["quiz"], c["fails"]])
        return response
    schools = sorted({s.strip() for s in LearnerProfile.objects.exclude(school_name="").values_list("school_name", flat=True)}, key=str.lower)
    context = {**admin.site.each_context(request), "title": f"Group report: {label}" if label else "Class and school reports",
               "label": label, "g": report, "classroom": classroom, "school": school, "schools": schools,
               "classrooms": Classroom.objects.select_related("facilitator").order_by("archived", "name"), "query": request.GET.urlencode()}
    return render(request, "admin/group_report.html", context)


# ---------------------------------------------------------------- learners at risk

def at_risk_learners():
    """Learners who may be falling behind, each with the reasons, most reasons first."""
    learners = list(User.objects.filter(role=User.Role.LEARNER, is_active=True).select_related("learner_profile", "learner_profile__tier"))
    ids = [u.pk for u in learners]
    events = _activity_by_learner(ids)
    now = timezone.now()
    tries = defaultdict(list)
    for row in (QuizAttempt.objects.filter(learner_id__in=ids).values("learner_id", "lesson_id", "lesson__title")
                .annotate(n=Count("id"), passes=Count("id", filter=Q(passed=True)))):
        if row["n"] >= STUCK_TRIES and not row["passes"]:
            tries[row["learner_id"]].append(row)
    quiz = {r["learner_id"]: r for r in QuizResult.objects.filter(learner_id__in=ids).values("learner_id")
            .annotate(avg=Avg("score_percent"), n=Count("id"), fails=Count("id", filter=Q(passed=False)))}
    out = []
    for user in learners:
        ev = events.get(user.pk, [])
        recent = sum(1 for w in ev if w >= now - timedelta(days=14))
        prior = sum(1 for w in ev if now - timedelta(days=28) <= w < now - timedelta(days=14))
        last = max(ev) if ev else None
        reasons = []
        if not ev:
            joined = (now - user.date_joined).days
            if joined >= 7:
                reasons.append(("bi-hourglass-top", f"Joined {joined} days ago and has not finished anything"))
        else:
            if prior >= 3 and recent <= prior / 2:
                reasons.append(("bi-graph-down-arrow", f"Activity dropped: {recent} things in the last 2 weeks, down from {prior}"))
            quiet = (now - last).days
            if quiet >= IDLE_DAYS:
                reasons.append(("bi-moon-stars-fill", f"No activity for {quiet} days"))
        for row in tries.get(user.pk, [])[:2]:
            reasons.append(("bi-arrow-repeat", f"Tried “{row['lesson__title']}” {row['n']} times without passing"))
        q = quiz.get(user.pk)
        if q and q["fails"] >= 2:
            reasons.append(("bi-x-circle-fill", f"{q['fails']} quizzes not passed yet"))
        if q and q["n"] >= 3 and q["avg"] < LOW_AVERAGE:
            reasons.append(("bi-life-preserver", f"Low quiz average: {round(q['avg'])}%"))
        if reasons:
            out.append({"user": user, "profile": getattr(user, "learner_profile", None), "reasons": reasons, "last": last,
                        "recent": recent, "prior": prior})
    out.sort(key=lambda r: (-len(r["reasons"]), r["last"] or r["user"].date_joined))
    return out


def at_risk_count():
    """How many learners are at risk, for the admin dashboard (cached for ten minutes)."""
    return cache.get_or_set("c4k-at-risk-count", lambda: len(at_risk_learners()), 600)


def at_risk(request):
    rows = at_risk_learners()
    cache.set("c4k-at-risk-count", len(rows), 600)
    if request.GET.get("format") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="learners-at-risk.csv"'
        w = csv.writer(response)
        w.writerow(["Name", "Username", "School", "Tier", "Last activity", "Reasons"])
        for r in rows:
            p = r["profile"]
            w.writerow([r["user"].get_full_name() or r["user"].username, r["user"].username, p.school_name if p else "",
                        p.tier.name if p and p.tier else "", f"{r['last']:%Y-%m-%d}" if r["last"] else "Never",
                        "; ".join(text for _, text in r["reasons"])])
        return response
    context = {**admin.site.each_context(request), "title": "Learners at risk", "rows": rows, "idle_days": IDLE_DAYS, "stuck_tries": STUCK_TRIES,
               "low_average": LOW_AVERAGE}
    return render(request, "admin/at_risk.html", context)
