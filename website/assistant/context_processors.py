import logging

from django.db import DatabaseError

from .access import area_for, can_use, has_connection

logger = logging.getLogger(__name__)


def assistant(request):
    """`assistant_area` = "admin", "teach", "learn" or "family" when the assistant button belongs on this page, else ""."""
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated and user.is_active):
        return {"assistant_area": ""}
    area = area_for(user, request.path)
    if not area:
        return {"assistant_area": ""}
    try:
        show = can_use(user, area) and (has_connection() or user.is_superuser)
    except DatabaseError:  # e.g. the assistant's migration has not run yet: hide the button, keep the page working
        logger.warning("Assistant tables are missing. Run: python manage.py migrate")
        return {"assistant_area": ""}
    return {"assistant_area": area if show else ""}
