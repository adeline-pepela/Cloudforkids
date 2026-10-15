from datetime import timedelta

from django import forms
from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from accounts.models import User

from . import mpesa, services
from .models import Certificate, Payment, Payout, Plan, PromoCode, Subscription


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("name", "tagline", "price_kes", "duration_days", "all_courses", "quizzes", "labs", "ai_assistant", "credential", "is_active")
    list_editable = ("price_kes", "is_active")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    """Add a subscription here to give a learner a plan by hand without a payment (e.g. a sponsored pilot)."""

    list_display = ("learner", "plan", "starts_at", "ends_at", "source", "note")
    list_filter = ("plan", "source")
    search_fields = ("learner__username", "learner__first_name", "learner__last_name", "note")
    raw_id_fields = ("learner",)
    date_hierarchy = "ends_at"


class ManualPaymentForm(forms.ModelForm):
    """Recording money received outside the website (cash, bank transfer...). Saving it starts the plan."""

    learner = forms.ModelChoiceField(User.objects.filter(role=User.Role.LEARNER).order_by("first_name", "username"))
    method = forms.ChoiceField(choices=[c for c in Payment.Method.choices if c[0] in ("cash", "bank", "mpesa", "other")],
                               initial="cash", help_text="Use M-Pesa for money sent to the Paybill/Till outside the website")
    amount = forms.IntegerField(min_value=0, required=False, help_text="KES received. Leave empty for the plan's full price")

    class Meta:
        model = Payment
        fields = ("learner", "plan", "method", "amount", "reference", "phone", "note")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("created_at", "receipt_no", "learner", "plan", "amount", "discount_note", "method", "status", "mpesa_receipt", "paid_by")
    list_filter = ("status", "method", "plan", "promo")
    search_fields = ("learner__username", "learner__first_name", "phone", "mpesa_receipt", "reference", "checkout_request_id", "sponsor_name", "sponsor_email")
    date_hierarchy = "created_at"
    actions = ["refund_payments"]

    @admin.display(description="Receipt")
    def receipt_no(self, obj):
        if obj.status in (Payment.Status.PAID, Payment.Status.REFUNDED):
            return format_html('<a href="{}" target="_blank">{}</a>', services.receipt_url(obj), obj.receipt_number)
        return "-"

    @admin.display(description="Paid by")
    def paid_by(self, obj):
        return obj.payer_label

    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            kwargs["form"] = ManualPaymentForm
        return super().get_form(request, obj, **kwargs)

    def get_fields(self, request, obj=None):
        if obj is None:
            return ManualPaymentForm.Meta.fields
        return [f.name for f in Payment._meta.fields if f.name != "id"]

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ()
        return [f.name for f in Payment._meta.fields if f.name not in ("id", "note")]

    def save_model(self, request, obj, form, change):
        if change:
            return super().save_model(request, obj, form, change)
        data = form.cleaned_data
        amount = data["amount"] if data.get("amount") is not None else data["plan"].price_kes
        payment = services.record_manual_payment(
            data["learner"], data["plan"], amount, data["method"], reference=data.get("reference", ""),
            note=data.get("note", ""), recorded_by=request.user,
        )
        if data.get("phone"):
            payment.phone = data["phone"]
            payment.save(update_fields=["phone"])
        obj.__dict__.update(payment.__dict__)  # the admin's "added" message, log and redirect use the saved payment

    def save_related(self, request, form, formsets, change):
        if change:
            super().save_related(request, form, formsets, change)

    def has_delete_permission(self, request, obj=None):
        return False  # keep the money trail; refund instead

    @admin.action(description="Refund: mark refunded and end the plan (return the money in M-Pesa or the bank yourself)")
    def refund_payments(self, request, queryset):
        done = sum(services.refund(p) for p in queryset.filter(status=Payment.Status.PAID))
        self.message_user(request, f"{done} payment(s) marked refunded and their plans ended.", messages.SUCCESS if done else messages.WARNING)


