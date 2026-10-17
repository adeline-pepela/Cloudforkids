"""Emails: the Resend backend, its webhook, settings and confirmation, the new emails, Kiswahili, and the preview page."""

import base64
import hashlib
import hmac
import io
import json
import time
import urllib.error
from datetime import datetime, timedelta
from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import ClassMembership, Classroom, LearnerProfile, ParentLink, User

from . import email_text as T
from . import notify
from .models import EmailLog, EmailSuppression
from .resend_backend import ResendEmailBackend

PASSWORD = "Zq9!tr-Kenya42"
SECRET = "whsec_" + base64.b64encode(b"a-very-secret-webhook-key").decode()


def make(username, role="learner", **extra):
    return User.objects.create_user(username, email=f"{username}@example.com", password=PASSWORD, role=role,
                                    first_name=username.title(), **extra)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def resend_ok(email_id="re_123"):
    return FakeResponse(json.dumps({"id": email_id}).encode())


def http_error(code):
    return urllib.error.HTTPError("https://api.resend.com/emails", code, "busy", {"retry-after": "0"}, io.BytesIO(b'{"message":"x"}'))


@override_settings(RESEND_API_KEY="re_test", EMAIL_REPLY_TO="")
class BackendTests(TestCase):
    def message(self, to="mum@example.com", **headers):
        m = EmailMultiAlternatives("Hello", "Body", "Cloud for Kids <hello@cloudforkids.co.ke>", [to], headers=headers)
        m.attach_alternative("<p>Body</p>", "text/html")
        m.c4k_kind = "weekly"
        return m

    @mock.patch("core.resend_backend.time.sleep")
    @mock.patch("core.resend_backend.urllib.request.urlopen")
    def test_busy_is_retried_and_logged(self, urlopen, sleep):
        urlopen.side_effect = [http_error(429), http_error(503), resend_ok("re_abc")]
        self.assertEqual(ResendEmailBackend().send_messages([self.message(**{"List-Unsubscribe": "<https://x/>"})]), 1)
        log = EmailLog.objects.get()
        self.assertEqual((log.status, log.resend_id, log.attempts, log.kind), ("sent", "re_abc", 3, "weekly"))
        payload = json.loads(urlopen.call_args.args[0].data)
        self.assertEqual(payload["headers"], {"List-Unsubscribe": "<https://x/>"})
        self.assertEqual(payload["reply_to"], ["adelinemakokha@gmail.com"])  # the contact email in Site settings
        self.assertEqual(sleep.call_count, 2)

    @mock.patch("core.resend_backend.time.sleep")
    @mock.patch("core.resend_backend.urllib.request.urlopen")
    def test_a_real_refusal_is_not_retried(self, urlopen, sleep):
        urlopen.side_effect = [http_error(403)]
        with self.assertRaises(RuntimeError):
            ResendEmailBackend().send_messages([self.message()])
        self.assertEqual(EmailLog.objects.get().status, "failed")
        self.assertEqual(urlopen.call_count, 1)

    @mock.patch("core.resend_backend.urllib.request.urlopen")
    def test_blocked_addresses_are_skipped(self, urlopen):
        EmailSuppression.objects.create(email="Mum@Example.com", reason="bounced")
        self.assertEqual(ResendEmailBackend().send_messages([self.message()]), 0)
        urlopen.assert_not_called()
        self.assertEqual(EmailLog.objects.get().status, "skipped")

    @override_settings(EMAIL_REPLY_TO="team@cloudforkids.co.ke")
    @mock.patch("core.resend_backend.urllib.request.urlopen", side_effect=lambda *a, **k: resend_ok())
    def test_reply_to_setting_wins(self, urlopen):
        ResendEmailBackend().send_messages([self.message()])
        self.assertEqual(json.loads(urlopen.call_args.args[0].data)["reply_to"], ["team@cloudforkids.co.ke"])


