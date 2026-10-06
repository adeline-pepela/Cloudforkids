from django.db import models


class Partner(models.Model):
    name = models.CharField(max_length=150)
    description = models.CharField(max_length=300)
    role = models.CharField(max_length=100, blank=True, help_text="How they support the programme, e.g. Cloud credits")
    logo = models.ImageField(upload_to="partners/", blank=True, null=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def logo_src(self):
        """The uploaded logo, else static/img/partners/<name-as-slug>.(svg|png|jpg|webp) if that file exists."""
        if self.logo:
            return self.logo.url
        from django.contrib.staticfiles import finders
        from django.templatetags.static import static
        from django.utils.text import slugify

        for ext in ("svg", "png", "jpg", "webp"):
            path = f"img/partners/{slugify(self.name)}.{ext}"
            if finders.find(path):
                return static(path)
        return ""


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


class Testimonial(models.Model):
    """A quote from a parent, teacher or learner. Only published ones appear on the site."""

    name = models.CharField(max_length=100)
    role_label = models.CharField(max_length=100, help_text="e.g. Parent, Grade 7 learner, Head teacher")
    quote = models.TextField()
    photo = models.ImageField(upload_to="testimonials/", blank=True, null=True)
    published = models.BooleanField(default=False, help_text="Tick once you have permission to show this quote")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.name} ({self.role_label})"


class SiteSetting(models.Model):
    """The editable wording and contact details of the public website. There is only ever one row."""

    # Home page
    hero_eyebrow = models.CharField(max_length=150, default="Kenya's first cloud-literacy programme for kids")
    hero_title_start = models.CharField(max_length=100, default="Every Kenyan child,")
    hero_title_accent = models.CharField(max_length=60, default="cloud-ready", help_text="Highlighted word(s)")
    hero_title_end = models.CharField(max_length=60, default="by 2030.")
    hero_lead = models.TextField(default=(
        "Cloud for Kids teaches children aged 9-17 how data, the internet, and the cloud actually work, "
        "through school clubs, after-school hubs, and holiday bootcamps aligned to Kenya's CBC/CBE curriculum."))
    hero_note = models.CharField(max_length=200, blank=True, default="Foundational, Intermediate, Advanced: a 3-tier pathway from Grade 4 to Grade 12.")
    gap_title = models.CharField(max_length=200, default="Kenya's digital economy is growing faster than its cloud skills")
    why_now_title = models.CharField(max_length=100, default="Why now?")
    why_now_text = models.TextField(default=(
        "AWS, Microsoft, Samsung and Konza Technopolis are already investing in Kenya's digital skills ecosystem. "
        "Cloud for Kids plugs school-age children directly into that pipeline."))
    # About page
    about_title = models.CharField(max_length=200, default="Building Kenya's next generation of cloud-ready digital innovators")
    about_lead = models.TextField(default=(
        "Cloud for Kids is a cloud computing literacy programme for children aged 9 to 17, taught through school "
        "partnerships and after-school learning hubs and aligned to Kenya's CBC/CBE curriculum."))
    story_title = models.CharField(max_length=200, default="Closing the skills gap at the source")
    story_text = models.TextField(default="", help_text="Separate paragraphs with a blank line")
    mission = models.TextField(default="")
    vision = models.TextField(default="")
    north_star = models.CharField(max_length=200, default="Every Kenyan child, cloud-ready by 2030.")
    # Contact + footer
    contact_email = models.EmailField(default="adelinemakokha@gmail.com")
    footer_email = models.EmailField(blank=True, default="info@cloudforkids.co.ke")
    website = models.CharField(max_length=100, blank=True, default="www.cloudforkids.co.ke")
    phone = models.CharField(max_length=40, blank=True)
    location = models.CharField(max_length=200, default="Kenya, starting with an urban and peri-urban pilot")
    response_time = models.CharField(max_length=150, default="We aim to reply within 2 working days")
    footer_tagline = models.CharField(max_length=250, default="Building Kenya's cloud-ready generation, one classroom, one hub, one child at a time.")
    footer_copyright = models.CharField(max_length=250, default="Cloud for Kids. Building Kenya's Next Generation of Cloud-Ready Digital Innovators.")

    class Meta:
        verbose_name = "Site settings"
        verbose_name_plural = "Site settings"

    def __str__(self):
        return "Site settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class ImpactStat(models.Model):
    """A headline number, shown on the home page and/or the About page."""

    class Where(models.TextChoices):
        HOME = "home", "Home page"
        ABOUT = "about", "About page"

    value = models.CharField(max_length=20, help_text="e.g. 79%")
    label = models.CharField(max_length=200)
    source = models.CharField(max_length=100, blank=True)
    where = models.CharField(max_length=10, choices=Where.choices, default=Where.HOME)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["where", "order", "id"]

    def __str__(self):
        return f"{self.value} ({self.get_where_display()})"


