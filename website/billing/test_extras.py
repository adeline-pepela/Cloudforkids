"""Reminders, receipts, refunds and manual payments, reconciliation report, promo codes, sibling discount, sponsors."""

from datetime import timedelta
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import ParentLink, User

from . import access, mpesa, services
from .models import Payment, Plan, PromoCode, Subscription
from .reminders import run_plan_reminders
from .tests import MPESA, PASSWORD, TOKEN, callback, learner


def plan(slug):
    return Plan.objects.get(slug=slug)


def paid(kid, slug="core", code=""):
    q = services.quote(plan(slug), kid, kid, code)
    payment = services._new_payment(q, kid, payer=kid, phone="254712345678")
    return services.settle(payment, "0", "ok", receipt="RCP1", amount=payment.amount)


class ReminderTests(TestCase):
    def test_five_days_one_day_and_ended(self):
        kid = learner("kid")
        parent = User.objects.create_user("mum", email="mum@example.com", password=PASSWORD, role="parent")
        ParentLink.objects.create(parent=parent, child=kid)
        now = timezone.now()
        sub = Subscription.objects.create(learner=kid, plan=plan("core"), starts_at=now - timedelta(days=23), ends_at=now + timedelta(days=4, hours=12))
        self.assertEqual(run_plan_reminders(), 2)  # learner and parent
        self.assertEqual(run_plan_reminders(), 0)  # never twice
        self.assertIn("ends in 5 days", mail.outbox[0].subject)
        self.assertIn("checkout", mail.outbox[0].body)
        sub.ends_at = now + timedelta(hours=10)
        sub.save()
        self.assertEqual(run_plan_reminders(), 2)
        self.assertIn("ends tomorrow", mail.outbox[-1].subject)
        sub.ends_at = now - timedelta(hours=2)
        sub.save()
        self.assertEqual(run_plan_reminders(), 2)
        self.assertIn("has ended", mail.outbox[-1].subject)

    def test_no_reminder_when_already_renewed(self):
        kid = learner("kid")
        now = timezone.now()
        first = Subscription.objects.create(learner=kid, plan=plan("core"), starts_at=now - timedelta(days=24), ends_at=now + timedelta(days=4, hours=12))
        Subscription.objects.create(learner=kid, plan=plan("core"), starts_at=first.ends_at)
        self.assertEqual(run_plan_reminders(), 0)


class ReceiptAndRefundTests(TestCase):
    def test_receipt_page_and_privacy(self):
        kid = learner("kid")
        payment = paid(kid)
        self.client.force_login(kid)
        page = self.client.get(reverse("billing:receipt", args=[payment.pk]))
        for text in (payment.receipt_number, "RCP1", "KES 4,000", "Core plan"):
            self.assertContains(page, text)
        self.client.force_login(learner("other"))
        self.assertEqual(self.client.get(reverse("billing:receipt", args=[payment.pk])).status_code, 404)
        self.assertIn(payment.receipt_number, mail.outbox[0].body)

    def test_refund_ends_the_plan(self):
        kid = learner("kid")
        payment = paid(kid)
        self.assertEqual(access.current_plan(kid).slug, "core")
        self.assertTrue(services.refund(payment))
        self.assertFalse(services.refund(payment))  # only once
        payment.refresh_from_db()
        self.assertEqual(payment.status, "refunded")
        access.forget(kid)
        self.assertIsNone(access.current_plan(kid))

    def test_admin_records_cash_payment_and_refunds(self):
        admin_user = User.objects.create_superuser("boss", "b@example.com", PASSWORD, role="admin")
        kid = learner("kid")
        self.client.force_login(admin_user)
        reply = self.client.post(reverse("admin:billing_payment_add"), {
            "learner": kid.pk, "plan": plan("advanced").pk, "method": "cash", "amount": "5000", "reference": "CASH-7", "phone": "", "note": "Paid at the hub",
        })
        self.assertEqual(reply.status_code, 302, reply.content.decode()[:3000])
        payment = Payment.objects.get()
        self.assertEqual((payment.status, payment.method, payment.amount, payment.discount, payment.recorded_by), ("paid", "cash", 5000, 1000, admin_user))
        self.assertEqual(access.current_plan(kid).slug, "advanced")
        self.client.post(reverse("admin:billing_payment_changelist"), {"action": "refund_payments", "_selected_action": [payment.pk]})
        self.assertEqual(Payment.objects.get().status, "refunded")
        self.assertEqual(self.client.get(reverse("admin:billing_payment_change", args=[payment.pk])).status_code, 200)


