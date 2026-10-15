from django.contrib import admin
from django.db.models import Sum
from django.utils import timezone

from .models import LiveAttendance, LiveRoom, LiveSession


@admin.register(LiveRoom)
class LiveRoomAdmin(admin.ModelAdmin):
    list_display = ("classroom", "code", "chat_enabled", "open_mic", "student_video", "locked", "created_at")
    search_fields = ("classroom__name", "code")
    readonly_fields = ("code",)


class LiveAttendanceInline(admin.TabularInline):
    model = LiveAttendance
    extra = 0
    fields = ("user", "is_host", "first_joined_at", "left_at", "seconds", "can_speak", "removed")
    readonly_fields = ("user", "is_host", "first_joined_at", "left_at", "seconds")


@admin.register(LiveSession)
class LiveSessionAdmin(admin.ModelAdmin):
    """Each live class held. Participant minutes are what LiveKit bills on (the free plan includes 5,000 a month)."""

    list_display = ("__str__", "started_by", "started_at", "ended_at", "people", "minutes")
    list_filter = ("started_at",)
    date_hierarchy = "started_at"
    inlines = [LiveAttendanceInline]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("attendance").select_related("room__classroom", "started_by")

    @admin.display(description="People")
    def people(self, obj):
        return len(obj.attendance.all())

    @admin.display(description="Participant minutes")
    def minutes(self, obj):
        return obj.participant_minutes

    def changelist_view(self, request, extra_context=None):
        start = timezone.localtime().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        seconds = LiveAttendance.objects.filter(session__started_at__gte=start).aggregate(s=Sum("seconds"))["s"] or 0
        extra_context = {**(extra_context or {}), "title": f"Live classes ({round(seconds / 60):,} participant minutes this month)"}
        return super().changelist_view(request, extra_context=extra_context)
