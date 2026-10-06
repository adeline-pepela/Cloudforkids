from django.db import migrations


def remove(apps, schema_editor):
    apps.get_model("core", "SitePhoto").objects.filter(slot__in=["tier-explorer", "program-explorer"]).delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0013_seed_site_photos")]
    operations = [migrations.RunPython(remove, migrations.RunPython.noop)]
