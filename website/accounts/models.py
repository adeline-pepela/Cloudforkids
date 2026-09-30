from django.contrib.auth.models import AbstractUser
from django.db import models


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

    def __str__(self):
        return f"Learner profile: {self.user}"
