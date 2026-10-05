from django.core.management import call_command
from django.db import migrations


def seed_data(apps, schema_editor):
    """Populate tiers, courses, lessons, badges, partners and the demo account on a fresh database.
    Skipped when programme data already exists so admin edits are never overwritten."""
    Tier = apps.get_model("courses", "Tier")
    if not Tier.objects.exists():
        call_command("seed_data_fixed")


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0006_longer_slugs"),
        ("core", "0002_testimonial"),
        ("accounts", "0003_family_links"),
        ("dashboard", "0001_labcompletion"),
    ]

    operations = [
        migrations.RunPython(seed_data, migrations.RunPython.noop),
    ]
