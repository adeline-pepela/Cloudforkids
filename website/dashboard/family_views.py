"""The parent / guardian portal."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import LearnerProfile, ParentLink, User

from .family import child_report

MAX_LINK_TRIES = 6  # wrong codes allowed per parent every 15 minutes


def parent_only(view):
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.role != User.Role.PARENT:
            return redirect("dashboard:home")
        return view(request, *args, **kwargs)

    wrapper.__name__ = view.__name__
    return wrapper


def _children(parent):
    return [link.child for link in ParentLink.objects.filter(parent=parent).select_related("child", "child__learner_profile")]


@parent_only
def home(request):
    reports = [child_report(child) for child in _children(request.user)]
    return render(
        request,
        "parent/home.html",
        {
            "reports": reports,
            "nudge_count": sum(1 for r in reports if r["health"][0] in ("nudge", "new")),
            "children": [r["child"] for r in reports],
            "nav": "home",
        },
    )


@parent_only
def child_detail(request, child_id):
    link = get_object_or_404(ParentLink.objects.select_related("child"), parent=request.user, child_id=child_id)
    return render(
        request,
        "parent/child.html",
        {
            "r": child_report(link.child),
            "children": _children(request.user),
            "nav": link.child_id,
        },
    )


@parent_only
def add_child(request):
    key = f"family-link-tries-{request.user.pk}"
    tries = cache.get(key, 0)
    if request.method == "POST":
        if tries >= MAX_LINK_TRIES:
            messages.error(request, "Too many tries. Please wait a few minutes and try again.")
            return redirect("family:add")
        username = request.POST.get("username", "").strip()
        code = request.POST.get("code", "").strip().upper().replace(" ", "")
        profile = (
            LearnerProfile.objects.select_related("user")
            .filter(user__username__iexact=username, user__role=User.Role.LEARNER, family_code=code)
            .first()
            if username and code
            else None
        )
        if profile is None:
            cache.set(key, tries + 1, 900)
            messages.error(request, "We could not match that username and family code. Please check both and try again.")
            return redirect("family:add")
        _, created = ParentLink.objects.get_or_create(parent=request.user, child=profile.user)
        cache.delete(key)
        messages.success(
            request,
            f"You are now following {profile.user.first_name or profile.user.username}." if created else "You already follow this learner.",
        )
        return redirect("family:child", child_id=profile.user_id)
    return render(request, "parent/add_child.html", {"children": _children(request.user), "nav": "add"})


@parent_only
@require_POST
def remove_child(request, child_id):
    link = ParentLink.objects.filter(parent=request.user, child_id=child_id).first()
    if link is None:
        raise Http404
    link.delete()
    messages.success(request, "That learner has been removed from your list.")
    return redirect("family:home")
