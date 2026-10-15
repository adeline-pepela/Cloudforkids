import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from accounts.models import CODE_ALPHABET


class Plan(models.Model):
    """A paid plan: Starter, Core or Advanced. What each one unlocks is read from these fields (see billing.access)."""

    class Labs(models.TextChoices):
        NONE = "none", "None"
        GUIDED = "guided", "Guided labs (levels 1-2)"
        UNLIMITED = "unlimited", "Every lab, including the cloud sandbox"

    class Credential(models.TextChoices):
        COMPLETION = "completion", "Certificate of Completion"
        VERIFIED = "verified", "Verified Certificate of Achievement"
        HONORS = "honors", "Honors Certificate of Completion"

    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=60, help_text="e.g. Starter")
    tagline = models.CharField(max_length=60, blank=True, help_text="e.g. Cloud Explorer")
    price_kes = models.PositiveIntegerField("Price (KES)")
    duration_days = models.PositiveSmallIntegerField(default=28, help_text="How long one payment lasts (4 weeks = 28)")
    target_level = models.CharField(max_length=80, help_text="e.g. Foundation / Beginner")
    focus = models.CharField(max_length=200, help_text="Core focus, one sentence")
    best_for = models.CharField(max_length=250)
    all_courses = models.BooleanField(
        default=False, help_text="Every course on the platform. Off = only the courses in the learner's own programme"
    )
    quizzes = models.BooleanField(default=False, help_text="Lesson quizzes and module exams")
    labs = models.CharField(max_length=10, choices=Labs.choices, default=Labs.NONE)
    ai_assistant = models.BooleanField("AI learning assistant", default=False)
    project = models.CharField(max_length=120, help_text="e.g. Showcase Project (portfolio-ready)")
    demo_day = models.BooleanField(default=False)
    live_classes = models.BooleanField(default=True, help_text="Live online classes (only checked when LIVE_CLASSES_REQUIRE_PLAN is on)")
    credential = models.CharField(max_length=12, choices=Credential.choices, default=Credential.COMPLETION)
    order = models.PositiveSmallIntegerField(default=0, help_text="Higher = more features. Used to compare plans")
    is_active = models.BooleanField(default=True, help_text="Untick to stop selling this plan")

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.name} (KES {self.price_kes:,})"

    @property
    def weeks(self):
        return self.duration_days // 7


def new_certificate_code():
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(10))


class Subscription(models.Model):
    """A learner's plan for one paid period. The best plan among a learner's current periods is the one in force."""

    class Source(models.TextChoices):
        MPESA = "mpesa", "M-Pesa"
        ADMIN = "admin", "Granted by an admin"

    learner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="subscriptions")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(blank=True, help_text="Leave blank to use the plan's length from the start date")
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.ADMIN)
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-ends_at"]

    def __str__(self):
        return f"{self.learner} - {self.plan.name} until {timezone.localtime(self.ends_at):%d %b %Y}"

    def save(self, *args, **kwargs):
        if not self.ends_at:
            self.ends_at = self.starts_at + timedelta(days=self.plan.duration_days)
        super().save(*args, **kwargs)

    @property
    def is_current(self):
        now = timezone.now()
        return self.starts_at <= now < self.ends_at

    @property
    def days_left(self):
        return max(0, (self.ends_at - timezone.now()).days)


class PromoCode(models.Model):
    """A discount code typed at checkout, e.g. LAUNCH20."""

    code = models.CharField(max_length=30, unique=True, help_text="Letters and numbers; not case sensitive")
    description = models.CharField(max_length=150, blank=True, help_text="For the team, e.g. Launch week campaign")
    percent_off = models.PositiveSmallIntegerField(default=0, help_text="e.g. 20 for 20% off. Use this or a fixed amount")
    amount_off = models.PositiveIntegerField("Amount off (KES)", default=0)
    plans = models.ManyToManyField(Plan, blank=True, help_text="Leave empty for every plan")
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    max_uses = models.PositiveIntegerField(null=True, blank=True, help_text="Paid uses allowed in total. Empty = no limit")
    once_per_learner = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    @property
    def uses(self):
        return self.payments.filter(status=Payment.Status.PAID).count()

    def discount_on(self, price):
        off = round(price * min(self.percent_off, 100) / 100) + self.amount_off
        return min(off, price)


