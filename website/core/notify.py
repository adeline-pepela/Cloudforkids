"""Branded emails sent through the configured email backend (Resend in production).

Account emails (consent, approval, assignments) are sent always. Progress summaries and reminders respect
`User.email_notifications`, and each carries a one-click "stop these emails" link.
"""

import logging
import threading
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

logger = logging.getLogger(__name__)
TAGLINE = "Learn the cloud, one step at a time"
UNSUB_SALT = "c4k-unsubscribe"


def site_url():
    return settings.SITE_URL.rstrip("/")


def absolute(path):
    return f"{site_url()}{path}"


def unsubscribe_url(user):
    token = signing.dumps({"u": user.pk}, salt=UNSUB_SALT)
    return absolute(reverse("accounts:unsubscribe", args=[token]))


def read_unsubscribe_token(token):
    try:
        return signing.loads(token, salt=UNSUB_SALT, max_age=60 * 60 * 24 * 365)["u"]
    except (signing.BadSignature, KeyError):
        return None


def _deliver(message):
    try:
        message.send()
        return True
    except Exception:
        logger.exception("Could not send '%s' to %s", message.subject, message.to)
        return False


def send_email(to, subject, heading, paragraphs, *, cta=None, stats=None, bullets=None, note=None, user=None, optional=False, background=True):
    """Send one branded email. Returns True if it was handed to the mail service."""
    recipients = [to] if isinstance(to, str) else [t for t in to if t]
    if not recipients:
        return False
    if optional and user is not None and not user.email_notifications:
        return False
    ctx = {
        "tagline": TAGLINE, "heading": heading, "paragraphs": paragraphs, "stats": stats, "bullets": bullets, "note": note,
        "cta_text": cta[0] if cta else "", "cta_url": cta[1] if cta else "",
        "unsubscribe_url": unsubscribe_url(user) if (optional and user is not None) else "",
    }
    text = render_to_string("emails/branded.txt", ctx)
    html = render_to_string("emails/branded.html", ctx)
    message = EmailMultiAlternatives(subject, text, settings.DEFAULT_FROM_EMAIL, recipients)
    message.attach_alternative(html, "text/html")
    if background and not settings.TESTING:  # do not make a visitor wait for the mail service
        threading.Thread(target=_deliver, args=(message,), daemon=True).start()
        return True
    return _deliver(message)


def _name(user):
    return user.first_name or user.username


# ---------------- account emails ----------------

def send_welcome(user):
    if user.role == "facilitator":
        paragraphs = [
            f"Welcome, {_name(user)}. Your facilitator account has been created.",
            "Our team checks every new facilitator before class tools are switched on. This usually takes a day or two. "
            "We will email you as soon as you are approved.",
        ]
        cta = None
    elif user.role == "parent":
        paragraphs = [
            f"Welcome, {_name(user)}. Your parent account is ready.",
            "Ask your child to open My Profile and read out their family code. Then use Add a child to follow their progress from 0 to 100%.",
        ]
        cta = ("Add my child", absolute(reverse("family:add")))
    else:
        paragraphs = [
            f"Welcome to Cloud for Kids, {_name(user)}!",
            "Start your first lesson, try a Practice Lab and keep your learning streak going.",
        ]
        cta = ("Start learning", absolute(reverse("dashboard:home")))
    return send_email(user.email, "Welcome to Cloud for Kids", "You're in!", paragraphs, cta=cta)


def send_consent_request(consent):
    child = consent.user
    link = absolute(reverse("accounts:consent", args=[consent.token]))
    return send_email(
        consent.parent_email,
        f"Please approve {_name(child)}'s Cloud for Kids account",
        f"{_name(child)} would like to join Cloud for Kids",
        [
            f"Hello{(' ' + consent.parent_name) if consent.parent_name else ''},",
            f"{child.get_full_name() or child.username} has asked to join Cloud for Kids, a free cloud-computing learning programme for children in Kenya. "
            "Because they are under 13, we need your permission before the account can be used.",
            "The next page explains what we collect and why. You can approve or decline there. If you do nothing, the account stays locked.",
        ],
        cta=("Review and decide", link),
        note="If you do not know this child or did not expect this email, just ignore it.",
    )


def send_consent_result(consent, approved):
    child = consent.user
    if approved:
        return send_email(
            consent.parent_email, f"{_name(child)} can now use Cloud for Kids", "Thank you for approving",
            [f"{_name(child)}'s account is now active and can log in with the username {child.username}.",
             "Want to follow their progress? Create a free parent account, choose Parent / Guardian, and link with the family code on your child's profile page."],
            cta=("Create a parent account", absolute(reverse("accounts:signup"))),
        )
    return send_email(
        consent.parent_email, "Cloud for Kids account declined", "The account has been removed",
        ["As you asked, we have deleted the Cloud for Kids account request and the details that came with it. Nothing else is kept."],
    )


def notify_admins_new_facilitator(user):
    from .models import SiteSetting

    return send_email(
        SiteSetting.load().contact_email, "New facilitator waiting for approval", "A facilitator needs approval",
        [f"{user.get_full_name() or user.username} ({user.email}) signed up as a facilitator or teacher."],
        cta=("Review in the admin", absolute(reverse("admin:accounts_user_changelist") + "?role__exact=facilitator&is_approved__exact=0")),
    )


