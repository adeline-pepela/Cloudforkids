from django.core.management.base import BaseCommand
from django.utils.text import slugify

from accounts.models import User
from core.models import Partner
from courses.models import Badge, Course, Lesson, Tier


TIERS = [
    {
        "name": "Foundational",
        "grade_range": "Grade 4-6",
        "cbc_alignment": "Digital Literacy (Core Competency) & Pre-Technical Studies",
        "summary": "Unplugged, hands-on intro to how data, devices, and the cloud actually work.",
        "description": (
            "Designed to need little to no hardware or connectivity, the Foundational tier "
            "introduces core ideas of data, storage, networks, and the internet as groundwork "
            "for cloud concepts later on."
        ),
        "icon": "\u2601\ufe0f",
        "courses": [
            {
                "title": "What Is the Cloud, Really?",
                "summary": "Unplugged activities that explain data, storage, and networks with everyday objects.",
                "icon": "\U0001F4E6",
                "lessons": [
                    ("Where Does Your Data Live?", "An unplugged game that shows what a computer, a server and 'the cloud' actually are."),
                    ("Networks & the Internet", "Building a paper 'network' to understand how devices talk to each other."),
                    ("Data & Storage Basics", "Sorting, saving and organising information the way computers do."),
                    ("Being Safe and Kind Online", "Digital citizenship basics: passwords, privacy, and kindness online."),
                ],
            },
            {
                "title": "My First Digital Projects",
                "summary": "Simple, low-tech creative projects that build comfort with digital tools.",
                "icon": "\U0001F3A8",
                "lessons": [
                    ("Typing & Files 101", "Creating, naming, and saving your first digital files."),
                    ("Intro to Scratch", "Making a simple animation or game with block-based coding."),
                    ("Show What You Know", "A mini show-and-tell project presenting what 'the cloud' means to you."),
                ],
            },
        ],
    },
    {
        "name": "Intermediate",
        "grade_range": "Grade 7-9",
        "cbc_alignment": "Computer Science & Pre-Technical Studies (Junior Secondary)",
        "summary": "Hands-on cloud platforms and coding: first accounts, first programs, first deployments.",
        "description": (
            "Learners get hands-on with free-tier education offerings such as AWS Educate, "
            "Google Cloud Skills Boost, and Microsoft Learn for Educators, alongside basic "
            "coding from Scratch through to Python."
        ),
        "icon": "\u2699\ufe0f",
        "courses": [
            {
                "title": "Coding Foundations",
                "summary": "From block-based coding to real Python programs.",
                "icon": "\U0001F4BB",
                "lessons": [
                    ("From Scratch to Python", "Bridging visual coding to text-based Python programming."),
                    ("Variables & Loops", "Core programming concepts through short, fun Python exercises."),
                    ("Building a Simple Program", "Writing a small Python project from start to finish."),
                ],
            },
            {
                "title": "Getting Started in the Cloud",
                "summary": "First cloud accounts and first cloud-hosted mini-projects.",
                "icon": "\u2601\ufe0f",
                "lessons": [
                    ("Setting Up AWS Educate", "Creating and exploring a free AWS Educate learner account."),
                    ("Cloud Storage in Practice", "Uploading, organising and sharing files using real cloud storage."),
                    ("Your First Hosted Web Page", "Publishing a simple web page using a free cloud hosting tier."),
                    ("Intro to Google Cloud Skills Boost", "Exploring guided, hands-on labs in a real cloud console."),
                ],
            },
        ],
    },
    {
        "name": "Advanced",
        "grade_range": "Grade 10-12 (STEM Pathway)",
        "cbc_alignment": "Computer Studies / Technology & Engineering (STEM Pathway, Senior School)",
        "summary": "Project-based cloud computing: web hosting, databases, and intro AI/cloud services.",
        "description": (
            "Within the STEM pathway's Computer Studies track, learners undertake project-based "
            "units covering basic web hosting, simple databases, and introductory AI/cloud "
            "services, with an emphasis on portfolio-building toward AWS Educate, AWS re/Start "
            "and university Computer Science admission."
        ),
        "icon": "\U0001F680",
        "courses": [
            {
                "title": "Cloud Databases & Web Apps",
                "summary": "Build and host a simple database-backed web application.",
                "icon": "\U0001F5C3\ufe0f",
                "lessons": [
                    ("Databases 101", "How structured data is stored, queried, and secured in the cloud."),
                    ("Designing a Simple Web App", "Planning a small web app that reads and writes data."),
                    ("Deploying to the Cloud", "Hosting your project so anyone can access it online."),
                ],
            },
            {
                "title": "AI & Cloud Services",
                "summary": "An introductory look at AI services that run on the cloud.",
                "icon": "\U0001F916",
                "lessons": [
                    ("What Is Cloud AI?", "A friendly introduction to AI services offered by cloud providers."),
                    ("Trying a Managed AI Service", "Hands-on with a free-tier AI/ML service in a guided lab."),
                ],
            },
            {
                "title": "Capstone: Your Cloud Portfolio",
                "summary": "Package your best work into a portfolio for AWS Educate, re/Start or university applications.",
                "icon": "\U0001F393",
                "lessons": [
                    ("Choosing Your Capstone Project", "Scoping a capstone project that shows off your cloud skills."),
                    ("Building Your Capstone", "Building and documenting your capstone project."),
                    ("Presenting Your Portfolio", "Preparing a portfolio and pitch for next steps: AWS Educate, re/Start, or university."),
                ],
            },
        ],
    },
]

