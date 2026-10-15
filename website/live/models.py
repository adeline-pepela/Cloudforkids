"""Live online classes: a video room per class, run by the teacher, joined from a short link (cloudforkids.co.ke/r/CODE)."""

import json
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from accounts.models import Classroom, new_family_code


class LiveRoom(models.Model):
    """The class's permanent live room. The short link never changes, so a teacher can share it once for the whole term."""

    classroom = models.OneToOneField(Classroom, on_delete=models.CASCADE, related_name="live_room")
    code = models.CharField(max_length=8, unique=True, editable=False)
    # Settings the teacher changes during a class. They apply to everyone in the room straight away.
    chat_enabled = models.BooleanField(default=True, help_text="Learners may send chat messages and reactions")
    open_mic = models.BooleanField(default=False, help_text="Learners may unmute without raising a hand first")
    student_video = models.BooleanField(default=False, help_text="Learners may turn on their cameras")
    locked = models.BooleanField(default=False, help_text="Nobody new may join (learners already in may rejoin)")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Live room for {self.classroom.name}"

    def save(self, *args, **kwargs):
        if not self.code:
            code = new_family_code()
            while LiveRoom.objects.filter(code=code).exists():
                code = new_family_code()
            self.code = code
        super().save(*args, **kwargs)

    @property
    def current_session(self):
        """The class that is live now, or None. A session nobody ended is treated as over after LIVE_MAX_MINUTES."""
        cutoff = timezone.now() - timedelta(minutes=settings.LIVE_MAX_MINUTES)
        return self.sessions.filter(ended_at__isnull=True, started_at__gte=cutoff).first()

    def settings_json(self):
        """What every browser in the room needs to know. Sent to LiveKit as the room metadata."""
        return json.dumps({
            "chat": self.chat_enabled, "open_mic": self.open_mic, "video": self.student_video, "locked": self.locked,
        })


class LiveSession(models.Model):
    """One run of the live room, from the teacher pressing Start until the class ends."""

    room = models.ForeignKey(LiveRoom, on_delete=models.CASCADE, related_name="sessions")
    started_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.room.classroom.name} on {timezone.localtime(self.started_at):%Y-%m-%d %H:%M}"

    @property
    def livekit_name(self):
        return f"c4k-{self.room.code}-{self.pk}"

    @property
    def participant_minutes(self):
        return round(sum(a.seconds for a in self.attendance.all()) / 60)


class LiveAttendance(models.Model):
    """Who came to a live class and for how long. Time in the room is filled in by LiveKit's webhook."""

    session = models.ForeignKey(LiveSession, on_delete=models.CASCADE, related_name="attendance")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="live_attendance")
    is_host = models.BooleanField(default=False)
    first_joined_at = models.DateTimeField(auto_now_add=True)
    last_joined_at = models.DateTimeField(default=timezone.now)
    left_at = models.DateTimeField(null=True, blank=True)
    seconds = models.PositiveIntegerField(default=0, help_text="Total time in the room")
    can_speak = models.BooleanField(default=False, help_text="The teacher let this learner use their microphone")
    removed = models.BooleanField(default=False, help_text="The teacher removed this learner from the class")

    class Meta:
        unique_together = ("session", "user")
        ordering = ["first_joined_at"]

    def __str__(self):
        return f"{self.user} in {self.session}"
