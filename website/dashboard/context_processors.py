from .stats import learner_stats


def learner_chips(request):
    """Streak and XP for the learner top bar on lesson, course and profile pages."""
    user = getattr(request, "user", None)
    match = getattr(request, "resolver_match", None)
    if user is None or not user.is_authenticated or match is None:
        return {}
    if match.namespace in ("courses", "accounts"):
        return {"stats": learner_stats(user)}
    return {}


def unread_messages(request):
    """Number of unread messages, shown as a badge next to Messages in each sidebar."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    return {"unread_messages": user.received_messages.filter(read_at__isnull=True).count()}
