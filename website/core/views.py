from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse

from accounts.models import User
from courses.models import Course, Lesson, LessonCompletion, Tier
from dashboard.models import LabCompletion
from .forms import ContactForm, NewsletterForm
from django.http import Http404

from .models import ImpactStat, LegalPage, InfoCard, Partner, TeamMember, Testimonial


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


def grade_span(tiers):
    """'Grade 1 to Grade 12' from the tiers' own grade ranges."""
    import re

    numbers = [int(n) for t in tiers for n in re.findall(r"\d+", t.grade_range)]
    return f"Grade {min(numbers)} to Grade {max(numbers)}" if numbers else ""


def public_tiers():
    """Learners are 9 to 17, so the Grade 1-3 Explorer tier is not offered publicly."""
    return Tier.objects.exclude(slug="explorer")


def home(request):
    tiers = public_tiers()
    partners = Partner.objects.all()[:6]
    stats = ImpactStat.objects.filter(where=ImpactStat.Where.HOME)
    testimonials = Testimonial.objects.filter(published=True)
    return render(
        request,
        "core/home.html",
        {"tiers": tiers, "grade_span": grade_span(tiers), "partners": partners, "stats": stats, "testimonials": testimonials, "live": live_numbers()},
    )


def find_path(request):
    return render(request, "core/find_path.html", {"tiers": public_tiers()})


def about(request):
    return render(
        request,
        "core/about.html",
        {
            "stats": ImpactStat.objects.filter(where=ImpactStat.Where.ABOUT),
            "tiers": public_tiers(),
            "teach": _cards(InfoCard.Section.TEACH),
            "different": _cards(InfoCard.Section.DIFFERENT),
            "audience": _cards(InfoCard.Section.AUDIENCE),
            "roles": _cards(InfoCard.Section.ROLE),
            "team": TeamMember.objects.filter(published=True),
            "live": live_numbers(),
        },
    )


def curriculum(request):
    return redirect("courses:programs")


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


def legal(request, slug):
    page = LegalPage.objects.filter(slug=slug).first()
    if page is None:
        raise Http404
    return render(request, "core/legal.html", {"page": page})


def csrf_failed(request, reason=""):
    """A form was sent with an out-of-date security token (another tab logged in or out, or the page sat open too long).
    Instead of a bare 403, take the person back with a friendly note. Signing out always works."""
    from django.contrib.auth import logout
    from django.utils.http import url_has_allowed_host_and_scheme

    if request.path == reverse("accounts:logout"):
        logout(request)
        return redirect("core:home")
    messages.warning(request, "That page had expired, probably because you signed in or out in another tab. Please try again.")
    back = request.META.get("HTTP_REFERER", "")
    if back and url_has_allowed_host_and_scheme(back, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(back)
    return redirect("core:home")
