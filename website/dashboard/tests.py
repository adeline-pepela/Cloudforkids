from datetime import timedelta

from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ClassMembership, Classroom, Message, NotificationLog, ParentLink, User
from courses.models import Course, Enrollment, LessonCompletion, QuizResult
from core import notify

from .labs import get_labs
from .models import Lab, LabCompletion
from .stats import learner_stats

PASSWORD = "Zq9!tr-Kenya42"


def make(username, role="learner", **extra):
    return User.objects.create_user(username, email=f"{username}@example.com", password=PASSWORD, role=role, first_name=username.title(), **extra)


def finish(learner, count, days_ago=0, score=90):
    course = Course.objects.get(slug="what-is-the-cloud-really")
    enrollment, _ = Enrollment.objects.get_or_create(learner=learner, course=course)
    for lesson in course.lessons.all()[:count]:
        completion = LessonCompletion.objects.create(enrollment=enrollment, lesson=lesson, score_percent=score)
        LessonCompletion.objects.filter(pk=completion.pk).update(completed_at=timezone.now() - timedelta(days=days_ago))
        QuizResult.objects.create(learner=learner, lesson=lesson, score_percent=score, passed=score >= 70)


class LearnerStatsTests(TestCase):
    def test_xp_level_and_streak(self):
        kid = make("kid")
        finish(kid, 3)
        LabCompletion.objects.create(learner=kid, slug=get_labs()[0]["slug"])
        stats = learner_stats(kid)
        self.assertEqual(stats["xp"], 3 * 10 + 15)
        self.assertEqual(stats["level"], 1)
        self.assertEqual(stats["streak"], 1)
        self.assertEqual(stats["lessons_done"], 3)

    def test_streak_breaks_after_a_missed_day(self):
        kid = make("kid")
        finish(kid, 1, days_ago=3)
        self.assertEqual(learner_stats(kid)["streak"], 0)

    def test_labs_come_from_the_database(self):
        self.assertEqual(len(get_labs()), Lab.objects.filter(published=True).count())
        Lab.objects.filter(slug=get_labs()[0]["slug"]).update(published=False)
        self.assertEqual(len(get_labs()), Lab.objects.filter(published=True).count())

    def test_lab_completion_awards_xp_once(self):
        kid = make("kid")
        self.client.force_login(kid)
        slug = get_labs()[0]["slug"]
        first = self.client.post(reverse("dashboard:lab_complete", args=[slug])).json()
        second = self.client.post(reverse("dashboard:lab_complete", args=[slug])).json()
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(second["xp"], 15)

    def test_unknown_lab_is_404(self):
        self.client.force_login(make("kid"))
        self.assertEqual(self.client.get(reverse("dashboard:lab", args=["nope"])).status_code, 404)


class ParentReportTests(TestCase):
    def test_progress_strengths_and_weak_points(self):
        from .family import child_report

        kid = make("kid")
        finish(kid, 2, score=95)
        course = Course.objects.get(slug="what-is-the-cloud-really")
        QuizResult.objects.create(learner=kid, lesson=course.lessons.all()[3], score_percent=30, passed=False)
        report = child_report(kid)
        self.assertGreater(report["percent"], 0)
        self.assertEqual(len(report["strengths"]), 2)
        self.assertEqual(report["weak"][0].score_percent, 30)
        self.assertEqual(report["health"][0], "good")

    def test_new_learner_is_marked_not_started(self):
        from .family import child_report

        self.assertEqual(child_report(make("fresh"))["health"][0], "new")

    def test_inactive_learner_needs_a_nudge(self):
        from .family import child_report

        kid = make("quiet")
        finish(kid, 1, days_ago=9)
        QuizResult.objects.filter(learner=kid).update(updated_at=timezone.now() - timedelta(days=9))
        self.assertEqual(child_report(kid)["health"][0], "nudge")


class TeacherReportTests(TestCase):
    def test_class_report_statuses(self):
        from .teach import class_report

        teacher = make("teach", "facilitator")
        classroom = Classroom.objects.create(facilitator=teacher, name="Club")
        good, quiet, fresh, weak = make("good"), make("quiet"), make("fresh"), make("weak")
        for kid in (good, quiet, fresh, weak):
            ClassMembership.objects.create(classroom=classroom, learner=kid)
        finish(good, 2)
        QuizResult.objects.filter(learner=good).update(score_percent=90)
        finish(quiet, 1, days_ago=9)
        QuizResult.objects.filter(learner=quiet).update(updated_at=timezone.now() - timedelta(days=9))
        finish(weak, 2, score=20)
        report = class_report(classroom)
        status = {row["user"].username: row["status"] for row in report["roster"]}
        self.assertEqual(status["good"], "good")
        self.assertEqual(status["fresh"], "new")
        self.assertEqual(status["weak"], "help")
        self.assertEqual(status["quiet"], "nudge")
        self.assertEqual(report["count"], 4)
        self.assertTrue(report["hard"])