PARTNERS = [
    ("AWS / Konza Technopolis", "Cloud curriculum content, certification pathways, and workforce-enablement partnership."),
    ("Mastercard Foundation / eMobilis", "Youth digital-skills funding, with a co-funding precedent via AWS re/Start."),
    ("World Bank \u2013 Digital Economy Acceleration Project", "Infrastructure and education-quality funding."),
    ("Ajira Digital Centres", "Hub infrastructure for after-school and hub-based delivery."),
    ("Konza Jitume Hubs", "Community hub infrastructure supporting offline-first expansion."),
    ("Samsung", "Device and Digital Classroom infrastructure already deployed in Kenyan schools."),
    ("Ministry of Education / KICD", "Curriculum endorsement and CBC/CBE alignment."),
    ("Robotics Society of Kenya", "Advocacy partner for the Computer Science for All Bill, 2025."),
]


class Command(BaseCommand):
    help = "Seed the database with Cloud for Kids tiers, courses, lessons, badges, partners and a demo account."

    def handle(self, *args, **options):
        for tier_data in TIERS:
            tier, _ = Tier.objects.update_or_create(
                slug=slugify(tier_data["name"]),
                defaults={
                    "name": tier_data["name"],
                    "grade_range": tier_data["grade_range"],
                    "cbc_alignment": tier_data["cbc_alignment"],
                    "summary": tier_data["summary"],
                    "description": tier_data["description"],
                    "icon": tier_data["icon"],
                    "order": TIERS.index(tier_data),
                },
            )

            for c_index, course_data in enumerate(tier_data["courses"]):
                course, _ = Course.objects.update_or_create(
                    slug=slugify(course_data["title"]),
                    defaults={
                        "tier": tier,
                        "title": course_data["title"],
                        "summary": course_data["summary"],
                        "icon": course_data["icon"],
                        "order": c_index,
                    },
                )

                for l_index, (title, summary) in enumerate(course_data["lessons"]):
                    Lesson.objects.update_or_create(
                        course=course,
                        slug=slugify(title),
                        defaults={
                            "title": title,
                            "summary": summary,
                            "content": summary
                            + "\n\nThis lesson is part of the Cloud for Kids "
                            + tier.name
                            + " tier ("
                            + tier.grade_range
                            + "). Facilitator notes and full activity instructions go here.",
                            "duration_minutes": 30,
                            "order": l_index,
                        },
                    )

        badges = [
            ("First Lesson", "Completed your very first lesson.", "\U0001F680", "Complete 1 lesson"),
            ("Rising Cloud", "Completed 5 lessons.", "\u2601\ufe0f", "Complete 5 lessons"),
            ("Cloud Champion", "Completed 15 lessons across the programme.", "\U0001F3C6", "Complete 15 lessons"),
        ]
        for name, description, icon, criteria in badges:
            Badge.objects.update_or_create(
                name=name, defaults={"description": description, "icon": icon, "criteria": criteria}
            )

        for name, description in PARTNERS:
            Partner.objects.update_or_create(name=name, defaults={"description": description})

        if not User.objects.filter(username="demo_learner").exists():
            demo = User.objects.create_user(
                username="demo_learner",
                password="CloudForKids2026",
                first_name="Demo",
                last_name="Learner",
                email="demo@cloudforkids.example",
                role=User.Role.LEARNER,
            )
            self.stdout.write(self.style.SUCCESS("Created demo learner: demo_learner / CloudForKids2026"))
        else:
            demo = User.objects.get(username="demo_learner")

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {Tier.objects.count()} tiers, {Course.objects.count()} courses, "
            f"{Lesson.objects.count()} lessons, {Badge.objects.count()} badges, "
            f"{Partner.objects.count()} partners."
        ))
