from django.db import migrations

PLANS = [
    dict(
        slug="starter", name="Starter", tagline="Cloud Explorer", price_kes=2000, order=1, target_level="Foundation / Beginner",
        focus="Fundamental cloud concepts and self-paced introductory exploration.",
        best_for="Parents and kids testing the waters before committing to hands-on build tracks.",
        all_courses=False, quizzes=False, labs="none", ai_assistant=False, demo_day=False,
        project="Coursework exercises only", credential="completion",
    ),
    dict(
        slug="core", name="Core", tagline="Skill Builder", price_kes=4000, order=2, target_level="Intermediate / Skill Builder",
        focus="Applied learning with practical labs and structured assessments.",
        best_for="Students ready to build functional projects with step-by-step guidance.",
        all_courses=True, quizzes=True, labs="guided", ai_assistant=False, demo_day=False,
        project="Showcase Project (portfolio-ready)", credential="verified",
    ),
    dict(
        slug="advanced", name="Advanced", tagline="Advanced Builder", price_kes=6000, order=3, target_level="Comprehensive / Advanced Builder",
        focus="Full-stack cloud engineering, AI tooling, and public presentation.",
        best_for="Motivated students aiming to deploy real systems online and showcase their work to peers and mentors.",
        all_courses=True, quizzes=True, labs="unlimited", ai_assistant=True, demo_day=True,
        project="Live Online Project + Demo Day Presentation", credential="honors",
    ),
]


def seed(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    for row in PLANS:
        Plan.objects.get_or_create(slug=row["slug"], defaults={**row, "duration_days": 28})


class Migration(migrations.Migration):
    dependencies = [("billing", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
