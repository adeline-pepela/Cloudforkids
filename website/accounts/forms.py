from django import forms
from django.contrib.auth.forms import UserCreationForm

from core.forms import BootstrapFormMixin

from .models import LearnerProfile, User


class SignUpForm(BootstrapFormMixin, UserCreationForm):
    first_name = forms.CharField(max_length=150, required=True)
    last_name = forms.CharField(max_length=150, required=True)
    email = forms.EmailField(required=True)
    role = forms.ChoiceField(choices=User.Role.choices, initial=User.Role.LEARNER)

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "role", "phone_number", "password1", "password2"]

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.role = self.cleaned_data["role"]
        if commit:
            user.save()
            if user.role == User.Role.LEARNER:
                LearnerProfile.objects.get_or_create(user=user)
        return user


class LearnerProfileForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = LearnerProfile
        fields = [
            "tier",
            "grade",
            "school_name",
            "county",
            "parent_guardian_name",
            "parent_guardian_email",
            "parent_guardian_phone",
            "date_of_birth",
            "bio",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "bio": forms.Textarea(attrs={"rows": 3}),
        }
