"""Prices and discounts, turning payments into plans, refunds, payouts, sponsor links, and certificates."""

import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.db import transaction
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone

from core import notify

from . import access, mpesa
from .models import Certificate, MpesaBalance, Payment, Payout, Plan, PromoCode, Subscription

logger = logging.getLogger(__name__)

CREDENTIAL_RANK = {Plan.Credential.COMPLETION: 1, Plan.Credential.VERIFIED: 2, Plan.Credential.HONORS: 3}
QUERY_AFTER = timedelta(seconds=20)  # ask Daraja ourselves if no callback arrived by then
QUERY_EVERY = 15  # seconds between our own status queries for one payment
GIVE_UP_AFTER = timedelta(minutes=10)


SPONSOR_SALT = "c4k-sponsor"
SPONSOR_LINK_DAYS = 90
PAYMENT_LINK_SALT = "c4k-sponsor-payment"


# ---------------- prices and discounts ----------------

@dataclass
class Quote:
    plan: Plan
    list_price: int
    discount: int = 0
    note: str = ""
    promo: PromoCode = None
    promo_error: str = ""

    @property
    def amount(self):
        return self.list_price - self.discount


def find_promo(code, plan, learner):
    """(PromoCode, "") if the code can be used for this plan and learner, else (None, reason)."""
    code = (code or "").strip().upper()
    if not code:
        return None, ""
    promo = PromoCode.objects.filter(code=code, is_active=True).first()
    now = timezone.now()
    if promo is None or (promo.valid_from and now < promo.valid_from) or (promo.valid_until and now > promo.valid_until):
        return None, "That promo code is not valid."
    if promo.plans.exists() and not promo.plans.filter(pk=plan.pk).exists():
        return None, f"That promo code does not apply to the {plan.name} plan."
    if promo.max_uses is not None and promo.uses >= promo.max_uses:
        return None, "That promo code has been used up."
    if promo.once_per_learner and promo.payments.filter(learner=learner, status=Payment.Status.PAID).exists():
        return None, "This learner has already used that promo code."
    return promo, ""


def sibling_discount_applies(payer, learner):
    """A parent paying for a second (or third...) child who has a sibling on a current plan."""
    from accounts.models import ParentLink

    if payer is None or payer.role != "parent" or settings.SIBLING_DISCOUNT_PERCENT <= 0:
        return False
    siblings = ParentLink.objects.filter(parent=payer).exclude(child=learner).values_list("child_id", flat=True)
    now = timezone.now()
    return Subscription.objects.filter(learner_id__in=list(siblings), starts_at__lte=now, ends_at__gt=now).exists()


def quote(plan, learner, payer=None, promo_code=""):
    """The price to charge. Discounts do not stack: the bigger of the promo code and the sibling discount wins."""
    q = Quote(plan=plan, list_price=plan.price_kes)
    options = []
    if sibling_discount_applies(payer, learner):
        pct = settings.SIBLING_DISCOUNT_PERCENT
        options.append((round(plan.price_kes * pct / 100), f"Sibling discount {pct}%", None))
    promo, q.promo_error = find_promo(promo_code, plan, learner)
    if promo:
        options.append((promo.discount_on(plan.price_kes), f"Promo {promo.code}", promo))
    if options:
        q.discount, q.note, q.promo = max(options, key=lambda o: o[0])
        q.discount = min(q.discount, plan.price_kes)
    return q


def _new_payment(q, learner, **fields):
    return Payment.objects.create(
        learner=learner, plan=q.plan, list_price=q.list_price, discount=q.discount, discount_note=q.note, promo=q.promo,
        amount=q.amount, **fields,
    )


def start_payment(payer, learner, q, phone, **sponsor):
    """Create the Payment and send the STK Push. Raises mpesa.MpesaError if Safaricom refuses.
    A 100% discount needs no M-Pesa: the plan is given straight away."""
    if q.amount == 0:
        payment = _new_payment(q, learner, payer=payer, phone=phone, method=Payment.Method.FREE, **sponsor)
        return settle(payment, "0", q.note or "Free")
    payment = _new_payment(q, learner, payer=payer, phone=phone, **sponsor)
    try:
        merchant_id, checkout_id = mpesa.stk_push(phone, payment.amount, f"C4K{payment.pk}", f"{q.plan.name} plan")
    except mpesa.MpesaError as exc:
        payment.status = Payment.Status.FAILED
        payment.result_desc = str(exc)[:255]
        payment.save(update_fields=["status", "result_desc"])
        raise
    payment.merchant_request_id, payment.checkout_request_id = merchant_id, checkout_id
    payment.save(update_fields=["merchant_request_id", "checkout_request_id"])
    return payment


