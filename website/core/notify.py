"""Branded emails sent through the configured email backend (Resend in production).

The wording of every email lives in core.email_text, in English and Kiswahili; each person gets their own language.
Account emails (sign-up, consent, approval, password, receipts) are always sent. The rest belong to a category that
people can turn off on their email settings page; those carry a one-click unsubscribe header for Gmail and Yahoo.
"""

import logging
import threading
from datetime import datetime, time, timedelta

from django.conf import settings
from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.db import close_old_connections
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone

from . import email_text as T

logger = logging.getLogger(__name__)
TAGLINE = "Learn the cloud, one step at a time"
UNSUB_SALT = "c4k-unsubscribe"
CONFIRM_SALT = "c4k-confirm-email"
CONFIRM_MAX_AGE = 60 * 60 * 24 * 14


def site_url():
    return settings.SITE_URL.rstrip("/")


def absolute(path):
    return f"{site_url()}{path}"


def email_header_url():
    """The animated header (logo and drifting clouds) at the top of every email. Built by scripts/make_email_header.py."""
    return absolute(static("img/email/header.gif"))


# ---------------- links: email settings, one-click unsubscribe, confirming an address ----------------

def settings_token(user, category=None):
    data = {"u": user.pk}
    if category:
        data["c"] = category
    return signing.dumps(data, salt=UNSUB_SALT)


def read_settings_token(token):
    """(user id, category or None) from an email settings link, or (None, None)."""
    try:
        data = signing.loads(token, salt=UNSUB_SALT, max_age=60 * 60 * 24 * 365)
        return data["u"], data.get("c")
    except (signing.BadSignature, KeyError, TypeError):
        return None, None


def read_unsubscribe_token(token):
    return read_settings_token(token)[0]


def unsubscribe_url(user, category=None):
    """The email settings page for this person (no login needed); with a category it offers to stop that kind."""
    url = absolute(reverse("accounts:email_settings", args=[settings_token(user)]))
    return f"{url}?stop={category}" if category else url


def one_click_url(user, category):
    return absolute(reverse("accounts:one_click_unsubscribe", args=[settings_token(user, category)]))


def confirm_url(user, next_path=""):
    token = signing.dumps({"u": user.pk, "e": user.email.strip().lower()}, salt=CONFIRM_SALT)
    url = absolute(reverse("accounts:confirm_email", args=[token]))
    return f"{url}?next={next_path}" if next_path else url


def read_confirm_token(token):
    try:
        data = signing.loads(token, salt=CONFIRM_SALT, max_age=CONFIRM_MAX_AGE)
        return data["u"], data["e"]
    except (signing.BadSignature, KeyError, TypeError):
        return None, None


# ---------------- composing and sending ----------------

def lang_for(person):
    return T.lang_of(getattr(person, "language", "en"))


def _fmt(value, values):
    return value.format(**values) if isinstance(value, str) else value


def compose(kind, lang, values=None, *, extra=(), bullets=None, stats=None, cta_url="", cta_text=None, user=None, note=None, preview=None):
    """The subject and the template context of one email. `extra` paragraphs are added as written (a teacher's note)."""
    entry = T.EMAILS[kind]
    words = entry[lang]
    values = values or {}
    category = entry["category"]
    paragraphs = [_fmt(p, values) for p in words.get("paragraphs", [])] + [p for p in extra if p]
    stat_labels = words.get("stats", [])
    ctx = {
        "lang": lang, "chrome": T.CHROME[lang], "header_url": email_header_url(),
        "heading": _fmt(words.get("heading", ""), values), "paragraphs": paragraphs,
        "stats": [{"value": v, "label": label} for v, label in zip(stats or [], stat_labels)] or None,
        "bullets": bullets or None,
        "cta_text": (cta_text or _fmt(words.get("cta", ""), values)) if cta_url else "", "cta_url": cta_url,
        "note": note if note is not None else _fmt(words.get("note", ""), values),
        "preview": preview or (paragraphs[0] if paragraphs else ""),
        "settings_url": unsubscribe_url(user) if user is not None and user.pk else "",
        "stop_url": unsubscribe_url(user, category) if (category and user is not None and user.pk) else "",
    }
    return _fmt(words.get("subject", ""), values), ctx, category