def send_teacher_approved(user):
    return send_email(
        user.email, "Your facilitator account is approved", "You're approved!",
        [f"Good news, {_name(user)}. You can now create classes, share join codes and follow your learners' progress."],
        cta=("Open my dashboard", absolute(reverse("teach:home"))),
    )


# ---------------- classes and messages ----------------

def family_recipients(learner):
    """People to email about a learner: the learner (if they have an email) and any linked parent accounts."""
    people = []
    if learner.email:
        people.append(learner)
    people.extend(link.parent for link in learner.parent_links.select_related("parent") if link.parent.email)
    return people


def notify_assignment(assignment):
    classroom, course = assignment.classroom, assignment.course
    due = f" Please finish it by {assignment.due_date:%d %B %Y}." if assignment.due_date else ""
    sent = 0
    for member in classroom.memberships.select_related("learner"):
        for person in family_recipients(member.learner):
            subject = f"New assignment from {classroom.facilitator.first_name or 'your teacher'}: {course.title}"
            paragraphs = [
                f"Your teacher set a new assignment for {classroom.name}: {course.title}.{due}" if person.pk == member.learner_id
                else f"{_name(member.learner)}'s teacher set a new assignment for {classroom.name}: {course.title}.{due}",
            ]
            if assignment.note:
                paragraphs.append(f"Message from the teacher: {assignment.note}")
            url = absolute(reverse("dashboard:home") if person.pk == member.learner_id else reverse("family:child", args=[member.learner_id]))
            sent += send_email(person.email, subject, "New assignment", paragraphs, cta=("Open Cloud for Kids", url), user=person, optional=True)
    return sent


def send_message_email(message):
    recipient = message.recipient
    sender = message.sender
    url = absolute(reverse("messaging:inbox"))
    return send_email(
        recipient.email, f"Message from {_name(sender)}: {message.subject}", message.subject,
        [f"{sender.get_full_name() or sender.username} wrote:", message.body],
        cta=("Open my messages", url), user=recipient, optional=True,
    )


# ---------------- scheduled: weekly summary and nudges ----------------

def _log(user, kind, key):
    from accounts.models import NotificationLog

    _, created = NotificationLog.objects.get_or_create(user=user, kind=kind, key=key)
    return created


def run_weekly_summaries(dry_run=False):
    """One email per parent each ISO week, covering all their linked children."""
    from accounts.models import ParentLink, User
    from dashboard.family import child_report

    year, week, _ = timezone.now().isocalendar()
    key = f"{year}-W{week:02d}"
    sent = 0
    for parent in User.objects.filter(role="parent", is_active=True, email_notifications=True).exclude(email=""):
        links = ParentLink.objects.filter(parent=parent).select_related("child")
        if not links:
            continue
        if not dry_run and not _log(parent, "weekly", key):
            continue
        bullets, stats = [], None
        for link in links:
            r = child_report(link.child)
            bullets.append(
                f"{r['name']}: {r['percent']}% of the path done, {r['this_week']} lesson or lab"
                f"{'s' if r['this_week'] != 1 else ''} this week, {r['stats']['streak']}-day streak"
                + (f", quiz average {r['avg_score']}%" if r["avg_score"] is not None else "") + f". Last active {r['last_active_text']}."
            )
        if len(links) == 1:
            r = child_report(links[0].child)
            stats = [{"value": f"{r['percent']}%", "label": "of path done"}, {"value": r["this_week"], "label": "done this week"},
                     {"value": r["stats"]["streak"], "label": "day streak"}]
        if dry_run:
            sent += 1
            continue
        ok = send_email(
            parent.email, "Your child's week on Cloud for Kids", f"Here is the week, {_name(parent)}",
            ["A quick look at how your child is doing:"], bullets=bullets, stats=stats,
            cta=("See the full report", absolute(reverse("family:home"))), user=parent, optional=True, background=False,
        )
        sent += bool(ok)
    return sent


def run_nudges(days=4, dry_run=False):
    """Remind a learner (and their parents) when there has been no activity for a few days. One reminder per quiet spell."""
    from accounts.models import User
    from dashboard.family import child_report

    now = timezone.now()
    sent = 0
    for child in User.objects.filter(role="learner", is_active=True).select_related("learner_profile"):
        r = child_report(child)
        last = r["last_active"]
        if last is None:
            if now - child.date_joined < timedelta(days=days - 1):
                continue
            key, line = "never", f"{_name(child)} has not finished a lesson yet. A first 10-minute lesson is the best way to start."
        elif (now - last) >= timedelta(days=days) and r["percent"] < 100:
            key, line = last.date().isoformat(), f"{_name(child)} has not studied for {(now - last).days} days. Keep the streak alive with one short lesson."
        else:
            continue
        for person in family_recipients(child):
            if dry_run:
                sent += 1
                continue
            if not person.email_notifications or not _log(person, "nudge", f"{child.pk}:{key}"):
                continue
            to_child = person.pk == child.pk
            sent += bool(send_email(
                person.email, "A little nudge from Cloud for Kids", "Time for a short lesson?",
                [line.replace(f"{_name(child)} has", "You have").replace(f"{_name(child)}'s", "your") if to_child else line],
                cta=("Open Cloud for Kids", absolute(reverse("dashboard:home") if to_child else reverse("family:child", args=[child.pk]))),
                user=person, optional=True, background=False,
            ))
    return sent
