# Cloud for Kids

A web application for **Cloud for Kids**, a proposed cloud computing literacy
programme for Kenyan children aged 9–17, aligned to Kenya's CBC/CBE curriculum. 

## What's included

This isn't just a marketing site — it's a working learning platform:

- **Marketing pages**: Home, About, Programs, Curriculum/CBC alignment, Partners, Impact
  (Theory of Change), Contact (saves messages to the database, viewable in Django admin).
- **Accounts**: sign up / log in, with roles for Learner, Parent/Guardian, Facilitator, and
  Admin. Learners have an extended profile (tier, grade, school, county, parent/guardian
  contact info).
- **Courses**: three programme tiers (Foundational Grade 4–6, Intermediate Grade 7–9, Advanced
  Grade 10–12), each with courses and lessons seeded from the real Cloud for Kids curriculum
  described in the concept note.
- **Enrollment & progress tracking**: learners enroll in courses, mark lessons complete, and
  see a progress bar per course.
- **Badges**: simple gamification (First Lesson, Rising Cloud, Cloud Champion, and a
  "graduate" badge per completed course), awarded automatically.
- **Learner dashboard**: enrolled courses with progress, suggested next courses, and badges
  earned.
- **Django admin**: full content management for tiers, courses, lessons, partners, contact
  messages, badges, and users — no code changes needed to update content.

## Tech stack

- Python 3 + Django 5
- SQLite (default; swap `DATABASES` in `cloudforkids/settings.py` for Postgres/MySQL in
  production)
- Bootstrap 5 (via CDN) + a custom kid-friendly, colorful theme (`static/css/style.css`) using
  a sky-blue palette, playful "Baloo 2" headings, and a subtle Kenyan flag accent stripe.
- No JavaScript framework — server-rendered Django templates.

## Project structure

```
website/
  cloudforkids/       # project settings, root urls
  accounts/           # custom User model, LearnerProfile, signup/login/profile
  courses/            # Tier, Course, Lesson, Enrollment, Badge models + views + seed command
  core/                # marketing pages, Partner & ContactMessage models
  dashboard/           # learner dashboard view
  templates/           # all HTML templates (base.html + one folder per app)
  static/css/style.css # the kid-friendly visual theme
```

## Setup

1. **Create a virtual environment and install dependencies**

   ```bash
   cd website
   python3 -m venv .venv
   source .venv/bin/activate   # on Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Run migrations**

   ```bash
   python manage.py migrate
   ```

3. **Seed the database** with the Cloud for Kids curriculum, badges, and partner list:

   ```bash
   python manage.py seed_data
   ```

   This also creates a demo learner account: **username `demo_learner` / password
   `CloudForKids2026`**.

4. **Create an admin account** (to manage content via `/admin/`):

   ```bash
   python manage.py createsuperuser
   ```

5. **Run the dev server**

   ```bash
   python manage.py runserver
   ```

   Visit `http://127.0.0.1:8000/`.

## Editing content

Almost everything on the site (tiers, courses, lessons, partners) is stored in the database
and editable from the Django admin at `/admin/` — no template or Python edits required to
update copy. To change the design system (colors, fonts), edit `static/css/style.css`.

## Notes

- The `role` field on the user model (`accounts/models.py`) distinguishes learners, parents,
  facilitators, and admins — useful groundwork if you later want different dashboards per role.
- Lesson content is stored as plain text for now; swap in a rich-text/markdown field later if
  facilitators need formatted lesson content.
- This is a development-ready build (`DEBUG = True`, SQLite, no payment integration). Before
  going live: set `DEBUG = False`, configure `ALLOWED_HOSTS`, move to Postgres, set a real
  `SECRET_KEY` via environment variable, and configure static file serving (e.g. WhiteNoise or
  a CDN).
