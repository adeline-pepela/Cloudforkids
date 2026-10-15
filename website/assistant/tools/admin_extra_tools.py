"""Admin tools beyond plain records: plans and payments (through billing.services), group emails (through core.notify)
and learner import from an attached CSV (through the same function as Tools > Import learners).
M-Pesa payouts are deliberately absent: money leaving the business is always sent by a person."""

import threading

from django.conf import settings

from . import Result, ToolError, iso, short, tool
from .admin_tools import AREA, _admin_url, _staff

EMAIL_LIMIT = 3000
AUDIENCES = {
    "all_parents": "every parent and guardian", "all_learners": "every learner", "all_facilitators": "every facilitator",
    "class_parents": "the parents of one class", "class_learners": "the learners of one class",
    "tier_parents": "the parents of learners in one programme tier",
}


def _learner(ctx, learner_id):
    from accounts.models import User

    _staff(ctx)
    learner = User.objects.filter(pk=learner_id or 0, role=User.Role.LEARNER).first()
    if learner is None:
        raise ToolError(f"No learner with id {learner_id}. Find them with search_records on accounts.user.")
    return learner


def _name(user):
    return user.get_full_name() or user.username


def _plan(name):
    from billing.models import Plan

    plan = Plan.objects.filter(slug__iexact=str(name)).first() or Plan.objects.filter(name__iexact=str(name)).first()
    if plan is None:
        raise ToolError(f"No plan called {name}. Plans: {', '.join(Plan.objects.values_list('name', flat=True))}.")
    return plan


def _need_perm(ctx, perm, what):
    if not ctx.user.has_perm(perm):
        raise ToolError(f"You don't have permission to {what}.")


# ---------------------------------------------------------------- plans and payments

def _undo_grant(ctx, info):
    from billing import access
    from billing.models import Payment, Subscription

    _need_perm(ctx, "billing.delete_subscription", "remove plans")
    sub = Subscription.objects.filter(pk=info["id"]).select_related("learner").first()
    if sub is None:
        return "It was already gone."
    if Payment.objects.filter(subscription=sub).exists():
        raise ToolError("A payment is attached to that plan now, so it was left in place.")
    sub.delete()
    access.forget(sub.learner)
    return "Removed the plan it gave."


@tool(AREA, "give_plan",
      "Give a learner a plan without a payment (a sponsored or pilot place), as adding a Subscription in the admin does. "
      "A renewal of the same plan starts when the current one ends.",
      {"learner_id": {"type": "integer"}, "plan": {"type": "string", "description": "Plan name, e.g. Core"},
       "note": {"type": "string", "description": "Why, e.g. Sponsored by the Konza pilot"}}, ["learner_id", "plan"],
      writes=True, always_confirm=True, undo=_undo_grant,
      describe=lambda ctx, a: f"Give {_name(_learner(ctx, a.get('learner_id')))} the {a.get('plan')} plan free"
                              + (f" ({a['note']})" if a.get("note") else ""))
def give_plan(ctx, args):
    from billing import services

    _need_perm(ctx, "billing.add_subscription", "give plans")
    learner, plan = _learner(ctx, args.get("learner_id")), _plan(args.get("plan"))
    sub = services.grant(learner, plan, note=str(args.get("note") or "Given by an admin")[:200])
    return Result({"message": f"{_name(learner)} is on {plan.name} from {iso(sub.starts_at)} to {iso(sub.ends_at)}."},
                  undo={"id": sub.pk}, undo_label="Remove the plan")


