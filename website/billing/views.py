import json
import logging
import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.models import ParentLink, User

from . import access, mpesa, services
from .models import Certificate, Payment, Plan

logger = logging.getLogger(__name__)

FEATURE_ROWS = [
    ("Price", lambda p: f"KES {p.price_kes:,}"),
    ("Duration", lambda p: f"{p.weeks} weeks"),
    ("Target level", lambda p: p.target_level),
    ("Course access", lambda p: "All platform courses" if p.all_courses else "Courses in your own programme"),
    ("Hands-on labs", lambda p: {"none": "None", "guided": "Guided labs included", "unlimited": "Unlimited cloud sandbox labs"}[p.labs]),
    ("Quizzes & tests", lambda p: "Unlimited quizzes & module exams" if p.quizzes else "None"),
    ("AI assistant / tutor", lambda p: "Dedicated AI learning assistant" if p.ai_assistant else "Not included"),
    ("Project work", lambda p: p.project),
    ("Credential", lambda p: p.get_credential_display()),
]


def _children(parent):
    return [link.child for link in ParentLink.objects.filter(parent=parent).select_related("child")]


def _page(request, template, context):
    """Billing pages sit inside the parent portal for parents and the learner area for everyone else."""
    if request.user.role == User.Role.PARENT:
        context.setdefault("children", _children(request.user))
        context.setdefault("nav", "plan")
        context["base_template"] = "parent/base.html"
    else:
        context.setdefault("nav", "plan")
        context["base_template"] = "learner/base.html"
    return render(request, template, context)


def _buyable_learners(user):
    """Learners this user may buy a plan for: themselves (a learner) or their linked children (a parent)."""
    if user.role == User.Role.LEARNER:
        return [user]
    if user.role == User.Role.PARENT:
        return _children(user)
    return []


def pricing(request):
    plans = list(Plan.objects.filter(is_active=True))
    current = access.current_plan(request.user) if request.user.is_authenticated else None
    return render(
        request,
        "billing/pricing.html",
        {
            "plans": plans,
            "current": current,
            "rows": [(label, [fn(p) for p in plans]) for label, fn in FEATURE_ROWS],
        },
    )


def checkout(request, slug):
    plan = get_object_or_404(Plan, slug=slug, is_active=True)
    if not request.user.is_authenticated:  # visitors create an account first, then come back here
        return redirect(f"{reverse('accounts:signup')}?{urlencode({'next': request.get_full_path()})}")
    learners = _buyable_learners(request.user)
    if not learners:
        if request.user.role == User.Role.PARENT:
            messages.info(request, "Link your child's account first, then choose a plan for them.")
            return redirect("family:add")
        messages.info(request, "Plans are bought by learners or their parents.")
        return redirect("billing:pricing")

    chosen_id = request.POST.get("learner") or request.GET.get("learner")
    learner = next((l for l in learners if str(l.pk) == str(chosen_id)), learners[0])
    phone = request.POST.get("phone", "").strip() or request.user.phone_number
    promo_code = (request.POST.get("promo") or request.GET.get("promo") or "").strip().upper()
    q = services.quote(plan, learner, request.user, promo_code)
    error = ""

    if request.method == "POST" and request.POST.get("action") != "apply":
        payment, error = _pay(request.user, learner, q, phone)
        if payment:
            return redirect("billing:payment", payment_id=payment.pk)

    return _page(
        request,
        "billing/checkout.html",
        {"plan": plan, "learners": learners, "learner": learner, "phone": phone, "error": error, "q": q, "promo": promo_code,
         "current": access.current_subscription(learner), "for_child": request.user.role == User.Role.PARENT,
         "applied": request.POST.get("action") == "apply"},
    )


def _pay(payer, learner, q, phone, **sponsor):
    """Start a payment for a quote. Returns (payment, error)."""
    if q.amount == 0:
        return services.start_payment(payer, learner, q, mpesa.normalize_phone(phone) or "", **sponsor), ""
    msisdn = mpesa.normalize_phone(phone)
    if msisdn is None:
        return None, "Enter a Safaricom number like 0712 345 678."
    if mpesa.configured():
        try:
            return services.start_payment(payer, learner, q, msisdn, **sponsor), ""
        except mpesa.MpesaError as exc:
            return None, f"M-Pesa could not start the payment: {exc}"
    if settings.DEBUG:  # local testing: the payment page offers "Simulate paid / cancel"
        payment = services._new_payment(q, learner, payer=payer, phone=msisdn, checkout_request_id=f"SIM-{secrets.token_hex(8)}", **sponsor)
        return payment, ""
    return None, "Online payment is not switched on yet. Please contact us and we will set up the plan for you."


def _can_see_payment(user, payment):
    """The payer, the learner, the learner's linked parents and staff."""
    if not user.is_authenticated:
        return False
    return (
        user.pk in (payment.payer_id, payment.learner_id) or access.has_full_access(user)
        or ParentLink.objects.filter(parent=user, child_id=payment.learner_id).exists()
    )


def _own_payment(request, payment_id):
    payment = get_object_or_404(Payment.objects.select_related("plan", "learner", "subscription", "payer"), pk=payment_id)
    if not _can_see_payment(request.user, payment):
        raise Http404
    return payment


