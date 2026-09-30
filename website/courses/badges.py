"""Simple badge-awarding rules, checked after a learner completes a lesson."""

from .models import Badge, Enrollment, LearnerBadge, LessonCompletion


def check_and_award_badges(user):
    newly_awarded = []

    def award(name, description, icon, criteria):
        badge, _ = Badge.objects.get_or_create(
            name=name, defaults={"description": description, "icon": icon, "criteria": criteria}
        )
        _, created = LearnerBadge.objects.get_or_create(learner=user, badge=badge)
        if created:
            newly_awarded.append(badge)

    total_completions = LessonCompletion.objects.filter(enrollment__learner=user).count()

    if total_completions >= 1:
        award("First Lesson", "Completed your very first lesson.", "\U0001F680", "Complete 1 lesson")

    if total_completions >= 5:
        award("Rising Cloud", "Completed 5 lessons.", "\u2601\ufe0f", "Complete 5 lessons")

    if total_completions >= 15:
        award("Cloud Champion", "Completed 15 lessons across the programme.", "\U0001F3C6", "Complete 15 lessons")

    for enrollment in Enrollment.objects.filter(learner=user):
        if enrollment.is_complete:
            award(
                f"{enrollment.course.title} Graduate",
                f"Finished every lesson in {enrollment.course.title}.",
                "\U0001F393",
                f"Complete all lessons in {enrollment.course.title}",
            )

    return newly_awarded
