"""A learner's page for one class, and the class discussion board (posting and moderating, shared with the teacher)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts.models import ClassPost, Classroom
from live import moderation

from .classroom import TABS, can_post, learner_class_page, post_too_fast
from .stats import learner_stats


@login_required
def class_detail(request, class_id):
    classroom = get_object_or_404(Classroom.objects.select_related("facilitator", "tier"), pk=class_id)
    if request.user.pk == classroom.facilitator_id:
        return redirect("teach:class", class_id=classroom.pk)
    if not classroom.memberships.filter(learner=request.user).exists():
        raise Http404
    tab = request.GET.get("tab") if request.GET.get("tab") in TABS else "discussion"
    ctx = learner_class_page(classroom, request.user)
    ctx.update(tab=tab, nav="classes", stats=learner_stats(request.user))
    return render(request, "learner/class_detail.html", ctx)


def _back(request, classroom):
    nxt = request.POST.get("next", "")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(nxt)
    if request.user.pk == classroom.facilitator_id:
        return redirect("teach:discussion", class_id=classroom.pk)
    return redirect(reverse("dashboard:class", args=[classroom.pk]) + "?tab=discussion")


@login_required
@require_POST
def discussion_post(request, class_id):
    classroom = get_object_or_404(Classroom, pk=class_id)
    teacher = request.user.pk == classroom.facilitator_id
    if not (teacher or classroom.memberships.filter(learner=request.user).exists()):
        raise Http404
    if not can_post(request.user, classroom):
        messages.error(request, "The teacher has turned the class discussion off.")
        return _back(request, classroom)
    body = request.POST.get("body", "").strip()[:1500]
    if not body:
        messages.error(request, "Write something first.")
        return _back(request, classroom)
    parent = None
    if request.POST.get("parent"):
        parent = classroom.posts.filter(pk=request.POST["parent"], parent__isnull=True, hidden=False, flagged=False).first()
        if parent is None:
            messages.error(request, "That post is no longer there.")
            return _back(request, classroom)
    if not teacher and post_too_fast(request.user):
        messages.error(request, "Slow down a little, then post again.")
        return _back(request, classroom)
    reason = moderation.check(body, host=teacher)
    ClassPost.objects.create(classroom=classroom, author=request.user, parent=parent, body=body, flagged=bool(reason), reason=reason or "")
    if reason:
        messages.error(request, moderation.REASONS[reason].replace("Your message", "Your post"))
    else:
        messages.success(request, "Posted.")
    return _back(request, classroom)


@login_required
@require_POST
def discussion_action(request, class_id, post_id, action):
    """Authors may delete their own posts. The teacher may delete any post, pin it, or restore one the filter blocked."""
    classroom = get_object_or_404(Classroom, pk=class_id)
    post = get_object_or_404(ClassPost, pk=post_id, classroom=classroom)
    teacher = request.user.pk == classroom.facilitator_id
    if action == "delete" and (teacher or post.author_id == request.user.pk):
        post.hidden = True
        post.save(update_fields=["hidden"])
        messages.success(request, "Post removed.")
    elif action == "pin" and teacher and post.parent_id is None:
        post.pinned = not post.pinned
        post.save(update_fields=["pinned"])
    elif action == "allow" and teacher and post.flagged:
        post.flagged = False
        post.save(update_fields=["flagged"])
        messages.success(request, "The post is now visible to the class.")
    else:
        raise Http404
    return _back(request, classroom)
