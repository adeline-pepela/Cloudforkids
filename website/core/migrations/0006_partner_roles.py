from django.db import migrations

ROLES = {
    "AWS / Konza Technopolis": "Cloud platform and tech hub",
    "Ajira Digital Centres": "Digital skills centres",
    "Konza Jitume Hubs": "Learning hubs",
    "Mastercard Foundation / eMobilis": "Youth skills funding and training",
    "Ministry of Education / KICD": "Curriculum alignment",
    "Robotics Society of Kenya": "Robotics and STEM community",
    "Samsung": "Technology and devices",
}
NEW = [
    ("AWS UserGroup Kenya", "Community of AWS builders and learners in Kenya.", "Community and mentors"),
    ("Safaricom WIT Tech in Kids", "Safaricom's Women in Tech programme introducing children to technology.", "Mentorship"),
    ("Amazon Web Services", "Global cloud provider behind AWS Educate and AWS re/Start.", "Cloud platform and learning resources"),
]


def add(apps, schema_editor):
    Partner = apps.get_model("core", "Partner")
    for name, role in ROLES.items():
        Partner.objects.filter(name=name, role="").update(role=role)
    for name, description, role in NEW:
        Partner.objects.get_or_create(name=name, defaults={"description": description, "role": role})


class Migration(migrations.Migration):
    dependencies = [("core", "0005_course_structure")]
    operations = [migrations.RunPython(add, migrations.RunPython.noop)]
