import json
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import ParentLink, User
from courses.models import Course, Enrollment, LessonCompletion, Tier
from dashboard.models import Lab

from . import access, mpesa, services
from .models import Certificate, Payment, Plan, Subscription

PASSWORD = "pw-12345-Zq"
TOKEN = "callback-secret-123"
MPESA = dict(
    MPESA_CONSUMER_KEY="key", MPESA_CONSUMER_SECRET="secret", MPESA_SHORTCODE="174379", MPESA_PASSKEY="pass",
    MPESA_CALLBACK_TOKEN=TOKEN, MPESA_TILL_NUMBER="",
)


def learner(username, tier="foundational", plan=None):
    user = User.objects.create_user(username, password=PASSWORD, role="learner", first_name=username.title(), last_name="Otieno", email=f"{username}@example.com")
    user.learner_profile.tier = Tier.objects.get(slug=tier)
    user.learner_profile.save()
    if plan:
        services.grant(user, Plan.objects.get(slug=plan))
    return user


def callback(checkout_id, code=0, amount=2000, receipt="QWE123RTY"):
    stk = {"MerchantRequestID": "m-1", "CheckoutRequestID": checkout_id, "ResultCode": code, "ResultDesc": "done"}
    if code == 0:
        stk["CallbackMetadata"] = {"Item": [
            {"Name": "Amount", "Value": amount}, {"Name": "MpesaReceiptNumber", "Value": receipt},
            {"Name": "TransactionDate", "Value": 20261014120000}, {"Name": "PhoneNumber", "Value": 254712345678},
        ]}
    return json.dumps({"Body": {"stkCallback": stk}})


class PlanSeedTests(TestCase):
    def test_three_plans_match_the_price_list(self):
        plans = {p.slug: p for p in Plan.objects.all()}
        self.assertEqual([p.slug for p in Plan.objects.all()], ["starter", "core", "advanced"])
        self.assertEqual([plans[s].price_kes for s in ("starter", "core", "advanced")], [2000, 4000, 6000])
        self.assertTrue(all(p.weeks == 4 for p in plans.values()))
        self.assertFalse(plans["starter"].quizzes)
        self.assertEqual(plans["core"].labs, Plan.Labs.GUIDED)
        self.assertTrue(plans["advanced"].ai_assistant)

    def test_pricing_page_is_public(self):
        page = self.client.get(reverse("billing:pricing"))
        for text in ("Starter", "Core", "Advanced", "2,000", "4,000", "6,000", "Honors Certificate of Completion"):
            self.assertContains(page, text)


