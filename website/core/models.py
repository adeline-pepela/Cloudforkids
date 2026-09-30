from django.db import models


class Partner(models.Model):
    name = models.CharField(max_length=150)
    description = models.CharField(max_length=300)
    logo = models.ImageField(upload_to="partners/", blank=True, null=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ContactMessage(models.Model):
    class Role(models.TextChoices):
        PARENT = "parent", "Parent / Guardian"
        SCHOOL = "school", "School / Head Teacher"
        PARTNER = "partner", "Partner / Investor / Donor"
        FACILITATOR = "facilitator", "Facilitator / Teacher"
        OTHER = "other", "Other"

    name = models.CharField(max_length=150)
    email = models.EmailField()
    phone_number = models.CharField(max_length=20, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.OTHER)
    message = models.TextField()
    submitted_at = models.DateTimeField(auto_now_add=True)
    handled = models.BooleanField(default=False)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"{self.name} ({self.get_role_display()}) - {self.submitted_at:%Y-%m-%d}"


class NewsletterSubscriber(models.Model):
    email = models.EmailField(unique=True)
    subscribed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email