def _deliver(message):
    try:
        message.send()
        return True
    except Exception:
        logger.exception("Could not send '%s' to %s", message.subject, message.to)
        return False
    finally:
        if threading.current_thread() is not threading.main_thread():
            close_old_connections()  # the email log write opened a connection in this thread


def send(kind, to, *, lang="en", values=None, user=None, extra=(), bullets=None, stats=None, cta_url="", cta_text=None, note=None,
         background=True):
    """Send one email from the catalog. `user` is the account it is for (their settings and unsubscribe links).
    Returns True if it was handed to the mail service."""
    recipients = [to] if isinstance(to, str) else [t for t in to if t]
    if not recipients:
        return False
    category = T.EMAILS[kind]["category"]
    if category and user is not None and not user.wants_email(category):
        return False
    subject, ctx, category = compose(kind, lang, values, extra=extra, bullets=bullets, stats=stats, cta_url=cta_url, cta_text=cta_text,
                                     user=user, note=note)
    text = render_to_string("emails/branded.txt", ctx)
    html = render_to_string("emails/branded.html", ctx)
    headers = {}
    if category and user is not None and user.pk:
        headers = {"List-Unsubscribe": f"<{one_click_url(user, category)}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}
    message = EmailMultiAlternatives(subject, text, settings.DEFAULT_FROM_EMAIL, recipients, headers=headers)
    message.attach_alternative(html, "text/html")
    message.c4k_kind = kind
    message.c4k_user_id = getattr(user, "pk", None)
    if background and not settings.TESTING:  # do not make a visitor wait for the mail service
        threading.Thread(target=_deliver, args=(message,), daemon=True).start()
        return True
    return _deliver(message)


def send_email(to, subject, heading, paragraphs, *, cta=None, user=None, optional=False, background=True, lang="en"):
    """A one-off email written by a person (the assistant's announcements). Optional ones count as News."""
    return send("announcement", to, lang=lang, values={"subject": subject, "heading": heading}, user=user if optional else None,
                extra=paragraphs, cta_url=cta[1] if cta else "", cta_text=cta[0] if cta else None, note="", background=background)


def _name(user):
    return user.first_name or user.username


def course_title(course, lang):
    return (course.title_sw if lang == "sw" else "") or course.title


def ui(text, lang):
    """Website wording (a badge name, a certificate level) in Kiswahili when the site has a translation for it."""
    if lang != "sw" or not text:
        return text
    from .translation import _lookup, load_map

    return _lookup(text, load_map()) or text


def _when(dt, lang):
    local = timezone.localtime(dt)
    return f"{T.day(local, lang)} {'at' if lang == 'en' else 'saa'} {local:%H:%M}"


# ---------------- account emails ----------------

def send_welcome(user):
    lang = lang_for(user)
    if user.role == "facilitator":
        kind, path = "welcome_facilitator", reverse("teach:home")
    elif user.role == "parent":
        kind, path = "welcome_parent", reverse("family:add")
    else:
        kind, path = "welcome_learner", reverse("dashboard:home")
    extra, cta, url = [], None, absolute(path)
    if user.email and not user.email_verified:  # the welcome email doubles as the confirmation email
        extra = T.EMAILS["confirm_line"][lang]["paragraphs"]
        url = confirm_url(user, path)
        cta = T.EMAILS["confirm_line"][lang]["cta"]
    return send(kind, user.email, lang=lang, values={"name": _name(user)}, user=user, extra=extra, cta_url=url, cta_text=cta)


def send_confirm_email(user):
    return send("confirm_email", user.email, lang=lang_for(user), values={"name": _name(user), "email": user.email},
                user=user, cta_url=confirm_url(user))


def send_password_changed(user):
    if not user.email:
        return False
    lang = lang_for(user)
    return send("password_changed", user.email, lang=lang, user=user,
                values={"name": _name(user), "username": user.username, "when": _when(timezone.now(), lang)},
                cta_url=absolute(reverse("accounts:password_reset")))


def send_consent_request(consent):
    child = consent.user
    return send(
        "consent_request", consent.parent_email, lang=lang_for(child),
        values={"child": _name(child), "child_full": child.get_full_name() or child.username,
                "parent": f" {consent.parent_name}" if consent.parent_name else ""},
        cta_url=absolute(reverse("accounts:consent", args=[consent.token])),
    )


def send_consent_result(consent, approved):
    child = consent.user
    if approved:
        return send("consent_approved", consent.parent_email, lang=lang_for(child),
                    values={"child": _name(child), "username": child.username}, cta_url=absolute(reverse("accounts:signup")))
    return send("consent_declined", consent.parent_email, lang=lang_for(child))


def notify_admins_new_facilitator(user):
    from .models import SiteSetting

    return send("admin_new_facilitator", SiteSetting.load().contact_email,
                values={"name": user.get_full_name() or user.username, "email": user.email},
                cta_url=absolute(reverse("admin:accounts_user_changelist") + "?role__exact=facilitator&is_approved__exact=0"))


def send_teacher_approved(user):
    return send("teacher_approved", user.email, lang=lang_for(user), values={"name": _name(user)}, user=user,
                cta_url=absolute(reverse("teach:home")))


def send_parent_linked(parent, child):
    if parent.email:
        send("parent_linked_parent", parent.email, lang=lang_for(parent), values={"child": _name(child)}, user=parent,
             cta_url=absolute(reverse("family:child", args=[child.pk])))
    if child.email:
        send("parent_linked_learner", child.email, lang=lang_for(child), values={"parent": parent.get_full_name() or parent.username},
             user=child)


# ---------------- classes and messages ----------------

def family_recipients(learner):
    """People to email about a learner: the learner (if they have an email) and any linked parent accounts."""
    people = []
    if learner.email:
        people.append(learner)
    people.extend(link.parent for link in learner.parent_links.select_related("parent") if link.parent.email)
    return people


def _for(person, learner, kind_base):
    """('…_learner', link to the learner's page) for the learner, ('…_parent', the family page) for a parent."""
    mine = person.pk == learner.pk
    url = absolute(reverse("dashboard:home") if mine else reverse("family:child", args=[learner.pk]))
    return f"{kind_base}_{'learner' if mine else 'parent'}", url


def notify_assignment(assignment):
    classroom, course = assignment.classroom, assignment.course
    sent = 0
    for member in classroom.memberships.select_related("learner"):
        for person in family_recipients(member.learner):
            kind, url = _for(person, member.learner, "assignment")
            lang = lang_for(person)
            due = T.text(kind, lang, "due", date=T.long_date(assignment.due_date, lang)) if assignment.due_date else ""
            extra = [T.text(kind, lang, "teacher_note", note=assignment.note)] if assignment.note else []
            sent += send(kind, person.email, lang=lang, user=person, cta_url=url, extra=extra, values={
                "teacher": classroom.facilitator.first_name or ("your teacher" if lang == "en" else "mwalimu wako"),
                "course": course_title(course, lang), "classroom": classroom.name, "child": _name(member.learner), "due": due})
    return sent


def notify_live_scheduled(classroom, sessions):
    """Tell learners in the class (and their parents) about newly scheduled live classes, with the link to join."""
    if not sessions:
        return 0
    first = timezone.localtime(sessions[0].starts_at)
    room = sessions[0].live_room_obj
    url = absolute(reverse("live_short", args=[room.code]))
    sent = 0
    for member in classroom.memberships.select_related("learner"):
        for person in family_recipients(member.learner):
            kind, _ = _for(person, member.learner, "live_scheduled")
            lang = lang_for(person)
            sent += send(kind, person.email, lang=lang, user=person, cta_url=url, values={
                "classroom": classroom.name, "child": _name(member.learner),
                "topic": f" ({sessions[0].title})" if sessions[0].title else "",
                "short": T.short_day(first, lang), "when": T.day(first, lang), "time": f"{first:%H:%M}",
                "repeat": T.text(kind, lang, "repeat", n=len(sessions)) if len(sessions) > 1 else "",
                "passcode": T.text(kind, lang, "passcode_line", code=room.passcode) if room.passcode else ""})
    return sent


def send_live_reminder(person, learner, session, room, start):
    kind, _ = _for(person, learner, "live_reminder")
    lang = lang_for(person)
    return send(kind, person.email, lang=lang, user=person, background=False,
                cta_url=absolute(reverse("live_short", args=[room.code])), values={
                    "classroom": session.classroom.name, "title": session.display_title, "time": f"{start:%H:%M}",
                    "child": _name(learner),
                    "passcode": T.text(kind, lang, "passcode_line", code=room.passcode) if room.passcode else ""})


def send_missed_live(parent, learner, classroom, started_at):
    lang = lang_for(parent)
    when = timezone.localtime(started_at)
    return send("missed_live", parent.email, lang=lang, user=parent,
                cta_url=absolute(reverse("family:child", args=[learner.pk])),
                values={"child": _name(learner), "classroom": classroom.name, "when": T.day(when, lang), "time": f"{when:%H:%M}"})


def send_message_email(message):
    recipient, sender = message.recipient, message.sender
    return send("message", recipient.email, lang=lang_for(recipient), user=recipient, extra=[message.body],
                cta_url=absolute(reverse("messaging:inbox")),
                values={"sender": _name(sender), "sender_full": sender.get_full_name() or sender.username, "topic": message.subject})


# ---------------- celebrations ----------------

def badge_bullets(kind, lang, badges):
    return [T.text(kind, lang, "bullet", badge=ui(b.name, lang), description=ui(b.description, lang)) for b in badges]


def send_badges(learner, badges):
    """One email per person for the badges a learner just earned (a lesson can unlock several at once)."""
    if not badges:
        return 0
    from courses.models import Course

    graduate = next((b for b in badges if b.name.endswith(" Graduate")), None)
    course = Course.objects.filter(title=graduate.name[: -len(" Graduate")]).first() if graduate else None
    sent = 0
    for person in family_recipients(learner):
        kind, url = _for(person, learner, "badges")
        lang = lang_for(person)
        if person.pk == learner.pk:
            url = absolute(reverse("dashboard:achievements"))
        extra = [T.text(kind, lang, "course_done", child=_name(learner), course=course_title(course, lang))] if course else []
        sent += send(kind, person.email, lang=lang, user=person, cta_url=url, extra=extra,
                     bullets=badge_bullets(kind, lang, badges),
                     values={"name": _name(learner), "child": _name(learner), "first": ui(badges[0].name, lang)})
    return sent


def send_certificate(cert):
    learner = cert.learner
    url = absolute(reverse("billing:certificate", args=[cert.code]))
    sent = 0
    for person in family_recipients(learner):
        kind, _ = _for(person, learner, "certificate")
        lang = lang_for(person)
        sent += send(kind, person.email, lang=lang, user=person, cta_url=url, values={
            "name": _name(learner), "child": _name(learner), "course": course_title(cert.course, lang),
            "level": ui(cert.get_level_display(), lang), "code": cert.code})
    return sent


# ---------------- scheduled: weekly and monthly reports, nudges ----------------

def _log(user, kind, key):
    from accounts.models import NotificationLog

    _, created = NotificationLog.objects.get_or_create(user=user, kind=kind, key=key)
    return created


def weekly_bullet(lang, r):
    words = T.EMAILS["weekly"][lang]
    score = words["score"].format(n=r["avg_score"]) if r["avg_score"] is not None else ""
    last = T.ago(r["last_active"], timezone.now(), lang)
    return words["bullet"].format(child=r["name"], percent=r["percent"], week=r["this_week"], streak=r["stats"]["streak"],
                                  score=score, last=last)


def run_weekly_summaries(dry_run=False):
    """One email per parent each ISO week, covering all their linked children."""
    from accounts.models import ParentLink, User
    from dashboard.family import child_report

    year, week, _ = timezone.now().isocalendar()
    key = f"{year}-W{week:02d}"
    sent = 0
    for parent in User.objects.filter(role="parent", is_active=True, email_notifications=True, email_progress=True).exclude(email=""):
        links = list(ParentLink.objects.filter(parent=parent).select_related("child"))
        if not links:
            continue
        if not dry_run and not _log(parent, "weekly", key):
            continue
        if dry_run:
            sent += 1
            continue
        lang = lang_for(parent)
        reports = [child_report(link.child) for link in links]
        stats = None
        if len(reports) == 1:
            r = reports[0]
            stats = [f"{r['percent']}%", r["this_week"], r["stats"]["streak"]]
        ok = send("weekly", parent.email, lang=lang, user=parent, values={"name": _name(parent)}, stats=stats,
                  bullets=[weekly_bullet(lang, r) for r in reports], cta_url=absolute(reverse("family:home")), background=False)
        sent += bool(ok)
    return sent


def _last_month(now):
    first_this = timezone.localtime(now).date().replace(day=1)
    first_last = (first_this - timedelta(days=1)).replace(day=1)
    tz = timezone.get_current_timezone()
    return first_last, timezone.make_aware(datetime.combine(first_last, time.min), tz), timezone.make_aware(datetime.combine(first_this, time.min), tz)


def month_numbers(child, start, end):
    from billing.models import Certificate
    from courses.models import LearnerBadge, LessonCompletion
    from dashboard.models import LabCompletion

    return {
        "lessons": LessonCompletion.objects.filter(enrollment__learner=child, completed_at__gte=start, completed_at__lt=end).count(),
        "labs": LabCompletion.objects.filter(learner=child, completed_at__gte=start, completed_at__lt=end).count(),
        "badges": LearnerBadge.objects.filter(learner=child, earned_at__gte=start, earned_at__lt=end).count(),
        "certs": Certificate.objects.filter(learner=child, issued_at__gte=start, issued_at__lt=end).count(),
    }


def monthly_bullet(lang, name, numbers, percent, avg_score):
    words = T.EMAILS["monthly"][lang]
    if not (numbers["lessons"] or numbers["labs"] or numbers["badges"] or numbers["certs"]):
        return words["quiet"].format(child=name)
    score = words["score"].format(n=avg_score) if avg_score is not None else ""
    return words["bullet"].format(child=name, percent=percent, score=score, **numbers)


def run_monthly_reports(dry_run=False, now=None, any_day=False):
    """On the first days of a month: one review of the month before per parent, covering all their children.
    The daily job calls it every day; it only sends on the 1st to the 3rd (once per parent, thanks to the log)."""
    from accounts.models import ParentLink, User
    from dashboard.family import child_report

    now = now or timezone.now()
    if not any_day and timezone.localtime(now).day > 3:
        return 0
    month, start, end = _last_month(now)
    key = f"{month:%Y-%m}"
    sent = 0
    for parent in User.objects.filter(role="parent", is_active=True, email_notifications=True, email_progress=True).exclude(email=""):
        links = list(ParentLink.objects.filter(parent=parent).select_related("child"))
        if not links:
            continue
        if dry_run:
            sent += 1
            continue
        if not _log(parent, "monthly", key):
            continue
        lang = lang_for(parent)
        bullets, stats = [], None
        for link in links:
            numbers, r = month_numbers(link.child, start, end), child_report(link.child)
            bullets.append(monthly_bullet(lang, _name(link.child), numbers, r["percent"], r["avg_score"]))
            bullets.extend(area_bullets("monthly", lang, _name(link.child), r["strengths"], r["weak"]))
            if len(links) == 1:
                stats = [numbers["lessons"], numbers["labs"], numbers["badges"]]
        ok = send("monthly", parent.email, lang=lang, user=parent, bullets=bullets, stats=stats,
                  values={"name": _name(parent), "month": T.month_name(month, lang)},
                  cta_url=absolute(reverse("family:home")), background=False)
        sent += bool(ok)
    return sent


def lesson_title(lesson, lang):
    return (lesson.title_sw if lang == "sw" else "") or lesson.title


def area_bullets(kind, lang, child, strong, weak):
    """'Strong in …' and 'Needs practice …' lines from lists of QuizResults."""
    words, out = T.EMAILS[kind][lang], []
    if strong:
        out.append(words["strong"].format(child=child, items=", ".join(lesson_title(q.lesson, lang) for q in strong[:3])))
    if weak:
        out.append(words["weak"].format(child=child, items=", ".join(lesson_title(q.lesson, lang) for q in weak[:3])))
    return out


def report_recipients(learner):
    """(email, account or None, language) for each parent of a learner: linked parent accounts, then the guardian email on the profile."""
    people, seen = [], set()
    for link in learner.parent_links.select_related("parent"):
        if link.parent.email and link.parent.email.lower() not in seen:
            seen.add(link.parent.email.lower())
            people.append((link.parent.email, link.parent, lang_for(link.parent)))
    profile = getattr(learner, "learner_profile", None)
    guardian = (profile.parent_guardian_email or "").strip() if profile else ""
    if guardian and guardian.lower() not in seen:
        people.append((guardian, None, lang_for(learner)))
    return people


def send_progress_report(learner, report):
    """Email a learner's progress report (numbers, strong and weak areas, the next lesson) to their parents. Sent by an admin."""
    sent = 0
    for email, parent, lang in report_recipients(learner):
        name = _name(learner)
        if report["activities"]:
            bullets = area_bullets("progress_report", lang, name, report["strong"], report["weak"])
            nxt = next((c["next"] for c in report["courses"] if c["next"]), None)
            if nxt:
                bullets.append(T.text("progress_report", lang, "next", lesson=lesson_title(nxt, lang)))
        else:
            bullets = [T.text("progress_report", lang, "quiet", child=name)]
        url = absolute(reverse("family:child", args=[learner.pk])) if parent else absolute(reverse("core:home"))
        quiz = f"{report['quiz_avg']}%" if report["quiz_avg"] is not None else "-"
        sent += bool(send("progress_report", email, lang=lang, user=parent, bullets=bullets, cta_url=url, background=False,
                          stats=[f"{report['percent']}%", report["lessons_done"], quiz],
                          values={"child": name, "parent": f" {parent.first_name}" if parent and parent.first_name else ""}))
    return sent


def send_manual_nudge(learner):
    """An admin pressed "Send reminder": the usual quiet-learner reminder, to the learner and their parents, right away."""
    from dashboard.family import child_report

    last = child_report(learner)["last_active"]
    sent = 0
    for person in family_recipients(learner):
        if last is None:
            kind, url = _for(person, learner, "nudge_start")
            days = 0
        else:
            kind, url = _for(person, learner, "nudge")
            days = max((timezone.now() - last).days, 1)
        sent += bool(send(kind, person.email, lang=lang_for(person), user=person, cta_url=url, background=False,
                          values={"child": _name(learner), "days": days}))
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
            key, base, quiet = "never", "nudge_start", 0
        elif (now - last) >= timedelta(days=days) and r["percent"] < 100:
            key, base, quiet = last.date().isoformat(), "nudge", (now - last).days
        else:
            continue
        for person in family_recipients(child):
            if dry_run:
                sent += 1
                continue
            if not person.wants_email("reminders") or not _log(person, "nudge", f"{child.pk}:{key}"):
                continue
            kind, url = _for(person, child, base)
            sent += bool(send(kind, person.email, lang=lang_for(person), user=person, cta_url=url, background=False,
                              values={"child": _name(child), "days": quiet}))
    return sent


# ---------------- the admin preview page ----------------

def preview(kind, lang, user=None, header_url=None):
    """(subject, html, text) of one email with sample values, exactly as the template renders it."""
    entry = T.EMAILS[kind]
    sample = dict(entry.get("sample", {}))
    extra = sample.pop(f"_paragraphs_{lang}", None) or sample.pop("_paragraphs", [])
    sample.pop("_paragraphs_sw", None)
    bullets = sample.pop("_bullets", None)
    stats = sample.pop("stats", None)
    rows = sample.pop("bullets", None)
    if rows and kind == "weekly":
        bullets = [weekly_bullet(lang, {"name": b["child"], "percent": b["percent"], "this_week": b["week"], "stats": {"streak": b["streak"]},
                                        "avg_score": b["score"], "last_active": timezone.now()}) for b in rows]
    elif rows and kind == "monthly":
        bullets = [monthly_bullet(lang, b["child"], {k: b[k] for k in ("lessons", "labs", "badges", "certs")}, b["percent"], b["score"]) for b in rows]
    elif rows and kind == "progress_report":
        words = T.EMAILS[kind][lang]
        bullets = [line for b in rows for line in (words["strong"].format(items=b["strong"]), words["weak"].format(items=b["weak"]),
                                                     words["next"].format(lesson=b["next"]))]
    elif rows:
        bullets = [T.text(kind, lang, "bullet", **b) for b in rows]
    # sample dates and set phrases in the reader's language
    sample_day = timezone.make_aware(datetime(2026, 10, 19, 16, 0))
    if "date" in sample:
        sample["date"] = T.day(sample_day + timedelta(days=1), lang) if kind.startswith("plan_") else T.long_date(sample_day + timedelta(days=4), lang)
    if "month" in sample:
        sample["month"] = T.month_name(sample_day - timedelta(days=40), lang)
    if "when" in sample:
        sample["when"] = (_when(sample_day, lang) if kind == "password_changed" else T.text(kind, lang, "tomorrow")
                          if kind.startswith("plan_ending") else T.day(sample_day, lang))
    if "short" in sample:
        sample["short"] = T.short_day(sample_day, lang)
    if kind == "payment_failed":
        sample["reason"] = T.text(kind, lang, "cancelled")
    if "level" in sample:
        sample["level"] = ui(sample["level"], lang)
    if "due" in entry[lang]:
        sample["due"] = T.text(kind, lang, "due", date=sample["date"])
        extra = [T.text(kind, lang, "teacher_note", note="Finish the quiz before Friday's class." if lang == "en" else "Maliza jaribio kabla ya darasa la Ijumaa.")]
    cta_text = None
    if kind.startswith("welcome_"):
        extra, cta_text = T.EMAILS["confirm_line"][lang]["paragraphs"], T.EMAILS["confirm_line"][lang]["cta"]
    if kind == "receipt":
        bullets = [T.text(kind, lang, "receipt_no", n="C4K-000123"), T.text(kind, lang, "mpesa_code", n="TJK8XYZ123")]
    if kind == "announcement":
        cta_text = "See the calendar" if lang == "en" else "Ona kalenda"
    subject, ctx, _ = compose(kind, lang, sample, extra=extra, bullets=bullets, stats=stats, cta_url=absolute("/"), cta_text=cta_text, user=user)
    if not (cta_text or T.EMAILS[kind][lang].get("cta")):
        ctx["cta_url"] = ""
    if header_url:  # the admin page shows the header from this server, even before it is deployed
        ctx["header_url"] = header_url
    return subject, render_to_string("emails/branded.html", ctx), render_to_string("emails/branded.txt", ctx)