class AccessTests(TestCase):
    def setUp(self):
        self.course = Course.objects.get(slug="what-is-the-cloud-really")  # Foundational
        self.lesson = self.course.lessons.get(slug="data-storage-basics")
        self.other = Course.objects.get(slug="cloud-databases-web-apps")  # Advanced programme

    def test_no_plan_means_no_lessons(self):
        kid = learner("kid")
        self.client.force_login(kid)
        self.assertRedirects(self.client.get(self.lesson.get_absolute_url()), reverse("billing:my_plan"))
        self.assertRedirects(self.client.get(reverse("courses:enroll", args=[self.course.slug])), reverse("billing:my_plan"))
        self.assertFalse(Enrollment.objects.filter(learner=kid).exists())
        self.assertContains(self.client.get(self.course.get_absolute_url()), "Choose a plan to open these lessons")

    def test_starter_reads_own_programme_without_quizzes(self):
        kid = learner("kid", plan="starter")
        self.client.force_login(kid)
        page = self.client.get(self.lesson.get_absolute_url())
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, "mcq-question")
        self.assertNotContains(page, "quiz-cfg")
        # another programme's course is locked
        self.assertRedirects(self.client.get(self.other.lessons.first().get_absolute_url()), reverse("billing:my_plan"))
        # quizzes and the exam are closed
        check = self.client.post(reverse("courses:quiz_check", args=[self.course.slug, self.lesson.slug]), "{}", content_type="application/json")
        self.assertEqual(check.status_code, 403)
        self.assertRedirects(self.client.get(self.course.exam.get_absolute_url()), self.course.get_absolute_url())

    def test_starter_finishes_by_reading_and_gets_a_completion_certificate(self):
        kid = learner("kid", plan="starter")
        self.client.force_login(kid)
        lessons = self.course.teaching_lessons
        for lesson in lessons:
            reply = self.client.post(reverse("courses:mark_lesson_complete", args=[self.course.slug, lesson.slug]))
        self.assertRedirects(reply, self.course.get_absolute_url())  # skips the exam
        self.assertEqual(LessonCompletion.objects.filter(enrollment__learner=kid).count(), len(lessons))
        cert = Certificate.objects.get(learner=kid, course=self.course)
        self.assertEqual(cert.level, Plan.Credential.COMPLETION)

    def test_core_opens_everything_and_keeps_quizzes(self):
        kid = learner("kid", plan="core")
        self.client.force_login(kid)
        self.assertEqual(self.client.get(self.other.lessons.first().get_absolute_url()).status_code, 200)
        page = self.client.get(self.lesson.get_absolute_url())
        self.assertContains(page, "mcq-question")
        reply = self.client.post(reverse("courses:mark_lesson_complete", args=[self.course.slug, self.lesson.slug]))
        self.assertRedirects(reply, self.lesson.get_absolute_url())  # quiz must be passed first
        self.assertFalse(LessonCompletion.objects.filter(enrollment__learner=kid).exists())

    def test_core_certificate_needs_the_exam_and_is_verified(self):
        kid = learner("kid", plan="core")
        self.client.force_login(kid)
        enrollment = Enrollment.objects.create(learner=kid, course=self.course)
        for lesson in self.course.teaching_lessons:
            LessonCompletion.objects.create(enrollment=enrollment, lesson=lesson)
        self.assertIsNone(services.issue_certificate(kid, enrollment))
        LessonCompletion.objects.create(enrollment=enrollment, lesson=self.course.exam)
        self.assertEqual(services.issue_certificate(kid, enrollment).level, Plan.Credential.VERIFIED)
        # an upgrade raises the level of an existing certificate
        services.grant(kid, Plan.objects.get(slug="advanced"))
        self.assertEqual(services.issue_certificate(kid, enrollment).level, Plan.Credential.HONORS)

    def test_labs_by_plan(self):
        easy = Lab.objects.filter(level=1).first()
        hard = Lab.objects.filter(level=3).first()
        for plan, easy_ok, hard_ok in (("starter", False, False), ("core", True, False), ("advanced", True, True)):
            kid = learner(f"kid-{plan}", plan=plan)
            self.client.force_login(kid)
            self.assertEqual(self.client.get(reverse("dashboard:lab", args=[easy.slug])).status_code, 200 if easy_ok else 302, plan)
            self.assertEqual(self.client.get(reverse("dashboard:lab", args=[hard.slug])).status_code, 200 if hard_ok else 302, plan)
            done = self.client.post(reverse("dashboard:lab_complete", args=[hard.slug]))
            self.assertEqual(done.status_code, 200 if hard_ok else 403, plan)

    def test_teachers_see_everything_without_a_plan(self):
        teacher = User.objects.create_user("teach", password=PASSWORD, role="facilitator")
        self.client.force_login(teacher)
        self.assertEqual(self.client.get(self.other.lessons.first().get_absolute_url()).status_code, 200)
        self.assertTrue(access.can_open_lab(teacher, 3))

    def test_expired_plan_is_not_in_force(self):
        kid = learner("kid")
        Subscription.objects.create(learner=kid, plan=Plan.objects.get(slug="advanced"),
                                    starts_at=timezone.now() - timedelta(days=40), ends_at=timezone.now() - timedelta(days=12))
        self.assertIsNone(access.current_plan(kid))

    def test_best_current_plan_wins_and_renewals_stack(self):
        kid = learner("kid", plan="starter")
        services.grant(kid, Plan.objects.get(slug="core"))
        self.assertEqual(access.current_plan(kid).slug, "core")
        first = Subscription.objects.get(learner=kid, plan__slug="core")
        second = services.grant(kid, Plan.objects.get(slug="core"))
        self.assertEqual(second.starts_at, first.ends_at)


