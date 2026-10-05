from django.contrib import admin
from django.urls import reverse

from .models import ContactMessage, SitePhoto, UITranslation, LegalPage, ImpactStat, InfoCard, NewsletterSubscriber, Partner, SiteSetting, TeamMember, Testimonial

admin.site.site_header = "Cloud for Kids Admin"
admin.site.site_title = "Cloud for Kids Admin"
admin.site.index_title = "Dashboard"


@admin.register(Partner)
class PartnerAdmin(admin.ModelAdmin):
    list_display = ("name", "role", "description")
    search_fields = ("name", "role", "description")


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "role", "submitted_at", "handled")
    list_filter = ("handled", "role")
    list_editable = ("handled",)
    search_fields = ("name", "email", "message")
    date_hierarchy = "submitted_at"
    actions = ["mark_handled", "mark_unhandled"]

    @admin.action(description="Mark selected messages as handled")
    def mark_handled(self, request, queryset):
        self.message_user(request, f"{queryset.update(handled=True)} message(s) marked as handled.")

    @admin.action(description="Mark selected messages as not handled")
    def mark_unhandled(self, request, queryset):
        self.message_user(request, f"{queryset.update(handled=False)} message(s) marked as not handled.")


@admin.register(NewsletterSubscriber)
class NewsletterSubscriberAdmin(admin.ModelAdmin):
    list_display = ("email", "subscribed_at")
    search_fields = ("email",)
    date_hierarchy = "subscribed_at"


@admin.register(UITranslation)
class UITranslationAdmin(admin.ModelAdmin):
    list_display = ("english_short", "swahili", "updated_at")
    search_fields = ("english", "swahili")
    list_per_page = 50

    @admin.display(description="English")
    def english_short(self, obj):
        return obj.english[:90]

    def save_model(self, request, obj, form, change):
        from .translation import clear_cache

        super().save_model(request, obj, form, change)
        clear_cache()

    def delete_model(self, request, obj):
        from .translation import clear_cache

        super().delete_model(request, obj)
        clear_cache()


@admin.register(SitePhoto)
class SitePhotoAdmin(admin.ModelAdmin):
    list_display = ("slot", "has_image", "credit_name", "url")
    search_fields = ("slot", "credit_name")

    @admin.display(boolean=True, description="Photo")
    def has_image(self, obj):
        return bool(obj.src)

    def save_model(self, request, obj, form, change):
        from django.core.cache import cache

        super().save_model(request, obj, form, change)
        cache.delete("site-photos-v1")

    def delete_model(self, request, obj):
        from django.core.cache import cache

        super().delete_model(request, obj)
        cache.delete("site-photos-v1")


@admin.register(LegalPage)
class LegalPageAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "updated_at")
    readonly_fields = ("updated_at",)


@admin.register(Testimonial)
class TestimonialAdmin(admin.ModelAdmin):
    list_display = ("name", "role_label", "published", "order")
    list_filter = ("published",)
    list_editable = ("published", "order")
    search_fields = ("name", "quote")


@admin.register(SiteSetting)
class SiteSettingAdmin(admin.ModelAdmin):
    """One row only: the website's editable wording and contact details."""

    fieldsets = (
        ("Home page", {"fields": ("hero_eyebrow", "hero_title_start", "hero_title_accent", "hero_title_end", "hero_lead", "hero_note", "gap_title", "why_now_title", "why_now_text")}),
        ("About page", {"fields": ("about_title", "about_lead", "story_title", "story_text", "mission", "vision", "north_star")}),
        ("Contact and footer", {"fields": ("contact_email", "footer_email", "website", "phone", "location", "response_time", "footer_tagline", "footer_copyright")}),
    )

    def has_add_permission(self, request):
        return not SiteSetting.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        from django.shortcuts import redirect

        SiteSetting.load()
        return redirect(reverse("admin:core_sitesetting_change", args=[1]))