class MessagingTests(TestCase):
    def setUp(self):
        self.teacher, self.mum, self.kid = make("teach", "facilitator"), make("mum", "parent"), make("kid")
        self.classroom = Classroom.objects.create(facilitator=self.teacher, name="Club")
        ClassMembership.objects.create(classroom=self.classroom, learner=self.kid)
        ParentLink.objects.create(parent=self.mum, child=self.kid)

    def send(self, to="class", **extra):
        self.client.force_login(self.teacher)
        data = {"classroom": self.classroom.pk, "to": to, "subject": "Hello", "body": "Please read lesson 2."}
        data.update(extra)
        return self.client.post(reverse("messaging:compose"), data)

    def test_class_message_reaches_learners_and_parents(self):
        self.send()
        self.assertEqual(set(Message.objects.values_list("recipient__username", flat=True)), {"kid", "mum"})
        self.assertEqual(len(mail.outbox), 2)

    def test_message_to_one_childs_parents_only(self):
        self.send(to=str(self.kid.pk))
        self.assertEqual(list(Message.objects.values_list("recipient__username", flat=True)), ["mum"])

    def test_cannot_message_someone_elses_class(self):
        rival = make("rival", "facilitator")
        self.client.force_login(rival)
        response = self.client.post(reverse("messaging:compose"), {"classroom": self.classroom.pk, "to": "class", "subject": "x", "body": "y"})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Message.objects.exists())

    def test_learner_can_read_but_not_send_or_compose(self):
        self.send()
        self.client.force_login(self.kid)
        inbox = self.client.get(reverse("messaging:inbox"))
        self.assertContains(inbox, "Hello")
        message = Message.objects.get(recipient=self.kid)
        self.client.post(reverse("messaging:reply", args=[message.pk]), {"body": "hi teacher"})
        self.assertEqual(Message.objects.filter(sender=self.kid).count(), 0)
        self.assertRedirects(self.client.get(reverse("messaging:compose")), reverse("messaging:inbox"), fetch_redirect_response=False)

    def test_parent_replies_and_teacher_sees_it(self):
        self.send(to=str(self.kid.pk))
        message = Message.objects.get(recipient=self.mum)
        self.client.force_login(self.mum)
        self.client.post(reverse("messaging:reply", args=[message.pk]), {"body": "Thanks, noted."})
        reply = Message.objects.get(sender=self.mum)
        self.assertEqual(reply.recipient, self.teacher)
        self.assertEqual(reply.reply_to, message)

    def test_strangers_cannot_open_messages(self):
        self.send()
        message = Message.objects.get(recipient=self.mum)
        self.client.force_login(make("snoop", "parent"))
        self.assertRedirects(self.client.get(reverse("messaging:detail", args=[message.pk])), reverse("messaging:inbox"), fetch_redirect_response=False)

    def test_opening_marks_read_and_unread_count(self):
        self.send(to=str(self.kid.pk))
        self.client.force_login(self.mum)
        self.assertContains(self.client.get(reverse("family:home")), 'class="l-badge">1')
        message = Message.objects.get(recipient=self.mum)
        self.client.get(reverse("messaging:detail", args=[message.pk]))
        message.refresh_from_db()
        self.assertIsNotNone(message.read_at)


class NotificationTests(TestCase):
    def setUp(self):
        self.mum, self.kid = make("mum", "parent"), make("kid")
        ParentLink.objects.create(parent=self.mum, child=self.kid)

    def test_weekly_summary_goes_once_per_week(self):
        finish(self.kid, 2)
        call_command("send_notifications", "--weekly")
        call_command("send_notifications", "--weekly")
        weekly = [m for m in mail.outbox if "week" in m.subject]
        self.assertEqual(len(weekly), 1)
        self.assertEqual(weekly[0].to, ["mum@example.com"])
        self.assertIn("Kid", weekly[0].body)
        self.assertIn("Stop these emails", weekly[0].body)

    def test_unsubscribed_parent_gets_nothing(self):
        self.mum.email_notifications = False
        self.mum.save()
        call_command("send_notifications", "--weekly", "--nudges")
        self.assertEqual(len(mail.outbox), 0)

    def test_nudge_after_quiet_days_only_once(self):
        finish(self.kid, 1, days_ago=6)
        QuizResult.objects.filter(learner=self.kid).update(updated_at=timezone.now() - timedelta(days=6))
        call_command("send_notifications", "--nudges")
        call_command("send_notifications", "--nudges")
        recipients = sorted(m.to[0] for m in mail.outbox)
        self.assertEqual(recipients, ["kid@example.com", "mum@example.com"])
        self.assertEqual(NotificationLog.objects.filter(kind="nudge").count(), 2)

    def test_no_nudge_for_active_learner(self):
        finish(self.kid, 1, days_ago=0)
        call_command("send_notifications", "--nudges")
        self.assertEqual(len(mail.outbox), 0)

    def test_new_learner_gets_a_start_nudge_after_a_few_days(self):
        User.objects.filter(pk=self.kid.pk).update(date_joined=timezone.now() - timedelta(days=5))
        call_command("send_notifications", "--nudges")
        self.assertTrue(any("nudge" in m.subject.lower() for m in mail.outbox))

    def test_email_has_html_and_text_parts(self):
        notify.send_email("x@example.com", "Hi", "Heading", ["Body line"], cta=("Go", "https://example.com/go"))
        message = mail.outbox[0]
        self.assertIn("https://example.com/go", message.body)
        self.assertEqual(message.alternatives[0][1], "text/html")
        self.assertIn("Heading", message.alternatives[0][0])
