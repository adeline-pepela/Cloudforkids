from django.core.management import call_command
from django.db import migrations


def seed_data(apps, schema_editor):
    """Populate tiers, courses, lessons, badges, partners and the demo
    account automatically whenever `migrate` is run, so the site never
    shows an empty "Programme data hasn't been seeded yet" state on a
    fresh database."""
    call_command("seed_data_fixed")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0002_lesson_lesson_type_lesson_pass_score_percent"),
        ("core", "0001_initial"),
        ("accounts", "0002_initial"),
    ]

    operations = [
        migrations.RunPython(seed_data, noop),
    ]
