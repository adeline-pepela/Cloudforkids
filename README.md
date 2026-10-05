# Cloud for Kids

A learning platform for **Cloud for Kids**, a cloud-computing literacy programme for Kenyan children
aged 7 to 17, aligned to Kenya's CBC/CBE curriculum. It is a working product, not only a marketing site:
learners study and practise, parents follow progress, and facilitators run classes.

> Branch `Pre-production`: feature-complete build ready for final testing before launch.
> See [Before going live](#before-going-live) for what is still open.

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

## Moving data between databases

```bash
python manage.py dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.permission -e sessions -e admin.logentry -o dump.json
# point DATABASE_URL at the new database, then:
python manage.py migrate && python manage.py flush --no-input && python manage.py loaddata dump.json
```

## Before going live

- Set `DEBUG = False`, a real `SECRET_KEY` and `ALLOWED_HOSTS` from environment variables (`manage.py check --deploy` lists the rest).
- Set secure cookies and HTTPS redirect, and serve static files (WhiteNoise or a CDN).
- Remove or change the demo account.
- Add the real photos in `static/img/photos/` (missing ones show a coloured icon placeholder).
- Decide whether facilitator sign-up needs admin approval (today anyone can choose that role at sign-up;
  they only see learners who join their class with the code).
- Quiz scoring is done in the browser and reported to the server, so a determined user could bypass it.
  Moving the answer key server-side is the next hardening step.
- Foundational starts at Grade 4, so ages 7 and 8 are not covered yet.
