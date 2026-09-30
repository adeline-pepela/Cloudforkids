from django import forms

from .models import ContactMessage, NewsletterSubscriber


class BootstrapFormMixin:
    """Adds Bootstrap classes to every field widget automatically."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            existing = field.widget.attrs.get("class", "")
            if isinstance(field.widget, forms.Select):
                field.widget.attrs["class"] = (existing + " form-select rounded-3").strip()
            else:
                field.widget.attrs["class"] = (existing + " form-control rounded-3").strip()


class ContactForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ["name", "email", "phone_number", "role", "message"]
        widgets = {
            "message": forms.Textarea(attrs={"rows": 5, "placeholder": "Tell us a bit about what you're looking for..."}),
        }


class NewsletterForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = NewsletterSubscriber
        fields = ["email"]
        widgets = {
            "email": forms.EmailInput(attrs={"placeholder": "you@example.com"}),
        }
