from django.conf import settings
from django.db import models


class Lab(models.Model):
    """A Practice Lab (practical simulation). The interactive part lives in
    templates/learner/labs/<slug>.html + static/js/labs.js; everything shown about it comes from here."""

    class Tone(models.TextChoices):
        SKY = "sky", "Sky blue"
        PURPLE = "purple", "Purple"
        GRASS = "grass", "Green"
        SUN = "sun", "Yellow"
        CORAL = "coral", "Coral"

    slug = models.SlugField(unique=True, help_text="Must match a lab template in templates/learner/labs/")
    title = models.CharField(max_length=100)
    summary = models.CharField(max_length=250)
    icon = models.CharField(max_length=40, default="joystick", help_text="Bootstrap Icons name, e.g. robot")
    tone = models.CharField(max_length=10, choices=Tone.choices, default=Tone.SKY)
    minutes = models.PositiveIntegerField(default=5)
    level = models.PositiveSmallIntegerField(default=1, help_text="Difficulty 1 (easy) to 3 (hard)")
    skill = models.CharField(max_length=150, help_text="The skill it practises, shown to learners and parents")
    order = models.PositiveIntegerField(default=0)
    published = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.title


class LabCompletion(models.Model):
    """A learner finished a practical simulation (Practice Lab)."""

    learner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lab_completions")
    slug = models.SlugField(help_text="Slug of the Lab that was finished")
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("learner", "slug")
        ordering = ["-completed_at"]

    def __str__(self):
        return f"{self.learner} finished {self.slug}"
