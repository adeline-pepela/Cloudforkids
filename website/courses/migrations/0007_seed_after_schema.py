from django.db import migrations


class Migration(migrations.Migration):
    """Seeding used to run here. It now runs after `migrate` finishes (courses/seeding.py), once every column exists."""

    dependencies = [
        ("courses", "0006_longer_slugs"),
        ("core", "0002_testimonial"),
        ("accounts", "0003_family_links"),
        ("dashboard", "0001_labcompletion"),
    ]

    operations = []
