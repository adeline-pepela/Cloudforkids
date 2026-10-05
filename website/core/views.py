from django.contrib import messages
from django.shortcuts import redirect, render

from accounts.models import User
from courses.models import Course, Lesson, LessonCompletion, Tier
from dashboard.models import LabCompletion
from .forms import ContactForm, NewsletterForm
from .models import ImpactStat, InfoCard, Partner, TeamMember, Testimonial


def _cards(section):
    return InfoCard.objects.filter(section=section, published=True)


def live_numbers():
    """Real numbers from the database, shown on the public pages."""
    return {
        "learners": User.objects.filter(role=User.Role.LEARNER).count(),
        "courses": Course.objects.count(),
        "lessons": Lesson.objects.count(),
        "lessons_done": LessonCompletion.objects.count(),
        "labs_done": LabCompletion.objects.count(),
    }


def home(request):
    tiers = Tier.objects.all()
    partners = Partner.objects.all()[:6]
    stats = ImpactStat.objects.filter(where=ImpactStat.Where.HOME)
    testimonials = Testimonial.objects.filter(published=True)
    return render(
        request,
        "core/home.html",
        {"tiers": tiers, "partners": partners, "stats": stats, "testimonials": testimonials, "live": live_numbers()},
    )


def find_path(request):
    return render(request, "core/find_path.html", {"tiers": Tier.objects.all()})


def cloud_demo(request):
    return render(request, "core/cloud_demo.html")


def about(request):
    return render(
        request,
        "core/about.html",
        {
            "stats": ImpactStat.objects.filter(where=ImpactStat.Where.ABOUT),
            "tiers": Tier.objects.all(),
            "teach": _cards(InfoCard.Section.TEACH),
            "different": _cards(InfoCard.Section.DIFFERENT),
            "audience": _cards(InfoCard.Section.AUDIENCE),
            "roles": _cards(InfoCard.Section.ROLE),
            "team": TeamMember.objects.filter(published=True),
            "live": live_numbers(),
        },
    )


def curriculum(request):
    tiers = Tier.objects.prefetch_related("courses__lessons")
    return render(request, "core/curriculum.html", {"tiers": tiers})


def partners(request):
    all_partners = Partner.objects.all()
    return render(request, "core/partners.html", {"partners": all_partners})


def impact(request):
    return render(request, "core/impact.html", {"steps": _cards(InfoCard.Section.THEORY)})


def contact(request):
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Thanks for reaching out! We'll be in touch soon.")
            return redirect("core:contact")
    else:
        form = ContactForm()
    return render(request, "core/contact.html", {"form": form, "writes": _cards(InfoCard.Section.WRITES)})


def subscribe_newsletter(request):
    if request.method == "POST":
        form = NewsletterForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "You're subscribed! Watch your inbox for updates.")
        else:
            messages.error(request, "That didn't look like a valid email \u2014 please try again.")
    return redirect(request.META.get("HTTP_REFERER", "core:home"))
