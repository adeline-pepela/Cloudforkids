from django.db import migrations


def update(apps, schema_editor):
    Setting = apps.get_model("core", "SiteSetting")
    Stat = apps.get_model("core", "ImpactStat")
    Legal = apps.get_model("core", "LegalPage")
    Photo = apps.get_model("core", "SitePhoto")

    for s in Setting.objects.all():
        for field in ("hero_lead", "about_lead"):
            text = getattr(s, field)
            setattr(s, field, text.replace("aged 7-17", "aged 9-17").replace("aged 7 to 17", "aged 9 to 17"))
        if s.hero_note.startswith("Explorer, Foundational"):
            s.hero_note = "Foundational, Intermediate, Advanced: a 3-tier pathway from Grade 4 to Grade 12."
        s.save()
    Stat.objects.filter(where="about", value="7\u201317").update(value="9\u201317", label="years old: upper primary to senior secondary")
    Stat.objects.filter(where="about", value="4", label__startswith="tiers").update(value="3", label="tiers: Foundational, Intermediate, Advanced")
    Stat.objects.filter(where="about", value="Gr 1\u201312").update(value="Gr 4\u201312")
    for page in Legal.objects.all():
        page.body = page.body.replace("aged 7 to 17", "aged 9 to 17")
        page.save()
    # Drop the stock Unsplash photos; the pages now show Cloud for Kids illustrations. Photos uploaded in the admin stay.
    Photo.objects.filter(image="", url__contains="unsplash.com").delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0014_remove_explorer_photos")]
    operations = [migrations.RunPython(update, migrations.RunPython.noop)]
