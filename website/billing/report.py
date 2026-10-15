"""Admin billing report: revenue, plan health, and a payment list to match against the M-Pesa / bank statement."""

import csv
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from django.contrib import admin
from django.db.models import Count, Sum
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from .models import Payment, Plan, Subscription

PLAN_COLOURS = {"starter": "#2FBF71", "core": "#1CA7EC", "advanced": "#8B6BE8"}


def _day(text, fallback):
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return fallback


def _bounds(start, end):
    tz = timezone.get_current_timezone()
    return datetime.combine(start, time.min, tz), datetime.combine(end + timedelta(days=1), time.min, tz)


def _months_back(today, n):
    first = today.replace(day=1)
    months = []
    for _ in range(n):
        months.append(first)
        first = (first - timedelta(days=1)).replace(day=1)
    return list(reversed(months))


def _is_upgrade(payment):
    """True when the learner already had a lower plan running when this one was paid."""
    when = payment.paid_at
    best = (
        Subscription.objects.filter(learner_id=payment.learner_id, starts_at__lte=when, ends_at__gt=when)
        .exclude(pk=payment.subscription_id).order_by("-plan__order").values_list("plan__order", flat=True).first()
    )
    return best is not None and best < payment.plan.order


def build(start, end):
    now = timezone.now()
    lo, hi = _bounds(start, end)
    in_range = Payment.objects.filter(paid_at__gte=lo, paid_at__lt=hi, status__in=[Payment.Status.PAID, Payment.Status.REFUNDED])
    paid = in_range.filter(status=Payment.Status.PAID)
    totals = paid.aggregate(revenue=Sum("amount"), discounts=Sum("discount"), n=Count("id"))
    refunds = in_range.filter(status=Payment.Status.REFUNDED).aggregate(total=Sum("amount"), n=Count("id"))

    current = Subscription.objects.filter(starts_at__lte=now, ends_at__gt=now)
    active_ids = set(current.values_list("learner_id", flat=True))
    # a learner's access ends when their last current or queued period ends
    last_end = {}
    for sub in Subscription.objects.filter(ends_at__gt=now).values("learner_id", "ends_at"):
        if sub["ends_at"] > last_end.get(sub["learner_id"], now):
            last_end[sub["learner_id"]] = sub["ends_at"]
    expiring = sum(1 for lid, end_at in last_end.items() if lid in active_ids and end_at <= now + timedelta(days=7))
    lapsed = (
        Subscription.objects.filter(ends_at__gt=now - timedelta(days=30), ends_at__lte=now)
        .exclude(learner_id__in=last_end.keys()).values("learner_id").distinct().count()
    )
    by_plan_now = list(current.values("plan__name").annotate(n=Count("learner", distinct=True)).order_by("plan__order"))

    rows = list(in_range.select_related("learner", "plan", "payer", "promo", "recorded_by").order_by("paid_at"))
    upgrades = sum(1 for p in rows if p.status == Payment.Status.PAID and _is_upgrade(p))

    by_method = list(paid.values("method").annotate(total=Sum("amount"), n=Count("id")).order_by("-total"))
    methods = dict(Payment.Method.choices)
    for m in by_method:
        m["label"] = methods.get(m["method"], m["method"])
    by_plan = list(paid.values("plan__name").annotate(total=Sum("amount"), n=Count("id")).order_by("-total"))
    promos = list(paid.exclude(discount=0).values("discount_note").annotate(total=Sum("discount"), n=Count("id")).order_by("-n")[:8])

    # revenue per month for the last 12 months, by plan
    months = _months_back(timezone.localdate(), 12)
    m_lo, _ = _bounds(months[0], months[0])
    monthly = defaultdict(lambda: defaultdict(int))
    for p in Payment.objects.filter(status=Payment.Status.PAID, paid_at__gte=m_lo).select_related("plan"):
        local = timezone.localtime(p.paid_at)
        monthly[p.plan.slug][(local.year, local.month)] += p.amount
    chart = {
        "labels": [m.strftime("%b %Y") for m in months],
        "datasets": [
            {"label": plan.name, "data": [monthly[plan.slug][(m.year, m.month)] for m in months],
             "backgroundColor": PLAN_COLOURS.get(plan.slug, "#94A3B8")}
            for plan in Plan.objects.all()
        ],
    }
    return {
        "revenue": totals["revenue"] or 0, "payments": totals["n"], "discounts": totals["discounts"] or 0,
        "average": round((totals["revenue"] or 0) / totals["n"]) if totals["n"] else 0,
        "refund_total": refunds["total"] or 0, "refund_n": refunds["n"],
        "active": len(active_ids), "expiring": expiring, "lapsed": lapsed, "upgrades": upgrades,
        "by_plan_now": by_plan_now, "by_method": by_method, "by_plan": by_plan, "promos": promos,
        "rows": rows, "chart": chart,
    }


CSV_HEADER = ["Paid at", "Receipt no.", "Status", "Method", "M-Pesa code", "Reference", "Phone", "Learner", "Paid by",
              "Plan", "List price", "Discount", "Discount note", "Amount", "Refunded at", "Recorded by"]


def _csv_row(p):
    return [
        timezone.localtime(p.paid_at).strftime("%Y-%m-%d %H:%M"), p.receipt_number, p.get_status_display(), p.get_method_display(),
        p.mpesa_receipt, p.reference, p.phone, p.learner.get_full_name() or p.learner.username, p.payer_label, p.plan.name,
        p.list_price, p.discount, p.discount_note, p.amount,
        timezone.localtime(p.refunded_at).strftime("%Y-%m-%d") if p.refunded_at else "", str(p.recorded_by or ""),
    ]


def billing_report(request):
    today = timezone.localdate()
    start = _day(request.GET.get("start"), today.replace(day=1))
    end = _day(request.GET.get("end"), today)
    if end < start:
        start, end = end, start
    data = build(start, end)
    if request.GET.get("format") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="cloud-for-kids-payments-{start}-to-{end}.csv"'
        w = csv.writer(response)
        w.writerow(CSV_HEADER)
        for p in data["rows"]:
            w.writerow(_csv_row(p))
        w.writerow([])
        w.writerow(["Total paid (excluding refunds)", "", "", "", "", "", "", "", "", "", "", data["discounts"], "", data["revenue"]])
        return response
    first = today.replace(day=1)
    presets = [
        ("This month", first, today),
        ("Last month", (first - timedelta(days=1)).replace(day=1), first - timedelta(days=1)),
        ("Last 7 days", today - timedelta(days=6), today),
        ("This year", date(today.year, 1, 1), today),
    ]
    context = {**admin.site.each_context(request), "title": "Billing report", "d": data, "start": start, "end": end, "presets": presets}
    return render(request, "admin/billing_report.html", context)
