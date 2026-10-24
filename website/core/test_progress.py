from datetime import timedelta
from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ClassMembership, Classroom, LearnerNote, ParentLink, User
from courses.models import Course, Enrollment, Lesson, LessonCompletion, LessonTime, QuizAttempt, QuizResult, Tier
from courses.quiz import parse_questions, record_result

from . import notify
from .progress import build_learner_report
from .progress_groups import at_risk_learners

PASSWORD = "Zq9!tr-Kenya42"
QUIZ = (
    '<div class="mcq-question" data-correct="0"><p class="mcq-prompt">What is a <em>database</em>?</p><div class="mcq-options">'
    '<button type="button" class="mcq-option" data-index="0">A</button><button type="button" class="mcq-option" data-index="1">B</button>'
    '</div><div class="mcq-explain">Because.</div></div>'
    '<div class="mcq-question" data-correct="1"><p class="mcq-prompt">Second one?</p><div class="mcq-options">'
    '<button type="button" class="mcq-option" data-index="0">A</button><button type="button" class="mcq-option" data-index="1">B</button>'
    '</div><div class="mcq-explain">Because.</div></div>'
)


class ProgressFeaturesTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_superuser("boss3", "b3@example.com", PASSWORD, role="admin")
        self.client.force_login(self.admin)
        self.tier = Tier.objects.create(name="Foundational", slug="found-x", grade_range="4-6", summary="s")
        self.course = Course.objects.create(tier=self.tier, title="Cloud 101", slug="cloud-101-x", summary="s")
        self.lessons = [Lesson.objects.create(course=self.course, title=f"L{i}", slug=f"l{i}", content=QUIZ, order=i) for i in range(1, 4)]
        self.kid = User.objects.create_user("amani2", "amani@example.com", PASSWORD, role="learner", first_name="Amani")
        self.kid.learner_profile.tier = self.tier
        self.kid.learner_profile.school_name = "Sunrise Primary"
        self.kid.learner_profile.parent_guardian_email = "guardian@example.com"
        self.kid.learner_profile.save()
        self.enrollment = Enrollment.objects.create(learner=self.kid, course=self.course)
        LessonCompletion.objects.create(enrollment=self.enrollment, lesson=self.lessons[0], score_percent=100)
        record_result(self.kid, self.lessons[0], 2, 2, [])
        for _ in range(3):
            record_result(self.kid, self.lessons[1], 0, 2, [0, 1])

    def test_every_attempt_and_wrong_question_is_kept(self):
        self.assertEqual(QuizAttempt.objects.filter(learner=self.kid).count(), 4)
        self.assertEqual(QuizResult.objects.get(learner=self.kid, lesson=self.lessons[1]).score_percent, 0)
        self.assertEqual(parse_questions(QUIZ)[0]["text"], "What is a database?")
        r = build_learner_report(self.kid)
        self.assertEqual(r["tries"]["count"], 4)
        self.assertEqual(r["tries"]["retried"][0]["count"], 3)
        self.assertIsNone(r["tries"]["retried"][0]["to_pass"])
        self.assertEqual(r["tries"]["missed"][0]["text"], "What is a database?")
        self.assertTrue(any("Redo the quiz" in s["text"] for s in r["next_steps"]))
        self.assertEqual(r["compare"]["n"], 1)

    def test_time_on_a_lesson_is_counted_by_the_server_clock(self):
        self.client.force_login(self.kid)
        url = reverse("courses:lesson_time", args=[self.course.slug, self.lessons[0].slug])
        with mock.patch("courses.views.time.time", return_value=1000.0):
            self.assertEqual(self.client.post(url, "{}", content_type="application/json").json()["added"], 0)
        with mock.patch("courses.views.time.time", return_value=1020.0):
            self.assertEqual(self.client.post(url, "{}", content_type="application/json").json()["added"], 20)
        with mock.patch("courses.views.time.time", return_value=5000.0):  # a page left open for an hour counts one ping at most
            self.assertEqual(self.client.post(url, "{}", content_type="application/json").json()["added"], 45)
        with mock.patch("courses.views.time.time", return_value=9000.0):  # coming back to the tab does not count the time away
            self.assertEqual(self.client.post(url, '{"resume": true}', content_type="application/json").json()["added"], 0)
        self.assertEqual(LessonTime.objects.get(learner=self.kid).seconds, 65)

    def test_report_page_actions_pdf_and_notes(self):
        url = reverse("tools:learner_detail", args=[self.kid.pk])
        page = self.client.get(url)
        self.assertContains(page, "Most missed question")
        self.assertContains(page, "Recommended next steps")
        self.assertContains(page, "Compared with their tier")
        pdf = self.client.get(url + "?format=pdf")
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        self.client.post(url, {"action": "note", "body": "Spoke to parent"})
        note = LearnerNote.objects.get(learner=self.kid)
        self.assertEqual(note.author, self.admin)
        self.assertContains(self.client.get(url), "Spoke to parent")
        self.client.post(url, {"action": "delete_note", "note": note.pk})
        self.assertFalse(LearnerNote.objects.exists())

    def test_reminder_and_emailed_report(self):
        url = reverse("tools:learner_detail", args=[self.kid.pk])
        self.client.post(url, {"action": "nudge"})
        self.assertEqual(mail.outbox[-1].to, ["amani@example.com"])
        mail.outbox.clear()
        self.client.post(url, {"action": "email_report"})
        self.assertEqual(mail.outbox[0].to, ["guardian@example.com"])
        self.assertIn("Amani", mail.outbox[0].subject)
        self.assertIn("Needs more practice", mail.outbox[0].body)
        mail.outbox.clear()
        self.client.post(reverse("tools:learner_list"), {"action": "nudge", "learner": [self.kid.pk], "next": reverse("tools:at_risk")})
        self.assertEqual(len(mail.outbox), 1)

    def test_class_and_school_reports(self):
        teacher = User.objects.create_user("teach1", password=PASSWORD, role="facilitator", is_approved=True)
        room = Classroom.objects.create(facilitator=teacher, name="Cloud Club")
        ClassMembership.objects.create(classroom=room, learner=self.kid)
        page = self.client.get(reverse("tools:group_report") + f"?classroom={room.pk}")
        self.assertContains(page, "Cloud Club")
        self.assertContains(page, "Amani")
        self.assertContains(page, "What is a database?")
        csv_reply = self.client.get(reverse("tools:group_report") + f"?classroom={room.pk}&format=csv")
        self.assertIn("amani2", csv_reply.content.decode())
        self.assertContains(self.client.get(reverse("tools:group_report") + "?school=sunrise primary"), "Amani")
        self.assertContains(self.client.get(reverse("tools:group_report")), "Pick a class or a school")

    def test_at_risk_list_and_dashboard_alert(self):
        rows = {r["user"].pk: r for r in at_risk_learners()}
        self.assertIn(self.kid.pk, rows)
        self.assertTrue(any("3 times without passing" in text for _, text in rows[self.kid.pk]["reasons"]))
        self.assertContains(self.client.get(reverse("tools:at_risk")), "Amani")
        self.assertContains(self.client.get(reverse("admin:index")), "may be falling behind")

    def test_teacher_notes_and_family_next_steps(self):
        teacher = User.objects.create_user("teach2", password=PASSWORD, role="facilitator", is_approved=True)
        room = Classroom.objects.create(facilitator=teacher, name="Cloud Club")
        ClassMembership.objects.create(classroom=room, learner=self.kid)
        self.client.force_login(teacher)
        url = reverse("teach:learner", args=[room.pk, self.kid.pk])
        self.client.post(url, {"body": "Paired with Baraka"})
        page = self.client.get(url)
        self.assertContains(page, "Paired with Baraka")
        self.assertContains(page, "Recommended next steps")
        parent = User.objects.create_user("mum", "mum@example.com", PASSWORD, role="parent")
        ParentLink.objects.create(parent=parent, child=self.kid)
        self.client.force_login(parent)
        family = self.client.get(reverse("family:child", args=[self.kid.pk]))
        self.assertContains(family, "Recommended next steps")
        self.assertNotContains(family, "Paired with Baraka")

    def test_learner_dashboard_shows_next_steps(self):
        self.client.force_login(self.kid)
        page = self.client.get(reverse("dashboard:home"))
        self.assertContains(page, "Your next steps")
        self.assertContains(page, "Redo the quiz in")

    def test_monthly_email_names_strong_and_weak_lessons(self):
        lines = notify.area_bullets("monthly", "en", "Amani", list(QuizResult.objects.filter(passed=True)), list(QuizResult.objects.filter(passed=False)))
        self.assertEqual(lines, ["Amani is strongest in L1.", "Amani should practise L2 next."])

    def test_learner_profile_page_shows_the_new_charts(self):
        LessonTime.objects.create(learner=self.kid, lesson=self.lessons[0], day=timezone.localdate() - timedelta(days=1), seconds=600)
        page = self.client.get(reverse("admin:accounts_learnerprofile_change", args=[self.kid.learner_profile.pk]))
        self.assertContains(page, "ch-time")
        self.assertContains(page, "ch-tries")
        self.assertContains(page, "10 min")
