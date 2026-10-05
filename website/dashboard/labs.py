"""Practice Labs come from the database (dashboard.models.Lab). The interactive part of each lab
lives in static/js/labs.js and templates/learner/labs/<slug>.html."""

from django.template import TemplateDoesNotExist
from django.template.loader import get_template

XP_PER_LESSON = 10
XP_PER_LAB = 15
XP_PER_LEVEL = 100
LEVEL_NAMES = ["Cloud Seed", "Sprout", "Explorer", "Builder", "Navigator", "Architect", "Cloud Hero"]


def _as_dict(lab):
    return {
        "slug": lab.slug,
        "title": lab.title,
        "summary": lab.summary,
        "icon": f"bi-{lab.icon}",
        "tone": lab.tone,
        "minutes": lab.minutes,
        "level": lab.level,
        "skill": lab.skill,
    }


def get_labs():
    """Published labs, in display order, as plain dicts."""
    from .models import Lab

    return [_as_dict(lab) for lab in Lab.objects.filter(published=True)]


def get_lab(slug):
    from .models import Lab

    lab = Lab.objects.filter(slug=slug, published=True).first()
    return _as_dict(lab) if lab else None


def lab_count():
    from .models import Lab

    return Lab.objects.filter(published=True).count()


def lab_template_exists(slug):
    try:
        get_template(f"learner/labs/{slug}.html")
        return True
    except TemplateDoesNotExist:
        return False
