import json
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User

from . import mpesa, services
from .models import MpesaBalance, Payout
from .tests import MPESA, PASSWORD, TOKEN

B2C = dict(MPESA, MPESA_INITIATOR_NAME="the API initiator", MPESA_SECURITY_CREDENTIAL="encrypted==",
           SITE_URL="https://cloudforkids.co.ke", MPESA_ENV="production")


def b2c_result(originator, code=0, receipt="SJK123ABC"):
    result = {"ResultType": 0, "ResultCode": code, "ResultDesc": "done", "OriginatorConversationID": originator,
              "ConversationID": "AG_1", "TransactionID": receipt}
    if code == 0:
        result["ResultParameters"] = {"ResultParameter": [
            {"Key": "TransactionAmount", "Value": 50}, {"Key": "TransactionReceipt", "Value": receipt},
            {"Key": "ReceiverPartyPublicName", "Value": "254712345678 - Jane Wanjiru"},
            {"Key": "B2CWorkingAccountAvailableFunds", "Value": 950.0}, {"Key": "B2CUtilityAccountAvailableFunds", "Value": 120.5},
        ]}
    return json.dumps({"Result": result})


@override_settings(**B2C)
class PayoutTests(TestCase):
    def setUp(self):
        self.boss = User.objects.create_superuser("boss", "boss@example.com", PASSWORD)
        self.client.force_login(self.boss)

    def _send(self, follow=False, **extra):
        data = {"phone": "0712 345 678", "amount": "50", "reason": "Tutor fee", "command": "BusinessPayment", "confirm": "on", **extra}
        return self.client.post(reverse("admin:billing_payout_add"), data, follow=follow)

    def test_admin_sends_money_and_the_result_settles_it(self):
        with mock.patch.object(mpesa, "_request", return_value={"ResponseCode": "0", "ConversationID": "AG_1"}) as req, \
                mock.patch.object(mpesa, "access_token", return_value="tok"):
            reply = self._send()
        self.assertRedirects(reply, reverse("admin:billing_payout_changelist"))
        payout = Payout.objects.get()
        sent = req.call_args.args[1]
        self.assertEqual((sent["PartyA"], sent["PartyB"], sent["Amount"], sent["InitiatorName"]),
                         ("174379", "254712345678", 50, "the API initiator"))
        self.assertTrue(sent["ResultURL"].startswith("https://cloudforkids.co.ke/plans/pay/payout/result/"))
        self.assertEqual((payout.status, payout.conversation_id, payout.requested_by), ("sending", "AG_1", self.boss))

        url = reverse("billing:b2c_result", args=[TOKEN])
        for _ in range(2):  # Safaricom may send the result twice
            self.assertEqual(self.client.post(url, b2c_result(payout.originator_id), content_type="application/json").json()["ResultCode"], 0)
        payout.refresh_from_db()
        self.assertEqual((payout.status, payout.transaction_id, payout.receiver_name), ("paid", "SJK123ABC", "254712345678 - Jane Wanjiru"))
        self.assertEqual(MpesaBalance.objects.first().accounts["Working Account"], 950.0)

    def test_failed_result_and_timeout(self):
        bad = Payout.objects.create(phone="254712345678", amount=50, reason="x", originator_id="o-1")
        lost = Payout.objects.create(phone="254712345678", amount=60, reason="y", originator_id="o-2")
        self.client.post(reverse("billing:b2c_result", args=[TOKEN]), b2c_result("o-1", code=2001), content_type="application/json")
        self.client.post(reverse("billing:b2c_timeout", args=[TOKEN]), json.dumps({"OriginatorConversationID": "o-2"}), content_type="application/json")
        bad.refresh_from_db(), lost.refresh_from_db()
        self.assertEqual((bad.status, lost.status), ("failed", "unknown"))

    def test_safaricom_refusal_is_shown_and_kept(self):
        with mock.patch.object(mpesa, "b2c_send", side_effect=mpesa.MpesaError("Initiator information is invalid")):
            reply = self._send(follow=True)
        self.assertContains(reply, "M-Pesa refused the payout: Initiator information is invalid")
        self.assertEqual(Payout.objects.get().status, "failed")

    def test_form_checks(self):
        self.assertContains(self._send(phone="12345"), "Enter a Safaricom number")
        self.assertContains(self._send(amount="5"), "greater than or equal to 10")
        Payout.objects.create(phone="254712345678", amount=50, reason="x", originator_id="o-1")
        self.assertContains(self._send(), "in the last 5 minutes")
        self.assertEqual(Payout.objects.count(), 1)

    def test_only_super_admins_send(self):
        staff = User.objects.create_user("staff", password=PASSWORD, is_staff=True)
        staff.user_permissions.add(*__import__("django.contrib.auth.models", fromlist=["Permission"]).Permission.objects.filter(
            codename__endswith="_payout"))
        self.client.force_login(staff)
        self.assertEqual(self._send().status_code, 403)

    def test_callbacks_need_the_token(self):
        self.assertEqual(self.client.post(reverse("billing:b2c_result", args=["guess"]), "{}", content_type="application/json").status_code, 403)

    def test_balance_check(self):
        with mock.patch.object(mpesa, "_request", return_value={"ResponseCode": "0"}) as req, \
                mock.patch.object(mpesa, "access_token", return_value="tok"):
            self.client.post(reverse("admin:billing_payout_balance"))
        self.assertIn("/accountbalance/", req.call_args.args[0])
        body = json.dumps({"Result": {"ResultCode": 0, "ResultDesc": "ok", "ResultParameters": {"ResultParameter": [
            {"Key": "AccountBalance", "Value": "Working Account&KES&700.00&700.00&0.00&0.00|Utility Account&KES&1500.25&1500.25&0.00&0.00"},
        ]}}})
        self.client.post(reverse("billing:balance_result", args=[TOKEN]), body, content_type="application/json")
        self.assertEqual(MpesaBalance.objects.first().accounts, {"Working Account": 700.0, "Utility Account": 1500.25})
        self.assertContains(self.client.get(reverse("admin:billing_payout_changelist")), "1,500.25")


