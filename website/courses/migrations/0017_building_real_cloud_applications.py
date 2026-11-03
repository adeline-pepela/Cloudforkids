from django.db import migrations

KEY = "building-real-cloud-applications"


def add_course(apps, schema_editor):
    """Add Building Real Cloud Applications (Intermediate tier) to databases that already hold the programme (a new database gets it when it is seeded)."""
    from courses.added_courses import install

    install(KEY, apps.get_model("courses", "Tier"), apps.get_model("courses", "Course"), apps.get_model("courses", "Lesson"))


def remove_course(apps, schema_editor):
    from courses.added_courses import uninstall

    uninstall(KEY, apps.get_model("courses", "Course"))


class Migration(migrations.Migration):

    dependencies = [("courses", "0016_computer_packages_basics")]

    operations = [migrations.RunPython(add_course, remove_course)]
