from django.contrib.auth.models import AbstractUser
import secrets

from django.conf import settings
from django.db import models

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I so codes are easy to read out


def new_family_code():
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))


class User(AbstractUser):
    """Custom user for Cloud for Kids.

    A user can be a learner (a child, usually signed up with a parent's
    help), a parent/guardian, a facilitator/teacher, or a site admin.
    """

    class Role(models.TextChoices):
        LEARNER = "learner", "Learner"
        PARENT = "parent", "Parent / Guardian"
        FACILITATOR = "facilitator", "Facilitator / Teacher"
        ADMIN = "admin", "Administrator"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.LEARNER)
    phone_number = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def is_learner(self):
        return self.role == self.Role.LEARNER


class LearnerProfile(models.Model):
    """Extra info collected for learners (mostly children)."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="learner_profile")
    tier = models.ForeignKey(
        "courses.Tier", null=True, blank=True, on_delete=models.SET_NULL, related_name="learners"
    )
    grade = models.CharField(max_length=20, blank=True, help_text="e.g. Grade 6")
    school_name = models.CharField(max_length=150, blank=True)
    county = models.CharField(max_length=100, blank=True)
    parent_guardian_name = models.CharField(max_length=150, blank=True)
    parent_guardian_email = models.EmailField(blank=True)
    parent_guardian_phone = models.CharField(max_length=20, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    bio = models.TextField(blank=True)
    family_code = models.CharField(
        max_length=8, unique=True, null=True, blank=True, editable=False,
        help_text="Secret code the learner gives a parent so the parent can link to this account",
    )

    def save(self, *args, **kwargs):
        if not self.family_code:
            code = new_family_code()
            while LearnerProfile.objects.filter(family_code=code).exists():
                code = new_family_code()
            self.family_code = code
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Learner profile: {self.user}"


class ParentLink(models.Model):
    """A parent/guardian who is allowed to follow a learner's progress."""

    parent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="children_links")
    child = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="parent_links")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("parent", "child")
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.parent} follows {self.child}"


class Classroom(models.Model):
    """A class or club run by a facilitator / teacher. Learners join with the join code."""

    facilitator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="classrooms")
    name = models.CharField(max_length=120, help_text="e.g. Grade 6 Cloud Club")
    description = models.CharField(max_length=300, blank=True)
    tier = models.ForeignKey(
        "courses.Tier", null=True, blank=True, on_delete=models.SET_NULL, related_name="classrooms",
        help_text="The programme tier this class follows (progress is measured against it)",
    )
    school_name = models.CharField(max_length=150, blank=True)
    join_code = models.CharField(max_length=8, unique=True, editable=False)
    archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["archived", "name"]

    def __str__(self):
        return f"{self.name} ({self.facilitator})"

    def save(self, *args, **kwargs):
        if not self.join_code:
            code = new_family_code()
            while Classroom.objects.filter(join_code=code).exists():
                code = new_family_code()
            self.join_code = code
        super().save(*args, **kwargs)


class ClassMembership(models.Model):
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name="memberships")
    learner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="class_memberships")
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("classroom", "learner")
        ordering = ["learner__first_name", "learner__username"]

    def __str__(self):
        return f"{self.learner} in {self.classroom}"


class Assignment(models.Model):
    """A course a facilitator asks a class to work on, with an optional due date."""

    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name="assignments")
    course = models.ForeignKey("courses.Course", on_delete=models.CASCADE, related_name="assignments")
    note = models.CharField(max_length=300, blank=True, help_text="A short message to the class")
    due_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_date", "-created_at"]

    def __str__(self):
        return f"{self.course} for {self.classroom}"
