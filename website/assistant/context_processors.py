from .access import can_use, has_connection


def assistant(request):
    """`assistant_area` = "admin" or "teach" when the assistant button belongs on this page, else "".
    Cheap checks first, so learners and parents never cost a query."""
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated and user.is_active):
        return {"assistant_area": ""}
    if request.path.startswith("/admin/"):
        area = "admin" if user.is_staff else ""
    else:
        area = "teach" if user.role == "facilitator" and user.is_approved else ""
    if area and can_use(user, area) and (has_connection() or user.is_superuser):
        return {"assistant_area": area}
    return {"assistant_area": ""}
