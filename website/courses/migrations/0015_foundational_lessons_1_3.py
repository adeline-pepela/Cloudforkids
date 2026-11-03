from pathlib import Path

from django.db import migrations, models

CONTENT_DIR = Path(__file__).resolve().parent.parent / "lesson_content"

# The full Foundational lessons 1-3 (topics, key takeaways, labs, games and a bigger question pool),
# and the course's module exam rebuilt from all of their questions, dealt as a random set on each attempt.
# slug: (summary, minutes, questions per attempt)
LESSONS = {
    "where-does-your-data-live": ("Understanding the cloud, data, and where information is stored.", 150, 10),
    "networks-the-internet": ("Understanding how computers connect and communicate with each other.", 150, 10),
    "data-storage-basics": ("Understanding different types of data, how it is stored, and different storage solutions.", 150, 10),
}


def load_lessons(apps, schema_editor):
    """Replace the three lesson pages in databases that already hold them (a new database reads the files when it is seeded).
    The old Kiswahili pages no longer match the new quiz questions, so they are cleared until they are translated again."""
    Lesson = apps.get_model("courses", "Lesson")
    for slug, (summary, minutes, quiz_size) in LESSONS.items():
        content = (CONTENT_DIR / f"{slug}.html").read_text(encoding="utf-8")
        Lesson.objects.filter(slug=slug, lesson_type="lesson").update(
            content=content, content_sw="", summary=summary, duration_minutes=minutes, quiz_size=quiz_size
        )
    from courses.exams import ensure_exam

    Course = apps.get_model("courses", "Course")
    for course in Course.objects.filter(lessons__slug__in=LESSONS).distinct():
        ensure_exam(course, refresh=True)


class Migration(migrations.Migration):

    dependencies = [("courses", "0014_lessontime_quizattempt")]

    operations = [
        migrations.AlterField(
            model_name="lesson",
            name="quiz_size",
            field=models.PositiveSmallIntegerField(
                default=0, verbose_name="Questions per attempt",
                help_text="0 asks every question each time. If the lesson or module exam holds more questions than this number, each attempt asks a different random set of this size.",
            ),
        ),
        migrations.RunPython(load_lessons, migrations.RunPython.noop),
    ]
