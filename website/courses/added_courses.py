"""Courses added after the original programme, whose lesson pages live in lesson_content/.

Each course in COURSES has its lessons and a module exam built from all of their quiz questions (dealt as a random set
of `exam_size` on each attempt). `install(key, Tier, Course, Lesson)` works with real or historical models and adds
a course once; `install_all` adds every course (used when a new database is seeded).
"""

from pathlib import Path

from .exams import QUESTION, asked, build_exam_content

CONTENT_DIR = Path(__file__).resolve().parent / "lesson_content"

COURSES = {
    "computer-packages-basics": {
        "tier": "foundational", "position": "first", "icon": "pc-display-horizontal",
        "title": "Computer Packages & Basics", "title_sw": "Misingi ya Kompyuta",
        "summary": "Meet the parts of a computer, the software that runs on it, and how files and folders keep your work organised.",
        "summary_sw": "Kutana na sehemu za kompyuta, programu zinazoendeshwa juu yake, na jinsi mafaili na folda zinavyopanga kazi yako.",
        # slug: (title, Kiswahili title, summary, minutes)
        "lessons": {
            "what-is-a-computer-components-how-they-work": (
                "What Is a Computer? Components & How They Work", "Kompyuta ni Nini? Vipengele na Jinsi Vinavyofanya Kazi",
                "Understanding computer components and how they work together.", 210),
            "computer-software-programs": (
                "Computer Software & Programs", "Programu za Kompyuta",
                "Understanding software, programs, operating systems, and how they use hardware.", 210),
            "files-folders-data-organization": (
                "Files, Folders & Data Organization", "Mafaili, Folda na Upangaji wa Data",
                "Understanding how computers organize and store information.", 210),
        },
        "exam_size": 15, "exam_pass": 80, "exam_minutes": 60,  # "Answer all 15 questions", 12 of 15 to pass
    },
    "building-real-cloud-applications": {
        "tier": "intermediate", "position": "last", "icon": "cloud-arrow-up-fill",
        "title": "Building Real Cloud Applications", "title_sw": "Kujenga Programu Halisi za Wingu",
        "summary": "Cloud service models, deploying apps, cloud databases and APIs, and keeping cloud data secure.",
        "summary_sw": "Aina za huduma za wingu, kuchapisha programu, hifadhidata za wingu na API, na kulinda data ya wingu.",
        "lessons": {
            "cloud-services-platforms-how-cloud-actually-works": (
                "Cloud Services & Platforms: How Cloud Actually Works", "Huduma na Majukwaa ya Wingu: Jinsi Wingu Linavyofanya Kazi Hasa",
                "Understanding cloud platforms, services, and deployment models.", 270),
            "building-cloud-applications-databases": (
                "Building Cloud Applications & Databases", "Kujenga Programu za Wingu na Hifadhidata",
                "Building real applications with databases, APIs, and user interfaces.", 270),
            "cloud-security-data-protection": (
                "Cloud Security & Data Protection", "Usalama wa Wingu na Ulinzi wa Data",
                "Securing cloud applications and protecting data.", 210),
        },
        "exam_size": 20, "exam_pass": 70, "exam_minutes": 90,  # "Answer all 20 questions", 70% to pass
    },
}


class _Titled:  # build_exam_content only needs the course title
    def __init__(self, title):
        self.title = title


def install(key, Tier, Course, Lesson):
    """Add one course (once) to its tier. Returns True if it was added."""
    spec = COURSES[key]
    tier = Tier.objects.filter(slug=spec["tier"]).first()
    if tier is None or Course.objects.filter(slug=key).exists():
        return False
    siblings = Course.objects.filter(tier=tier)
    if spec["position"] == "first":
        for course in siblings:  # make room at the start of the tier
            course.order += 1
            course.save(update_fields=["order"])
        order = 0
    else:
        last = siblings.order_by("-order").first()
        order = last.order + 1 if last else 0
    course = Course.objects.create(
        tier=tier, slug=key, icon=spec["icon"], order=order, title=spec["title"], title_sw=spec["title_sw"],
        summary=spec["summary"], summary_sw=spec["summary_sw"],
    )
    pending, questions = [], []
    for position, (slug, (title, title_sw, summary, minutes)) in enumerate(spec["lessons"].items()):
        content = (CONTENT_DIR / f"{slug}.html").read_text(encoding="utf-8")
        questions.extend(QUESTION.findall(content))
        pending.append(Lesson(
            course=course, slug=slug, title=title, title_sw=title_sw, summary=summary, content=content,
            duration_minutes=minutes, order=position, lesson_type="lesson", pass_score_percent=70,
        ))
    size, pass_percent = spec["exam_size"], spec["exam_pass"]
    pending.append(Lesson(
        course=course, slug=f"full-module-exam-{key}", title=f"Full Module Exam: {spec['title']}",
        title_sw=f"Mtihani wa Kozi: {spec['title_sw']}", summary=f"Check everything you learned in {spec['title']}.",
        summary_sw=f"Pima ulichojifunza katika {spec['title_sw']}.",
        content=build_exam_content(_Titled(spec["title"]), questions, size=size, pass_percent=pass_percent),
        duration_minutes=max(spec["exam_minutes"], asked(questions, size) * 2), order=len(spec["lessons"]), lesson_type="exam",
        pass_score_percent=pass_percent, quiz_size=size,
    ))
    Lesson.objects.bulk_create(pending)  # bulk: no per-lesson signal, the exam is added explicitly above
    return True


def install_all(Tier, Course, Lesson):
    for key in COURSES:
        install(key, Tier, Course, Lesson)


def uninstall(key, Course):
    Course.objects.filter(slug=key).delete()
