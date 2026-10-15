"""Who may use the assistant, and where."""

from django.core.cache import cache

from accounts.models import User

from .models import AssistantSettings, Connection

HAS_CONNECTION_KEY = "assistant-has-connection-v1"


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
    return False


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