class PayoutForm(forms.ModelForm):
    """Sending money from the M-Pesa shortcode to a phone. Saving the form sends it."""

    phone = forms.CharField(help_text="Safaricom number, e.g. 0712 345 678")
    amount = forms.IntegerField(min_value=mpesa.B2C_MIN, max_value=mpesa.B2C_MAX,
                                help_text=f"KES {mpesa.B2C_MIN} to {mpesa.B2C_MAX:,}. Safaricom adds its own charge")
    command = forms.ChoiceField(choices=[(c, c) for c in mpesa.B2C_COMMANDS], initial="BusinessPayment",
                                help_text="BusinessPayment for most payouts")
    confirm = forms.BooleanField(label="I have checked the number and the amount")

    class Meta:
        model = Payout
        fields = ("phone", "amount", "reason", "command")

    def clean_phone(self):
        phone = mpesa.normalize_phone(self.cleaned_data["phone"])
        if phone is None:
            raise forms.ValidationError("Enter a Safaricom number like 0712 345 678.")
        return phone

    def clean(self):
        data = super().clean()
        if not mpesa.payouts_configured():
            raise forms.ValidationError("Payouts are not set up: MPESA_INITIATOR_NAME and MPESA_SECURITY_CREDENTIAL are missing.")
        recent = Payout.objects.filter(
            phone=data.get("phone"), amount=data.get("amount"), created_at__gte=timezone.now() - timedelta(minutes=5),
        ).exclude(status=Payout.Status.FAILED)
        if data.get("phone") and recent.exists():
            raise forms.ValidationError("The same amount went to this number in the last 5 minutes. Check the list before sending again.")
        return data


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    """Money sent out by M-Pesa B2C. Only super admins can send; nothing can be edited or deleted afterwards."""

    list_display = ("created_at", "phone", "receiver_name", "amount", "reason", "status", "transaction_id", "result_desc", "requested_by")
    list_filter = ("status",)
    search_fields = ("phone", "receiver_name", "transaction_id", "reason", "conversation_id")
    date_hierarchy = "created_at"
    actions = ["mark_paid", "mark_failed"]
    change_list_template = "admin/billing/payout/change_list.html"

    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            kwargs["form"] = PayoutForm
        return super().get_form(request, obj, **kwargs)

    def get_fields(self, request, obj=None):
        if obj is None:
            return ("phone", "amount", "reason", "command", "confirm")
        return [f.name for f in Payout._meta.fields if f.name != "id"]

    def get_readonly_fields(self, request, obj=None):
        return () if obj is None else [f.name for f in Payout._meta.fields if f.name != "id"]

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser and obj is None  # the list and its actions, never editing a payout

    def has_delete_permission(self, request, obj=None):
        return False

    def add_view(self, request, form_url="", extra_context=None):
        if request.method == "GET":
            f = services.funds_summary()
            self.message_user(request, f"Collected on the website by M-Pesa: KES {f['collected']:,}. Sent out: KES {f['sent']:,}. "
                                       f"Left: KES {f['left']:,}." + (f" Last M-Pesa balance: {f['balance']}." if f["balance"] else ""),
                              messages.INFO)
        return super().add_view(request, form_url, extra_context)

    def save_model(self, request, obj, form, change):
        data = form.cleaned_data
        try:
            payout = services.send_payout(data["phone"], data["amount"], data["reason"], request.user, data["command"])
            self.message_user(request, f"KES {payout.amount:,} sent to {payout.phone}. The result appears here within a minute.")
        except mpesa.MpesaError as exc:
            payout = Payout.objects.filter(phone=data["phone"], requested_by=request.user).first()
            self.message_user(request, f"M-Pesa refused the payout: {exc}", messages.ERROR)
        obj.__dict__.update(payout.__dict__)

    def response_add(self, request, obj, post_url_continue=None):
        return redirect("admin:billing_payout_changelist")

    def get_urls(self):
        return [path("balance/", self.admin_site.admin_view(self.check_balance), name="billing_payout_balance")] + super().get_urls()

    def changelist_view(self, request, extra_context=None):
        extra_context = {**(extra_context or {}), "funds": services.funds_summary(),
                         "can_send": mpesa.payouts_configured() and request.user.is_superuser}
        return super().changelist_view(request, extra_context)

    def check_balance(self, request):
        if request.method != "POST" or not request.user.is_superuser:
            return redirect("admin:billing_payout_changelist")
        try:
            mpesa.balance_request()
            self.message_user(request, "Balance requested. Refresh this page in a minute to see it.")
        except mpesa.MpesaError as exc:
            self.message_user(request, f"M-Pesa refused the balance check: {exc}", messages.ERROR)
        return redirect("admin:billing_payout_changelist")

    def _resolve(self, request, queryset, status):
        done = queryset.filter(status__in=[Payout.Status.SENDING, Payout.Status.UNKNOWN]).update(
            status=status, completed_at=timezone.now(), result_desc=f"Set by {request.user} after checking the statement")
        self.message_user(request, f"{done} payout(s) updated.", messages.SUCCESS if done else messages.WARNING)

    @admin.action(description="Checked the M-Pesa statement: the money WAS sent")
    def mark_paid(self, request, queryset):
        self._resolve(request, queryset, Payout.Status.PAID)

    @admin.action(description="Checked the M-Pesa statement: the money was NOT sent")
    def mark_failed(self, request, queryset):
        self._resolve(request, queryset, Payout.Status.FAILED)


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "description", "percent_off", "amount_off", "valid_from", "valid_until", "used", "max_uses", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "description")
    filter_horizontal = ("plans",)

    @admin.display(description="Paid uses")
    def used(self, obj):
        return obj.uses


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = ("learner", "course", "level", "code", "issued_at")
    list_filter = ("level",)
    search_fields = ("learner__username", "learner__first_name", "code")
    raw_id_fields = ("learner",)