@override_settings(**MPESA)
class MpesaCheckoutTests(TestCase):
    def setUp(self):
        self.kid = learner("kid")
        self.client.force_login(self.kid)

    def checkout(self, plan="starter", **data):
        with mock.patch.object(mpesa, "stk_push", return_value=("m-1", "ws_CO_1")) as push:
            reply = self.client.post(reverse("billing:checkout", args=[plan]), {"phone": "0712 345 678", **data})
        return reply, push

    def test_phone_numbers_are_normalised(self):
        self.assertEqual(mpesa.normalize_phone("0712 345 678"), "254712345678")
        self.assertEqual(mpesa.normalize_phone("+254 112 345 678"), "254112345678")
        self.assertEqual(mpesa.normalize_phone("712345678"), "254712345678")
        self.assertIsNone(mpesa.normalize_phone("0812345678"))
        self.assertIsNone(mpesa.normalize_phone("12345"))

    def test_checkout_sends_stk_push_and_waits(self):
        reply, push = self.checkout()
        payment = Payment.objects.get()
        self.assertRedirects(reply, reverse("billing:payment", args=[payment.pk]))
        push.assert_called_once_with("254712345678", 2000, f"C4K{payment.pk}", "Starter plan")
        self.assertEqual((payment.status, payment.checkout_request_id, payment.amount), ("pending", "ws_CO_1", 2000))
        self.assertIsNone(access.current_plan(self.kid))

    def test_bad_phone_is_refused(self):
        reply = self.client.post(reverse("billing:checkout", args=["starter"]), {"phone": "123"})
        self.assertContains(reply, "Enter a Safaricom number")
        self.assertFalse(Payment.objects.exists())

    def test_daraja_error_is_shown(self):
        with mock.patch.object(mpesa, "stk_push", side_effect=mpesa.MpesaError("Invalid PhoneNumber")):
            reply = self.client.post(reverse("billing:checkout", args=["core"]), {"phone": "0712345678"})
        self.assertContains(reply, "Invalid PhoneNumber")
        self.assertEqual(Payment.objects.get().status, "failed")

    def test_successful_callback_activates_the_plan_once(self):
        self.checkout("core")
        url = reverse("billing:mpesa_callback", args=[TOKEN])
        for _ in range(2):  # Safaricom may send the same result twice
            reply = self.client.post(url, callback("ws_CO_1", amount=4000), content_type="application/json")
            self.assertEqual(reply.json()["ResultCode"], 0)
        payment = Payment.objects.get()
        self.assertEqual((payment.status, payment.mpesa_receipt), ("paid", "QWE123RTY"))
        self.assertEqual(Subscription.objects.filter(learner=self.kid).count(), 1)
        self.assertEqual(access.current_plan(self.kid).slug, "core")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("QWE123RTY", mail.outbox[0].body)
        self.assertContains(self.client.get(reverse("billing:payment", args=[payment.pk])), "Payment received!")

    def test_wrong_token_is_rejected(self):
        self.checkout()
        reply = self.client.post(reverse("billing:mpesa_callback", args=["guess"]), callback("ws_CO_1"), content_type="application/json")
        self.assertEqual(reply.status_code, 403)
        self.assertEqual(Payment.objects.get().status, "pending")

    def test_cancelled_and_underpaid(self):
        self.checkout()
        url = reverse("billing:mpesa_callback", args=[TOKEN])
        self.client.post(url, callback("ws_CO_1", code=1032), content_type="application/json")
        self.assertEqual(Payment.objects.get().status, "cancelled")
        Payment.objects.update(status="pending", checkout_request_id="ws_CO_2")
        self.client.post(url, callback("ws_CO_2", amount=10), content_type="application/json")
        self.assertEqual(Payment.objects.get().status, "failed")
        self.assertIsNone(access.current_plan(self.kid))

    def test_status_check_asks_daraja_when_no_callback_came(self):
        self.checkout()
        Payment.objects.update(created_at=timezone.now() - timedelta(minutes=1))
        with mock.patch.object(mpesa, "stk_query", return_value=("0", "The service request is processed successfully.")):
            data = self.client.get(reverse("billing:payment_check", args=[Payment.objects.get().pk])).json()
        self.assertEqual(data["status"], "paid")
        self.assertEqual(access.current_plan(self.kid).slug, "starter")

    def test_payments_are_private(self):
        self.checkout()
        payment = Payment.objects.get()
        self.client.force_login(learner("other"))
        self.assertEqual(self.client.get(reverse("billing:payment", args=[payment.pk])).status_code, 404)

    def test_parent_pays_only_for_linked_children(self):
        parent = User.objects.create_user("mum", password=PASSWORD, role="parent")
        stranger = learner("stranger")
        self.client.force_login(parent)
        self.assertRedirects(self.client.get(reverse("billing:checkout", args=["core"])), reverse("family:add"))
        ParentLink.objects.create(parent=parent, child=self.kid)
        self.checkout("core", learner=stranger.pk)
        payment = Payment.objects.get()
        self.assertEqual((payment.learner, payment.payer), (self.kid, parent))
        self.assertContains(self.client.get(reverse("billing:my_plan")), "Kid Otieno")


class SimulatedPaymentTests(TestCase):
    @override_settings(DEBUG=True, MPESA_CONSUMER_KEY="")
    def test_local_simulation_without_mpesa(self):
        kid = learner("kid")
        self.client.force_login(kid)
        self.client.post(reverse("billing:checkout", args=["advanced"]), {"phone": "0712345678"})
        payment = Payment.objects.get()
        self.assertContains(self.client.get(reverse("billing:payment", args=[payment.pk])), "Simulate paid")
        self.client.post(reverse("billing:payment_simulate", args=[payment.pk]), {"outcome": "paid"})
        self.assertEqual(access.current_plan(kid).slug, "advanced")

    @override_settings(DEBUG=False, MPESA_CONSUMER_KEY="")
    def test_production_without_mpesa_says_so(self):
        self.client.force_login(learner("kid"))
        reply = self.client.post(reverse("billing:checkout", args=["core"]), {"phone": "0712345678"})
        self.assertContains(reply, "Online payment is not switched on yet")
        self.assertFalse(Payment.objects.exists())