@override_settings(RESEND_WEBHOOK_SECRET=SECRET)
class WebhookTests(TestCase):
    def post(self, event, secret=SECRET, stamp=None):
        body = json.dumps(event).encode()
        msg_id, stamp = "msg_1", str(stamp or int(time.time()))
        key = base64.b64decode(secret.split("_", 1)[1])
        sig = base64.b64encode(hmac.new(key, f"{msg_id}.{stamp}.".encode() + body, hashlib.sha256).digest()).decode()
        return self.client.post(reverse("resend_webhook"), body, content_type="application/json",
                                HTTP_SVIX_ID=msg_id, HTTP_SVIX_TIMESTAMP=stamp, HTTP_SVIX_SIGNATURE=f"v1,{sig}")

    def test_bad_or_old_signatures_are_refused(self):
        event = {"type": "email.bounced", "data": {"to": ["x@example.com"]}}
        other = "whsec_" + base64.b64encode(b"someone-else").decode()
        self.assertEqual(self.post(event, secret=other).status_code, 401)
        self.assertEqual(self.post(event, stamp=int(time.time()) - 3600).status_code, 401)
        self.assertFalse(EmailSuppression.objects.exists())

    def test_delivery_and_opens_are_recorded(self):
        log = EmailLog.objects.create(to="mum@example.com", subject="Hi", resend_id="re_1")
        self.post({"type": "email.delivered", "data": {"email_id": "re_1", "to": ["mum@example.com"]}})
        self.post({"type": "email.opened", "data": {"email_id": "re_1", "to": ["mum@example.com"]}})
        log.refresh_from_db()
        self.assertEqual(log.status, "delivered")
        self.assertIsNotNone(log.opened_at)

    def test_hard_bounce_blocks_the_address_soft_bounce_does_not(self):
        self.post({"type": "email.bounced", "data": {"to": ["gone@example.com"], "bounce": {"type": "Permanent", "message": "No such user"}}})
        self.post({"type": "email.bounced", "data": {"to": ["full@example.com"], "bounce": {"type": "Transient"}}})
        self.assertEqual(list(EmailSuppression.objects.values_list("email", flat=True)), ["gone@example.com"])

    def test_spam_complaint_turns_off_optional_emails(self):
        mum = make("mum", "parent")
        self.post({"type": "email.complained", "data": {"to": ["MUM@example.com"]}})
        mum.refresh_from_db()
        self.assertFalse(mum.email_notifications)
        self.assertFalse(EmailSuppression.objects.exists())  # password resets still reach her

    @override_settings(RESEND_WEBHOOK_SECRET="")
    def test_without_a_secret_nothing_is_accepted(self):
        self.assertEqual(self.client.post(reverse("resend_webhook"), "{}", content_type="application/json").status_code, 503)


class ConfirmationTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_welcome_email_carries_the_confirm_link(self):
        self.client.post(reverse("accounts:signup"), {
            "username": "newbie", "first_name": "New", "last_name": "Bie", "email": "newbie@example.com", "role": "parent",
            "password1": PASSWORD, "password2": PASSWORD, "accept_terms": "on"})
        user = User.objects.get(username="newbie")
        self.assertFalse(user.email_verified)
        self.assertContains(self.client.get(reverse("family:home"), follow=True), "Please confirm your email address")
        body = mail.outbox[0].body
        self.assertIn("Confirm my email", body)
        link = next(w for w in body.split() if "/confirm-email/" in w)
        self.client.get(link.split("cloudforkids.co.ke")[-1].split("testserver")[-1], follow=True)
        user.refresh_from_db()
        self.assertTrue(user.email_verified)
        self.assertNotContains(self.client.get(reverse("family:home"), follow=True), "Please confirm your email address")

    def test_link_for_an_old_address_does_not_confirm_the_new_one(self):
        user = make("kid", email_verified=False)
        link = notify.confirm_url(user).split(notify.site_url())[-1]
        User.objects.filter(pk=user.pk).update(email="new@example.com")
        self.client.get(link)
        user.refresh_from_db()
        self.assertFalse(user.email_verified)

    def test_send_again_is_limited(self):
        user = make("kid", email_verified=False)
        self.client.force_login(user)
        for _ in range(5):
            self.client.post(reverse("accounts:resend_confirmation"))
        self.assertEqual(len(mail.outbox), 3)

    def test_existing_accounts_count_as_confirmed(self):
        from django.db import connection
        from django.db.migrations.loader import MigrationLoader

        migration = MigrationLoader(connection).get_migration("accounts", "0011_email_preferences")
        added = next(op for op in migration.operations if getattr(op, "name", "") == "email_verified" and op.__class__.__name__ == "AddField")
        self.assertTrue(added.field.default)


