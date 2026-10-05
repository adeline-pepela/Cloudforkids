"""Admin tools: CSV learner import and the monthly programme report."""

import csv
import io
import re
import secrets
from collections import Counter
from datetime import date, datetime, timedelta

from django import forms
from django.contrib import admin
from django.db.models import Avg, Count
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import path
from django.utils import timezone

from accounts.models import ClassMembership, Classroom, LearnerProfile, ParentalConsent, ParentLink, User
from courses.models import Course, LearnerBadge, Lesson, LessonCompletion, QuizResult, Tier
from dashboard.models import LabCompletion

MAX_ROWS = 500
PASSWORD_ALPHABET = "abcdefghjkmnpqrstuvwxyzACDEFGHJKLMNPQRTUVWXYZ234679"  # no look-alike characters
SAMPLE_CSV = (
    "first_name,last_name,username,email,date_of_birth,grade,school,county,parent_name,parent_email,parent_phone\n"
    "Amani,Kamau,,,2014-03-12,Grade 5,Sunrise Primary,Nairobi,Wanjiku Kamau,wanjiku@example.com,0712345678\n"
    "Baraka,Otieno,,,2012-07-01,Grade 7,Sunrise Primary,Nairobi,,,\n"
)


# ---------------------------------------------------------------- learner import

class ImportForm(forms.Form):
    file = forms.FileField(label="CSV file")
    classroom = forms.ModelChoiceField(Classroom.objects.filter(archived=False), required=False, label="Add everyone to this class (optional)")
    tier = forms.ModelChoiceField(Tier.objects.all(), required=False, label="Learning tier (optional)")
    confirm = forms.BooleanField(label="I confirm the school or organisation holds parental consent for any learner under 13.")


def _username(first, last, taken):
    base = re.sub(r"[^a-z0-9]", "", f"{first}.{last}".lower()) or "learner"
    name, n = base, 1
    while name in taken or User.objects.filter(username__iexact=name).exists():
        n += 1
        name = f"{base}{n}"
    taken.add(name)
    return name


def import_learners(request):
    context = {**admin.site.each_context(request), "title": "Import learners", "form": ImportForm(), "sample": SAMPLE_CSV}
    if request.method == "POST":
        form = ImportForm(request.POST, request.FILES)
        context["form"] = form
        if form.is_valid():
            created, errors, taken = [], [], set()
            text = form.cleaned_data["file"].read().decode("utf-8-sig", "replace")
            rows = list(csv.DictReader(io.StringIO(text)))
            if len(rows) > MAX_ROWS:
                errors.append((0, f"Too many rows ({len(rows)}). Please import {MAX_ROWS} or fewer at a time."))
                rows = []
            for number, row in enumerate(rows, start=2):
                row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
                first, last = row.get("first_name", ""), row.get("last_name", "")
                if not first or not last:
                    errors.append((number, "first_name and last_name are required"))
                    continue
                born = None
                if row.get("date_of_birth"):
                    try:
                        born = datetime.strptime(row["date_of_birth"], "%Y-%m-%d").date()
                    except ValueError:
                        errors.append((number, f"date_of_birth '{row['date_of_birth']}' must look like 2014-03-12"))
                        continue
                email = row.get("email", "")
                if email and "@" not in email:
                    errors.append((number, f"email '{email}' is not valid"))
                    continue
                if row.get("username") and User.objects.filter(username__iexact=row["username"]).exists():
                    errors.append((number, f"username '{row['username']}' is already taken"))
                    continue
                username = row.get("username") or _username(first, last, taken)
                password = "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(8))
                user = User.objects.create_user(username, email=email, password=password, first_name=first, last_name=last, role=User.Role.LEARNER)
                profile = user.learner_profile  # created automatically for learners
                profile.date_of_birth = born
                profile.grade, profile.school_name, profile.county = row.get("grade", ""), row.get("school", ""), row.get("county", "")
                profile.parent_guardian_name = row.get("parent_name", "")
                profile.parent_guardian_email = row.get("parent_email", "")
                profile.parent_guardian_phone = row.get("parent_phone", "")
                if form.cleaned_data["tier"]:
                    profile.tier = form.cleaned_data["tier"]
                profile.save()
                if row.get("parent_email"):
                    ParentalConsent.objects.create(
                        user=user, parent_name=row.get("parent_name", ""), parent_email=row["parent_email"],
                        status=ParentalConsent.Status.APPROVED, method=ParentalConsent.Method.SCHOOL, decided_at=timezone.now(),
                    )
                if form.cleaned_data["classroom"]:
                    ClassMembership.objects.get_or_create(classroom=form.cleaned_data["classroom"], learner=user)
                created.append({"first": first, "last": last, "username": username, "password": password, "grade": row.get("grade", "")})
            out = io.StringIO()
            writer = csv.writer(out)
            writer.writerow(["First name", "Last name", "Username", "Password"])
            for c in created:
                writer.writerow([c["first"], c["last"], c["username"], c["password"]])
            context.update(done=True, created=created, errors=errors, credentials_csv=out.getvalue())
    return render(request, "admin/import_learners.html", context)