@admin.register(ImpactStat)
class ImpactStatAdmin(admin.ModelAdmin):
    list_display = ("value", "label", "source", "where", "order")
    list_editable = ("where", "order")
    list_filter = ("where",)


@admin.register(InfoCard)
class InfoCardAdmin(admin.ModelAdmin):
    list_display = ("title", "section", "icon", "published", "order")
    list_editable = ("published", "order")
    list_filter = ("section", "published")
    search_fields = ("title", "text")


@admin.register(TeamMember)
class TeamMemberAdmin(admin.ModelAdmin):
    list_display = ("name", "role", "email", "published", "order")
    list_editable = ("published", "order")


def _dashboard_data():
    """Everything the admin dashboard shows. Imported lazily so admin loads cleanly at startup."""
    from datetime import timedelta

    from django.contrib.admin.models import LogEntry
    from django.db.models import Count
    from django.db.models.functions import TruncDate
    from django.utils import timezone

    from accounts.models import LearnerProfile, User
    from courses.models import Course, Enrollment, Lesson, LessonCompletion

    def url(name):
        return reverse(f"admin:{name}_changelist")

    now = timezone.now()
    today = now.date()

    def daily(qs, field, days):
        start = today - timedelta(days=days - 1)
        rows = (
            qs.filter(**{f"{field}__date__gte": start})
            .annotate(d=TruncDate(field))
            .values("d")
            .annotate(n=Count("id"))
        )
        counts = {r["d"]: r["n"] for r in rows}
        labels, values = [], []
        for k in range(days):
            day = start + timedelta(days=k)
            labels.append(day.strftime("%d %b"))
            values.append(counts.get(day, 0))
        return {"labels": labels, "values": values}

    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)
    signups_week = User.objects.filter(date_joined__gte=week_ago).count()
    signups_prev = User.objects.filter(date_joined__gte=two_weeks_ago, date_joined__lt=week_ago).count()
    done_week = LessonCompletion.objects.filter(completed_at__gte=week_ago).count()
    unread = ContactMessage.objects.filter(handled=False).count()
    pending_testimonials = Testimonial.objects.filter(published=False).count()
    total_lessons = Lesson.objects.count()
    total_completions = LessonCompletion.objects.count()
    total_enrollments = Enrollment.objects.count()
    possible = sum(
        c.n_enroll * c.n_lessons for c in Course.objects.annotate(n_enroll=Count("enrollments", distinct=True), n_lessons=Count("lessons", distinct=True))
    )

    cards = [
        {"label": "Learners", "value": User.objects.filter(role=User.Role.LEARNER).count(), "sub": f"{signups_week} joined this week", "icon": "bi-people-fill", "tone": "t-sky", "url": url("accounts_user") + "?role__exact=learner"},
        {"label": "Enrollments", "value": total_enrollments, "sub": f"{Course.objects.count()} courses available", "icon": "bi-person-check-fill", "tone": "t-grass", "url": url("courses_enrollment")},
        {"label": "Lessons completed", "value": total_completions, "sub": f"{done_week} this week", "icon": "bi-check2-circle", "tone": "t-purple", "url": url("courses_lessoncompletion")},
        {"label": "Avg. course completion", "value": f"{round(total_completions / possible * 100) if possible else 0}%", "sub": f"{total_lessons} lessons in total", "icon": "bi-graph-up-arrow", "tone": "t-sun", "url": url("courses_course")},
        {"label": "Unread messages", "value": unread, "sub": "from the contact form", "icon": "bi-envelope-exclamation-fill", "tone": "t-coral", "url": url("core_contactmessage") + "?handled__exact=0", "alert": True},
        {"label": "Subscribers", "value": NewsletterSubscriber.objects.count(), "sub": "newsletter sign-ups", "icon": "bi-send-fill", "tone": "t-sky", "url": url("core_newslettersubscriber")},
    ]

    by_course = list(
        Course.objects.annotate(
            n_enroll=Count("enrollments", distinct=True),
            n_lessons=Count("lessons", distinct=True),
            n_done=Count("lessons__completions", distinct=True),
        ).order_by("-n_enroll", "title")
    )
    course_rows = []
    for c in by_course:
        rate = round(c.n_done / (c.n_enroll * c.n_lessons) * 100) if c.n_enroll and c.n_lessons else 0
        course_rows.append({"title": c.title, "icon": c.icon, "tier": c.tier.name, "enrollments": c.n_enroll, "lessons": c.n_lessons, "rate": rate, "url": reverse("admin:courses_course_change", args=[c.pk])})

    tier_counts = list(LearnerProfile.objects.values("tier__name").annotate(n=Count("id")).order_by("-n"))
    role_counts = list(User.objects.values("role").annotate(n=Count("id")).order_by("-n"))
    role_names = dict(User.Role.choices)
    top_lessons = list(
        Lesson.objects.annotate(n=Count("completions")).filter(n__gt=0).order_by("-n").values("title", "n")[:5]
    )

    charts = {
        "signups": daily(User.objects.all(), "date_joined", 30),
        "completions": daily(LessonCompletion.objects.all(), "completed_at", 14),
        "enrollments": {"labels": [c.title for c in by_course], "values": [c.n_enroll for c in by_course]},
        "tiers": {"labels": [r["tier__name"] or "No tier chosen" for r in tier_counts], "values": [r["n"] for r in tier_counts]},
        "roles": {"labels": [role_names.get(r["role"], r["role"]) for r in role_counts], "values": [r["n"] for r in role_counts]},
        "top_lessons": {"labels": [r["title"] for r in top_lessons], "values": [r["n"] for r in top_lessons]},
    }

    attention = []
    waiting_teachers = User.objects.filter(role=User.Role.FACILITATOR, is_approved=False).count()
    if waiting_teachers:
        attention.append({"icon": "bi-person-check-fill", "text": f"{waiting_teachers} facilitator{'s' if waiting_teachers != 1 else ''} waiting for approval", "url": url("accounts_user") + "?role__exact=facilitator&is_approved__exact=0"})
    from accounts.models import ParentalConsent

    waiting_consents = ParentalConsent.objects.filter(status="pending").count()
    if waiting_consents:
        attention.append({"icon": "bi-shield-check", "text": f"{waiting_consents} child account{'s' if waiting_consents != 1 else ''} waiting for parent consent", "url": url("accounts_parentalconsent") + "?status__exact=pending"})
    if unread:
        attention.append({"icon": "bi-envelope-exclamation-fill", "text": f"{unread} unread contact message{'s' if unread != 1 else ''}", "url": url("core_contactmessage") + "?handled__exact=0"})
    if pending_testimonials:
        attention.append({"icon": "bi-chat-quote-fill", "text": f"{pending_testimonials} testimonial{'s' if pending_testimonials != 1 else ''} waiting to be published", "url": url("core_testimonial") + "?published__exact=0"})
    if not Testimonial.objects.filter(published=True).exists():
        attention.append({"icon": "bi-megaphone-fill", "text": "No testimonials are live on the home page yet", "url": reverse("admin:core_testimonial_add")})
    if signups_week < signups_prev:
        attention.append({"icon": "bi-graph-down-arrow", "text": f"Sign-ups are down: {signups_week} this week vs {signups_prev} last week", "url": url("accounts_user")})

    return {
        "cards": cards,
        "charts": charts,
        "courses": course_rows,
        "attention": attention,
        "recent_users": User.objects.order_by("-date_joined")[:6],
        "recent_messages": ContactMessage.objects.order_by("-submitted_at")[:5],
        "recent_actions": LogEntry.objects.select_related("user", "content_type").order_by("-action_time")[:8],
        "signups_week": signups_week,
        "signups_prev": signups_prev,
    }


_original_each_context = admin.site.each_context


def _each_context(request):
    context = _original_each_context(request)
    # Only the admin home page needs the stats; skip the queries elsewhere.
    if request.path == reverse("admin:index"):
        context["c4k"] = _dashboard_data()
    return context


admin.site.each_context = _each_context