@override_settings(**B2C)
class DarajaRequestTests(TestCase):
    def test_stk_push_shows_the_account_name(self):
        with mock.patch.object(mpesa, "_request", return_value={"ResponseCode": "0", "CheckoutRequestID": "ws_1"}) as req, \
                mock.patch.object(mpesa, "access_token", return_value="tok"):
            mpesa.stk_push("254712345678", 2000, "C4K12", "Core plan")
        sent = req.call_args.args[1]
        self.assertEqual(sent["AccountReference"], "CloudForKids")
        self.assertTrue(sent["CallBackURL"].startswith("https://cloudforkids.co.ke/plans/pay/confirm/"))
        self.assertIn("api.safaricom.co.ke", req.call_args.args[0])

    def test_callback_addresses_avoid_words_daraja_blocks(self):
        for name in ("billing:mpesa_callback", "billing:b2c_result", "billing:b2c_timeout", "billing:balance_result", "billing:balance_timeout"):
            path = reverse(name, args=[TOKEN]).lower()
            for word in ("mpesa", "m-pesa", "safaricom", "query", "sql", "exec", "cmd"):
                self.assertNotIn(word, path, name)

    def test_funds_summary(self):
        Payout.objects.create(phone="254712345678", amount=300, reason="x", originator_id="a")
        Payout.objects.create(phone="254712345678", amount=99, reason="x", originator_id="b", status="failed")
        self.assertEqual(services.funds_summary()["sent"], 300)

    def test_status_query_still_processing_is_not_final(self):
        with mock.patch.object(mpesa, "_request", return_value={"ResultCode": "4999", "ResultDesc": "The transaction is still under processing"}), \
                mock.patch.object(mpesa, "access_token", return_value="tok"):
            self.assertIsNone(mpesa.stk_query("ws_1")[0])
