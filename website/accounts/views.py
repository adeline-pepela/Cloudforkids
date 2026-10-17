import logging

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import (
    LoginView, LogoutView, PasswordResetCompleteView, PasswordResetConfirmView, PasswordResetDoneView, PasswordResetView,
)
from django.core.cache import cache
from django.http import Http404, HttpResponse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.urls import reverse, reverse_lazy
from django.views.decorators.csrf import csrf_exempt
from urllib.parse import urlencode
from django.shortcuts import redirect, render

from .forms import ConsentAwareLoginForm, LearnerProfileForm, NewPasswordForm, ResetRequestForm, SignUpForm
from django.views.decorators.http import require_POST

from core import notify

from .models import ClassMembership, Classroom, LearnerProfile, ParentalConsent, User


class CloudForKidsLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = ConsentAwareLoginForm


logger = logging.getLogger(__name__)


class CloudForKidsPasswordResetView(PasswordResetView):
    """Asks for an email and sends a reset link (through Resend). Always shows the same "check your email"
    page, so nobody can find out which emails have accounts, and a mail-service hiccup never shows an error page."""

    template_name = "accounts/password_reset_form.html"
    form_class = ResetRequestForm
    email_template_name = "registration/password_reset_email.txt"
    html_email_template_name = "registration/password_reset_email.html"
    subject_template_name = "registration/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")
    max_per_hour = 5

    def form_valid(self, form):
        ip = self.request.META.get("REMOTE_ADDR", "?")
        key = f"pwreset-{ip}"
        tries = cache.get(key, 0)
        cache.set(key, tries + 1, 3600)
        if tries >= self.max_per_hour:
            return redirect(self.success_url)
        self.extra_email_context = {"header_url": notify.email_header_url()}
        try:
            return super().form_valid(form)
        except Exception:
            logger.exception("Password reset email failed")
            return redirect(self.success_url)


class CloudForKidsPasswordResetDoneView(PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"


class CloudForKidsPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    form_class = NewPasswordForm
    success_url = reverse_lazy("accounts:password_reset_complete")


class CloudForKidsPasswordResetCompleteView(PasswordResetCompleteView):
    template_name = "accounts/password_reset_complete.html"


class CloudForKidsLogoutView(LogoutView):
    next_page = "core:home"


def _safe_next(request):
    """Where to go after signing up (e.g. a plan checkout), if it is a page on this site."""
    target = request.POST.get("next") or request.GET.get("next") or ""
    ok = url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure())
    return target if ok else ""


def signup(request):
    next_url = _safe_next(request)
    if request.user.is_authenticated:
        return redirect(next_url or "dashboard:home")

    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            from core.email_text import lang_of

            user.language = lang_of(getattr(request, "LANGUAGE_CODE", "en"))
            User.objects.filter(pk=user.pk).update(language=user.language)
            if user.role == User.Role.LEARNER and form.needs_consent:
                notify.send_consent_request(user.consent)
                request.session["consent_user"] = user.pk
                return redirect("accounts:consent_pending")
            login(request, user)
            notify.send_welcome(user)
            if user.awaiting_approval:
                notify.notify_admins_new_facilitator(user)
                messages.success(request, "Welcome! Your account is created. We will approve your facilitator access shortly.")
                return redirect("teach:home")
            messages.success(request, f"Welcome to Cloud for Kids, {user.first_name}! Your account is ready.")
            return redirect(next_url or "dashboard:home")
    else:
        form = SignUpForm()
    return render(request, "accounts/signup.html", {"form": form, "next": next_url})


