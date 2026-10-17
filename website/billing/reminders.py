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


def _send(learner, sub, kind, days=None):
    """One email per person per period and kind (NotificationLog keeps them from repeating). `days` = days left, or None
    when the plan has ended."""
    from core import email_text as T

    sent = 0
    key = f"{sub.pk}:{kind}"
    for person in notify.family_recipients(learner):
        if not notify._log(person, "plan", key):
            continue
        to_child = person.pk == learner.pk
        email_kind = f"plan_{'ending' if days else 'ended'}_{'learner' if to_child else 'parent'}"
        lang = notify.lang_for(person)
        url = reverse("billing:checkout", args=[sub.plan.slug]) + ("" if to_child else f"?learner={learner.pk}")
        values = {"child": notify._name(learner), "plan": sub.plan.name}
        if days:
            values["when"] = T.text(email_kind, lang, "tomorrow") if days == 1 else T.text(email_kind, lang, "in_days", n=days)
            values["date"] = T.day(timezone.localtime(sub.ends_at), lang)
        sent += bool(notify.send(email_kind, person.email, lang=lang, user=person, values=values,
                                 cta_url=notify.absolute(url), background=False))
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
            sent += _send(sub.learner, sub, f"{days}d", days=days)
    # just ended (in the last day) with nothing after it
    for sub in Subscription.objects.filter(ends_at__gt=now - timedelta(days=1), ends_at__lte=now).select_related("learner", "plan"):
        if _plan_end(sub.learner, now) is not None or "(refunded)" in sub.note:
            continue
        if dry_run:
            sent += 1
            continue
        sent += _send(sub.learner, sub, "ended")
    return sent