def _new_period_start(learner, plan):
    """A renewal of the same plan starts when the current period ends; anything else starts now."""
    now = timezone.now()
    latest = (
        Subscription.objects.filter(learner=learner, plan=plan, ends_at__gt=now).order_by("-ends_at").first()
    )
    return latest.ends_at if latest else now


def grant(learner, plan, *, source=Subscription.Source.ADMIN, note=""):
    sub = Subscription.objects.create(
        learner=learner, plan=plan, starts_at=_new_period_start(learner, plan), source=source, note=note
    )
    access.forget(learner)
    return sub


def settle(payment, result_code, result_desc="", receipt="", amount=None):
    """Record how a payment ended. Safe to call more than once (callback and status check can both arrive)."""
    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment.pk)
        if payment.status != Payment.Status.PENDING:
            return payment
        payment.result_code, payment.result_desc = str(result_code), (result_desc or "")[:255]
        if str(result_code) == "0":
            if amount is not None and int(float(amount)) < payment.amount:
                payment.status = Payment.Status.FAILED
                payment.result_desc = f"Paid {amount}, expected {payment.amount}"
                logger.error("M-Pesa payment %s underpaid: %s", payment.pk, payment.result_desc)
            else:
                by_mpesa = payment.method == Payment.Method.MPESA
                payment.status = Payment.Status.PAID
                payment.mpesa_receipt = receipt if by_mpesa else ""
                payment.paid_at = timezone.now()
                payment.subscription = grant(
                    payment.learner, payment.plan,
                    source=Subscription.Source.MPESA if by_mpesa else Subscription.Source.ADMIN,
                    note=(f"M-Pesa {receipt}" if by_mpesa else f"{payment.get_method_display()} {payment.reference}").strip(),
                )
        elif str(result_code) in mpesa.CANCELLED_CODES:
            payment.status = Payment.Status.CANCELLED
        else:
            payment.status = Payment.Status.FAILED
        payment.save()
    if payment.status == Payment.Status.PAID:
        send_receipt(payment)
    return payment


def refresh(payment):
    """If Safaricom's callback has not arrived yet, ask Daraja directly."""
    if payment.status != Payment.Status.PENDING or not payment.checkout_request_id:
        return payment
    age = timezone.now() - payment.created_at
    if age < QUERY_AFTER or not cache.add(f"mpesa-query-{payment.pk}", 1, QUERY_EVERY):
        return payment  # too early, or asked Daraja moments ago (it limits how often we may ask)
    try:
        code, desc = mpesa.stk_query(payment.checkout_request_id)
    except mpesa.MpesaError:
        code, desc = None, ""
    if code is None:
        if age > GIVE_UP_AFTER:
            return settle(payment, "1037", "No answer from the phone")
        return payment
    # A query does not return the receipt number; the callback fills it in if it arrives later.
    return settle(payment, code, desc)


def record_manual_payment(learner, plan, amount, method, *, reference="", note="", recorded_by=None):
    """A cash, bank or other payment an admin received outside the website. The plan starts at once."""
    payment = Payment.objects.create(
        learner=learner, plan=plan, list_price=plan.price_kes, discount=max(0, plan.price_kes - amount),
        discount_note="Agreed price" if amount < plan.price_kes else "", amount=amount, method=method,
        reference=reference, note=note, recorded_by=recorded_by,
    )
    return settle(payment, "0", f"Recorded by {recorded_by}" if recorded_by else "Recorded by hand")


