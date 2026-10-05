from django.db import migrations

from core.translations_sw import SW
from core.translations_sw_content import CONTENT


def seed(apps, schema_editor):
    """Load the Kiswahili wording. Existing rows are left alone so admin edits are never overwritten."""
    UITranslation = apps.get_model("core", "UITranslation")
    for english, swahili in {**SW, **CONTENT}.items():
        UITranslation.objects.get_or_create(english=english, defaults={"swahili": swahili})


class Migration(migrations.Migration):
    dependencies = [("core", "0010_ui_translations")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