class AccountAlertTests(TestCase):
    def test_password_change_sends_an_alert(self):
        user = make("kid")
        with self.captureOnCommitCallbacks(execute=True):
            user.set_password("Another-Pass-77!")
            user.save()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("password was changed", mail.outbox[0].subject)
        self.assertIn(reverse("accounts:password_reset"), mail.outbox[0].body)

    def test_new_accounts_and_other_saves_send_nothing(self):
        with self.captureOnCommitCallbacks(execute=True):
            user = make("kid")
            user.first_name = "Kiddo"
            user.save()
        self.assertEqual(len(mail.outbox), 0)

    def test_linking_a_parent_tells_both(self):
        kid, mum = make("kid"), make("mum", "parent")
        cache.clear()
        self.client.force_login(mum)
        self.client.post(reverse("family:add"), {"username": "kid", "code": LearnerProfile.objects.get(user=kid).family_code})
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), ["kid@example.com", "mum@example.com"])
        self.assertTrue(any("can now see your progress" in m.subject for m in mail.outbox))


class FamilyEmailTests(TestCase):
    def setUp(self):
        self.kid, self.mum = make("kid"), make("mum", "parent")
        ParentLink.objects.create(parent=self.mum, child=self.kid)

    def finish_lesson(self, when=None):
        from courses.models import Course, Enrollment, LessonCompletion

        course = Course.objects.first()
        enrollment, _ = Enrollment.objects.get_or_create(learner=self.kid, course=course)
        lesson = course.lessons.exclude(pk__in=enrollment.completions.values("lesson")).first() if hasattr(enrollment, "completions") else course.lessons.first()
        done = LessonCompletion.objects.create(enrollment=enrollment, lesson=lesson)
        if when:
            LessonCompletion.objects.filter(pk=done.pk).update(completed_at=when)
        return enrollment

    def test_new_badge_is_celebrated_with_the_family(self):
        from courses.badges import check_and_award_badges

        self.finish_lesson()
        check_and_award_badges(self.kid)
        subjects = {m.to[0]: m.subject for m in mail.outbox}
        self.assertEqual(subjects["kid@example.com"], "You earned a new badge: First Lesson")
        self.assertEqual(subjects["mum@example.com"], "Kid earned a new badge: First Lesson")
        mail.outbox.clear()
        check_and_award_badges(self.kid)  # nothing new, nothing sent
        self.assertEqual(len(mail.outbox), 0)

    def test_celebrations_respect_the_setting(self):
        from courses.badges import check_and_award_badges

        User.objects.filter(pk=self.mum.pk).update(email_celebrations=False)
        self.finish_lesson()
        check_and_award_badges(self.kid)
        self.assertEqual([m.to for m in mail.outbox], [["kid@example.com"]])

    def test_certificate_email_links_to_the_certificate(self):
        from billing import services
        from billing.models import Plan

        services.grant(self.kid, Plan.objects.get(slug="core"))
        enrollment = self.finish_lesson()
        with mock.patch.object(services, "course_finished", return_value=True):
            cert = services.issue_certificate(self.kid, enrollment)
        certificate_mails = [m for m in mail.outbox if "certificate" in m.subject]
        self.assertEqual(len(certificate_mails), 2)
        self.assertIn(reverse("billing:certificate", args=[cert.code]), certificate_mails[0].body)

    def test_cancelled_mpesa_payment_sends_a_try_again_email(self):
        from billing import services
        from billing.models import Payment, Plan

        payment = Payment.objects.create(learner=self.kid, payer=self.mum, plan=Plan.objects.get(slug="core"), amount=4000,
                                         phone="254712345678", checkout_request_id="ws_1")
        services.settle(payment, "1032", "Request cancelled by user")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["mum@example.com"])
        self.assertIn("did not go through", mail.outbox[0].subject)
        self.assertIn("cancelled on the phone", mail.outbox[0].body)
        self.assertIn(f"/plans/core/checkout/?learner={self.kid.pk}", mail.outbox[0].body)
        services.settle(payment, "1032", "again")  # a second callback sends nothing more
        self.assertEqual(len(mail.outbox), 1)

    def test_monthly_report_once_and_only_early_in_the_month(self):
        tz = timezone.get_current_timezone()
        now = timezone.make_aware(datetime(2026, 11, 2, 9, 0), tz)
        self.finish_lesson(when=timezone.make_aware(datetime(2026, 10, 15, 12, 0), tz))
        self.assertEqual(notify.run_monthly_reports(now=now + timedelta(days=10)), 0)
        self.assertEqual(notify.run_monthly_reports(now=now), 1)
        self.assertEqual(notify.run_monthly_reports(now=now), 0)
        message = mail.outbox[0]
        self.assertEqual(message.subject, "October 2026 on Cloud for Kids")
        self.assertIn("lessons finished 1, labs 0", message.body)

    def test_kiswahili_reader_gets_kiswahili(self):
        User.objects.filter(pk=self.mum.pk).update(language="sw")
        self.mum.refresh_from_db()
        notify.send_parent_linked(self.mum, self.kid)
        sw = next(m for m in mail.outbox if m.to == ["mum@example.com"])
        self.assertEqual(sw.subject, "Sasa unamfuatilia Kid")
        self.assertIn("Mipangilio ya barua pepe", sw.body)
        self.assertIn('lang="sw"', sw.alternatives[0][0])

    def test_class_emails_follow_the_class_setting(self):
        teacher = make("teach", "facilitator")
        room = Classroom.objects.create(facilitator=teacher, name="Club")
        ClassMembership.objects.create(classroom=room, learner=self.kid)
        User.objects.filter(pk=self.kid.pk).update(email_class=False)
        self.client.force_login(teacher)
        self.client.post(reverse("messaging:compose"), {"classroom": room.pk, "to": "class", "subject": "Hello", "body": "Read lesson 2."})
        self.assertEqual([m.to for m in mail.outbox], [["mum@example.com"]])
        headers = mail.outbox[0].extra_headers
        self.assertIn("/one-click/", headers["List-Unsubscribe"])
        self.assertEqual(headers["List-Unsubscribe-Post"], "List-Unsubscribe=One-Click")