def sample_csv(request):
    response = HttpResponse(SAMPLE_CSV, content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="learners_template.csv"'
    return response


# ---------------------------------------------------------------- monthly report

def month_bounds(text):
    """(start, end) datetimes for 'YYYY-MM', defaulting to the current month."""
    today = timezone.now().date()
    try:
        year, month = (int(p) for p in text.split("-"))
        first = date(year, month, 1)
    except (ValueError, AttributeError):
        first = today.replace(day=1)
    nxt = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    tz = timezone.get_current_timezone()
    return first, timezone.make_aware(datetime.combine(first, datetime.min.time()), tz), timezone.make_aware(datetime.combine(nxt, datetime.min.time()), tz)


def build_report(first, start, end):
    in_period = {"completed_at__gte": start, "completed_at__lt": end}
    completions = LessonCompletion.objects.filter(**in_period)
    labs = LabCompletion.objects.filter(**in_period)
    quizzes = QuizResult.objects.filter(updated_at__gte=start, updated_at__lt=end)
    active = set(completions.values_list("enrollment__learner_id", flat=True)) | set(labs.values_list("learner_id", flat=True)) | set(quizzes.values_list("learner_id", flat=True))
    learners = User.objects.filter(role=User.Role.LEARNER)
    new_learners = learners.filter(date_joined__gte=start, date_joined__lt=end)

    tier_rows = []
    for tier in Tier.objects.all():
        tier_rows.append({
            "tier": tier,
            "learners": LearnerProfile.objects.filter(tier=tier).count(),
            "completions": completions.filter(lesson__course__tier=tier).count(),
        })
    course_rows = []
    for course in Course.objects.select_related("tier"):
        done = completions.filter(lesson__course=course)
        exam = course.exam
        course_rows.append({
            "course": course,
            "completions": done.count(),
            "learners": done.values("enrollment__learner").distinct().count(),
            "graduates": completions.filter(lesson=exam).count() if exam else 0,
        })
    lesson_stats = (
        QuizResult.objects.filter(updated_at__gte=start, updated_at__lt=end).values("lesson__title", "lesson__course__title")
        .annotate(avg=Avg("score_percent"), n=Count("id")).filter(n__gte=3).order_by("avg")[:5]
    )
    top_lessons = (
        completions.values("lesson__title", "lesson__course__title").annotate(n=Count("id")).order_by("-n")[:5]
    )
    days = (end - start).days
    per_day = {r["d"]: r["n"] for r in completions.annotate(d=TruncDate("completed_at")).values("d").annotate(n=Count("id"))}
    chart = [{"label": (first + timedelta(days=i)).strftime("%d"), "value": per_day.get((first + timedelta(days=i)), 0)} for i in range(days)]
    counties = Counter(c for c in new_learners.values_list("learner_profile__county", flat=True) if c)
    schools = Counter(s for s in LearnerProfile.objects.values_list("school_name", flat=True) if s)
    scores = quizzes.aggregate(avg=Avg("score_percent"))["avg"]
    total_q = quizzes.count()
    return {
        "first": first,
        "new_learners": new_learners.count(),
        "new_parents": User.objects.filter(role=User.Role.PARENT, date_joined__gte=start, date_joined__lt=end).count(),
        "new_facilitators": User.objects.filter(role=User.Role.FACILITATOR, date_joined__gte=start, date_joined__lt=end).count(),
        "new_classes": Classroom.objects.filter(created_at__gte=start, created_at__lt=end).count(),
        "active_learners": len(active),
        "lessons_completed": completions.count(),
        "labs_completed": labs.count(),
        "quizzes_taken": total_q,
        "quiz_pass_rate": round(quizzes.filter(passed=True).count() / total_q * 100) if total_q else None,
        "quiz_avg": round(scores) if scores is not None else None,
        "courses_completed": sum(r["graduates"] for r in course_rows),
        "badges": LearnerBadge.objects.filter(earned_at__gte=start, earned_at__lt=end).count(),
        "total_learners": learners.count(),
        "total_parents_linked": ParentLink.objects.values("parent").distinct().count(),
        "total_classes": Classroom.objects.filter(archived=False).count(),
        "total_schools": len(schools),
        "total_counties": LearnerProfile.objects.exclude(county="").values("county").distinct().count(),
        "pending_consent": ParentalConsent.objects.filter(status="pending").count(),
        "tier_rows": tier_rows,
        "course_rows": course_rows,
        "hard": list(lesson_stats),
        "top": list(top_lessons),
        "chart": chart,
        "counties": counties.most_common(8),
        "schools": schools.most_common(8),
    }


def monthly_report(request):
    first, start, end = month_bounds(request.GET.get("month", ""))
    report = build_report(first, start, end)
    if request.GET.get("format") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="cloud-for-kids-report-{first:%Y-%m}.csv"'
        w = csv.writer(response)
        w.writerow(["Cloud for Kids monthly report", f"{first:%B %Y}"])
        for label, key in [
            ("New learners", "new_learners"), ("New parents", "new_parents"), ("New facilitators", "new_facilitators"), ("New classes", "new_classes"),
            ("Active learners", "active_learners"), ("Lessons completed", "lessons_completed"), ("Practice labs finished", "labs_completed"),
            ("Quizzes taken", "quizzes_taken"), ("Quiz pass rate %", "quiz_pass_rate"), ("Average quiz score %", "quiz_avg"),
            ("Courses completed", "courses_completed"), ("Badges earned", "badges"), ("Total learners", "total_learners"),
            ("Parents linked", "total_parents_linked"), ("Active classes", "total_classes"), ("Schools", "total_schools"), ("Counties", "total_counties"),
        ]:
            w.writerow([label, "" if report[key] is None else report[key]])
        w.writerow([])
        w.writerow(["Course", "Tier", "Lessons completed", "Learners", "Course completions"])
        for r in report["course_rows"]:
            w.writerow([r["course"].title, r["course"].tier.name, r["completions"], r["learners"], r["graduates"]])
        return response
    prev = (first - timedelta(days=1)).replace(day=1)
    nxt = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    months = []
    cursor = timezone.now().date().replace(day=1)
    for _ in range(12):
        months.append(cursor)
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    context = {**admin.site.each_context(request), "title": "Monthly report", "r": report, "month": first, "prev": prev, "next": nxt, "months": months,
               "future": nxt > timezone.now().date()}
    return render(request, "admin/monthly_report.html", context)


def urls():
    wrap = admin.site.admin_view
    return [
        path("import-learners/", wrap(import_learners), name="import_learners"),
        path("learners-template.csv", wrap(sample_csv), name="learners_template"),
        path("report/", wrap(monthly_report), name="monthly_report"),
    ]
