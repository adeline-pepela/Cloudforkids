from django.db import migrations

from core.translations_sw import SW


def seed(apps, schema_editor):
    """Add the Kiswahili wording for meeting passcodes and the waiting room. Existing rows are left alone."""
    UITranslation = apps.get_model("core", "UITranslation")
    for english, swahili in SW.items():
        UITranslation.objects.get_or_create(english=english, defaults={"swahili": swahili})


class Migration(migrations.Migration):
    dependencies = [("core", "0021_class_page_translations")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
