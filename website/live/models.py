"""Live online classes: a video room per class, run by the teacher, joined from a short link (cloudforkids.co.ke/r/CODE)."""

import json
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from accounts.models import Classroom, new_family_code


class LiveRoom(models.Model):
    """A live room with its own short link. Every class has one main room (its permanent link, shared once for the term);
    a teacher can also create meetings for later, each with its own link, an optional passcode and its own rules."""

    class Audience(models.TextChoices):
        CLASS = "class", "Learners in this class"
        ANYONE = "anyone", "Any Cloud for Kids learner with the link (and the passcode, if set)"

    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name="live_rooms")
    is_main = models.BooleanField(default=True, help_text="The class's permanent room (one per class)")
    title = models.CharField(max_length=150, blank=True, help_text="Meeting name, e.g. Revision before the exam")
    code = models.CharField(max_length=8, unique=True, editable=False)
    passcode = models.CharField(max_length=20, blank=True, help_text="Learners type this before joining. Leave blank for none")
    waiting_room = models.BooleanField(default=False, help_text="The teacher lets each person in")
    audience = models.CharField(max_length=10, choices=Audience.choices, default=Audience.CLASS)
    # Settings the teacher changes during a class. They apply to everyone in the room straight away.
    chat_enabled = models.BooleanField(default=True, help_text="Learners may send chat messages and reactions")
    open_mic = models.BooleanField(default=False, help_text="Learners may unmute without raising a hand first")
    student_video = models.BooleanField(default=False, help_text="Learners may turn on their cameras")
    locked = models.BooleanField(default=False, help_text="Nobody new may join (learners already in may rejoin)")
    board = models.BooleanField(default=False, help_text="The shared whiteboard is showing")
    board_draw = models.BooleanField(default=False, help_text="Learners may draw on the whiteboard")
    recording = models.BooleanField(default=False, help_text="The teacher is recording right now")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["classroom"], condition=models.Q(is_main=True), name="one_main_live_room_per_class"),
        ]

    def __str__(self):
        return f"{self.display_title} ({self.classroom.name})"

    @property
    def display_title(self):
        return self.title or ("Live classroom" if self.is_main else "Live meeting")

    def check_passcode(self, attempt):
        import hmac

        return not self.passcode or hmac.compare_digest(self.passcode.strip().lower(), (attempt or "").strip().lower())

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
            "board": self.board, "board_draw": self.board_draw, "rec": self.recording,
        })


class LiveSession(models.Model):
    """One run of the live room, from the teacher pressing Start until the class ends."""

    room = models.ForeignKey(LiveRoom, on_delete=models.CASCADE, related_name="sessions")
    started_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    groups = models.PositiveSmallIntegerField(default=0, help_text="Number of breakout groups running (0 = everyone together)")
    followup_done = models.BooleanField(default=False, help_text="Badges given and missed-class emails sent")

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.room.classroom.name} on {timezone.localtime(self.started_at):%Y-%m-%d %H:%M}"

    @property
    def livekit_name(self):
        return f"c4k-{self.room.code}-{self.pk}"

    def room_name(self, group=0):
        """LiveKit room for the whole class (group 0) or for one breakout group."""
        return self.livekit_name if not group else f"{self.livekit_name}-g{group}"

    def room_names(self):
        return [self.room_name(g) for g in range(self.groups + 1)]

    @property
    def minutes_long(self):
        end = self.ended_at or timezone.now()
        return round((end - self.started_at).total_seconds() / 60)

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
    group = models.PositiveSmallIntegerField(default=0, help_text="Breakout group (0 = the main room)")
    admitted = models.BooleanField(default=True, help_text="False while waiting in the waiting room")

    class Meta:
        unique_together = ("session", "user")
        ordering = ["first_joined_at"]

    def __str__(self):
        return f"{self.user} in {self.session}"


class LiveChatMessage(models.Model):
    """Every chat message is kept so the teacher and admins can review it. Blocked messages are kept too, flagged."""

    session = models.ForeignKey(LiveSession, on_delete=models.CASCADE, related_name="chat")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="live_chat")
    group = models.PositiveSmallIntegerField(default=0)
    text = models.CharField(max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)
    announce = models.BooleanField(default=False, help_text="Teacher message to every breakout group")
    flagged = models.BooleanField(default=False, help_text="Blocked by the filter and never shown to the class")
    reason = models.CharField(max_length=40, blank=True)
    hidden = models.BooleanField(default=False, help_text="Deleted by the teacher")

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.user}: {self.text[:40]}"


class LivePoll(models.Model):
    session = models.ForeignKey(LiveSession, on_delete=models.CASCADE, related_name="polls")
    question = models.CharField(max_length=200)
    options = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.question

    def counts(self):
        counts = [0] * len(self.options)
        for choice in self.votes.values_list("choice", flat=True):
            if 0 <= choice < len(counts):
                counts[choice] += 1
        return counts

    def rows(self):
        return list(zip(self.options, self.counts()))

    def as_dict(self):
        return {"id": self.pk, "q": self.question, "options": self.options, "counts": self.counts(), "closed": self.closed_at is not None}


class LivePollVote(models.Model):
    poll = models.ForeignKey(LivePoll, on_delete=models.CASCADE, related_name="votes")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    choice = models.PositiveSmallIntegerField()

    class Meta:
        unique_together = ("poll", "user")


class LiveLaunch(models.Model):
    """A lesson (and its quiz) the teacher opened for the whole class during a live class."""

    session = models.ForeignKey(LiveSession, on_delete=models.CASCADE, related_name="launches")
    lesson = models.ForeignKey("courses.Lesson", on_delete=models.CASCADE, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class LiveRecording(models.Model):
    """A recording of the teacher only (their voice and their camera or shared screen), never the learners."""

    class Status(models.TextChoices):
        RECORDING = "recording", "Recording"
        READY = "ready", "Ready to watch"
        FAILED = "failed", "Failed"

    session = models.ForeignKey(LiveSession, on_delete=models.CASCADE, related_name="recordings")
    egress_id = models.CharField(max_length=64, unique=True)
    filepath = models.CharField(max_length=300)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RECORDING)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(default=0)
    size_bytes = models.BigIntegerField(default=0)
    error = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"Recording of {self.session}"
