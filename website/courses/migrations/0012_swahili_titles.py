from django.db import migrations

from core.translations_sw_content import COURSES, LESSONS, TIERS


def fill(apps, schema_editor):
    """Kiswahili names for the original tiers, courses and lessons (only where nothing is set yet)."""
    Tier, Course, Lesson = (apps.get_model("courses", n) for n in ("Tier", "Course", "Lesson"))
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


class Migration(migrations.Migration):
    dependencies = [("courses", "0011_explorer_tier"), ("core", "0011_seed_ui_translations")]
    operations = [migrations.RunPython(fill, migrations.RunPython.noop)]
