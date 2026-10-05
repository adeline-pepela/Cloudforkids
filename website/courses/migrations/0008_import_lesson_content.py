from pathlib import Path

from django.db import migrations

CONTENT_DIR = Path(__file__).resolve().parent.parent / "lesson_content"


def import_content(apps, schema_editor):
    """The lesson pages used to be template files; copy their HTML into Lesson.content so the
    database is the single source of truth (edit lessons in the admin from now on)."""
    Lesson = apps.get_model("courses", "Lesson")
    for lesson in Lesson.objects.all():
        path = CONTENT_DIR / f"{lesson.slug}.html"
        if path.exists():
            lesson.content = path.read_text(encoding="utf-8")
            lesson.save(update_fields=["content"])


class Migration(migrations.Migration):

    dependencies = [("courses", "0007_seed_after_schema")]

    operations = [migrations.RunPython(import_content, migrations.RunPython.noop)]