def _status_context(payment, *, check_url, simulate_url, retry_url, receipt_url, done_url, done_label):
    return {
        "payment": payment, "check_url": check_url, "simulate_url": simulate_url, "retry_url": retry_url,
        "receipt_url": receipt_url, "done_url": done_url, "done_label": done_label,
        "simulate": settings.DEBUG and (payment.checkout_request_id or "").startswith("SIM-"),
    }


@login_required
def payment_status(request, payment_id):
    payment = _own_payment(request, payment_id)
    parent = request.user.role == User.Role.PARENT
    return _page(request, "billing/payment.html", _status_context(
        payment,
        check_url=reverse("billing:payment_check", args=[payment.pk]),
        simulate_url=reverse("billing:payment_simulate", args=[payment.pk]),
        retry_url=f"{reverse('billing:checkout', args=[payment.plan.slug])}?learner={payment.learner_id}",
        receipt_url=reverse("billing:receipt", args=[payment.pk]),
        done_url=reverse("billing:my_plan") if parent else reverse("dashboard:home"),
        done_label="See plans" if parent else "Start learning",
    ))


@login_required
def payment_check(request, payment_id):
    payment = services.refresh(_own_payment(request, payment_id))
    return JsonResponse({"status": payment.status, "label": payment.get_status_display(), "detail": payment.result_desc})


def _simulate(request, payment):
    """Local testing only (DEBUG, and M-Pesa not configured): pretend the payer answered the prompt."""
    if not (settings.DEBUG and (payment.checkout_request_id or "").startswith("SIM-")):
        raise Http404
    if request.POST.get("outcome") == "paid":
        services.settle(payment, "0", "Simulated payment", receipt=f"SIM{payment.pk:07d}", amount=payment.amount)
    else:
        services.settle(payment, "1032", "Simulated: cancelled by the payer")


@login_required
@require_POST
def payment_simulate(request, payment_id):
    payment = _own_payment(request, payment_id)
    _simulate(request, payment)
    return redirect("billing:payment", payment_id=payment.pk)


def _receipt_page(request, payment, back_url):
    if payment.status not in (Payment.Status.PAID, Payment.Status.REFUNDED):
        raise Http404
    from core.models import SiteSetting

    return render(request, "billing/receipt.html", {
        "payment": payment, "site": SiteSetting.objects.first(), "kra_pin": settings.BILLING_KRA_PIN, "back_url": back_url,
    })


@login_required
def receipt(request, payment_id):
    payment = _own_payment(request, payment_id)
    return _receipt_page(request, payment, reverse("billing:my_plan") if request.user.role in ("learner", "parent") else "")


# ---------------- sponsors (no account needed) ----------------

def _sponsored_learner(token):
    learner_id = services.read_sponsor_token(token)
    learner = User.objects.filter(pk=learner_id, role=User.Role.LEARNER, is_active=True).first() if learner_id else None
    if learner is None:
        raise Http404("This sponsor link is not valid any more. Ask the family for a new one.")
    return learner


def short_name(user):
    """First name and last initial: what strangers (sponsors, certificate checkers) see of a child."""
    if user.first_name and user.last_name:
        return f"{user.first_name} {user.last_name[:1]}."
    return user.first_name or user.username


def sponsor(request, token):
    """A page a family shares with a relative, friend or organisation who wants to pay for a learner's plan."""
    learner = _sponsored_learner(token)
    plans = list(Plan.objects.filter(is_active=True))
    data = request.POST if request.method == "POST" else {}
    chosen = next((p for p in plans if p.slug == (data.get("plan") or request.GET.get("plan"))), None) or next(
        (p for p in plans if p.slug == "core"), plans[0])
    form = {k: (data.get(k) or "").strip() for k in ("name", "email", "phone", "message")}
    error = ""
    if request.method == "POST":
        if not form["name"] or "@" not in form["email"]:
            error = "Please give your name and email so we can send your receipt."
        else:
            q = services.quote(chosen, learner)
            payment, error = _pay(
                None, learner, q, form["phone"], sponsor_name=form["name"][:120], sponsor_email=form["email"][:254],
                sponsor_message=form["message"][:300],
            )
            if payment:
                return redirect("billing:sponsor_payment", token=services.payment_token(payment))
    return render(request, "billing/sponsor.html", {
        "learner_name": short_name(learner), "plans": plans, "chosen": chosen, "form": form, "error": error,
        "current": access.current_subscription(learner),
    })


def _sponsor_payment(token):
    payment_id = services.read_payment_token(token)
    payment = Payment.objects.select_related("plan", "learner", "subscription").filter(pk=payment_id).first() if payment_id else None
    if payment is None or not payment.sponsor_email:
        raise Http404
    return payment


def sponsor_payment(request, token):
    payment = _sponsor_payment(token)
    context = _status_context(
        payment,
        check_url=reverse("billing:sponsor_payment_check", args=[token]),
        simulate_url=reverse("billing:sponsor_payment_simulate", args=[token]),
        retry_url="", receipt_url=reverse("billing:sponsor_receipt", args=[token]),
        done_url=reverse("core:home"), done_label="Back to Cloud for Kids",
    )
    context.update(base_template="base.html", sponsor_view=True, learner_name=short_name(payment.learner))
    return render(request, "billing/payment.html", context)


