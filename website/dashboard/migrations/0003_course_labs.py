from django.db import migrations

# Practice Labs for "Computer Packages & Basics" (Foundational) and "Building Real Cloud Applications" (Intermediate).
# (slug, title, summary, icon, tone, minutes, level, skill)
LABS = [
    ("build-a-computer-lab", "Build Your Computer", "Put the parts into the case in the right order, then switch it on and watch it start up.",
     "motherboard-fill", "sky", 6, 1, "Computer parts and how they work together"),
    ("hardware-software-lab", "Hardware or Software?", "Sort 18 cards into the things you can touch and the programs that run on them.",
     "window-stack", "purple", 4, 1, "Telling hardware from software"),
    ("file-organizer-lab", "Tidy Up the Files", "A messy desktop! Use each file's extension to put it in the right folder.",
     "folder-fill", "sun", 5, 1, "Files, folders and file types"),
    ("service-model-lab", "IaaS, PaaS or SaaS?", "Match each company's cloud need to the service model that fits it best.",
     "stack", "grass", 5, 2, "Choosing a cloud service model"),
    ("deploy-scale-lab", "Deploy & Scale an App", "Launch an app step by step, then use auto-scaling to keep it fast for 50,000 users.",
     "cloud-upload-fill", "coral", 7, 2, "Deploying apps and auto-scaling"),
    ("sql-query-lab", "Query the Class Database", "Build SQL queries to find Grade 9 students, subject averages and the top scorers.",
     "database-fill", "sky", 8, 2, "Asking a database questions with SQL"),
    ("api-explorer-lab", "API Explorer", "Send GET, POST, PUT and DELETE requests to a pretend school API and watch the database change.",
     "braces", "purple", 8, 3, "REST APIs and JSON"),
    ("security-audit-lab", "Security Audit", "Find and fix five security problems in a pretend school app, from HTTPS to permission checks.",
     "bug-fill", "grass", 8, 2, "Finding and fixing security problems"),
]


def add_labs(apps, schema_editor):
    Lab = apps.get_model("dashboard", "Lab")
    start = (Lab.objects.order_by("-order").values_list("order", flat=True).first() or 0) + 1
    for n, (slug, title, summary, icon, tone, minutes, level, skill) in enumerate(LABS):
        Lab.objects.get_or_create(slug=slug, defaults=dict(
            title=title, summary=summary, icon=icon, tone=tone, minutes=minutes, level=level, skill=skill, order=start + n))


def remove_labs(apps, schema_editor):
    apps.get_model("dashboard", "Lab").objects.filter(slug__in=[lab[0] for lab in LABS]).delete()


class Migration(migrations.Migration):

    dependencies = [("dashboard", "0002_lab")]

    operations = [migrations.RunPython(add_labs, remove_labs)]
