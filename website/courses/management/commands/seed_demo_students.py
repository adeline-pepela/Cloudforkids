"""Fill the site with demo learners at different stages, so the dashboards, teacher view and numbers look alive.

    python manage.py seed_demo_students            # add 50 demo learners (safe to re-run)
    python manage.py seed_demo_students --count 30
    python manage.py seed_demo_students --clear    # remove every demo learner again

Demo accounts are named demo.<first>.<n> with the password "demo-pass-123" and an @demo.cloudforkids.local email,
so they are easy to spot and delete. Nothing is emailed.
"""

import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import ParentalConsent, User
from courses.badges import check_and_award_badges
from courses.models import Course, Enrollment, Lesson, LessonCompletion, QuizResult, Tier
from dashboard.models import Lab, LabCompletion

PASSWORD = "demo-pass-123"
DOMAIN = "demo.cloudforkids.local"
FIRST = ["Amani", "Wanjiru", "Kevin", "Achieng", "Brian", "Njeri", "Otieno", "Faith", "Mwangi", "Zawadi", "Juma", "Akinyi", "Kamau",
         "Halima", "Baraka", "Naliaka", "Samuel", "Wambui", "Hassan", "Mercy", "Peter", "Nyambura", "Ali", "Cynthia", "Dennis"]
LAST = ["Otieno", "Kariuki", "Mohamed", "Wafula", "Chebet", "Mutua", "Njoroge", "Omondi", "Kiprono", "Mwende", "Barasa", "Adhiambo"]
SCHOOLS = [("Kibera Primary School", "Nairobi"), ("Mombasa Girls High", "Mombasa"), ("Kisumu Boys High", "Kisumu"),
           ("Nakuru Academy", "Nakuru"), ("Konza Technopolis School", "Machakos"), ("Eldoret Junior School", "Uasin Gishu")]
# tier slug -> (age range, grades) for the three public tiers
TIERS = {"foundational": ((9, 11), ["Grade 4", "Grade 5", "Grade 6"]),
         "intermediate": ((12, 14), ["Grade 7", "Grade 8", "Grade 9"]),
         "advanced": ((15, 17), ["Grade 10", "Grade 11", "Grade 12"])}
# (label, fraction of the course lessons finished, labs done)
STAGES = [("just joined", 0, 0), ("getting started", 0.2, 0), ("on track", 0.5, 1), ("keen", 0.75, 2), ("finisher", 1.0, 3)]


class Command(BaseCommand):
    help = "Create (or with --clear remove) demo learners with progress, different tiers and badges."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=50)
        parser.add_argument("--clear", action="store_true")

    def handle(self, *args, **opts):
        if opts["clear"]:
            deleted, _ = User.objects.filter(email__endswith="@" + DOMAIN).delete()
            self.stdout.write(f"Removed demo learners ({deleted} records).")
            return
        rng = random.Random(7)
        tiers = {t.slug: t for t in Tier.objects.filter(slug__in=TIERS)}
        if not tiers:
            self.stderr.write("No tiers found. Run the normal seeding first.")
            return
        labs = list(Lab.objects.filter(published=True))
        created = 0
        with transaction.atomic():
            for n in range(1, opts["count"] + 1):
                slug = list(TIERS)[n % len(TIERS)]
                if slug not in tiers:
                    continue
                first, last = FIRST[n % len(FIRST)], rng.choice(LAST)
                username = f"demo.{first.lower()}.{n}"
                if User.objects.filter(username=username).exists():
                    continue
                (lo, hi), grades = TIERS[slug]
                age = rng.randint(lo, hi)
                user = User.objects.create_user(username, f"{username}@{DOMAIN}", PASSWORD, role="learner",
                                                first_name=first, last_name=last)
                profile = user.learner_profile
                school, county = rng.choice(SCHOOLS)
                profile.tier = tiers[slug]
                profile.grade = rng.choice(grades)
                profile.school_name, profile.county = school, county
                profile.date_of_birth = date.today().replace(year=date.today().year - age, month=3, day=15)
                profile.parent_guardian_name = f"Parent of {first}"
                profile.parent_guardian_email = f"parent.{n}@{DOMAIN}"
                profile.save()
                if age < 13:
                    ParentalConsent.objects.create(user=user, parent_name=profile.parent_guardian_name, parent_email=profile.parent_guardian_email,
                                                   status="approved", method="admin", decided_at=timezone.now())
                self.add_progress(user, tiers[slug], STAGES[n % len(STAGES)], labs, rng)
                created += 1
        self.stdout.write(self.style.SUCCESS(f"Created {created} demo learners. Password for all: {PASSWORD}  (undo: --clear)"))

    def add_progress(self, user, tier, stage, labs, rng):
        _, fraction, lab_count = stage
        courses = list(tier.courses.all())
        if not courses:
            return
        # most learners follow their own tier; some also try a course from another tier
        picked = courses[:max(1, round(len(courses) * max(fraction, .34)))]
        if fraction >= .5 and rng.random() < .35:
            other = Course.objects.exclude(tier=tier).exclude(tier__slug="explorer").order_by("?").first()
            if other:
                picked.append(other)
        now = timezone.now()
        day = rng.randint(0, 2)  # 0 = active today, so streaks show up
        for course in picked:
            enrollment = Enrollment.objects.create(learner=user, course=course)
            lessons = list(course.lessons.filter(lesson_type=Lesson.LessonType.LESSON))
            for lesson in lessons[:round(len(lessons) * fraction)]:
                when = now - timedelta(days=day, hours=rng.randint(0, 5))
                day += rng.choice([0, 1, 1])
                score = rng.randint(65, 100)
                completion = LessonCompletion.objects.create(enrollment=enrollment, lesson=lesson, score_percent=score)
                LessonCompletion.objects.filter(pk=completion.pk).update(completed_at=when)
                QuizResult.objects.update_or_create(learner=user, lesson=lesson, defaults={"score_percent": score, "passed": True})
        for lab in rng.sample(labs, min(lab_count, len(labs))):
            done = LabCompletion.objects.create(learner=user, slug=lab.slug)
            LabCompletion.objects.filter(pk=done.pk).update(completed_at=now - timedelta(days=rng.randint(0, 6)))
        check_and_award_badges(user)