def consent_pending(request):
    """Shown to a child under 13 after signing up: their parent has been emailed."""
    user = User.objects.filter(pk=request.session.get("consent_user"), is_active=False).select_related("consent").first()
    consent = getattr(user, "consent", None) if user else None
    if consent is None or consent.status != ParentalConsent.Status.PENDING:
        return redirect("accounts:login")
    if request.method == "POST":
        key = f"consent-resend-{consent.pk}"
        if cache.get(key, 0) >= 3:
            messages.error(request, "We already sent that email a few times. Please check the spam folder.")
        else:
            cache.set(key, cache.get(key, 0) + 1, 3600)
            notify.send_consent_request(consent)
            messages.success(request, "We sent the email again.")
        return redirect("accounts:consent_pending")
    local, _, domain = consent.parent_email.partition("@")
    masked = f"{local[:1]}***@{domain}"
    return render(request, "accounts/consent_pending.html", {"masked_email": masked, "child": user})


def consent_review(request, token):
    """The page a parent opens from the email to approve or decline their child's account."""
    consent = ParentalConsent.objects.filter(token=token).select_related("user").first()
    if consent is None:
        raise Http404
    child = consent.user
    if consent.status != ParentalConsent.Status.PENDING:
        return render(request, "accounts/consent_done.html", {"consent": consent, "child": child, "already": True})
    if request.method == "POST":
        decision = request.POST.get("decision")
        if decision == "approve":
            consent.status = ParentalConsent.Status.APPROVED
            consent.decided_at = timezone.now()
            consent.save(update_fields=["status", "decided_at"])
            child.is_active = True
            child.save(update_fields=["is_active"])
            notify.send_consent_result(consent, approved=True)
            return render(request, "accounts/consent_done.html", {"consent": consent, "child": child, "approved": True})
        if decision == "decline":
            notify.send_consent_result(consent, approved=False)
            child.delete()  # remove the request and the details that came with it
            return render(request, "accounts/consent_done.html", {"declined": True})
    return render(request, "accounts/consent_review.html", {"consent": consent, "child": child, "profile": getattr(child, "learner_profile", None)})


CATEGORY_ORDER = ["progress", "class", "reminders", "celebrations", "news"]


def _categories_for(user, lang):
    from core.email_text import CATEGORIES

    sw = lang == "sw"
    rows = []
    for key in CATEGORY_ORDER:
        if key == "progress" and user.role != User.Role.PARENT:
            continue
        en_name, sw_name, en_help, sw_help = CATEGORIES[key]
        rows.append({"key": key, "name": sw_name if sw else en_name, "help": sw_help if sw else en_help, "on": getattr(user, f"email_{key}")})
    return rows


def email_settings(request, token):
    """Which optional emails someone gets, and in which language. Opened from the link in any email: no login needed."""
    from core.email_text import CATEGORIES, lang_of

    user_id, _ = notify.read_settings_token(token)
    user = User.objects.filter(pk=user_id).first() if user_id else None
    if user is None:
        raise Http404
    stop = request.GET.get("stop", "")
    stop = stop if stop in CATEGORIES else ""
    if request.method == "POST":
        action = request.POST.get("action")
        fields = []
        if action == "stop" and stop:
            setattr(user, f"email_{stop}", False)
            fields = [f"email_{stop}"]
        elif action == "none":
            user.email_notifications = False
            fields = ["email_notifications"]
        else:
            user.email_notifications = True
            fields = ["email_notifications", "language"]
            for row in _categories_for(user, "en"):
                setattr(user, f"email_{row['key']}", bool(request.POST.get(row["key"])))
                fields.append(f"email_{row['key']}")
            if request.POST.get("language") in ("en", "sw"):
                user.language = request.POST["language"]
        user.save(update_fields=fields)
        messages.success(request, "Your email settings are saved.")
        return redirect("accounts:email_settings", token=token)
    lang = lang_of(getattr(request, "LANGUAGE_CODE", "en"))
    return render(request, "accounts/email_settings.html", {
        "target": user, "token": token, "categories": _categories_for(user, lang),
        "stop": stop, "stop_name": (CATEGORIES[stop][1] if lang == "sw" else CATEGORIES[stop][0]) if stop else "",
    })


@login_required
def my_email_settings(request):
    return redirect("accounts:email_settings", token=notify.settings_token(request.user))