class LanguageTests(TestCase):
    def test_switching_the_site_language_switches_the_email_language(self):
        kid = make("kid")
        self.client.force_login(kid)
        self.client.cookies["django_language"] = "sw"
        self.client.get(reverse("dashboard:home"))
        kid.refresh_from_db()
        self.assertEqual(kid.language, "sw")

    def test_every_email_exists_in_both_languages(self):
        for kind, entry in T.EMAILS.items():
            for field in entry["en"]:
                self.assertIn(field, entry["sw"], f"{kind} has no Kiswahili {field}")


class PreviewPageTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("boss", "boss@example.com", PASSWORD, role="admin")
        self.client.force_login(self.admin)

    def test_every_email_previews_in_both_languages(self):
        url = reverse("tools:email_previews")
        for kind in T.EMAILS:
            if kind == "confirm_line":
                continue
            for lang in ("en", "sw"):
                response = self.client.get(url, {"kind": kind, "lang": lang})
                self.assertEqual(response.status_code, 200, f"{kind} {lang}")
                self.assertNotIn("{", response.context["subject"], f"{kind} {lang} has an unfilled placeholder")
                self.assertNotIn("{", response.context["text"].replace("{%", ""), f"{kind} {lang} has an unfilled placeholder")

    def test_send_me_a_test(self):
        self.client.post(reverse("tools:email_preview_send"), {"kind": "weekly", "lang": "sw"})
        self.assertEqual(mail.outbox[0].to, ["boss@example.com"])
        self.assertTrue(mail.outbox[0].subject.startswith("[Preview] Wiki ya mtoto wako"))

    def test_preview_page_is_for_staff_only(self):
        self.client.force_login(make("kid"))
        self.assertNotEqual(self.client.get(reverse("tools:email_previews")).status_code, 200)
