"""Resend's webhook (delivery, bounces, spam complaints) and the admin page that previews every email."""

import base64
import hashlib
import hmac
import json
import logging
import time

from django.conf import settings
from django.contrib import messages
from django.core.mail import EmailMultiAlternatives
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import email_text as T
from . import notify
from .models import EmailLog, EmailSuppression

logger = logging.getLogger(__name__)
TOLERANCE = 5 * 60  # seconds a webhook signature stays valid

STATUS_FOR = {
    "email.delivered": EmailLog.Status.DELIVERED,
    "email.delivery_delayed": EmailLog.Status.DELAYED,
    "email.bounced": EmailLog.Status.BOUNCED,
    "email.complained": EmailLog.Status.COMPLAINED,
}


def signature_ok(secret, headers, body):
    """Resend signs webhooks the Svix way: base64 HMAC-SHA256 of "id.timestamp.body" with the whsec_ secret."""
    msg_id, stamp, signatures = headers.get("svix-id", ""), headers.get("svix-timestamp", ""), headers.get("svix-signature", "")
    if not (secret and msg_id and stamp and signatures):
        return False
    try:
        if abs(time.time() - int(stamp)) > TOLERANCE:
            return False
        key = base64.b64decode(secret.split("_", 1)[1] if secret.startswith("whsec_") else secret)
    except (ValueError, TypeError):
        return False
    expected = base64.b64encode(hmac.new(key, f"{msg_id}.{stamp}.".encode() + body, hashlib.sha256).digest()).decode()
    return any(hmac.compare_digest(expected, part.split(",", 1)[1]) for part in signatures.split() if "," in part)


@csrf_exempt
@require_POST
def resend_webhook(request):
    secret = settings.RESEND_WEBHOOK_SECRET
    if not secret:
        return HttpResponse("Webhook secret not set", status=503)
    if not signature_ok(secret, request.headers, request.body):
        return HttpResponse("Bad signature", status=401)
    try:
        event = json.loads(request.body)
    except ValueError:
        return HttpResponseBadRequest("Not JSON")
    kind, data = event.get("type", ""), event.get("data") or {}
    log = EmailLog.objects.filter(resend_id=data.get("email_id") or "-").first()
    if log:
        if kind in STATUS_FOR and not (log.status in (EmailLog.Status.BOUNCED, EmailLog.Status.COMPLAINED) and kind == "email.delivered"):
            log.status = STATUS_FOR[kind]
        if kind == "email.opened" and log.opened_at is None:
            log.opened_at = timezone.now()
        if kind == "email.bounced":
            log.error = str((data.get("bounce") or {}).get("message") or "Bounced")[:2000]
        log.save()
    addresses = [a for a in (data.get("to") or []) if a]
    if kind == "email.bounced":
        bounce = data.get("bounce") or {}
        if str(bounce.get("type", "")).lower() not in ("transient", "temporary"):  # a mailbox full today may work tomorrow
            for address in addresses:
                EmailSuppression.objects.get_or_create(email=address.strip().lower(), defaults={
                    "reason": EmailSuppression.Reason.BOUNCED, "detail": str(bounce.get("message") or "")[:300]})
    elif kind == "email.complained":
        _complained(addresses)
    return HttpResponse("ok")


def _complained(addresses):
    """Someone marked us as spam: stop every optional email to them. Addresses without an account are blocked outright;
    people with an account still get password resets and receipts."""
    from accounts.models import User

    for address in addresses:
        users = User.objects.filter(email__iexact=address)
        if users.exists():
            users.update(email_notifications=False)
        else:
            EmailSuppression.objects.get_or_create(email=address.strip().lower(), defaults={
                "reason": EmailSuppression.Reason.COMPLAINED, "detail": "Marked an email as spam"})


# ---------------- admin: preview every email ----------------

def email_previews(request):
    kind = request.GET.get("kind") or "welcome_learner"
    lang = "sw" if request.GET.get("lang") == "sw" else "en"
    if kind not in T.EMAILS:
        kind = "welcome_learner"
    subject, html, text = notify.preview(kind, lang, user=request.user, header_url=request.build_absolute_uri(static("img/email/header.gif")))
    groups = [(title, [{"key": k, "name": k.replace("_", " ").capitalize(), "category": T.EMAILS[k]["category"]} for k in kinds])
              for title, kinds in T.GROUPS]
    return render(request, "admin/email_previews.html", {
        "title": "Email previews", "groups": groups, "kind": kind, "lang": lang, "subject": subject, "html": html, "text": text,
        "category": T.EMAILS[kind]["category"],
        "category_name": T.CATEGORIES[T.EMAILS[kind]["category"]][0] if T.EMAILS[kind]["category"] else "",
    })


@require_POST
def email_preview_send(request):
    kind = request.POST.get("kind", "")
    lang = "sw" if request.POST.get("lang") == "sw" else "en"
    if kind not in T.EMAILS or not request.user.email:
        messages.error(request, "Add an email address to your admin account first.")
        return redirect("tools:email_previews")
    subject, html, text = notify.preview(kind, lang, user=request.user)
    message = EmailMultiAlternatives(f"[Preview] {subject}", text, settings.DEFAULT_FROM_EMAIL, [request.user.email])
    message.attach_alternative(html, "text/html")
    message.c4k_kind, message.c4k_user_id = f"preview:{kind}", request.user.pk
    try:
        message.send()
        messages.success(request, f"Sent a preview of “{subject}” to {request.user.email}.")
    except Exception as err:
        messages.error(request, f"Could not send: {err}")
    return redirect(f"{reverse('tools:email_previews')}?kind={kind}&lang={lang}")