def unsubscribe(request, token):
    """Links in emails sent before the settings page existed."""
    return redirect("accounts:email_settings", token=token)


@csrf_exempt
def one_click_unsubscribe(request, token):
    """RFC 8058 one-click unsubscribe (the "Unsubscribe" button Gmail and Yahoo show). POST only changes the setting."""
    user_id, category = notify.read_settings_token(token)
    user = User.objects.filter(pk=user_id).first() if user_id else None
    if user is None:
        raise Http404
    if request.method != "POST":
        return redirect(f"{reverse('accounts:email_settings', args=[token])}" + (f"?stop={category}" if category else ""))
    field = f"email_{category}" if category and hasattr(user, f"email_{category}") else "email_notifications"
    setattr(user, field, False)
    user.save(update_fields=[field])
    return HttpResponse("Unsubscribed.", content_type="text/plain")


def confirm_email(request, token):
    user_id, address = notify.read_confirm_token(token)
    user = User.objects.filter(pk=user_id).first() if user_id else None
    if user is None or user.email.strip().lower() != address:
        messages.error(request, "That confirmation link has expired or is for an old email address. Log in and ask for a new one.")
        return redirect("accounts:login")
    if not user.email_verified:
        user.email_verified = True
        user.save(update_fields=["email_verified"])
    messages.success(request, "Thank you! Your email address is confirmed.")
    target = request.GET.get("next", "")
    if not url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        target = ""
    if request.user.is_authenticated:
        return redirect(target or "dashboard:home")
    return redirect(f"{reverse('accounts:login')}?{urlencode({'next': target})}" if target else "accounts:login")


@login_required
@require_POST
def resend_confirmation(request):
    user = request.user
    key = f"confirm-resend-{user.pk}"
    if not user.email or user.email_verified:
        return redirect(request.POST.get("next") or "dashboard:home")
    if cache.get(key, 0) >= 3:
        messages.error(request, "We already sent the link a few times. Please check the spam folder, or try again in an hour.")
    else:
        cache.set(key, cache.get(key, 0) + 1, 3600)
        notify.send_confirm_email(user)
        messages.success(request, "We sent you a new confirmation link. Check your inbox.")
    target = request.POST.get("next", "")
    return redirect(target if url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}) and target else "dashboard:home")


@login_required
def profile(request):
    if request.user.role == "parent":
        return redirect("family:home")
    if request.user.role == "facilitator":
        return redirect("teach:home")
    profile_obj, _ = LearnerProfile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        form = LearnerProfileForm(request.POST, instance=profile_obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect("accounts:profile")
    else:
        form = LearnerProfileForm(instance=profile_obj)
    return render(
        request,
        "accounts/profile.html",
        {
            "form": form,
            "badge_count": request.user.badges.count(),
            "family_code": profile_obj.family_code,
            "memberships": request.user.class_memberships.select_related("classroom", "classroom__facilitator"),
        },
    )


@login_required
@require_POST
def join_class(request):
    if request.user.role != User.Role.LEARNER:
        return redirect("dashboard:home")
    code = request.POST.get("code", "").strip().upper().replace(" ", "")
    classroom = Classroom.objects.filter(join_code=code, archived=False).select_related("facilitator").first() if code else None
    if classroom is None:
        messages.error(request, "We could not find a class with that code. Check it with your teacher and try again.")
    else:
        _, created = ClassMembership.objects.get_or_create(classroom=classroom, learner=request.user)
        messages.success(request, f"You joined {classroom.name}. Your class schedule is below." if created else f"You are already in {classroom.name}.")
        return redirect("dashboard:classes")
    return redirect("accounts:profile")


@login_required
@require_POST
def leave_class(request, class_id):
    ClassMembership.objects.filter(classroom_id=class_id, learner=request.user).delete()
    messages.success(request, "You left the class.")
    return redirect("dashboard:classes")
