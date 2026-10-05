from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Lesson


@receiver(post_save, sender=Lesson)
def keep_exam_in_place(sender, instance, raw=False, **kwargs):
    """When a teaching lesson is saved, make sure its course has a module exam and that the exam is last."""
    if raw or instance.lesson_type != Lesson.LessonType.LESSON:
        return
    from .exams import ensure_exam

    ensure_exam(instance.course)
