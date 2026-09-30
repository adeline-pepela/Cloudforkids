from django.contrib import admin

from .models import ContactMessage, NewsletterSubscriber, Partner


@admin.register(Partner)
class PartnerAdmin(admin.ModelAdmin):
    list_display = ("name", "description")


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "role", "submitted_at", "handled")
    list_filter = ("role", "handled")
    search_fields = ("name", "email", "message")


@admin.register(NewsletterSubscriber)
class NewsletterSubscriberAdmin(admin.ModelAdmin):
    list_display = ("email", "subscribed_at")
