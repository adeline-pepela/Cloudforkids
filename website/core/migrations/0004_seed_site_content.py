from django.db import migrations

STORY = (
    "A 2025 SAP survey found that 79% of Kenyan firms cite cloud computing as their biggest skills shortage. "
    "Most solutions target adults who are already out of school. Cloud for Kids starts earlier, so young learners "
    "arrive at the STEM pathway in Senior School and at Kenya's growing technology job market already cloud-literate.\n\n"
    "We don't assume reliable internet in every classroom. The programme is phased and hybrid: an urban and "
    "peri-urban pilot first, then an offline-first “unplugged cloud concepts” curriculum and mobile learning "
    "hubs, modelled on Ajira Digital Centres and Konza Technopolis's Jitume hubs."
)
MISSION = ("To close Kenya's cloud skills gap at the source by building genuine cloud literacy into childhood "
           "education, not just adult retraining.")
VISION = ("Every Kenyan child, cloud-ready by 2030: confident to build, store, share and protect what they create online.")

STATS = [
    ("home", "79%", "of Kenyan firms cite cloud computing as their #1 skills shortage", "SAP survey, 2025"),
    ("home", "84.2%", "of public-school teachers struggle to use classroom technology", "TSC survey"),
    ("home", "35.3%", "of Kenyan schools are internet-connected", "The Star, 2026"),
    ("home", "36.3%", "of Kenya's population is under 15, a huge, underserved cohort", "Worldometer, 2025"),
    ("about", "7–17", "years old: upper primary to senior secondary", ""),
    ("about", "3", "tiers: Foundational, Intermediate, Advanced", ""),
    ("about", "Gr 4–12", "mapped to CBC/CBE and the STEM pathway", ""),
    ("about", "79%", "of Kenyan firms name cloud as their top skills shortage", "SAP survey, 2025"),
]

CARDS = [
    ("teach", "hand-index-thumb", "Hands-on first", "Short lessons, activities and quizzes. Learners build and try things, not just read about them."),
    ("teach", "wifi-off", "Works offline", "Unplugged activities mean learning continues where connectivity is limited."),
    ("teach", "journal-check", "Curriculum aligned", "Built around CBC/CBE and the new Senior School STEM pathway."),
    ("teach", "shield-check", "Safe & kind online", "Digital citizenship is part of every tier, from strong passwords to kind words."),
    ("different", "", "First cloud-specific literacy programme", "First cloud-specific (not just general coding) literacy programme for kids in Kenya."),
    ("different", "", "Aligned to CBC/CBE", "Directly aligned to CBC/CBE and the new Senior School STEM pathway."),
    ("different", "", "A feeder pipeline", "A feeder pipeline into AWS Educate, AWS re/Start, and university Computer Science, complementing, not competing with, the existing ecosystem."),
    ("different", "", "Built for real connectivity", "Built around Kenya's real connectivity realities with a hybrid offline/online model."),
    ("audience", "person-hearts", "Parents & guardians", "Give your child a head start in a high-demand field."),
    ("audience", "buildings", "Schools", "Ready-made lessons and quizzes that fit your timetable."),
    ("audience", "easel", "Facilitators", "Clear lesson plans and activities to run with a class or club."),
    ("audience", "people", "Partners & donors", "Help fund and grow a cloud-ready generation."),
    ("role", "", "Head of Curriculum", ""),
    ("role", "", "Head of Partnerships", ""),
    ("role", "", "Lead Facilitator", ""),
    ("theory", "", "Inputs", "Curriculum, trained facilitators, partner schools and hubs, and seed funding."),
    ("theory", "", "Activities", "In-school clubs, after-school hub sessions, holiday bootcamps, and teacher training."),
    ("theory", "", "Outputs", "Learners trained per tier, facilitators & teachers trained, partner schools and hubs established."),
    ("theory", "", "Outcomes", "Improved digital & cloud literacy, stronger STEM pathway readiness, increased interest in cloud careers."),
    ("theory", "", "Impact", "A stronger, cloud-skilled Kenyan youth talent pipeline, and a narrower urban-rural digital divide."),
    ("writes", "person-hearts", "Parents asking which tier fits their child", ""),
    ("writes", "buildings", "Schools interested in joining the pilot", ""),
    ("writes", "easel", "Teachers who want to facilitate a club", ""),
    ("writes", "people", "Partners, donors and investors", ""),
]


def seed(apps, schema_editor):
    Setting = apps.get_model("core", "SiteSetting")
    ImpactStat = apps.get_model("core", "ImpactStat")
    InfoCard = apps.get_model("core", "InfoCard")
    TeamMember = apps.get_model("core", "TeamMember")

    Setting.objects.get_or_create(pk=1, defaults={"story_text": STORY, "mission": MISSION, "vision": VISION})
    if not ImpactStat.objects.exists():
        for order, (where, value, label, source) in enumerate(STATS):
            ImpactStat.objects.create(where=where, value=value, label=label, source=source, order=order)
    if not InfoCard.objects.exists():
        counters = {}
        for section, icon, title, text in CARDS:
            counters[section] = counters.get(section, -1) + 1
            InfoCard.objects.create(section=section, icon=icon, title=title, text=text, order=counters[section])
    if not TeamMember.objects.exists():
        TeamMember.objects.create(
            name="Adeline Makokha", role="General Consultant",
            bio="Programme design, curriculum strategy, and investor relations.",
            email="adelinemakokha@gmail.com",
        )


class Migration(migrations.Migration):

    dependencies = [("core", "0003_site_content")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
