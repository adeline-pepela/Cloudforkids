"""What a user may open, based on their plan.

Facilitators, admins and staff see everything (they teach it). Learners need a current plan:
  Starter  - the courses in their own programme, no quizzes/exams (they mark lessons done themselves), no labs
  Core     - every course, quizzes and exams, guided labs (levels 1-2)
  Advanced - everything in Core plus every lab, the AI assistant, a live project and Demo Day
"""

from django.utils import timezone

from .models import Plan, Subscription

GUIDED_LAB_MAX_LEVEL = 2


def has_full_access(user):
    return user.is_authenticated and (user.is_staff or user.role in ("facilitator", "admin"))


def current_subscription(user):
    """The learner's subscription in force right now: the best plan among their current periods."""
    if not user.is_authenticated:
        return None
    cache = getattr(user, "_c4k_subscription", False)
    if cache is not False:
        return cache
    now = timezone.now()
    sub = (
        Subscription.objects.filter(learner=user, starts_at__lte=now, ends_at__gt=now)
        .select_related("plan").order_by("-plan__order", "-ends_at").first()
    )
    user._c4k_subscription = sub
    return sub


def current_plan(user):
    sub = current_subscription(user)
    return sub.plan if sub else None


def forget(user):
    """Drop the per-request cache after a plan changes."""
    if hasattr(user, "_c4k_subscription"):
        del user._c4k_subscription


def own_tier(user):
    from courses.tiers import suggested_tier

    profile = getattr(user, "learner_profile", None)
    return profile.tier if profile and profile.tier_id else suggested_tier(profile)


def can_open_course(user, course):
    if has_full_access(user):
        return True
    plan = current_plan(user)
    if plan is None:
        return False
    if plan.all_courses:
        return True
    tier = own_tier(user)
    return tier is not None and course.tier_id == tier.pk


def can_take_quizzes(user):
    if has_full_access(user):
        return True
    plan = current_plan(user)
    return bool(plan and plan.quizzes)


def can_open_lab(user, level):
    if has_full_access(user):
        return True
    plan = current_plan(user)
    if plan is None or plan.labs == Plan.Labs.NONE:
        return False
    return plan.labs == Plan.Labs.UNLIMITED or level <= GUIDED_LAB_MAX_LEVEL


def lab_limit_text(user):
    """Why labs are locked, for the Practice Lab page."""
    plan = current_plan(user)
    if plan is None:
        return "Choose a plan to start the Practice Labs."
    if plan.labs == Plan.Labs.NONE:
        return f"Practice Labs are not part of the {plan.name} plan. Core includes guided labs; Advanced includes every lab."
    if plan.labs == Plan.Labs.GUIDED:
        return "Your Core plan includes the guided labs (levels 1 and 2). Advanced unlocks the level 3 cloud sandbox labs."
    return ""


def can_join_live(user):
    """Live classes are open to every learner in a class unless LIVE_CLASSES_REQUIRE_PLAN is on."""
    from django.conf import settings

    if has_full_access(user) or not settings.LIVE_CLASSES_REQUIRE_PLAN:
        return True
    plan = current_plan(user)
    return bool(plan and plan.live_classes)
