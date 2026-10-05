from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect, render

from .forms import LearnerProfileForm, SignUpForm
from django.views.decorators.http import require_POST

from .models import ClassMembership, Classroom, LearnerProfile, User


class CloudForKidsLoginView(LoginView):
    template_name = "accounts/login.html"


class CloudForKidsLogoutView(LogoutView):
    next_page = "core:home"


def signup(request):
    if request.user.is_authenticated:
        return redirect("dashboard:home")

    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f"Welcome to Cloud for Kids, {user.first_name}! Your account is ready.")
            return redirect("dashboard:home")
    else:
        form = SignUpForm()
    return render(request, "accounts/signup.html", {"form": form})


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
