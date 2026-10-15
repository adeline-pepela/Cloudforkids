import logging

from django.db import DatabaseError

from .access import can_use, has_connection

logger = logging.getLogger(__name__)


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
    if not area:
        return {"assistant_area": ""}
    try:
        show = can_use(user, area) and (has_connection() or user.is_superuser)
    except DatabaseError:  # e.g. the assistant's migration has not run yet: hide the button, keep the page working
        logger.warning("Assistant tables are missing. Run: python manage.py migrate")
        return {"assistant_area": ""}
    return {"assistant_area": area if show else ""}
