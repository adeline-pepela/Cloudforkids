# Cloud for Kids

A learning platform for **Cloud for Kids**, a cloud-computing literacy programme for Kenyan children
aged 7 to 17, aligned to Kenya's CBC/CBE curriculum. It is a working product, not only a marketing site:
learners study and practise, parents follow progress, and facilitators run classes.

> Branch `Pre-production`: feature-complete build ready for final testing before launch.
> See [Deploying](#deploying-render-or-any-python-host) and [Still open before launch](#still-open-before-launch).

## Who uses it

| Role | Where they land | What they do |
|---|---|---|
| **Learner** (7 to 17) | `/dashboard/` | Follow a learning path, read lessons, pass quizzes, try Practice Labs, earn badges and keep a streak. Join a class with a code. |
| **Parent / guardian** | `/family/` | Link to their child with a family code, see progress from 0 to 100%, strengths, weak points, activity and tips. |
| **Facilitator / teacher** | `/teach/` | Create classes, share a join code, see a class roster, set assignments, find hardest topics, export CSV. |
| **Admin** | `/admin/` | Manage all content, users and site wording from a custom dashboard. |

Role is chosen at sign-up (Learner, Parent, Facilitator) or by an admin on the **Add user** page.
Each role is redirected to its own area after login.

## How the content works

Everything shown on the site comes from the database (PostgreSQL). Nothing is hard-coded in templates.

```
Tier (3)  ->  Course (8)  ->  Lesson (36)
Foundational   2 courses       28 teaching lessons + 8 module exams
Intermediate   3 courses
Advanced       3 courses
```

- **Lessons** store their HTML in `Lesson.content` (edit in Admin > Lessons). Quiz questions are
  `mcq-question` blocks inside that HTML. The original lesson files are kept in
  `courses/lesson_content/` and are imported by migration `0008` on a fresh database.
- **Module exams**: every course ends with a "Full Module Exam" built automatically from the
  lessons' quiz questions (`courses/exams.py`). Saving a lesson creates the exam if missing; in
  Admin > Courses use *Create / rebuild the module exam* to refresh it, or run
  `python manage.py build_exams --refresh`.
- **Practice Labs** (5 simulations) have their details in the `Lab` table. The interactive part lives in
  `templates/learner/labs/<slug>.html` and `static/js/labs.js`.
- **Website wording and numbers** are editable in Admin: *Site settings* (hero, About text, contact
  details, footer), *Impact stats*, *Info cards*, *Team members*, *Partners*, *Testimonials*.
  Live counts (learners, lessons completed, labs finished) are calculated from the database.

## Learning rules

- A lesson with a quiz can only be marked complete after the learner **passes the quiz**
  (default 70%). The quiz sits on the right of the lesson page. The server checks the score and the
  question count, and stores the best result in `QuizResult`.
- A course is **complete when its module exam is passed**. That awards a "Course Graduate" badge.
- Each completion stores the score (`LessonCompletion.score_percent`).
- **XP and levels**: 10 XP per lesson, 15 XP per lab, 100 XP per level (seven level names).
- **Streak**: consecutive days with a lesson or lab finished.
- **Badges** are awarded automatically: First Lesson, Rising Cloud, Cloud Champion, Lab Explorer,
  Lab Master, 3-Day and 7-Day Streak, and one Graduate badge per course.

## Parent portal (`/family/`)

1. The learner opens **My Profile** and reads the 6-character **family code**.
2. The parent opens **Add a child** and enters the learner's username and that code.
   Wrong guesses are limited (6 tries per 15 minutes) and the message never reveals whether a username exists.
3. The parent sees per child: progress from 0 to 100% along the tier path, streak, level, quiz average,
   time learning, strengths (quizzes passed at 80% or more), weak points (failed quizzes and labs not
   tried), course-by-course lessons with scores, a 14-day activity chart, badges, and tips for helping at
   home. Reports can be printed. A parent can only open children they linked.

## Facilitator portal (`/teach/`)

1. The facilitator creates a **class** (optionally tied to a tier). It gets a join code.
2. Learners enter the code under **My classes** on their profile page. Only learners who joined see
   a teacher's data, and teachers only see their own classes.
3. The class page shows the roster with progress, quiz average, streak, last active and a status
   (On track, Inactive, Needs help, Not started, Finished), a learners-active chart, hardest topics,
   a lesson-by-lesson completion table, suggestions, CSV export and print.
4. **Assignments**: assign a course with a due date and note. Learners see it under *From your teacher* on
   their home page, with their progress.
5. A **Curriculum** page lets the teacher preview every lesson.

## Admin (`/admin/`)

A fixed sidebar and dashboard (stats, charts, items needing attention), light and dark theme. Add user
asks for the role. Classes, assignments, parent links, labs and all site content are managed here.

## Tech stack

- Python 3.11 and Django 5.2, custom `accounts.User` (roles learner, parent, facilitator, admin).
- **PostgreSQL** (Neon) through `DATABASE_URL`; SQLite is the automatic fallback for quick local runs.
- Bootstrap 5.3, Bootstrap Icons, Chart.js and fonts, all self-hosted in `static/vendor/` (works offline).
- Server-rendered templates, small vanilla JS files, no front-end framework.

## Project structure

```
website/
  cloudforkids/   settings, root URLs
  accounts/       User, LearnerProfile (+family code), ParentLink, Classroom, ClassMembership, Assignment
  courses/        Tier, Course, Lesson, Enrollment, LessonCompletion, QuizResult, Badge, exam builder
  core/           public pages, SiteSetting, ImpactStat, InfoCard, TeamMember, Partner, Testimonial
  dashboard/      learner dashboard + labs, parent portal (family*), facilitator portal (teach*)
  templates/      base, learner, parent, teach, admin overrides, partials
  static/         css, js, img, vendor (self-hosted libraries)
```

## Setup

```bash
cd website
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then put your DATABASE_URL in .env (or leave unset to use SQLite)
python manage.py migrate        # builds the schema and seeds the programme on an empty database
python manage.py createsuperuser
python manage.py runserver
```

`migrate` seeds the 3 tiers, 8 courses, 36 lessons, badges, partners, labs and site wording only when the
database is empty, and never overwrites existing content. It also creates a demo account
`demo_learner` (see `seed_data_fixed.py`); **delete or change its password before launch**.

## Forgot password and email (Resend)

`/accounts/password-reset/` emails a one-time link (valid 2 hours) through [Resend](https://resend.com).
Put the key in `website/.env`:

```
RESEND_API_KEY=re_xxxxxxxx
EMAIL_FROM=Cloud for Kids <no-reply@your-verified-domain>
```

- Without `RESEND_API_KEY` emails are printed in the server console (handy for local testing).
- Until a domain is verified in Resend, `onboarding@resend.dev` only delivers to your own Resend account email.
- The page always says "check your email" whether or not the address exists, a mail failure never shows an error,
  and each IP can request 5 resets per hour. Accounts need an email on file to reset.
- The login, sign-up and reset pages use Unsplash photos (hotlinked, credited on the page).

## Moving data between databases

```bash
python manage.py dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.permission -e sessions -e admin.logentry -o dump.json
# point DATABASE_URL at the new database, then:
python manage.py migrate && python manage.py flush --no-input && python manage.py loaddata dump.json
```

## Safety, consent and accounts

- **Terms and Privacy pages** (`/terms/`, `/privacy/`) are editable in Admin > Legal pages. The text is a draft: have a lawyer review it
  against Kenya's Data Protection Act, 2019 before launch.
- **Learners aged 7 to 17 only.** Sign-up asks for a date of birth. A learner **under 13** is created locked, and their parent or guardian gets an
  email with an Approve / Decline page. Decline deletes the account. Admins can record consent another way (Admin > Parental consents).
- **Facilitators are approved by an admin** before class tools work (Admin > Users > Approve selected facilitators). They are emailed when approved.
- **Learners cannot send messages.** Facilitators write to a class (learners and linked parents) or to one child's parents; parents can reply.
- **Quizzes are graded on the server.** The lesson page never contains the answers; the browser asks the server to check each answer, and options
  appear in a random order. Scores come from the server's own record.

## Languages

English and Kiswahili (EN | SW switch). Fixed wording is translated from the **UI translations** table (Admin > UI translations, about 670 entries,
`python manage.py load_translations` adds new ones). Tier, course and lesson names and the whole **Explorer** tier have Kiswahili versions
(the `*_sw` fields). Other lesson bodies fall back to English until a Kiswahili page is added in the lesson's admin form. Have a native speaker review the translations.

## Explorer tier (Grade 1 to 3)

A fourth, first tier for ages 7 and 8: *My Digital World* (computers, tapping and typing, where pictures live, staying safe) and *Little Coders*
(instructions, patterns), each with a module exam, in English and Kiswahili. New learners get a starting tier from their age (`courses/tiers.py`).

## Emails (Resend)

Account emails (consent, approval, assignments, messages) and scheduled emails: a **weekly progress summary** for parents and **reminders** after a few quiet days.
Every optional email has a one-click unsubscribe. Run from a scheduler (the Render blueprint does this):

```
python manage.py send_notifications --weekly    # Sunday evening
python manage.py send_notifications --nudges    # every morning
```

## Admin tools

- **Import learners** (Admin > Tools): upload a CSV (template provided), logins are generated and shown once, optional class and tier.
- **Monthly report** (Admin > Tools): learners, activity, quiz results, courses completed, by tier, course, county and school. Download CSV or print.
- **Site photos**: choose or upload the photo for each page slot, with a credit.

## Tests

`python manage.py test` runs about 110 tests on an in-memory database (roles, consent, quiz rules, parent link, class codes, messaging, emails, languages, imports, reports).

## Deploying (Render or any Python host)

`render.yaml` is a ready blueprint (web service plus the two email jobs). Whatever host you use, set these **environment variables** before the first deploy;
the app refuses to start without the first three:

| Variable | Example |
|---|---|
| `SECRET_KEY` | a long random string (never reuse the dev one) |
| `ALLOWED_HOSTS` | `cloudforkids.co.ke,www.cloudforkids.co.ke` |
| `DATABASE_URL` | your Neon connection string |
| `SITE_URL` | `https://cloudforkids.co.ke` (links inside emails) |
| `RESEND_API_KEY`, `EMAIL_FROM` | from Resend, with a verified sending domain |
| `CSRF_TRUSTED_ORIGINS` | optional, derived from `ALLOWED_HOSTS` as `https://<host>` when not set |

`DEBUG` is off unless you set `DEBUG=True` (local `.env` only). Build with `pip install -r requirements.txt && python manage.py collectstatic --noinput`,
run `python manage.py migrate`, start with `gunicorn cloudforkids.wsgi`. Static files are served by WhiteNoise.
If a login or form shows "CSRF verification failed. Origin checking failed", the site's `https://` address is missing from the trusted origins: check `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS`.

## Still open before launch

- Legal review of the Terms and Privacy text, and a native-speaker review of the Kiswahili.
- Uploaded files (team and testimonial photos) are stored on the server disk; use object storage (S3, Cloudinary) if your host wipes disks on deploy.
- Moving the lesson-page images and the remaining lesson bodies to Kiswahili.
