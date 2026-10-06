from .stats import learner_stats


def learner_chips(request):
    """Streak and XP for the learner top bar on lesson, course and profile pages."""
    user = getattr(request, "user", None)
    match = getattr(request, "resolver_match", None)
    if user is None or not user.is_authenticated or match is None:
        return {}
    if match.namespace in ("courses", "accounts"):
        return {"stats": learner_stats(user)}
    return {}


def unread_messages(request):
    """Number of unread messages, shown as a badge next to Messages in each sidebar."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    return {"unread_messages": user.received_messages.filter(read_at__isnull=True).count()}


def resume_learning(request):
    """`resume_lesson` = the next unfinished lesson for a signed-in learner, for the "Continue learning" buttons."""
    user = getattr(request, "user", None)
    match = getattr(request, "resolver_match", None)
    if user is None or not user.is_authenticated or user.role != "learner" or match is None:
        return {}
    if match.namespace not in ("core", "courses", "accounts"):
        return {}
    from courses.models import Enrollment, Lesson, LessonCompletion

    last = (LessonCompletion.objects.filter(enrollment__learner=user).select_related("enrollment")
            .order_by("-completed_at").first())
    enrollments = list(Enrollment.objects.filter(learner=user))
    if last:  # start with the course they were last working on
        enrollments.sort(key=lambda e: e.id != last.enrollment_id)
    for enrollment in enrollments:
        done = enrollment.completed_lesson_ids
        for lesson in enrollment.course.lessons.filter(lesson_type=Lesson.LessonType.LESSON):
            if lesson.id not in done:
                return {"resume_lesson": lesson}
    return {}
