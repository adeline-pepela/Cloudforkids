"""The in-app assistant for admins and facilitators: provider connections, settings, chats and the actions it took."""

from django.conf import settings
from django.core.cache import cache
from django.db import models

SETTINGS_CACHE_KEY = "assistant-settings-v1"


class Connection(models.Model):
    """One AI provider + model + API key. The key is sealed (encrypted) and never sent back to a browser."""

    class Provider(models.TextChoices):
        ANTHROPIC = "anthropic", "Claude (Anthropic)"
        OPENAI = "openai", "OpenAI"
        GEMINI = "gemini", "Gemini (Google)"
        DEEPSEEK = "deepseek", "DeepSeek"

    provider = models.CharField(max_length=20, choices=Provider.choices)
    model = models.CharField(max_length=100, help_text="e.g. claude-sonnet-5-5, gpt-5-mini, gemini-2.5-flash, deepseek-chat")
    label = models.CharField(max_length=80, blank=True, help_text="Shown in the assistant's model menu")
    key_sealed = models.TextField(editable=False)
    key_last4 = models.CharField(max_length=4, editable=False)
    is_default = models.BooleanField(default=False)
    tested_at = models.DateTimeField(help_text="When the key and model last answered a test")
    saved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    saved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_default", "provider", "model"]

    def __str__(self):
        return self.display_name

    @property
    def display_name(self):
        return self.label or f"{self.get_provider_display()} · {self.model}"

    @property
    def tag(self):
        return f"{self.provider}:{self.model}"

    def api_key(self):
        from .crypto import unseal

        return unseal(self.key_sealed)


class AssistantSettings(models.Model):
    """Office-wide switches. There is only ever one row."""

    enabled = models.BooleanField(default=True, help_text="Turn the assistant on or off for everyone")
    for_admins = models.BooleanField("Admins can use it", default=True)
    for_tutors = models.BooleanField("Facilitators can use it", default=True)
    for_learners = models.BooleanField(
        "Learners can use the study helper", default=True,
        help_text="Only learners whose plan includes the AI learning assistant (Admin > Plans). It reads and explains, never changes anything",
    )
    for_parents = models.BooleanField("Parents can use it", default=True, help_text="About their own linked children only")
    read_only = models.BooleanField(
        default=False, help_text="It can search, read and answer questions, but changes nothing"
    )
    confirm_writes = models.BooleanField(
        "Ask before every change", default=True,
        help_text="Each change is shown as one sentence with Approve and Decline. Emails, messages and deletions always ask",
    )
    max_rounds = models.PositiveSmallIntegerField(default=8, help_text="Most tool steps it may take for one request (2 to 12)")

    class Meta:
        verbose_name = verbose_name_plural = "Assistant settings"

    def __str__(self):
        return "Assistant settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        self.max_rounds = min(12, max(2, self.max_rounds or 8))
        super().save(*args, **kwargs)
        cache.delete(SETTINGS_CACHE_KEY)

    @classmethod
    def load(cls):
        found = cache.get(SETTINGS_CACHE_KEY)
        if found is None:
            found, _ = cls.objects.get_or_create(pk=1)
            cache.set(SETTINGS_CACHE_KEY, found, 30)
        return found


class Thread(models.Model):
    """One conversation with the assistant, in one area (the admin console or the facilitator portal)."""

    class Area(models.TextChoices):
        ADMIN = "admin", "Admin console"
        TEACH = "teach", "Facilitator portal"
        LEARN = "learn", "Learner study helper"
        FAMILY = "family", "Family portal"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="assistant_threads")
    area = models.CharField(max_length=10, choices=Area.choices)
    title = models.CharField(max_length=120, blank=True)
    connection = models.ForeignKey(Connection, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    busy = models.BooleanField(default=False, help_text="The assistant is working on a reply")
    cancel = models.BooleanField(default=False, help_text="The user pressed Stop")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.title or f"Chat {self.pk}"


class Turn(models.Model):
    """One message in a thread: the user's, the assistant's (with any tool calls it made), or a tool's result."""

    class Role(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"
        TOOL = "tool", "Tool result"

    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name="turns")
    role = models.CharField(max_length=10, choices=Role.choices)
    text = models.TextField(blank=True)
    reasoning = models.TextField(blank=True)
    tool_calls = models.JSONField(default=list, blank=True, help_text="[{id, name, args}] asked for by the assistant")
    raw = models.JSONField(null=True, blank=True, help_text="The provider's own content blocks, replayed exactly")
    model = models.CharField(max_length=130, blank=True, help_text="provider:model that wrote this reply")
    call_id = models.CharField(max_length=80, blank=True)
    tool_name = models.CharField(max_length=60, blank=True)
    failed = models.BooleanField(default=False)
    error = models.CharField(max_length=500, blank=True)
    streaming = models.BooleanField(default=False)
    screen = models.JSONField(null=True, blank=True, help_text="What the user's screen showed when they sent this")
    files = models.JSONField(default=list, blank=True, help_text="Files attached to this message: [{name, type, kind, text|data, size}]")
    usage = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class Action(models.Model):
    """A tool the assistant used (or asked to use). Changes are the activity log, and carry what undo needs."""

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting for approval"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"
        DECLINED = "declined", "Declined"
        UNDONE = "undone", "Undone"

    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name="actions")
    turn = models.ForeignKey(Turn, on_delete=models.CASCADE, related_name="actions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="assistant_actions")
    call_id = models.CharField(max_length=80)
    tool = models.CharField(max_length=60)
    args = models.JSONField(default=dict, blank=True)
    writes = models.BooleanField(default=False)
    summary = models.CharField(max_length=300)
    status = models.CharField(max_length=10, choices=Status.choices)
    result = models.TextField(blank=True)
    undo = models.JSONField(null=True, blank=True)
    undo_label = models.CharField(max_length=40, blank=True)
    link = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.user}: {self.summary} ({self.get_status_display()})"
