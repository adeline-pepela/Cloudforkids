from django.db import migrations

OLD_NOTE = "Foundational, Intermediate, Advanced: a 3-tier pathway from Grade 4 to Grade 12."
NEW_NOTE = "Explorer, Foundational, Intermediate, Advanced: a 4-tier pathway from Grade 1 to Grade 12."


def update(apps, schema_editor):
    Setting = apps.get_model("core", "SiteSetting")
    Stat = apps.get_model("core", "ImpactStat")
    Setting.objects.filter(hero_note=OLD_NOTE).update(hero_note=NEW_NOTE)
    Stat.objects.filter(where="about", value="3").update(value="4", label="tiers: Explorer, Foundational, Intermediate, Advanced")
    Stat.objects.filter(where="about", value="Gr 4\u201312").update(value="Gr 1\u201312")


class Migration(migrations.Migration):
    dependencies = [("core", "0008_seed_legal_pages")]
    operations = [migrations.RunPython(update, migrations.RunPython.noop)]