def refund(payment):
    """Mark a paid payment refunded and end the plan it bought. The money itself is returned in the M-Pesa portal or bank."""
    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment.pk)
        if payment.status != Payment.Status.PAID:
            return False
        now = timezone.now()
        payment.status, payment.refunded_at = Payment.Status.REFUNDED, now
        payment.save(update_fields=["status", "refunded_at"])
        sub = payment.subscription
        if sub and sub.ends_at > now:
            sub.ends_at = max(sub.starts_at, now)
            sub.note = f"{sub.note} (refunded)".strip()
            sub.save(update_fields=["ends_at", "note"])
        access.forget(payment.learner)
    return True


# ---------------- payouts (B2C) and balances ----------------

def send_payout(phone, amount, reason, requested_by=None, command="BusinessPayment"):
    """Send money from the shortcode to a phone. Returns the Payout (status "sending" until Safaricom's result arrives).
    Raises mpesa.MpesaError if Safaricom refuses the request; the Payout is then kept as failed."""
    payout = Payout.objects.create(
        phone=phone, amount=amount, reason=reason[:100], command=command, requested_by=requested_by,
        originator_id=f"C4K-{uuid.uuid4().hex}",
    )
    try:
        payout.conversation_id = mpesa.b2c_send(phone, amount, reason, "Cloud for Kids", payout.originator_id, command)
    except mpesa.MpesaError as exc:
        payout.status, payout.result_desc, payout.completed_at = Payout.Status.FAILED, str(exc)[:255], timezone.now()
        payout.save(update_fields=["status", "result_desc", "completed_at"])
        raise
    payout.save(update_fields=["conversation_id"])
    logger.info("B2C payout %s of KES %s to %s sent by %s", payout.pk, amount, phone, requested_by)
    return payout


def _find_payout(result):
    if result.get("originator_id"):
        payout = Payout.objects.filter(originator_id=result["originator_id"]).first()
        if payout:
            return payout
    if result.get("conversation_id"):
        return Payout.objects.filter(conversation_id=result["conversation_id"]).first()
    return None


B2C_FUNDS = (
    ("Working Account", "B2CWorkingAccountAvailableFunds"),
    ("Utility Account", "B2CUtilityAccountAvailableFunds"),
    ("Charges Paid Account", "B2CChargesPaidAccountAvailableFunds"),
)


def settle_payout(result):
    """Record Safaricom's B2C result. Safe to call more than once."""
    payout = _find_payout(result)
    if payout is None:
        logger.warning("B2C result for unknown payout %s / %s", result["originator_id"], result["conversation_id"])
        return None
    params = result["params"]
    with transaction.atomic():
        payout = Payout.objects.select_for_update().get(pk=payout.pk)
        if payout.status in (Payout.Status.PAID, Payout.Status.FAILED):
            return payout
        payout.result_code, payout.result_desc = result["result_code"], result["result_desc"][:255]
        payout.transaction_id = str(params.get("TransactionReceipt") or result["transaction_id"] or "")[:30]
        payout.receiver_name = str(params.get("ReceiverPartyPublicName") or "")[:120]
        payout.status = Payout.Status.PAID if result["result_code"] == "0" else Payout.Status.FAILED
        payout.completed_at = timezone.now()
        payout.save()
    funds = {name: float(params[key]) for name, key in B2C_FUNDS if params.get(key) is not None}
    if funds:
        MpesaBalance.objects.create(accounts=funds, source="Payout result")
    return payout


def payout_timed_out(result):
    """Safaricom gave up waiting. The money may or may not have moved, so do not resend before checking the statement."""
    payout = _find_payout(result)
    if payout and payout.status == Payout.Status.SENDING:
        payout.status, payout.result_desc = Payout.Status.UNKNOWN, (result.get("result_desc") or "Safaricom timed out")[:255]
        payout.save(update_fields=["status", "result_desc"])
    return payout


def record_balance(result):
    if result["result_code"] != "0":
        logger.warning("Balance check failed: %s %s", result["result_code"], result["result_desc"])
        return None
    accounts = mpesa.parse_balances(result["params"].get("AccountBalance"))
    return MpesaBalance.objects.create(accounts=accounts, source="Balance check") if accounts else None