@tool(AREA, "record_payment",
      "Record money received outside the website (cash, bank transfer, M-Pesa sent to the Paybill) for a learner's plan, "
      "as Payments > Add does. The plan starts at once and a receipt is emailed.",
      {"learner_id": {"type": "integer"}, "plan": {"type": "string"},
       "amount": {"type": "integer", "description": "KES received; leave out for the full price"},
       "method": {"type": "string", "enum": ["cash", "bank", "mpesa", "other"]},
       "reference": {"type": "string", "description": "Bank or M-Pesa reference"}, "note": {"type": "string"}},
      ["learner_id", "plan", "method"], writes=True, always_confirm=True,
      describe=lambda ctx, a: f"Record a {a.get('method')} payment of "
                              + (f"KES {int(a['amount']):,}" if a.get("amount") not in (None, "") else "the full price")
                              + f" for {_name(_learner(ctx, a.get('learner_id')))}'s {a.get('plan')} plan, and email the receipt")
def record_payment(ctx, args):
    from billing import services

    _need_perm(ctx, "billing.add_payment", "record payments")
    learner, plan = _learner(ctx, args.get("learner_id")), _plan(args.get("plan"))
    amount = plan.price_kes if args.get("amount") in (None, "") else int(args["amount"])
    if amount < 0:
        raise ToolError("The amount can't be negative.")
    method = args.get("method") if args.get("method") in ("cash", "bank", "mpesa", "other") else "cash"
    payment = services.record_manual_payment(
        learner, plan, amount, method, reference=str(args.get("reference") or "")[:60], note=str(args.get("note") or "")[:200],
        recorded_by=ctx.user,
    )
    return Result({"message": f"Recorded KES {amount:,} for {_name(learner)}. {plan.name} has started and the receipt is on its way.",
                   "status": payment.get_status_display()}, link=_admin_url(payment))


# ---------------------------------------------------------------- group emails

def _audience(args):
    from accounts.models import ClassMembership, ParentLink, User

    who = args.get("audience")
    people = User.objects.filter(is_active=True).exclude(email="")
    if who == "all_parents":
        return people.filter(role=User.Role.PARENT)
    if who == "all_learners":
        return people.filter(role=User.Role.LEARNER)
    if who == "all_facilitators":
        return people.filter(role=User.Role.FACILITATOR, is_approved=True)
    if who in ("class_parents", "class_learners"):
        kids = ClassMembership.objects.filter(classroom_id=args.get("class_id") or 0).values("learner")
        if who == "class_learners":
            return people.filter(pk__in=kids)
        return people.filter(pk__in=ParentLink.objects.filter(child__in=kids).values("parent"))
    if who == "tier_parents":
        kids = User.objects.filter(learner_profile__tier__name__iexact=str(args.get("tier") or "")).values("pk")
        return people.filter(pk__in=ParentLink.objects.filter(child__in=kids).values("parent"))
    raise ToolError(f"Choose an audience: {', '.join(AUDIENCES)}.")


def _describe_email(ctx, args):
    _staff(ctx)
    count = _audience(args).filter(email_notifications=True).count()
    return (f"Email \"{short(args.get('subject'), 60)}\" to {AUDIENCES.get(args.get('audience'), 'a group')} "
            f"({count} {'person' if count == 1 else 'people'} who accept emails)")


@tool(AREA, "email_announcement",
      "Send a branded Cloud for Kids email to a group: every parent, learner or facilitator, the parents or learners of one "
      "class, or the parents of one tier. People who turned emails off are skipped, and every email has an unsubscribe link. "
      "Super admins only.",
      {"audience": {"type": "string", "enum": list(AUDIENCES)},
       "class_id": {"type": "integer", "description": "For class_parents or class_learners"},
       "tier": {"type": "string", "description": "Tier name, for tier_parents"}, "subject": {"type": "string"},
       "heading": {"type": "string"}, "message": {"type": "string", "description": "The body. Separate paragraphs with a blank line"},
       "button_text": {"type": "string"}, "button_link": {"type": "string", "description": "A page on the Cloud for Kids website"}},
      ["audience", "subject", "message"], writes=True, always_confirm=True, describe=_describe_email)
