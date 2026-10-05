from django.db import migrations

from courses.starter import install


def add_explorer(apps, schema_editor):
    """Existing databases get the Explorer (Grade 1-3) tier. Fresh databases get it from courses/seeding.py."""
    Tier, Course, Lesson = (apps.get_model("courses", name) for name in ("Tier", "Course", "Lesson"))
    if Tier.objects.exists():
        install(Tier, Course, Lesson)


class Migration(migrations.Migration):

    dependencies = [("courses", "0010_swahili_fields")]

    operations = [migrations.RunPython(add_explorer, migrations.RunPython.noop)]