def funds_summary():
    """What came in through M-Pesa on the website and what has been sent out, shown on the payout form."""
    collected = Payment.objects.filter(method=Payment.Method.MPESA, status=Payment.Status.PAID).aggregate(t=Sum("amount"))["t"] or 0
    sent = Payout.objects.exclude(status=Payout.Status.FAILED).aggregate(t=Sum("amount"))["t"] or 0
    return {"collected": collected, "sent": sent, "left": collected - sent, "balance": MpesaBalance.objects.first()}


def receipt_url(payment):
    """The receipt page; sponsors (no account) get a private signed link."""
    if payment.sponsor_email and payment.payer is None:
        return reverse("billing:sponsor_receipt", args=[payment_token(payment)])
    return reverse("billing:receipt", args=[payment.pk])


def send_receipt(payment):
    sub = payment.subscription
    name = payment.learner.first_name or payment.learner.username
    lines = [p for p in (
        f"We received KES {payment.amount:,} for {name}'s {payment.plan.name} plan." if payment.amount
        else f"{name}'s {payment.plan.name} plan is free with {payment.discount_note}.",
        f"It is active until {timezone.localtime(sub.ends_at):%d %B %Y}." if sub else "",
    ) if p]
    bullets = [f"Receipt number: {payment.receipt_number}"]
    if payment.mpesa_receipt:
        bullets.append(f"M-Pesa code: {payment.mpesa_receipt}")
    if payment.discount:
        bullets.append(f"{payment.discount_note}: KES {payment.discount:,} off")
    family = {u for u in (payment.payer, payment.learner) if u and u.email}
    gift = []
    if payment.sponsor_name:
        family.update(link.parent for link in payment.learner.parent_links.select_related("parent") if link.parent.email)
        gift = [f"This plan is a gift from {payment.sponsor_name}."
                + (f" Their message: “{payment.sponsor_message}”" if payment.sponsor_message else "")]
    if family:
        notify.send_email(
            [u.email for u in family], f"Payment received: {payment.plan.name} plan", "Thank you! The plan is active",
            lines + gift, bullets=bullets,
            cta=("See the receipt", notify.absolute(reverse("billing:receipt", args=[payment.pk]))),
        )
    if payment.sponsor_email:
        notify.send_email(
            payment.sponsor_email, "Thank you for sponsoring a learner", f"Thank you, {payment.sponsor_name}!",
            [f"Your gift of KES {payment.amount:,} gives {name} the {payment.plan.name} plan on Cloud for Kids."] + lines[1:],
            bullets=bullets, cta=("See the receipt", notify.absolute(receipt_url(payment))),
        )


# ---------------- sponsor links ----------------

def sponsor_token(learner):
    return signing.dumps(learner.pk, salt=SPONSOR_SALT, compress=True)


def read_sponsor_token(token):
    try:
        return signing.loads(token, salt=SPONSOR_SALT, max_age=SPONSOR_LINK_DAYS * 86400)
    except signing.BadSignature:
        return None


def payment_token(payment):
    """Lets a sponsor (who has no account) follow their payment and open its receipt."""
    return signing.dumps(payment.pk, salt=PAYMENT_LINK_SALT, compress=True)


def read_payment_token(token):
    try:
        return signing.loads(token, salt=PAYMENT_LINK_SALT, max_age=365 * 86400)
    except signing.BadSignature:
        return None


# ---------------- certificates ----------------

def course_finished(user, enrollment):
    """With quizzes the module exam must be passed; on Starter (no quizzes) every lesson must be marked done."""
    if access.can_take_quizzes(user):
        return enrollment.is_complete
    teaching = {lesson.id for lesson in enrollment.course.teaching_lessons}
    return bool(teaching) and teaching <= enrollment.completed_lesson_ids


def issue_certificate(user, enrollment):
    """Issue (or raise the level of) the certificate for a finished course. Returns the certificate if new or upgraded."""
    plan = access.current_plan(user)
    if plan is None or not course_finished(user, enrollment):
        return None
    cert, created = Certificate.objects.get_or_create(
        learner=user, course=enrollment.course, defaults={"level": plan.credential}
    )
    if created:
        return cert
    if CREDENTIAL_RANK[plan.credential] > CREDENTIAL_RANK[cert.level]:
        cert.level = plan.credential
        cert.save(update_fields=["level"])
        return cert
    return None
