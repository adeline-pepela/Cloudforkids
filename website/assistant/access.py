"""Who may use the assistant, and where."""

from django.core.cache import cache

from accounts.models import User

from .models import AssistantSettings, Connection

HAS_CONNECTION_KEY = "assistant-has-connection-v1"
AREAS = ("admin", "teach", "learn", "family")
READ_ONLY_AREAS = ("learn",)  # the learner study helper explains and never changes anything


def learner_plan_allows(user):
    """The study helper comes with plans that include the AI learning assistant (Admin > Plans)."""
    from billing.access import current_plan, has_full_access

    if has_full_access(user):
        return True
    plan = current_plan(user)
    return bool(plan and plan.ai_assistant)


def can_use(user, area, settings=None):
    if not (user and user.is_authenticated and user.is_active):
        return False
    settings = settings or AssistantSettings.load()
    if not settings.enabled:
        return False
    if area == "admin":
        return settings.for_admins and user.is_staff
    if area == "teach":
        return settings.for_tutors and user.role == User.Role.FACILITATOR and not user.awaiting_approval
    if area == "learn":
        return settings.for_learners and user.role == User.Role.LEARNER and learner_plan_allows(user)
    if area == "family":
        return settings.for_parents and user.role == User.Role.PARENT
    return False


def area_for(user, path):
    """Which assistant belongs on this page for this person, before any setting is checked."""
    if path.startswith("/admin/"):
        return "admin" if user.is_staff else ""
    return {User.Role.FACILITATOR: "teach", User.Role.LEARNER: "learn", User.Role.PARENT: "family"}.get(user.role, "")


def has_connection():
    found = cache.get(HAS_CONNECTION_KEY)
    if found is None:
        found = Connection.objects.exists()
        cache.set(HAS_CONNECTION_KEY, found, 60)
    return found


def connections_changed():
    cache.delete(HAS_CONNECTION_KEY)


def default_connection():
    return Connection.objects.order_by("-is_default", "-saved_at").first()
