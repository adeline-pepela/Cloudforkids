from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect, render

from .forms import LearnerProfileForm, SignUpForm
from .models import LearnerProfile


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
            messages.success(request, f"Welcome to Cloud for Kids, {user.first_name}\! Your account is ready.")
            return redirect("dashboard:home")
    else:
        form = SignUpForm()
    return render(request, "accounts/signup.html", {"form": form})


@login_required
def profile(request):
    profile_obj, _ = LearnerProfile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        form = LearnerProfileForm(request.POST, instance=profile_obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect("accounts:profile")
    else:
        form = LearnerProfileForm(instance=profile_obj)
    return render(request, "accounts/profile.html", {"form": form})