class ReportTests(TestCase):
    def test_report_page_and_csv(self):
        admin_user = User.objects.create_superuser("boss", "b@example.com", PASSWORD, role="admin")
        kid = learner("kid", plan="starter")
        paid(kid, "core")  # an upgrade from Starter
        refunded = paid(learner("kid2"), "starter")
        services.refund(refunded)
        self.client.force_login(admin_user)
        page = self.client.get(reverse("tools:billing_report"))
        self.assertEqual(page.context["d"]["revenue"], 4000)
        self.assertEqual(page.context["d"]["refund_total"], 2000)
        self.assertEqual(page.context["d"]["upgrades"], 1)
        self.assertContains(page, "RCP1")
        csv_reply = self.client.get(reverse("tools:billing_report") + "?format=csv")
        body = csv_reply.content.decode()
        self.assertIn("Receipt no.", body)
        self.assertEqual(body.count("RCP1"), 2)
        self.client.force_login(kid)
        self.assertEqual(self.client.get(reverse("tools:billing_report")).status_code, 302)  # admins only


@override_settings(**MPESA)
class PromoAndSiblingTests(TestCase):
    def test_promo_code_rules(self):
        kid = learner("kid")
        promo = PromoCode.objects.create(code="launch20", percent_off=20, max_uses=1)
        promo.plans.add(plan("core"))
        self.assertEqual(services.quote(plan("core"), kid, kid, "LAUNCH20").amount, 3200)
        self.assertEqual(services.quote(plan("core"), kid, kid, "launch20 ").amount, 3200)  # case and spaces
        self.assertIn("does not apply", services.quote(plan("starter"), kid, kid, "LAUNCH20").promo_error)
        self.assertIn("not valid", services.quote(plan("core"), kid, kid, "NOPE").promo_error)
        PromoCode.objects.create(code="OLD", amount_off=500, valid_until=timezone.now() - timedelta(days=1))
        self.assertIn("not valid", services.quote(plan("core"), kid, kid, "OLD").promo_error)
        paid(kid, "core", code="LAUNCH20")
        self.assertIn("used up", services.quote(plan("core"), learner("kid2"), None, "LAUNCH20").promo_error)

    def test_checkout_applies_promo_and_charges_less(self):
        kid = learner("kid")
        PromoCode.objects.create(code="HALF", percent_off=50)
        self.client.force_login(kid)
        page = self.client.post(reverse("billing:checkout", args=["advanced"]), {"promo": "half", "action": "apply"})
        self.assertContains(page, "Promo HALF")
        self.assertContains(page, "Pay KES 3,000 with M-Pesa")
        with mock.patch.object(mpesa, "stk_push", return_value=("m", "ws_1")) as push:
            self.client.post(reverse("billing:checkout", args=["advanced"]), {"promo": "HALF", "phone": "0712345678"})
        self.assertEqual(push.call_args[0][1], 3000)
        payment = Payment.objects.get()
        self.assertEqual((payment.list_price, payment.discount, payment.amount, payment.promo.code), (6000, 3000, 3000, "HALF"))

    def test_free_code_starts_the_plan_without_mpesa(self):
        kid = learner("kid")
        PromoCode.objects.create(code="SCHOLAR", percent_off=100)
        self.client.force_login(kid)
        with mock.patch.object(mpesa, "stk_push") as push:
            reply = self.client.post(reverse("billing:checkout", args=["core"]), {"promo": "SCHOLAR"})
        push.assert_not_called()
        payment = Payment.objects.get()
        self.assertRedirects(reply, reverse("billing:payment", args=[payment.pk]))
        self.assertEqual((payment.status, payment.method, payment.amount), ("paid", "free", 0))
        self.assertEqual(access.current_plan(kid).slug, "core")

    def test_sibling_discount_for_second_child_and_best_discount_wins(self):
        parent = User.objects.create_user("mum", password=PASSWORD, role="parent")
        first, second = learner("first", plan="core"), learner("second")
        for child in (first, second):
            ParentLink.objects.create(parent=parent, child=child)
        q = services.quote(plan("core"), second, parent)
        self.assertEqual((q.discount, q.note), (400, "Sibling discount 10%"))
        self.assertEqual(services.quote(plan("core"), first, parent).discount, 0)  # no sibling on a plan
        self.assertEqual(services.quote(plan("core"), second, second).discount, 0)  # only when a parent pays
        PromoCode.objects.create(code="BIG", percent_off=25)
        q = services.quote(plan("core"), second, parent, "BIG")
        self.assertEqual((q.discount, q.note), (1000, "Promo BIG"))