class InfoCard(models.Model):
    """Small repeated blocks of website text: values, audiences, reasons, theory-of-change steps, open roles."""

    class Section(models.TextChoices):
        TEACH = "teach", "About: how we teach"
        AUDIENCE = "audience", "About: who it's for"
        DIFFERENT = "different", "About: why we are different"
        ROLE = "role", "About: open roles"
        THEORY = "theory", "Impact: theory of change step"
        WRITES = "writes", "Contact: who usually writes to us"

    section = models.CharField(max_length=12, choices=Section.choices)
    icon = models.CharField(max_length=40, blank=True, help_text="Bootstrap Icons name, e.g. shield-check")
    title = models.CharField(max_length=150)
    text = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    published = models.BooleanField(default=True)

    class Meta:
        ordering = ["section", "order", "id"]

    def __str__(self):
        return f"{self.get_section_display()}: {self.title}"


class TeamMember(models.Model):
    name = models.CharField(max_length=100)
    role = models.CharField(max_length=100)
    bio = models.CharField(max_length=300, blank=True)
    email = models.EmailField(blank=True)
    photo = models.ImageField(upload_to="team/", blank=True, null=True)
    order = models.PositiveIntegerField(default=0)
    published = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.name

    @property
    def initials(self):
        return "".join(part[0] for part in self.name.split()[:2]).upper()


class LegalPage(models.Model):
    """Terms, Privacy Policy and other legal text, editable in the admin."""

    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=150)
    body = models.TextField(help_text="HTML. Use <h2>, <p>, <ul> and <li>.")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class UITranslation(models.Model):
    """One piece of website wording in Kiswahili. Applied when a visitor reads the site in Kiswahili.
    The English text must match the page exactly. Use {n} for a number (for example "{n} day streak")."""

    english = models.TextField(unique=True)
    swahili = models.TextField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "UI translation"
        ordering = ["english"]

    def __str__(self):
        return self.english[:80]


class SitePhoto(models.Model):
    """A photo shown on a page, chosen by slot name (for example about-hero). Upload a file or paste an image address."""

    slot = models.SlugField(unique=True, help_text="Where it is used, for example about-hero, contact, tier-explorer")
    image = models.ImageField(upload_to="site/", blank=True, null=True, help_text="Upload a photo, or paste an address below")
    url = models.URLField(blank=True, max_length=400, help_text="Address of an image, for example from Unsplash")
    alt = models.CharField(max_length=200, blank=True, help_text="Describe the photo for screen readers")
    credit_name = models.CharField(max_length=100, blank=True, help_text="Photographer, shown as a small credit")
    credit_url = models.URLField(blank=True, max_length=400)

    class Meta:
        ordering = ["slot"]

    def __str__(self):
        return self.slot

    @property
    def src(self):
        if self.image:
            return self.image.url
        if "images.unsplash.com" in self.url and "?" not in self.url:
            return self.url + "?auto=format&fit=crop&w=1400&q=75"
        return self.url