class CertificatePageTests(TestCase):
    def test_strangers_see_first_name_and_initial_only(self):
        kid = learner("amani", plan="core")
        cert = Certificate.objects.create(learner=kid, course=Course.objects.first(), level="verified")
        page = self.client.get(reverse("billing:certificate", args=[cert.code]))
        self.assertContains(page, "Amani O.")
        self.assertNotContains(page, "Amani Otieno")
        self.client.force_login(kid)
        self.assertContains(self.client.get(reverse("billing:certificate", args=[cert.code])), "Amani Otieno")
        self.assertEqual(self.client.get(reverse("billing:certificate", args=["NOPE"])).status_code, 404)


class CallbackParsingTests(TestCase):
    def test_parse(self):
        data = mpesa.parse_callback(json.loads(callback("abc", amount=6000)))
        self.assertEqual((data["checkout_request_id"], data["result_code"], data["receipt"], data["amount"]), ("abc", "0", "QWE123RTY", 6000))
        self.assertIsNone(mpesa.parse_callback({"hello": 1}))


class PlanPagesTests(TestCase):
    def test_learner_and_parent_pages_show_the_plan(self):
        kid = learner("kid", plan="core")
        Certificate.objects.create(learner=kid, course=Course.objects.first(), level="verified")
        Payment.objects.create(learner=kid, payer=kid, plan=Plan.objects.get(slug="core"), amount=4000, phone="254712345678",
                               status="paid", mpesa_receipt="ABC123")
        self.client.force_login(kid)
        page = self.client.get(reverse("billing:my_plan"))
        for text in ("Core", "Upgrade to Advanced", "Verified Certificate of Achievement", "ABC123"):
            self.assertContains(page, text)
        self.assertContains(self.client.get(reverse("billing:checkout", args=["advanced"])), "starts as soon as you pay")
        self.assertContains(self.client.get(reverse("dashboard:labs")), "Advanced unlocks the level 3")
        self.assertNotContains(self.client.get(reverse("dashboard:home")), "Choose a plan to open your lessons")

        parent = User.objects.create_user("mum", password=PASSWORD, role="parent")
        ParentLink.objects.create(parent=parent, child=kid)
        ParentLink.objects.create(parent=parent, child=learner("sis"))
        self.client.force_login(parent)
        home = self.client.get(reverse("family:home"))
        self.assertContains(home, "Core plan until")
        self.assertContains(home, "No plan yet")
        self.assertContains(self.client.get(reverse("family:child", args=[kid.pk])), "Renew or upgrade")
        self.assertContains(self.client.get(reverse("billing:checkout", args=["starter"])), "Who is this plan for?")

    def test_learner_without_plan_sees_the_banner(self):
        self.client.force_login(learner("kid"))
        self.assertContains(self.client.get(reverse("dashboard:home")), "Choose a plan to open your lessons")
        self.assertContains(self.client.get(reverse("billing:my_plan")), "No active plan")


class VisitorCheckoutTests(TestCase):
    def test_visitor_creates_an_account_then_lands_on_checkout(self):
        checkout = reverse("billing:checkout", args=["core"])
        reply = self.client.get(checkout)
        signup = f"{reverse('accounts:signup')}?next=%2Fplans%2Fcore%2Fcheckout%2F"
        self.assertRedirects(reply, signup)
        page = self.client.get(signup)
        self.assertContains(page, 'name="next" value="/plans/core/checkout/"')
        self.assertContains(page, "?next=/plans/core/checkout/")  # the "Log in" link keeps the way back
        born = timezone.localdate().replace(year=timezone.localdate().year - 15, day=1)
        reply = self.client.post(signup, {
            "username": "newbie", "first_name": "New", "last_name": "Bie", "email": "newbie@example.com", "role": "learner",
            "password1": PASSWORD + "x!", "password2": PASSWORD + "x!", "accept_terms": "on", "date_of_birth": born.isoformat(),
            "next": "/plans/core/checkout/",
        })
        self.assertRedirects(reply, checkout)
        page = self.client.get(checkout)
        self.assertContains(page, "Pay KES 4,000 with M-Pesa")
        self.assertContains(page, "Coming soon")
        self.assertContains(page, 'value="bank" disabled')

    def test_outside_next_is_ignored(self):
        born = timezone.localdate().replace(year=timezone.localdate().year - 15, day=1)
        reply = self.client.post(reverse("accounts:signup"), {
            "username": "newbie", "first_name": "New", "last_name": "Bie", "email": "newbie@example.com", "role": "learner",
            "password1": PASSWORD + "x!", "password2": PASSWORD + "x!", "accept_terms": "on", "date_of_birth": born.isoformat(),
            "next": "https://evil.example.com/",
        })
        self.assertRedirects(reply, reverse("dashboard:home"))