@override_settings(**MPESA)
class SponsorTests(TestCase):
    def setUp(self):
        self.kid = learner("amani")
        self.token = services.sponsor_token(self.kid)

    def test_sponsor_pays_without_an_account(self):
        page = self.client.get(reverse("billing:sponsor", args=[self.token]))
        self.assertContains(page, "Amani O.")
        self.assertNotContains(page, "Otieno")
        with mock.patch.object(mpesa, "stk_push", return_value=("m", "ws_S1")):
            reply = self.client.post(reverse("billing:sponsor", args=[self.token]), {
                "plan": "advanced", "name": "Auntie Wanjiru", "email": "auntie@example.com", "phone": "0722000000", "message": "Go Amani!",
            })
        payment = Payment.objects.get()
        self.assertIsNone(payment.payer)
        self.assertEqual((payment.sponsor_name, payment.amount), ("Auntie Wanjiru", 6000))
        status_url = reply.url
        self.assertContains(self.client.get(status_url), "Check your phone")
        self.client.post(reverse("billing:mpesa_callback", args=[TOKEN]), callback("ws_S1", amount=6000), content_type="application/json")
        self.assertEqual(access.current_plan(self.kid).slug, "advanced")
        self.assertContains(self.client.get(status_url), "Thank you for your gift!")
        receipt = self.client.get(reverse("billing:sponsor_receipt", args=[status_url.rstrip("/").rsplit("/", 1)[1]]))
        self.assertContains(receipt, "Auntie Wanjiru (sponsor)")
        self.assertContains(receipt, "Amani O.")
        subjects = [m.subject for m in mail.outbox]
        self.assertIn("Thank you for sponsoring a learner", subjects)
        family = next(m for m in mail.outbox if m.to == ["amani@example.com"])
        self.assertIn("gift from Auntie Wanjiru", family.body)

    def test_bad_links_and_missing_details(self):
        self.assertEqual(self.client.get(reverse("billing:sponsor", args=["forged"])).status_code, 404)
        self.assertEqual(self.client.get(reverse("billing:sponsor_receipt", args=["forged"])).status_code, 404)
        reply = self.client.post(reverse("billing:sponsor", args=[self.token]), {"plan": "core", "name": "", "email": "x", "phone": "0712345678"})
        self.assertContains(reply, "Please give your name and email")
        self.assertFalse(Payment.objects.exists())

    def test_family_sees_the_sponsor_link(self):
        self.client.force_login(self.kid)
        self.assertContains(self.client.get(reverse("billing:my_plan")), "/plans/sponsor/")