def sponsor_payment_check(request, token):
    payment = services.refresh(_sponsor_payment(token))
    return JsonResponse({"status": payment.status, "label": payment.get_status_display(), "detail": payment.result_desc})


@require_POST
def sponsor_payment_simulate(request, token):
    _simulate(request, _sponsor_payment(token))
    return redirect("billing:sponsor_payment", token=token)


def sponsor_receipt(request, token):
    return _receipt_page(request, _sponsor_payment(token), "")


def _token_ok(token):
    expected = settings.MPESA_CALLBACK_TOKEN
    return bool(expected) and secrets.compare_digest(token, expected)


def _body(request):
    try:
        return json.loads(request.body or b"{}")
    except ValueError:
        return {}


ACCEPTED = {"ResultCode": 0, "ResultDesc": "Accepted"}


@csrf_exempt
@require_POST
def mpesa_callback(request, token):
    """Safaricom posts the STK Push result here. Always answer 'accepted' so Daraja does not retry forever."""
    if not _token_ok(token):
        return HttpResponseForbidden()
    data = mpesa.parse_callback(_body(request))
    if data:
        payment = Payment.objects.filter(checkout_request_id=data["checkout_request_id"]).first()
        if payment is None:
            logger.warning("M-Pesa callback for unknown request %s", data["checkout_request_id"])
        else:
            payment = services.settle(payment, data["result_code"], data["result_desc"], data["receipt"], data["amount"])
            if data["receipt"] and not payment.mpesa_receipt and payment.status == Payment.Status.PAID:
                payment.mpesa_receipt = data["receipt"]  # settled earlier by a status query, which has no receipt
                payment.save(update_fields=["mpesa_receipt"])
    return JsonResponse(ACCEPTED)


@csrf_exempt
@require_POST
def b2c_result(request, token):
    """The outcome of a payout an admin sent."""
    if not _token_ok(token):
        return HttpResponseForbidden()
    result = mpesa.parse_result(_body(request))
    if result:
        services.settle_payout(result)
    return JsonResponse(ACCEPTED)


@csrf_exempt
@require_POST
def b2c_timeout(request, token):
    if not _token_ok(token):
        return HttpResponseForbidden()
    body = _body(request)
    result = mpesa.parse_result(body) or {
        "originator_id": str(body.get("OriginatorConversationID", "")),
        "conversation_id": str(body.get("ConversationID", "")),
        "result_desc": "Safaricom timed out",
    }
    services.payout_timed_out(result)
    return JsonResponse(ACCEPTED)


@csrf_exempt
@require_POST
def balance_result(request, token):
    if not _token_ok(token):
        return HttpResponseForbidden()
    result = mpesa.parse_result(_body(request))
    if result:
        services.record_balance(result)
    return JsonResponse(ACCEPTED)


@csrf_exempt
@require_POST
def balance_timeout(request, token):
    if not _token_ok(token):
        return HttpResponseForbidden()
    logger.warning("M-Pesa balance check timed out")
    return JsonResponse(ACCEPTED)


@login_required
def my_plan(request):
    """A learner's plan, or each linked child's plan for a parent."""
    user = request.user
    if user.role == User.Role.LEARNER:
        people, template = [user], "billing/my_plan.html"
    elif user.role == User.Role.PARENT:
        people, template = _children(user), "billing/family_plans.html"
    else:
        return redirect("billing:pricing")
    rows = []
    for person in people:
        sub = access.current_subscription(person)
        rows.append({
            "learner": person,
            "sub": sub,
            "upgrades": Plan.objects.filter(is_active=True, order__gt=sub.plan.order) if sub else Plan.objects.filter(is_active=True),
            "payments": Payment.objects.filter(learner=person).exclude(status=Payment.Status.PENDING).select_related("plan")[:10],
            "sponsor_url": request.build_absolute_uri(reverse("billing:sponsor", args=[services.sponsor_token(person)])),
            "certificates": Certificate.objects.filter(learner=person).select_related("course"),
        })
    context = {"rows": rows, "plans": Plan.objects.filter(is_active=True)}
    if user.role == User.Role.PARENT:
        context["children"] = people
    else:
        context["r"] = rows[0]
    return _page(request, template, context)


def certificate(request, code):
    """The printable certificate. Anyone with the code can open it, which is how it is verified."""
    cert = get_object_or_404(Certificate.objects.select_related("learner", "course__tier"), code=code.upper())
    learner = cert.learner
    owner = request.user.is_authenticated and (
        request.user.pk == learner.pk or ParentLink.objects.filter(parent=request.user, child=learner).exists()
        or access.has_full_access(request.user)
    )
    # Strangers verifying a certificate see the first name and last initial only (the learner is a child).
    name = (learner.get_full_name() or learner.username) if owner else short_name(learner)
    return render(request, "billing/certificate.html", {"cert": cert, "name": name, "owner": owner})
