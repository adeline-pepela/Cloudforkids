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
    terms_accepted_at = models.DateTimeField(null=True, blank=True, help_text="When they accepted the Terms and Privacy Policy")
    email_notifications = models.BooleanField(default=True, help_text="Progress summaries and reminders by email")
    is_approved = models.BooleanField(
        default=True, help_text="Facilitators need an admin's approval before they can use classes"
    )

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def awaiting_approval(self):
        return self.role == self.Role.FACILITATOR and not self.is_approved

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
    location = models.CharField(max_length=150, blank=True, help_text="Where the class meets, e.g. Computer lab, Room 4")
    meeting_link = models.URLField(blank=True, help_text="Optional link for online sessions (Google Meet, Zoom, Teams)")
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


class ClassSession(models.Model):
    """One scheduled meeting of a class. Learners in the class see it in their calendar."""

    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name="sessions")
    title = models.CharField(max_length=150, blank=True, help_text="e.g. Intro to cloud storage. Leave blank to use the class name")
    starts_at = models.DateTimeField()
    duration_minutes = models.PositiveSmallIntegerField(default=60)
    location = models.CharField(max_length=150, blank=True, help_text="Leave blank to use the class venue")
    meeting_link = models.URLField(blank=True, help_text="Leave blank to use the class link")
    notes = models.CharField(max_length=300, blank=True, help_text="e.g. Bring your laptop")

    class Meta:
        ordering = ["starts_at"]

    def __str__(self):
        return f"{self.classroom.name}: {self.starts_at:%Y-%m-%d %H:%M}"

    @property
    def display_title(self):
        return self.title or self.classroom.name

    @property
    def ends_at(self):
        from datetime import timedelta

        return self.starts_at + timedelta(minutes=self.duration_minutes)

    @property
    def where(self):
        return self.location or self.classroom.location

    @property
    def link(self):
        return self.meeting_link or self.classroom.meeting_link


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


def new_consent_token():
    return secrets.token_urlsafe(32)


class ParentalConsent(models.Model):
    """A parent or guardian's permission for a child under 13 to use the platform (Kenya Data Protection Act, 2019)."""

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting for parent"
        APPROVED = "approved", "Approved"
        DECLINED = "declined", "Declined"

    class Method(models.TextChoices):
        EMAIL = "email", "Parent approved by email link"
        SCHOOL = "school", "Added by a school or facilitator"
        ADMIN = "admin", "Recorded by an admin"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="consent")
    parent_name = models.CharField(max_length=150, blank=True)
    parent_email = models.EmailField()
    token = models.CharField(max_length=64, unique=True, default=new_consent_token, editable=False)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    method = models.CharField(max_length=10, choices=Method.choices, default=Method.EMAIL)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} - {self.get_status_display()}"


class NotificationLog(models.Model):
    """Remembers which scheduled emails were sent, so nobody gets the same reminder twice."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_log")
    kind = models.CharField(max_length=30)
    key = models.CharField(max_length=80)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "kind", "key")

    def __str__(self):
        return f"{self.kind} {self.key} -> {self.user}"


class Message(models.Model):
    """A message from a facilitator to a parent or learner (or a parent's reply). Learners cannot send messages."""

    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_messages")
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="received_messages")
    classroom = models.ForeignKey(Classroom, null=True, blank=True, on_delete=models.SET_NULL, related_name="messages")
    about_learner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="messages_about"
    )
    reply_to = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="replies")
    subject = models.CharField(max_length=150)
    body = models.TextField(max_length=3000)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.sender} -> {self.recipient}: {self.subject}"
