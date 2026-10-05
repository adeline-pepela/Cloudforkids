"""First-run programme data. Runs once after `migrate` (post_migrate), when every column exists, and only on an empty
database, so it never overwrites content edited in the admin."""

import os
import sys
from pathlib import Path

from django.core.management import call_command

CONTENT_DIR = Path(__file__).resolve().parent / "lesson_content"


def seed_if_empty(**kwargs):
    if os.environ.get("SKIP_AUTO_SEED") or "flush" in sys.argv:
        return
    from django.db import connection

    from .models import Lesson, Tier

    if "courses_tier" not in connection.introspection.table_names():
        return
    if Tier.objects.exists():
        return
    call_command("seed_data_fixed", verbosity=0)
    for lesson in Lesson.objects.all():  # the lesson pages as designed live in lesson_content/
        path = CONTENT_DIR / f"{lesson.slug}.html"
        if path.exists():
            lesson.content = path.read_text(encoding="utf-8")
            lesson.save(update_fields=["content"])
    from .models import Course
    from .starter import install

    install(Tier, Course, Lesson)  # the Explorer tier (Grade 1-3) with Kiswahili

    from core.translations_sw_content import COURSES, LESSONS, TIERS

    for slug, (name, summary) in TIERS.items():
        Tier.objects.filter(slug=slug, name_sw="").update(name_sw=name, summary_sw=summary)
    for slug, (title, summary) in COURSES.items():
        Course.objects.filter(slug=slug, title_sw="").update(title_sw=title, summary_sw=summary)
    for slug, title in LESSONS.items():
        Lesson.objects.filter(slug=slug, title_sw="").update(title_sw=title)
    for course in Course.objects.exclude(title_sw=""):
        Lesson.objects.filter(course=course, lesson_type="exam", title_sw="").update(
            title_sw=f"Mtihani wa Kozi: {course.title_sw}", summary_sw=f"Pima ulichojifunza katika {course.title_sw}."
        )