def email_announcement(ctx, args):
    from core import notify

    _staff(ctx)
    if not ctx.user.is_superuser:
        raise ToolError("Only a super admin can email groups.")
    people = list(_audience(args).filter(email_notifications=True)[:EMAIL_LIMIT + 1])
    if not people:
        raise ToolError("Nobody in that group has an email address and accepts emails.")
    if len(people) > EMAIL_LIMIT:
        raise ToolError(f"That is more than {EMAIL_LIMIT} people. Send it in smaller groups.")
    cta = None
    link = str(args.get("button_link") or "")
    if args.get("button_text") and link:
        link = notify.absolute(link) if link.startswith("/") else link
        if not link.startswith(notify.site_url()):
            raise ToolError("Buttons may only link to the Cloud for Kids website.")
        cta = (str(args["button_text"])[:40], link)
    paragraphs = [p.strip() for p in str(args.get("message", "")).split("\n\n") if p.strip()]
    subject = str(args.get("subject"))[:150]
    heading = str(args.get("heading") or subject)[:150]

    def deliver():
        for person in people:
            notify.send_email(person.email, subject, heading, paragraphs, cta=cta, user=person, optional=True, background=False)

    if settings.TESTING:
        deliver()
    else:
        threading.Thread(target=deliver, daemon=True).start()
    n = len(people)
    return Result({"message": f"Sending to {n} {'person' if n == 1 else 'people'}. A big group takes a few minutes."})


# ---------------------------------------------------------------- learner import from an attached CSV

def _undo_import(ctx, info):
    from accounts.models import User

    _need_perm(ctx, "accounts.delete_user", "delete accounts")
    gone = User.objects.filter(pk__in=info["ids"], role=User.Role.LEARNER, last_login__isnull=True).delete()[0]
    return f"Removed the new learner accounts nobody had signed in to yet ({gone} records)."


@tool(AREA, "import_learners",
      "Create learner accounts from a CSV file attached to this chat, exactly as Tools > Import learners does. Columns: "
      "first_name, last_name (required), username, email, date_of_birth (2014-03-12), grade, school, county, parent_name, "
      "parent_email, parent_phone. Use it only after the admin has confirmed the school or organisation holds parental "
      "consent for any learner under 13.",
      {"file": {"type": "string", "description": "The attached file's name; leave out for the newest"},
       "class_id": {"type": "integer", "description": "Add everyone to this class (optional)"},
       "tier": {"type": "string", "description": "Programme tier name (optional)"},
       "consent_confirmed": {"type": "boolean", "description": "The admin confirmed parental consent is held for under-13s"}},
      ["consent_confirmed"], writes=True, always_confirm=True, undo=_undo_import,
      describe=lambda ctx, a: f"Create learner accounts from {ctx.attachment(a.get('file')).get('name')}"
                              + (f" and add them to class {a['class_id']}" if a.get("class_id") else "")
                              + " (parental consent for under-13s confirmed)")
def import_learners(ctx, args):
    from accounts.models import Classroom
    from core.admin_tools import create_learners
    from courses.models import Tier

    _staff(ctx)
    _need_perm(ctx, "accounts.add_user", "add users")
    if not args.get("consent_confirmed"):
        raise ToolError("First confirm that the school or organisation holds parental consent for any learner under 13.")
    file = ctx.attachment(args.get("file"))
    if file.get("kind") != "text":
        raise ToolError("Attach the learners as a CSV file.")
    classroom = Classroom.objects.filter(pk=args["class_id"], archived=False).first() if args.get("class_id") else None
    if args.get("class_id") and classroom is None:
        raise ToolError("There is no active class with that id.")
    tier = Tier.objects.filter(name__iexact=str(args["tier"])).first() if args.get("tier") else None
    created, errors = create_learners(file.get("text", "").lstrip("﻿"), classroom, tier)
    return Result({
        "created": len(created), "skipped_rows": [{"row": n, "why": why} for n, why in errors][:30],
        "logins": [{"name": f"{c['first']} {c['last']}", "username": c["username"], "password": c["password"]} for c in created],
        "note": "Share the logins safely. Learners can change their password after signing in.",
    }, undo={"ids": [c["id"] for c in created]}, undo_label="Remove these accounts")
