from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import LearnerProfile, User


@receiver(post_save, sender=User)
def ensure_learner_profile(sender, instance, raw=False, **kwargs):
    if not raw and instance.role == User.Role.LEARNER:
        LearnerProfile.objects.get_or_create(user=instance)
