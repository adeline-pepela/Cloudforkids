from django.contrib import admin

from .models import Lab, LabCompletion


@admin.register(LabCompletion)
class LabCompletionAdmin(admin.ModelAdmin):
    list_display = ("learner", "slug", "completed_at")
    list_filter = ("slug",)
    search_fields = ("learner__username", "slug")
    date_hierarchy = "completed_at"


@admin.register(Lab)
class LabAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "skill", "minutes", "level", "published", "order")
    list_editable = ("published", "order")
    search_fields = ("title", "skill")
    prepopulated_fields = {"slug": ("title",)}
