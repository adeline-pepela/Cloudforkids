from django.db import migrations

U = "https://images.unsplash.com/"

# slot, image id, photographer, photo page id, description
PHOTOS = [
    ("about-hero", "photo-1637148659333-aa7f09fc2d13", "Oscar Omondi", "sCrGzq9Ocag", "Children learning together at a table in Mwingi, Kenya"),
    ("about-story", "photo-1771935250558-48b750022c95", "Dwayne joe", "GDrqainbhRQ", "Two young people using laptops together in Nairobi"),
    ("about-pathway", "photo-1655720348590-c739c860beed", "Iwaria Inc.", "vWqBjWbc_H4", "Young Africans sitting together with a laptop"),
    ("about-cta", "photo-1547496614-d145e2fa88ed", "bennett tobias", "YMpvL5eAtg0", "Three smiling schoolboys in Kenya"),
    ("contact", "photo-1752850903501-4307079e0c4a", "Dwayne joe", "rtTOQMUsqhA", "A person working on laptops and a phone in Nairobi"),
    ("impact", "photo-1664990594667-9bd4c60cbcfb", "Blake Cheek", "8ocdFTNYQjI", "Children in school uniform in Nairobi, Kenya"),
    ("partners", "photo-1776039325163-f45315a484f3", "Dwayne joe", "rOIIHqh2itM", "A panel discussion with speakers in Nairobi"),
    ("tier-explorer", "photo-1729691032175-d6edd1581a31", "Blake Cheek", "un5MtX00fKM", "Young children sitting together in Nairobi, Kenya"),
    ("program-explorer", "photo-1729691032175-d6edd1581a31", "Blake Cheek", "un5MtX00fKM", "Young children sitting together in Nairobi, Kenya"),
    ("auth-login", "photo-1637148778990-621fbe8a8358", "Oscar Omondi", "Xz5kTUYAu9A", "A teacher standing in front of a class of children in Kenya"),
    ("auth-signup", "photo-1771935250558-48b750022c95", "Dwayne joe", "GDrqainbhRQ", "Two young people using laptops together in Nairobi"),
    ("auth-reset", "photo-1637148659333-aa7f09fc2d13", "Oscar Omondi", "sCrGzq9Ocag", "Children learning together at a table in Mwingi, Kenya"),
]


def seed(apps, schema_editor):
    SitePhoto = apps.get_model("core", "SitePhoto")
    for slot, image, who, page, alt in PHOTOS:
        SitePhoto.objects.get_or_create(slot=slot, defaults={
            "url": U + image, "alt": alt, "credit_name": who, "credit_url": f"https://unsplash.com/photos/{page}",
        })


class Migration(migrations.Migration):
    dependencies = [("core", "0012_site_photos")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
