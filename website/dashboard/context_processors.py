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
