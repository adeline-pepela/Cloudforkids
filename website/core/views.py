from django.contrib import messages
from django.shortcuts import redirect, render

from courses.models import Tier
from .forms import ContactForm, NewsletterForm
from .models import Partner


def home(request):
    tiers = Tier.objects.all()
    partners = Partner.objects.all()[:6]
    stats = [
        {"value": "79%", "label": "of Kenyan firms cite cloud computing as their #1 skills shortage", "source": "SAP survey, 2025"},
        {"value": "84.2%", "label": "of public-school teachers struggle to use classroom technology", "source": "TSC survey"},
        {"value": "35.3%", "label": "of Kenyan schools are internet-connected", "source": "The Star, 2026"},
        {"value": "36.3%", "label": "of Kenya's population is under 15 \u2014 a huge, underserved cohort", "source": "Worldometer, 2025"},
    ]
    return render(request, "core/home.html", {"tiers": tiers, "partners": partners, "stats": stats})


def about(request):
    return render(request, "core/about.html")


def curriculum(request):
    tiers = Tier.objects.prefetch_related("courses")
    return render(request, "core/curriculum.html", {"tiers": tiers})


def partners(request):
    all_partners = Partner.objects.all()
    return render(request, "core/partners.html", {"partners": all_partners})


def impact(request):
    return render(request, "core/impact.html")


def contact(request):
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Thanks for reaching out\! We'll be in touch soon.")
            return redirect("core:contact")
    else:
        form = ContactForm()
    return render(request, "core/contact.html", {"form": form})


def subscribe_newsletter(request):
    if request.method == "POST":
        form = NewsletterForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "You're subscribed\! Watch your inbox for updates.")
        else:
            messages.error(request, "That didn't look like a valid email \u2014 please try again.")
    return redirect(request.META.get("HTTP_REFERER", "core:home"))
