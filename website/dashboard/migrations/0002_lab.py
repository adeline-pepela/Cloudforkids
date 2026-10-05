from django.db import migrations, models

LABS = [
    ("cloud-save-lab", "Send It to the Cloud", "Save a photo to the cloud and watch where it travels.", "cloud-arrow-up-fill", "sky", 3, 1, "How the cloud stores things"),
    ("block-coder-lab", "Robot Block Coder", "Snap blocks together to guide the robot to the cloud.", "robot", "purple", 5, 1, "Sequences and coding thinking"),
    ("password-lab", "Password Power-Up", "Build a super-strong password and see how long it would take to crack.", "shield-lock-fill", "grass", 4, 1, "Staying safe online"),
    ("service-match-lab", "Cloud Services Match", "Match each cloud service to the job it does best.", "diagram-3-fill", "sun", 5, 2, "Storage, servers, databases and functions"),
    ("web-page-lab", "Build & Publish a Web Page", "Write a tiny web page, preview it, then publish it to a pretend cloud address.", "window-desktop", "coral", 8, 3, "Hosting a website"),
]


def add_labs(apps, schema_editor):
    Lab = apps.get_model("dashboard", "Lab")
    for order, (slug, title, summary, icon, tone, minutes, level, skill) in enumerate(LABS):
        Lab.objects.get_or_create(slug=slug, defaults=dict(
            title=title, summary=summary, icon=icon, tone=tone, minutes=minutes, level=level, skill=skill, order=order))


class Migration(migrations.Migration):

    dependencies = [("dashboard", "0001_labcompletion")]

    operations = [
        migrations.CreateModel(
            name="Lab",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slug", models.SlugField(help_text="Must match a lab template in templates/learner/labs/", unique=True)),
                ("title", models.CharField(max_length=100)),
                ("summary", models.CharField(max_length=250)),
                ("icon", models.CharField(default="joystick", help_text="Bootstrap Icons name, e.g. robot", max_length=40)),
                ("tone", models.CharField(choices=[("sky", "Sky blue"), ("purple", "Purple"), ("grass", "Green"), ("sun", "Yellow"), ("coral", "Coral")], default="sky", max_length=10)),
                ("minutes", models.PositiveIntegerField(default=5)),
                ("level", models.PositiveSmallIntegerField(default=1, help_text="Difficulty 1 (easy) to 3 (hard)")),
                ("skill", models.CharField(help_text="The skill it practises, shown to learners and parents", max_length=150)),
                ("order", models.PositiveIntegerField(default=0)),
                ("published", models.BooleanField(default=True)),
            ],
            options={"ordering": ["order", "id"]},
        ),
        migrations.AlterField(
            model_name="labcompletion",
            name="slug",
            field=models.SlugField(help_text="Slug of the Lab that was finished"),
        ),
        migrations.RunPython(add_labs, migrations.RunPython.noop),
    ]
