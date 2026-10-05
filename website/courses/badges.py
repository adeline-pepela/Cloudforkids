"""Simple badge-awarding rules, checked after a learner completes a lesson or a practice lab."""

from .models import Badge, Enrollment, LearnerBadge, LessonCompletion


def check_and_award_badges(user):
    # Imported here: the dashboard app depends on courses, so a top-level import would be circular.
    from dashboard.labs import lab_count
    from dashboard.models import LabCompletion
    from dashboard.stats import learning_streak

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
        award("First Lesson", "Completed your very first lesson.", "rocket-takeoff-fill", "Complete 1 lesson")

    if total_completions >= 5:
        award("Rising Cloud", "Completed 5 lessons.", "cloud-fill", "Complete 5 lessons")

    if total_completions >= 15:
        award("Cloud Champion", "Completed 15 lessons across the programme.", "trophy-fill", "Complete 15 lessons")

    labs_done = LabCompletion.objects.filter(learner=user).count()
    if labs_done >= 1:
        award("Lab Explorer", "Finished your first Practice Lab.", "wrench-adjustable", "Finish 1 Practice Lab")
    if labs_done >= lab_count() > 0:
        award("Lab Master", "Finished every Practice Lab.", "stars", "Finish all Practice Labs")

    streak = learning_streak(user)
    if streak >= 3:
        award("3-Day Streak", "Learned three days in a row.", "fire", "Learn 3 days in a row")
    if streak >= 7:
        award("7-Day Streak", "Learned seven days in a row.", "lightning-charge-fill", "Learn 7 days in a row")

    for enrollment in Enrollment.objects.filter(learner=user):
        if enrollment.is_complete:
            award(
                f"{enrollment.course.title} Graduate",
                f"Finished every lesson in {enrollment.course.title}.",
                "mortarboard-fill",
                f"Complete all lessons in {enrollment.course.title}",
            )

    return newly_awarded
