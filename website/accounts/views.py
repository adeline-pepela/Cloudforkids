import logging

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import (
    LoginView, LogoutView, PasswordResetCompleteView, PasswordResetConfirmView, PasswordResetDoneView, PasswordResetView,
)
from django.core.cache import cache
from django.http import Http404
from django.utils import timezone
from django.urls import reverse_lazy
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


def signup(request):
    if request.user.is_authenticated:
        return redirect("dashboard:home")

    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
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
            return redirect("dashboard:home")
    else:
        form = SignUpForm()
    return render(request, "accounts/signup.html", {"form": form})


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


def unsubscribe(request, token):
    user = User.objects.filter(pk=notify.read_unsubscribe_token(token)).first()
    if user is None:
        raise Http404
    done = False
    if request.method == "POST":
        user.email_notifications = False
        user.save(update_fields=["email_notifications"])
        done = True
    return render(request, "accounts/unsubscribe.html", {"done": done, "target": user})


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
        messages.success(request, f"You joined {classroom.name}." if created else f"You are already in {classroom.name}.")
    return redirect("accounts:profile")


@login_required
@require_POST
def leave_class(request, class_id):
    ClassMembership.objects.filter(classroom_id=class_id, learner=request.user).delete()
    messages.success(request, "You left the class.")
    return redirect("accounts:profile")
