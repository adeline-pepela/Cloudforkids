"""One class, seen by a learner (everything about the class in one place) and its discussion board (shared with the teacher)."""

from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from accounts.models import ClassPost
from courses.models import Enrollment, QuizResult

TABS = ["discussion", "assignments", "quizzes", "schedule", "recordings", "people"]


def short_name(user):
    """First name and an initial: what classmates see of each other."""
    if user.first_name:
        return f"{user.first_name} {user.last_name[:1]}." if user.last_name else user.first_name
    return user.username


def discussion(classroom, teacher_view=False):
    """Top-level posts (pinned first, newest next) with their replies (oldest first). Teachers also see blocked posts."""
    posts = list(
        classroom.posts.filter(parent__isnull=True).select_related("author").prefetch_related("replies__author")
    )
    visible = []
    for post in posts:
        if post.hidden or (post.flagged and not teacher_view):
            continue
        post.visible_replies = [
            r for r in sorted(post.replies.all(), key=lambda r: r.created_at)
            if not r.hidden and (teacher_view or not r.flagged)
        ]
        visible.append(post)
    return visible


def can_post(user, classroom):
    if user.pk == classroom.facilitator_id:
        return True
    return classroom.discussion_enabled and classroom.memberships.filter(learner=user).exists()


def post_too_fast(user):
    """One post every 10 seconds per learner."""
    return not cache.add(f"class-post-{user.pk}", 1, 10)


def learner_class_page(classroom, learner):
    """Everything the class page shows a learner."""
    from live.models import LiveAttendance, LiveRoom
    from live.views import class_recordings

    now = timezone.now()
    today = timezone.localdate()
    enrollments = {e.course_id: e for e in Enrollment.objects.filter(learner=learner).select_related("course")}

    assignments = []
    for a in classroom.assignments.select_related("course"):
        enrollment = enrollments.get(a.course_id)
        percent = enrollment.progress_percent if enrollment else 0
        assignments.append({
            "a": a, "percent": percent, "done": percent >= 100,
            "overdue": bool(a.due_date and a.due_date < today and percent < 100),
            "days_left": (a.due_date - today).days if a.due_date else None,
        })

    # Quizzes: the lessons with quizzes in the courses the teacher assigned (or the class programme when nothing is assigned)
    from courses.models import Course
    from courses.quiz import quiz_question_count

    course_ids = [a["a"].course_id for a in assignments]
    courses = Course.objects.filter(pk__in=course_ids) if course_ids else (
        Course.objects.filter(tier_id=classroom.tier_id) if classroom.tier_id else Course.objects.none()
    )
    results = {r.lesson_id: r for r in QuizResult.objects.filter(learner=learner)}
    quizzes = []
    for course in courses.prefetch_related("lessons"):
        for lesson in course.lessons.all():
            if quiz_question_count(lesson):
                quizzes.append({"lesson": lesson, "course": course, "result": results.get(lesson.pk)})
    quiz_done = sum(1 for q in quizzes if q["result"] and q["result"].passed)

    room = LiveRoom.objects.filter(classroom=classroom).first()
    attended = list(
        LiveAttendance.objects.filter(user=learner, session__room__classroom=classroom, removed=False)
        .select_related("session").order_by("-first_joined_at")[:10]
    )
    members = list(classroom.memberships.select_related("learner"))
    return {
        "classroom": classroom,
        "teacher": classroom.facilitator,
        "assignments": assignments,
        "assignments_open": sum(1 for a in assignments if not a["done"]),
        "quizzes": quizzes,
        "quiz_done": quiz_done,
        "upcoming": list(classroom.sessions.filter(starts_at__gte=now - timedelta(hours=2)).select_related("classroom__live_room")[:12]),
        "live_room": room,
        "live_now": room.current_session if room else None,
        "attended": attended,
        "recordings": list(class_recordings(classroom)[:20]),
        "classmates": sorted((short_name(m.learner) for m in members if m.learner_id != learner.pk), key=str.lower),
        "member_count": len(members),
        "posts": discussion(classroom),
        "can_post": can_post(learner, classroom),
    }
