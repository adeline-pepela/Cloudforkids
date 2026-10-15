"""Work around a live class: reminders before it, and after it badges for those who came and a note to parents of those
who missed it. Run from the request that ends a class and, as a safety net, from the 15-minute cron job."""

import logging
from datetime import timedelta

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import ClassSession, ParentLink
from core import notify

from .models import LiveAttendance, LiveSession

logger = logging.getLogger(__name__)

MIN_MINUTES_FOR_FOLLOWUP = 10  # a quick test call does not send "your child missed class" emails
REMINDER_WINDOW = (timedelta(minutes=5), timedelta(minutes=35))


def live_classes_attended(user):
    return LiveAttendance.objects.filter(user=user, is_host=False, removed=False).count()


def finish_session(session):
    """Mark the class over (if needed), give badges to learners who came and email parents of learners who missed it."""
    if session.followup_done:
        return
    if session.ended_at is None:
        session.ended_at = timezone.now()
    session.followup_done = True
    session.save(update_fields=["ended_at", "followup_done"])
    if session.minutes_long < MIN_MINUTES_FOR_FOLLOWUP:
        return

    from courses.badges import check_and_award_badges

    classroom = session.room.classroom
    came = set(session.attendance.filter(is_host=False, removed=False).values_list("user_id", flat=True))
    for member in classroom.memberships.select_related("learner"):
        learner = member.learner
        if learner.pk in came:
            try:
                check_and_award_badges(learner)
            except Exception:  # a badge problem must never stop the other learners' follow-ups
                logger.exception("Could not award live-class badges to %s", learner.pk)
            continue
        when = timezone.localtime(session.started_at)
        for link in ParentLink.objects.filter(child=learner).select_related("parent"):
            parent = link.parent
            if not parent.email:
                continue
            notify.send_email(
                parent.email, f"{notify._name(learner)} missed today's live class",
                "Missed live class",
                [
                    f"{notify._name(learner)} did not join the live class for {classroom.name} on {when:%A %d %B} at {when:%H:%M}.",
                    "If something got in the way (internet, a device, or another activity), the teacher's next live class is on "
                    "the class calendar. You can also message the teacher from your family dashboard.",
                ],
                cta=("Open the family dashboard", notify.absolute(reverse("family:child", args=[learner.pk]))),
                user=parent, optional=True,
            )


def send_reminders(now=None):
    """Email learners (and their parents) about live classes starting in the next half hour. Once per class each."""
    now = now or timezone.now()
    sessions = ClassSession.objects.filter(
        is_live=True, classroom__archived=False,
        starts_at__gt=now + REMINDER_WINDOW[0], starts_at__lte=now + REMINDER_WINDOW[1],
    ).select_related("classroom__live_room", "classroom__facilitator")
    sent = 0
    for ses in sessions:
        room = getattr(ses.classroom, "live_room", None)
        if room is None:
            continue
        url = notify.absolute(reverse("live_short", args=[room.code]))
        start = timezone.localtime(ses.starts_at)
        for member in ses.classroom.memberships.select_related("learner"):
            for person in notify.family_recipients(member.learner):
                if not notify._log(person, "live-reminder", f"{ses.pk}-{member.learner_id}"):
                    continue
                mine = person.pk == member.learner_id
                sent += notify.send_email(
                    person.email, f"Live class at {start:%H:%M}: {ses.display_title}", "Your live class starts soon",
                    [
                        (f"Your live class for {ses.classroom.name} starts at {start:%H:%M} today." if mine
                         else f"{notify._name(member.learner)}'s live class for {ses.classroom.name} starts at {start:%H:%M} today."),
                        "Open the link a few minutes early and use headphones if you have them.",
                    ],
                    cta=("Join the live class", url), user=person, optional=True, background=False,
                )
    return sent


def run_followups(now=None):
    """Finish classes the teacher left without ending, and any ended class that still needs its follow-up."""
    now = now or timezone.now()
    stale = now - timedelta(minutes=settings.LIVE_MAX_MINUTES)
    done = 0
    for session in LiveSession.objects.filter(followup_done=False).select_related("room__classroom"):
        if session.ended_at is not None or session.started_at < stale:
            finish_session(session)
            done += 1
    return done
