"""Plan renewal reminders: 5 days before, 1 day before, and on the day a plan runs out. Run daily."""

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from core import notify

from .models import Subscription

BEFORE = (5, 1)  # days before the end


def _plan_end(learner, now):
    """When the learner's access really ends: the latest end among their current and queued periods."""
    latest = Subscription.objects.filter(learner=learner, ends_at__gt=now).order_by("-ends_at").first()
    return latest


def _send(learner, sub, kind, subject, heading, line):
    """One email per person per period and kind (NotificationLog keeps them from repeating)."""
    sent = 0
    key = f"{sub.pk}:{kind}"
    for person in notify.family_recipients(learner):
        if not notify._log(person, "plan", key):
            continue
        to_child = person.pk == learner.pk
        url = reverse("billing:checkout", args=[sub.plan.slug]) + ("" if to_child else f"?learner={learner.pk}")
        sent += bool(notify.send_email(
            person.email, subject, heading,
            [line.replace(f"{notify._name(learner)}'s", "your") if to_child else line],
            cta=(f"Renew {sub.plan.name}", notify.absolute(url)), background=False,
        ))
    return sent


def run_plan_reminders(dry_run=False):
    now = timezone.now()
    sent = 0
    # coming to an end
    for days in BEFORE:
        start, stop = now + timedelta(days=days - 1), now + timedelta(days=days)
        for sub in Subscription.objects.filter(ends_at__gt=start, ends_at__lte=stop).select_related("learner", "plan"):
            if _plan_end(sub.learner, now).pk != sub.pk:
                continue  # a renewal is already queued after this period
            if dry_run:
                sent += 1
                continue
            when = "tomorrow" if days == 1 else f"in {days} days"
            sent += _send(
                sub.learner, sub, f"{days}d", f"{notify._name(sub.learner)}'s {sub.plan.name} plan ends {when}",
                "Time to renew?",
                f"{notify._name(sub.learner)}'s {sub.plan.name} plan ends on {timezone.localtime(sub.ends_at):%A %d %B}. "
                f"Renew now to keep lessons, quizzes and labs open without a break.",
            )
    # just ended (in the last day) with nothing after it
    for sub in Subscription.objects.filter(ends_at__gt=now - timedelta(days=1), ends_at__lte=now).select_related("learner", "plan"):
        if _plan_end(sub.learner, now) is not None or "(refunded)" in sub.note:
            continue
        if dry_run:
            sent += 1
            continue
        sent += _send(
            sub.learner, sub, "ended", f"{notify._name(sub.learner)}'s {sub.plan.name} plan has ended",
            "The plan has ended",
            f"{notify._name(sub.learner)}'s {sub.plan.name} plan ended today, so lessons are locked for now. "
            f"Progress, badges and certificates are all kept. Renew any time to carry on.",
        )
    return sent