class Payment(models.Model):
    """One plan payment: an M-Pesa STK Push (from a learner, parent or sponsor) or a payment recorded by an admin."""

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting for the payer"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled by the payer"
        REFUNDED = "refunded", "Refunded"

    class Method(models.TextChoices):
        MPESA = "mpesa", "M-Pesa"
        CASH = "cash", "Cash"
        BANK = "bank", "Bank transfer"
        FREE = "free", "Free (100% discount)"
        OTHER = "other", "Other"

    learner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="plan_payments")
    payer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="payments_made",
        help_text="Who started the payment (the learner or a parent). Empty for sponsors and admin-recorded payments",
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="payments")
    method = models.CharField(max_length=10, choices=Method.choices, default=Method.MPESA)
    list_price = models.PositiveIntegerField(default=0, help_text="Plan price before discounts (KES)")
    discount = models.PositiveIntegerField(default=0, help_text="KES taken off")
    discount_note = models.CharField(max_length=100, blank=True, help_text="e.g. Promo LAUNCH20 or Sibling discount 10%")
    promo = models.ForeignKey(PromoCode, null=True, blank=True, on_delete=models.SET_NULL, related_name="payments")
    amount = models.PositiveIntegerField(help_text="KES actually charged")
    phone = models.CharField(max_length=15, blank=True, help_text="M-Pesa number, 2547XXXXXXXX")
    sponsor_name = models.CharField(max_length=120, blank=True)
    sponsor_email = models.EmailField(blank=True)
    sponsor_message = models.CharField(max_length=300, blank=True)
    reference = models.CharField(max_length=60, blank=True, help_text="Bank or cash reference for payments recorded by hand")
    note = models.CharField(max_length=200, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="payments_recorded",
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    merchant_request_id = models.CharField(max_length=60, blank=True)
    checkout_request_id = models.CharField(max_length=60, unique=True, null=True, blank=True)
    mpesa_receipt = models.CharField("M-Pesa receipt", max_length=30, blank=True)
    result_code = models.CharField(max_length=10, blank=True)
    result_desc = models.CharField(max_length=255, blank=True)
    subscription = models.OneToOneField(Subscription, null=True, blank=True, on_delete=models.SET_NULL, related_name="payment")
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"KES {self.amount:,} {self.plan.name} for {self.learner} ({self.get_status_display()})"

    @property
    def receipt_number(self):
        return f"C4K-{(self.paid_at or self.created_at):%Y}-{self.pk:05d}"

    @property
    def payer_label(self):
        if self.sponsor_name:
            return f"{self.sponsor_name} (sponsor)"
        if self.payer:
            return self.payer.get_full_name() or self.payer.username
        return "Recorded by Cloud for Kids"


class Payout(models.Model):
    """Money sent from the M-Pesa shortcode to a phone (B2C), started by an admin."""

    class Status(models.TextChoices):
        SENDING = "sending", "Sent, waiting for Safaricom"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        UNKNOWN = "unknown", "Timed out: check the M-Pesa statement"

    phone = models.CharField(max_length=15, help_text="M-Pesa number that receives the money, 2547XXXXXXXX")
    amount = models.PositiveIntegerField(help_text="KES")
    reason = models.CharField(max_length=100, help_text="Shown in the M-Pesa statement, e.g. Tutor fee October")
    command = models.CharField(max_length=20, default="BusinessPayment")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SENDING)
    originator_id = models.CharField(max_length=60, unique=True)
    conversation_id = models.CharField(max_length=60, blank=True)
    transaction_id = models.CharField("M-Pesa code", max_length=30, blank=True)
    receiver_name = models.CharField(max_length=120, blank=True, help_text="As registered with M-Pesa")
    result_code = models.CharField(max_length=10, blank=True)
    result_desc = models.CharField(max_length=255, blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="payouts_sent",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"KES {self.amount:,} to {self.phone} ({self.get_status_display()})"


class MpesaBalance(models.Model):
    """The shortcode's balances as Safaricom last reported them (from a balance check or a B2C result)."""

    accounts = models.JSONField(default=dict, help_text='e.g. {"Working Account": 700.0, "Utility Account": 1200.0}')
    source = models.CharField(max_length=30)
    reported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-reported_at"]
        get_latest_by = "reported_at"

    def __str__(self):
        return ", ".join(f"{k}: KES {v:,.2f}" for k, v in self.accounts.items()) or "No balances"


class Certificate(models.Model):
    """Issued when a learner finishes a course. The level depends on the learner's plan; it is raised, never lowered."""

    learner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="certificates")
    course = models.ForeignKey("courses.Course", on_delete=models.CASCADE, related_name="certificates")
    level = models.CharField(max_length=12, choices=Plan.Credential.choices)
    code = models.CharField(max_length=12, unique=True, default=new_certificate_code, editable=False)
    issued_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("learner", "course")
        ordering = ["-issued_at"]

    def __str__(self):
        return f"{self.get_level_display()}: {self.course} - {self.learner}"
