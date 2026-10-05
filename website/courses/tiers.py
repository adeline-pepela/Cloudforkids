"""Which programme tier suits a learner when they have not picked one."""

import re
from datetime import date

from .models import Tier

BY_AGE = [(8, "explorer"), (11, "foundational"), (14, "intermediate"), (99, "advanced")]  # upper age limits
BY_GRADE = [(3, "explorer"), (6, "foundational"), (9, "intermediate"), (99, "advanced")]


def _pick(limit_table, value):
    for limit, slug in limit_table:
        if value <= limit:
            return Tier.objects.filter(slug=slug).first()
    return None


def suggested_tier(profile):
    """From the learner's date of birth, else their grade, else the Foundational tier (or the first one)."""
    tier = None
    born = getattr(profile, "date_of_birth", None)
    if born:
        today = date.today()
        age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        tier = _pick(BY_AGE, age)
    if tier is None and getattr(profile, "grade", ""):
        found = re.search(r"\d+", profile.grade)
        if found:
            tier = _pick(BY_GRADE, int(found.group()))
    return tier or Tier.objects.filter(slug="foundational").first() or Tier.objects.first()
