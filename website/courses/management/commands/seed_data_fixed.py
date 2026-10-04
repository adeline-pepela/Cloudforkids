import math

from django.core.management.base import BaseCommand
from django.utils.text import slugify

from accounts.models import User
from core.models import Partner
from courses.models import Badge, Course, Lesson, Tier


# ---------------------------------------------------------------------------
# Tiny inline-SVG building blocks used to draw lesson illustrations.
# Colours reference the site's CSS variables so visuals stay on-brand.
# Playful lessons (Foundational / Intermediate / AWS for Kids) lean on bright
# colours and emoji icons. Advanced-tier lessons use a calmer, more grown-up
# diagram style (muted greys/blues, geometric shapes, no emoji).
# ---------------------------------------------------------------------------

SKY = "var(--sky)"
SKY_DARK = "var(--sky-dark)"
SKY_LIGHT = "var(--sky-light)"
SUN = "var(--sun)"
GRASS = "var(--grass)"
INK = "var(--ink)"
AWS_BG = "#FFF4E6"
AWS_ORANGE = "#FF9900"
AWS_ORANGE_DARK = "#B35C00"
PRO_BG = "#F1F5F9"
PRO_BORDER = "#CBD5E1"
PRO_BORDER_SOFT = "#E2E8F0"
PRO_TEXT = "#475569"
PRO_TEXT_SOFT = "#64748B"


def _bg(fill=SKY_LIGHT):
    return f'<rect x="1" y="1" width="298" height="138" rx="18" fill="{fill}"/>'


def _icon(x, y, size, emoji):
    return (
        f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="middle" '
        f'dominant-baseline="middle">{emoji}</text>'
    )


def _label(x, y, text, size=11, color=INK, weight="600"):
    return (
        f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" '
        f'fill="{color}" text-anchor="middle">{text}</text>'
    )


def _arrow(x, y, glyph="\u2192", size=22, color=INK):
    return (
        f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" '
        f'text-anchor="middle" dominant-baseline="middle">{glyph}</text>'
    )


def _box(x, y, w, h, fill="#fff", stroke=SKY_DARK):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'


def _line(x1, y1, x2, y2, color=PRO_BORDER, width=2):
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{width}"/>'


def _dot(cx, cy, r=5, fill=SKY_DARK):
    return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}"/>'


def _svg(*parts):
    return (
        '<svg viewBox="0 0 300 140" xmlns="http://www.w3.org/2000/svg" '
        'class="lesson-visual-svg" role="img" aria-label="lesson illustration">'
        + "".join(parts)
        + "</svg>"
    )


# ---------------------------------------------------------------------------
# Multiple-choice quiz helpers (used for both in-lesson "Quiz Time" practice
# questions and the full module exam at the end of each course). Questions
# are built straight from each lesson's own Word Bank, so every answer and
# every distractor is content the learner has already met in that lesson -
# no separate question bank to keep in sync.
# ---------------------------------------------------------------------------

CHIP_EMOJI = ["\U0001F511", "\U0001F4D8", "\U0001F9E9", "\u2B50", "\U0001F30D", "\U0001F680"]


def _mcq_html(prompt, options, correct_index, explanation):
    option_buttons = "".join(
        f'<button type="button" class="mcq-option" data-index="{i}">{opt}</button>'
        for i, opt in enumerate(options)
    )
    return (
        f'<div class="mcq-question" data-correct="{correct_index}">'
        f'<p class="mcq-prompt">{prompt}</p>'
        f'<div class="mcq-options">{option_buttons}</div>'
        f'<div class="mcq-explain">{explanation}</div>'
        f"</div>"
    )


def _vocab_mcqs(vocab, count, prompt_template="Which word matches this definition? <em>\u201c{definition}\u201d</em>"):
    """Build `count` MCQs that ask the learner to match a Word Bank definition to its term."""
    terms = [t for t, _ in vocab]
    n = len(vocab)
    count = min(count, n)
    html_blocks = []
    for i in range(count):
        term, definition = vocab[i]
        rotated = terms[i:] + terms[:i]  # vary which option slot holds the right answer
        correct_index = rotated.index(term)
        html_blocks.append(
            _mcq_html(
                prompt_template.format(definition=definition),
                rotated,
                correct_index,
                f"<strong>{term}</strong> - {definition}",
            )
        )
    return "".join(html_blocks)


def _concept_chips(vocab, tone="fun"):
    chips = []
    for i, (term, _definition) in enumerate(vocab):
        emoji = "\u25AA" if tone == "pro" else CHIP_EMOJI[i % len(CHIP_EMOJI)]
        chips.append(
            f'<div class="concept-chip"><span class="chip-emoji">{emoji}</span>'
            f'<span class="chip-label">{term}</span></div>'
        )
    return "".join(chips)


# ---------------------------------------------------------------------------
# Lesson content builder
# ---------------------------------------------------------------------------

#: Hand-written "Did You Know?" facts and Kenya / real-world connections for
#: every lesson, keyed by lesson title. Looked up automatically inside
#: _lesson() so none of the existing _lesson(...) calls need to change shape.
LESSON_EXTRAS = {
    "Where Does Your Data Live?": {
        "fact": "Data centres already use roughly 1-2% of all the electricity on Earth - and that share keeps growing as more people save photos, videos and games to the cloud.",
        "real_world": "In Kenya, apps like M-Pesa and your favourite mobile game save their data on real servers in data centres - some of them right here in East Africa - not inside your phone.",
    },
    "Networks & the Internet": {
        "fact": "A message can hop through a dozen different routers in well under a second to cross from one side of the world to the other.",
        "real_world": "Kenya's National Fibre Optic Backbone links towns and cities the same way your paper network links houses to a router - smaller networks joined into one big network that connects to the rest of the world.",
    },
    "Data & Storage Basics": {
        "fact": "A single byte stores only one letter, yet a modern phone holds many gigabytes - billions of bytes, enough room for thousands of photos.",
        "real_world": "When you sort school notes into labelled folders on a shared family tablet, you're organising data exactly the way a school's student records system does.",
    },
    "Being Safe and Kind Online": {
        "fact": "Security experts often say four random, unrelated words make a stronger - and easier to remember - password than a short jumble of symbols.",
        "real_world": "Kenya's Data Protection Act protects your personal information online, and schools across the country run digital-safety weeks that teach exactly these password and kindness habits.",
    },
    "Typing & Files 101": {
        "fact": "The humble .txt file barely changed since the 1970s - it's one of the oldest file formats still used by almost every computer today.",
        "real_world": "Teachers and Huduma Centre staff rely on clearly named, well-organised digital files every day to find forms and records in seconds instead of hours.",
    },
    "Intro to Scratch": {
        "fact": "Scratch was created at MIT and is now used by tens of millions of young coders worldwide, in more than 70 languages.",
        "real_world": "Kenyan coding clubs and Digital Literacy Programme classrooms use Scratch as a first step before learners move on to text-based languages like Python - exactly the path this course follows.",
    },
    "Show What You Know": {
        "fact": "Teachers call it the 'Feynman technique': if you can explain an idea simply enough for a five-year-old to understand, you've truly mastered it.",
        "real_world": "Kenyan science and innovation fairs ask students to do exactly this - present a technical idea clearly to judges who may know nothing about the topic yet.",
    },
    "From Scratch to Python": {
        "fact": "Python is named after the British comedy group Monty Python, not the snake - its creator wanted a name that sounded fun and a little silly.",
        "real_world": "Python is one of the most in-demand programming languages for jobs in Kenya's growing tech sector, from Nairobi start-ups to global cloud providers.",
    },
    "Variables & Loops": {
        "fact": "Some of the very first computer bugs were literally real insects - in 1947 a moth got stuck inside a Harvard computer, and the term 'debugging' stuck ever since.",
        "real_world": "Mobile money apps like M-Pesa use loops behind the scenes to check thousands of transactions every second, and variables to keep track of every account's balance.",
    },
    "Building a Simple Program": {
        "fact": "Almost every successful app in the world started out as a small, buggy first draft - even the ones now worth billions.",
        "real_world": "Kenyan student developers at hackathons like those run by Safaricom or iHub often start with a small working program, just like your number-guessing game, before growing it into something bigger.",
    },
    "Setting Up AWS Educate": {
        "fact": "AWS Educate has given free cloud credits and training to millions of students in over 200 countries and territories since it launched.",
        "real_world": "Through Konza Technopolis and local training partners, Kenyan students increasingly use AWS Educate as their very first step into real, professional-grade cloud computing.",
    },
    "Cloud Storage in Practice": {
        "fact": "Most cloud storage providers automatically keep multiple copies of your files in different locations, so one hardware failure almost never means lost data.",
        "real_world": "Kenyan university students and NGOs commonly use cloud storage to share research and reports across teams working in different towns, without emailing huge attachments.",
    },
    "Your First Hosted Web Page": {
        "fact": "The World Wide Web - the system of linked pages you browse every day - is only about 35 years old, invented by Tim Berners-Lee in 1989.",
        "real_world": "Many young Kenyan entrepreneurs host their very first business or portfolio website on a free hosting tier, just like the one you'll use in this lesson, before ever paying for anything.",
    },
    "Intro to Google Cloud Skills Boost": {
        "fact": "AWS, Google Cloud, and Microsoft Azure together run most of the world's cloud computing - but under the hood, they're all solving the same basic problems of storage, compute and networking.",
        "real_world": "Kenyan tech hubs and universities often introduce students to more than one cloud provider, because employers value people who are comfortable moving between AWS, Google Cloud, and Azure.",
    },
    "What Is AWS and Why Does It Matter?": {
        "fact": "AWS was originally built to solve Amazon's own problem of needing more computing power during big shopping seasons - then Amazon realised it could rent that spare power to other companies too.",
        "real_world": "Through Konza Technopolis and AWS's own African data centre investments, AWS's presence in Kenya is growing, opening the door to local jobs supporting the same cloud that runs apps you already use.",
    },
    "Meet the Core AWS Services": {
        "fact": "Amazon S3 was one of the very first AWS services ever launched, back in 2006, and it now stores trillions of objects worldwide.",
        "real_world": "Kenyan start-ups building delivery apps, fintech products, and e-learning platforms often rely on exactly these four services - S3, EC2, Lambda, and RDS - as their technical foundation.",
    },
    "Your AWS Educate Account Tour": {
        "fact": "Digital badges like the ones AWS Educate awards are built on an open standard, so they can be verified and shared on professional profiles like LinkedIn.",
        "real_world": "Kenyan students have used AWS Educate badges in university and scholarship applications as real evidence of hands-on cloud skills, not just classroom theory.",
    },
    "Storing Files in the Cloud with Amazon S3": {
        "fact": "Amazon S3 is designed to be so reliable that if you stored 10 million files, you'd statistically expect to lose less than one over 10,000 years.",
        "real_world": "Kenyan photographers, journalists, and small businesses increasingly back up important files to S3-style cloud storage so a lost or stolen laptop doesn't mean losing everything.",
    },
    "Building Your First Website with AWS": {
        "fact": "Thousands of personal portfolios and student projects are hosted directly from S3 buckets because it's one of the cheapest ways to put a website online.",
        "real_world": "A Kenyan student who hosts a project this way can share a real, live link in university or AWS re/Start applications instead of just a screenshot.",
    },
    "AWS re/Start & Your Future in Cloud Careers": {
        "fact": "AWS re/Start graduates around the world have gone on to roles like cloud support associate, junior developer, and IT technician - often with no prior tech degree required.",
        "real_world": "AWS re/Start already runs in African countries through partners like AmaliTech, meaning the pathway in this lesson is a real, current route for Kenyan youth into tech careers.",
    },
    "Databases 101": {
        "fact": "SQL, the language used to query most databases, has existed since the 1970s and remains one of the most widely used programming languages in the world today.",
        "real_world": "Kenyan school management systems, hospital records, and mobile money platforms all rely on structured databases just like the one you designed in this lesson.",
    },
    "Designing a Simple Web App": {
        "fact": "Big streaming and shopping apps make billions of API calls between frontend, backend and database systems every single day to keep everything running smoothly.",
        "real_world": "Kenyan fintech and e-commerce apps, from ride-hailing services to online shops, are all built on this same three-layer frontend / backend / database pattern.",
    },
    "Deploying to the Cloud": {
        "fact": "Modern cloud deployment tools can publish a code update to a live production server in seconds - a process that used to take engineers hours or even days.",
        "real_world": "Kenyan software teams, including government digital service projects, deploy updates to the cloud several times a week, letting them fix problems and add features quickly.",
    },
    "What Is Cloud AI?": {
        "fact": "Many everyday tools you already use - spam filters, voice assistants, photo-tagging apps - are powered by managed cloud AI services working quietly in the background.",
        "real_world": "Kenyan agri-tech and health-tech start-ups use cloud AI to do things like spot crop diseases from photos or screen medical images, often raising exactly the ethical questions this lesson asks you to consider.",
    },
    "Trying a Managed AI Service": {
        "fact": "A single AI image-recognition API call can compare a photo against patterns learned from millions of training images, and return a result in well under a second.",
        "real_world": "Kenyan developers building apps for agriculture or healthcare often start by testing a free-tier managed AI service, exactly like you did in this lesson, before building anything custom.",
    },
    "Choosing Your Capstone Project": {
        "fact": "Famous products like Instagram and Twitter both began life as much smaller, simpler MVPs that their creators built in just weeks before growing them.",
        "real_world": "Kenyan hackathon teams at events like Pitch Night or Safaricom's competitions are judged heavily on exactly this skill - scoping a clear, achievable MVP rather than promising to build everything at once.",
    },
    "Building Your Capstone": {
        "fact": "Professional software teams almost never build a whole product in one go - they work in sprints usually lasting one to four weeks, then review and adjust.",
        "real_world": "Kenyan tech companies and government digital projects use the same sprint-and-documentation approach you're practising here to manage real, large-scale software projects.",
    },
    "Presenting Your Portfolio": {
        "fact": "Recruiters often spend less than a minute on a first look at a portfolio - exactly why a clear, confident pitch matters as much as the work itself.",
        "real_world": "AWS re/Start and university Computer Science admissions in Kenya increasingly ask applicants to present a portfolio and pitch just like the one you're building in this capstone.",
    },
}


def _lesson(title, summary, objectives, big_idea, activity, vocab, quiz, quiz_answer, visual, caption, tone="fun"):
    """Build a full, visual, interactive lesson record - enough reading, illustration
    and self-check material to comfortably fill a 30-minute session."""
    extras = LESSON_EXTRAS.get(title, {})
    fact = extras.get(
        "fact",
        "Cloud computing concepts like this one are used by real companies and governments every single day, all around the world.",
    )
    real_world = extras.get(
        "real_world",
        "Learners across Kenya are building exactly these skills right now, as part of the push to grow a cloud-ready generation.",
    )

    obj_items = "".join(f"<li>{o}</li>" for o in objectives)
    vocab_items = "".join(
        f'<details class="vocab-card"><summary>{term}</summary><p>{definition}</p></details>'
        for term, definition in vocab
    )
    concept_chips = _concept_chips(vocab, tone)
    practice_mcqs = _vocab_mcqs(vocab, 2 if len(vocab) >= 4 else 1)

    box_emoji_fact = "" if tone == "pro" else "\U0001F4A1"
    box_emoji_real = "" if tone == "pro" else "\U0001F30D"

    if tone == "pro":
        head_learn = "Objectives"
        head_idea = "Concept Overview"
        head_fact = "Worth Knowing:"
        head_try = "Hands-On Task"
        head_real = "Where This Shows Up:"
        head_word = "Key Terms"
        head_picture = "Concept Map"
        head_check = "Check Your Understanding"
        head_quiz = "Quiz Time"
        hint = ""
    else:
        head_learn = "\U0001F3AF What You'll Learn"
        head_idea = "\U0001F9E0 The Big Idea"
        head_fact = "Did You Know?"
        head_try = "\U0001F6E0\uFE0F Try It Yourself"
        head_real = "Real-World Connection:"
        head_word = "\U0001F4DA Word Bank"
        head_picture = "\U0001F5BC\uFE0F Picture the Ideas"
        head_check = "\u2705 Quick Check"
        head_quiz = "\U0001F4DD Quiz Time"
        hint = '<span class="hint-text">(tap a card to flip)</span>'

    content = f"""<div class="lesson-content tone-{tone}">
  <div class="lesson-visual">
    {visual}
    <p class="visual-caption">{caption}</p>
  </div>

  <div class="lesson-section">
    <h5 class="section-head">{head_learn}</h5>
    <ul class="objective-list">{obj_items}</ul>
  </div>

  <div class="lesson-section">
    <h5 class="section-head">{head_idea}</h5>
    <p>{big_idea}</p>
  </div>

  <div class="lesson-section fact-box">
    <span class="box-emoji">{box_emoji_fact}</span>
    <p><strong>{head_fact}</strong> {fact}</p>
  </div>

  <div class="lesson-section activity-card">
    <h5 class="section-head">{head_try}</h5>
    <p>{activity}</p>
  </div>

  <div class="lesson-section realworld-box">
    <span class="box-emoji">{box_emoji_real}</span>
    <p><strong>{head_real}</strong> {real_world}</p>
  </div>

  <div class="lesson-section">
    <h5 class="section-head">{head_word} {hint}</h5>
    <div class="vocab-grid">{vocab_items}</div>
  </div>

  <div class="lesson-section">
    <h5 class="section-head">{head_picture}</h5>
    <div class="illustration-grid">{concept_chips}</div>
  </div>

  <div class="lesson-section quiz-card">
    <h5 class="section-head">{head_check}</h5>
    <p>{quiz}</p>
    <details class="quiz-reveal">
      <summary>Reveal a model answer</summary>
      <p>{quiz_answer}</p>
    </details>
  </div>

  <div class="lesson-section">
    <h5 class="section-head">{head_quiz}</h5>
    <div class="mcq-block">{practice_mcqs}</div>
  </div>
</div>"""
    return {
        "title": title,
        "summary": summary,
        "content": content,
        "duration_minutes": 30,
        "lesson_type": "lesson",
        "pass_score_percent": 70,
        "_vocab": vocab,
        "_tone": tone,
    }


# ---------------------------------------------------------------------------
# Module exam builder: assembles one full, multi-question exam per course
# out of the Word Bank terms from every lesson in that course. This runs
# automatically after TIERS is built below, so none of the course/lesson
# data above needs to change shape.
# ---------------------------------------------------------------------------

def _build_exam(course_title, lessons):
    tone = lessons[0].get("_tone", "fun") if lessons else "fun"
    questions_per_lesson = max(2, math.ceil(10 / max(len(lessons), 1)))

    question_blocks = []
    for lesson in lessons:
        vocab = lesson.get("_vocab", [])
        question_blocks.append(_vocab_mcqs(vocab, questions_per_lesson))
    all_questions_html = "".join(question_blocks)
    total_questions = sum(min(questions_per_lesson, len(l.get("_vocab", []))) for l in lessons)
    total_questions = max(total_questions, 1)
    pass_score = 70
    duration = max(15, total_questions * 2)

    if tone == "pro":
        intro = (
            f"<p>This is the full module exam for <strong>{course_title}</strong>. It draws one or more "
            f"questions from every lesson in this module. Answer every question, then submit to see your "
            f"score - you'll need {pass_score}% to pass. You can retake it as many times as you like.</p>"
        )
        label = "Full Module Exam"
        submit_label = "Submit Exam"
    else:
        intro = (
            f"<p>\U0001F393 You've made it to the end of <strong>{course_title}</strong>! This exam checks "
            f"everything you learned across every lesson in this module. Answer all {total_questions} "
            f"questions, then tap <strong>Submit Exam</strong> to see your score. You'll need "
            f"{pass_score}% to pass - and you can always try again if you don't make it the first time.</p>"
        )
        label = "\U0001F393 Full Module Exam"
        submit_label = "\U0001F4CB Submit Exam & See My Score"

    content = f"""<div class="lesson-content tone-{tone}">
  <div class="exam-wrap">
    {intro}
    <div class="exam-form" data-pass="{pass_score}">
      <div class="exam-progress-wrap">
        <div class="exam-progress-track"><div class="exam-progress-bar"></div></div>
        <span class="exam-progress-label">Answered 0 of {total_questions}</span>
      </div>
      <div class="mcq-block">{all_questions_html}</div>
      <div class="exam-submit-row">
        <button type="button" class="exam-submit-btn btn btn-cloud btn-lg">{submit_label}</button>
      </div>
      <div class="exam-result"></div>
    </div>
  </div>
</div>"""

    return {
        "title": f"{label}: {course_title}",
        "summary": f"The full exam for this module, covering every lesson in {course_title}. Pass with {pass_score}% to complete it.",
        "content": content,
        "duration_minutes": duration,
        "lesson_type": "exam",
        "pass_score_percent": pass_score,
        "_vocab": [],
        "_tone": tone,
    }


TIERS = [
    {
        "name": "Foundational",
        "grade_range": "Grade 4-6",
        "cbc_alignment": "Digital Literacy (Core Competency) & Pre-Technical Studies",
        "summary": "Unplugged, hands-on intro to how data, storage, and the cloud actually work.",
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
                    _lesson(
                        "Where Does Your Data Live?",
                        "An unplugged game that shows what a computer, a server and 'the cloud' actually are.",
                        [
                            "Tell the difference between a device, a server, and 'the cloud'",
                            "Describe what really happens when you save a photo or a game score",
                        ],
                        (
                            "'The cloud' isn't floating in the sky! It's actually thousands of powerful "
                            "computers called servers, sitting in huge buildings called data centres all "
                            "over the world. When you save a photo in an app, your device sends that photo "
                            "over the internet to one of those servers, which keeps a safe copy for you. "
                            "'Cloud computing' just means borrowing someone else's computer power and "
                            "storage space instead of only using what's on your own device."
                        ),
                        (
                            "Play 'Pass the Data Parcel': make three paper signs - 'My Tablet', "
                            "'The Internet', and 'A Server in a Data Centre'. Stand in a line holding the "
                            "signs. Pass a small parcel (your 'data') from 'My Tablet' through 'The "
                            "Internet' to the 'Server', then have the Server pass back a 'Saved!' note. "
                            "Time how long the relay takes and talk about what could slow it down (a "
                            "wobbly connection, a far-away server)."
                        ),
                        [
                            ("Device", "Any gadget you use directly, like a phone, tablet or laptop"),
                            ("Server", "A powerful computer that stores data and runs programs for many people at once"),
                            ("Data Centre", "A big building full of servers, kept cool and safe"),
                            ("The Cloud", "A nickname for all the servers and data centres you can reach over the internet"),
                        ],
                        "If you save a photo in a cloud app, is it really floating in the sky? Where is it actually kept, and how did it get there?",
                        "It's saved as data on a real server inside a data centre - maybe thousands of kilometres away. The internet just makes the trip feel instant.",
                        _svg(
                            _bg(),
                            _icon(48, 62, 38, "\U0001F4F1"), _label(48, 100, "My Device", 10),
                            _arrow(118, 62),
                            _icon(150, 62, 40, "\U0001F310"), _label(150, 100, "Internet", 10),
                            _arrow(182, 62),
                            _icon(254, 62, 44, "\U0001F5A5\uFE0F"), _label(254, 103, "Server", 10),
                        ),
                        "Your photo travels from your device, through the internet, to a server far away.",
                    ),
                    _lesson(
                        "Networks & the Internet",
                        "Building a paper 'network' to understand how devices talk to each other.",
                        [
                            "Explain what a network is using a real-world example",
                            "Describe how the internet connects millions of smaller networks together",
                        ],
                        (
                            "A network is just a group of devices that can talk to each other - like a "
                            "classroom where everyone can pass notes. A router is the helper in the middle "
                            "that makes sure each note goes to the right person. The internet is the "
                            "biggest network of all: millions of smaller networks (homes, schools, "
                            "businesses) all connected together, so a message from Nairobi can reach a "
                            "server in another country in a fraction of a second."
                        ),
                        (
                            "Build a 'Paper Network': draw 5-6 houses on paper, each representing a "
                            "device, and place one 'router' card in the middle. Connect every house to the "
                            "router with string or yarn. Write a short message on a slip of paper and pass "
                            "it from one house to the router, and have the router hand it to the right "
                            "house. Then try connecting two separate paper networks with a single string - "
                            "that's like two schools joining the internet."
                        ),
                        [
                            ("Network", "A group of connected devices that can share information"),
                            ("Router", "A device that directs information to the correct place on a network"),
                            ("Internet", "A huge network made up of millions of smaller networks worldwide"),
                            ("IP Address", "A device's unique 'home address' on a network"),
                        ],
                        "Why does a message need a router instead of just being shouted to every device at once?",
                        "If every device shouted at once, messages would get lost or jumbled. A router checks each message's address and sends it only where it needs to go.",
                        _svg(
                            _bg(),
                            _icon(150, 40, 30, "\U0001F4E1"), _label(150, 68, "Router", 10),
                            _line(150, 50, 65, 92), _line(150, 50, 150, 92), _line(150, 50, 235, 92),
                            _icon(65, 108, 24, "\U0001F4BB"), _icon(150, 108, 24, "\U0001F4BB"), _icon(235, 108, 24, "\U0001F4BB"),
                        ),
                        "A router connects many devices into one network - the internet connects networks together.",
                    ),
                    _lesson(
                        "Data & Storage Basics",
                        "Sorting, saving and organising information the way computers do.",
                        [
                            "Explain what 'data' means in simple terms",
                            "Organise information into files and folders the way a computer does",
                        ],
                        (
                            "Data is just organised information - names, numbers, photos, even your "
                            "favourite game's high score. Deep inside, computers store everything as tiny "
                            "switches that are either on or off, which we write as 1s and 0s (a bit). "
                            "Group enough bits together and you get a byte, enough to store one letter. "
                            "Computers keep data tidy using files (a single saved item) stored inside "
                            "folders (containers that group related files), just like a filing cabinet."
                        ),
                        (
                            "Give each learner 12 colourful cards with different pictures or words on "
                            "them (animals, foods, numbers). Ask them to sort the cards into folders "
                            "(envelopes) by category, then label each envelope. Compare results as a class "
                            "- notice there are multiple 'correct' ways to organise the same data, just "
                            "like people name their computer folders differently."
                        ),
                        [
                            ("Data", "Information that can be stored and used by a computer"),
                            ("Bit", "The smallest piece of computer information: a 1 or a 0"),
                            ("File", "A single saved piece of information, like a photo or document"),
                            ("Folder", "A container used to group and organise related files"),
                        ],
                        "If a computer only understands 1s and 0s, how can it store something as colourful as a photo?",
                        "Computers turn colours, letters and sounds into numbers first, then store those numbers as patterns of 1s and 0s - and turn them back into colour when you view the photo.",
                        _svg(
                            _bg(),
                            _icon(60, 55, 28, "\U0001F5C2\uFE0F"), _icon(150, 55, 28, "\U0001F5C2\uFE0F"), _icon(240, 55, 28, "\U0001F5C2\uFE0F"),
                            _label(60, 92, "Animals", 10), _label(150, 92, "Numbers", 10), _label(240, 92, "Colours", 10),
                            _icon(150, 118, 22, "\U0001F500"),
                        ),
                        "Sorting cards into folders is just like how a computer organises files.",
                    ),
                    _lesson(
                        "Being Safe and Kind Online",
                        "Digital citizenship basics: passwords, privacy, and kindness online.",
                        [
                            "Create a password that is both strong and memorable",
                            "Describe at least three rules for staying safe and kind online",
                        ],
                        (
                            "Being online is a lot like being in a busy public place: you want to stay "
                            "safe and treat others well. A strong password is like a good lock - long, "
                            "unique, and not something others can guess (not your pet's name!). Privacy "
                            "means thinking before you share personal details like your address or school. "
                            "And being a good digital citizen means being kind in comments and chats, "
                            "because real people are on the other side of the screen."
                        ),
                        (
                            "Play the 'Password Strength Game': in pairs, write three passwords - one "
                            "weak ('12345'), one medium, and one strong (a silly four-word phrase like "
                            "'PurpleMangoJumps42'). Rank them from weakest to strongest and explain why. "
                            "Then role-play two short online chat scenarios, one kind and one unkind, and "
                            "discuss how each would feel to receive."
                        ),
                        [
                            ("Password", "A secret code that proves it's really you logging in"),
                            ("Privacy", "Keeping personal information to yourself and trusted people"),
                            ("Digital Citizen", "Someone who acts responsibly and kindly online"),
                            ("Cyberbullying", "Using the internet to repeatedly hurt or embarrass someone"),
                        ],
                        "Why is 'PurpleMangoJumps42' a stronger password than your dog's name?",
                        "A short, common password like a pet's name can be guessed quickly, while a long, unusual phrase takes far too long for guessing tools to crack.",
                        _svg(
                            _bg(),
                            _icon(88, 58, 40, "\U0001F511"), _label(88, 100, "Strong Password", 10),
                            _icon(212, 58, 40, "\U0001F4AC"), _label(212, 100, "Kind Words", 10),
                        ),
                        "A strong password and kind words both help keep the internet safer.",
                    ),
                ],
            },
            {
                "title": "My First Digital Projects",
                "summary": "Simple, low-tech creative projects that build comfort with digital tools.",
                "icon": "\U0001F3A8",
                "lessons": [
                    _lesson(
                        "Typing & Files 101",
                        "Creating, naming, and saving your first digital files.",
                        [
                            "Create, name, and save a digital file in a sensible place",
                            "Explain what a file extension tells you",
                        ],
                        (
                            "Every digital file has a name and usually a short tag at the end called a "
                            "file extension (like .txt or .jpg) that tells the computer what kind of file "
                            "it is and which app should open it. Good file names are clear and specific - "
                            "'MyStoryDraft1.txt' is much more useful than 'Untitled2'. Saving a file into a "
                            "sensibly named folder means you (and your future self!) can find it again in "
                            "seconds."
                        ),
                        (
                            "Open a simple text editor. Type a two-sentence description of your favourite "
                            "animal. Save the file with a clear name inside a folder called 'My Cloud for "
                            "Kids Projects'. Close the app, then practise finding and reopening the file "
                            "without help."
                        ),
                        [
                            ("File", "A single saved piece of digital work"),
                            ("Save", "Storing your work so it isn't lost when you close the app"),
                            ("Folder", "A place used to group related files together"),
                            ("File Extension", "The short tag at the end of a filename that shows its type"),
                        ],
                        "You save two files called 'homework' and 'Homework_Maths_Oct3.txt'. Which one will be easier to find in six months, and why?",
                        "'Homework_Maths_Oct3.txt' - it tells you exactly what the file is and when it was made, even months later.",
                        _svg(
                            _bg(),
                            _icon(88, 62, 38, "\u2328\uFE0F"), _label(88, 102, "Type", 10),
                            _arrow(150, 62),
                            _icon(212, 62, 38, "\U0001F5C3\uFE0F"), _label(212, 102, "Save & Name", 10),
                        ),
                        "Typing, naming, and saving are the first steps in any digital project.",
                    ),
                    _lesson(
                        "Intro to Scratch",
                        "Making a simple animation or game with block-based coding.",
                        [
                            "Snap together coding blocks to build a sequence of actions",
                            "Use a loop block to repeat an action automatically",
                        ],
                        (
                            "Scratch lets you build programs by snapping together colourful blocks instead "
                            "of typing text - each block is one instruction, like 'move 10 steps' or 'say "
                            "Hello!'. Put blocks in order (a sequence) and the computer follows them one by "
                            "one, just like a recipe. A loop block repeats a group of instructions "
                            "automatically, so your character can dance or bounce without you clicking "
                            "again and again."
                        ),
                        (
                            "Open Scratch (scratch.mit.edu) and pick a sprite. Use movement and 'say' "
                            "blocks to make it move and greet the viewer. Then wrap a 'repeat 10' loop "
                            "around a move block so your sprite bounces back and forth across the stage."
                        ),
                        [
                            ("Block", "A single snap-together instruction in Scratch"),
                            ("Sprite", "A character or object you can program in Scratch"),
                            ("Sequence", "A set of instructions carried out in order"),
                            ("Loop", "A block that repeats instructions automatically"),
                        ],
                        "What would happen to your sprite if you put the 'repeat' loop around the wrong blocks?",
                        "It might repeat forever, repeat too few or too many times, or repeat an action you didn't mean to repeat - always check exactly what's inside the loop.",
                        _svg(
                            _bg(),
                            _box(38, 38, 55, 22, SKY, SKY_DARK), _box(38, 66, 55, 22, GRASS, SKY_DARK), _box(38, 94, 55, 22, SUN, SKY_DARK),
                            _icon(225, 70, 48, "\U0001F431"), _label(225, 112, "Sprite", 10),
                        ),
                        "Scratch blocks snap together like puzzle pieces to build a program.",
                    ),
                    _lesson(
                        "Show What You Know",
                        "A mini show-and-tell project presenting what 'the cloud' means to you.",
                        [
                            "Summarise the big cloud computing ideas learned so far in your own words",
                            "Present a short project clearly to an audience",
                        ],
                        (
                            "Being able to explain an idea to someone else - in your own words, with your "
                            "own examples - is one of the best signs you truly understand it. A good "
                            "presentation doesn't need fancy slides: a clear poster, a Scratch project, or "
                            "even a short skit can explain 'what is the cloud' just as well, as long as it "
                            "has a beginning (what it is), a middle (an example), and an end (why it "
                            "matters)."
                        ),
                        (
                            "Choose one format: a poster, a one-minute Scratch animation, or a short "
                            "skit. Explain in your own words what 'the cloud' is, give one everyday example "
                            "(like saving a photo or playing an online game), and say why knowing this is "
                            "useful. Present it to family, classmates, or record it to share."
                        ),
                        [
                            ("Presentation", "Sharing information clearly with an audience"),
                            ("Audience", "The people watching or listening to your presentation"),
                            ("Showcase", "An event or moment where work is shown off"),
                        ],
                        "What is the one sentence you would use to explain 'the cloud' to a grandparent who has never used the internet?",
                        "There's no single right answer - a good one is short and uses an everyday example, like 'it's borrowing someone else's powerful computer to save and run things.'",
                        _svg(
                            _bg(),
                            _icon(150, 55, 48, "\U0001F5BC\uFE0F"), _label(150, 98, "Present & Share", 10),
                            _icon(68, 100, 22, "\u2B50"), _icon(232, 100, 22, "\u2B50"),
                        ),
                        "Explaining an idea in your own words proves you really understand it.",
                    ),
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
                    _lesson(
                        "From Scratch to Python",
                        "Bridging visual coding to text-based Python programming.",
                        [
                            "Compare a Scratch block to its equivalent line of Python code",
                            "Write and run a first Python program using print statements",
                        ],
                        (
                            "Python does the same jobs as Scratch blocks, just written as short lines of "
                            "text instead of snapped-together shapes. A Scratch 'say Hello!' block becomes "
                            "'print(\"Hello!\")' in Python. You write Python code inside a programme called "
                            "an IDE (Integrated Development Environment), which also catches mistakes in "
                            "your syntax - the exact spelling and punctuation rules Python needs to "
                            "understand your instructions."
                        ),
                        (
                            "Open a beginner-friendly IDE (like Thonny, or an online one such as "
                            "replit.com). Recreate three Scratch blocks you used before as Python lines: a "
                            "greeting, a maths calculation, and a repeated message using a loop. Run the "
                            "program and fix any error messages you see."
                        ),
                        [
                            ("Python", "A popular text-based programming language"),
                            ("Syntax", "The exact spelling and punctuation rules of a programming language"),
                            ("IDE", "A programme used to write, run, and debug code"),
                            ("Print statement", "A Python instruction that displays text or values on screen"),
                        ],
                        "What is the Python equivalent of a Scratch 'say Hello!' block?",
                        'print("Hello!") is the Python equivalent of a Scratch "say Hello!" block.',
                        _svg(
                            _bg(),
                            _box(35, 48, 70, 42, SKY, SKY_DARK), _label(70, 73, "Blocks", 11, "#fff"),
                            _arrow(150, 68),
                            _box(190, 48, 80, 42, "#1F2937", "#1F2937"), _label(230, 73, "print()", 11, SUN),
                        ),
                        "The same instruction can be a Scratch block or a line of Python code.",
                    ),
                    _lesson(
                        "Variables & Loops",
                        "Core programming concepts through short, fun Python exercises.",
                        [
                            "Store and update a value using a variable",
                            "Use a for loop and a while loop to repeat actions",
                        ],
                        (
                            "A variable is a labelled box that stores a value your program can use and "
                            "change, like 'score = 0'. Loops let you repeat instructions without copying "
                            "and pasting code: a for loop repeats a set number of times (great for 'do this "
                            "10 times'), while a while loop repeats until a condition becomes false (great "
                            "for 'keep going until the player quits')."
                        ),
                        (
                            "Write a Python program with a variable called score starting at 0. Use a for "
                            "loop to add 1 to the score five times, printing the score each time. Then "
                            "write a separate while loop that keeps asking 'Play again? (yes/no)' until the "
                            "player types 'no'."
                        ),
                        [
                            ("Variable", "A named container that stores a value a program can change"),
                            ("For loop", "A loop that repeats a set number of times"),
                            ("While loop", "A loop that repeats until a condition is no longer true"),
                        ],
                        "Why would a while loop be a better choice than a for loop for 'keep going until the player quits'?",
                        "A while loop keeps going until a condition changes (like the player typing 'no'), while a for loop only knows how to repeat a fixed number of times.",
                        _svg(
                            _bg(),
                            _box(38, 55, 95, 30, "#fff", SKY_DARK), _label(85, 74, "score = 0", 11),
                            _icon(205, 68, 38, "\U0001F501"), _label(205, 110, "Repeat", 10),
                        ),
                        "A variable stores a value, and a loop repeats an action automatically.",
                    ),
                    _lesson(
                        "Building a Simple Program",
                        "Writing a small Python project from start to finish.",
                        [
                            "Plan, write, and test a complete small Python program",
                            "Find and fix a bug using error messages",
                        ],
                        (
                            "Every real program starts as a plan: what should it do, what input does it "
                            "need, and what output should it produce? A classic beginner project is a "
                            "number-guessing game: the computer picks a secret number, the player enters "
                            "guesses (input), and the program tells them if they're too high or too low "
                            "(output) until they win. When something breaks, that's called a bug, and "
                            "fixing it is called debugging - reading the error message is always the first "
                            "clue."
                        ),
                        (
                            "Build a number-guessing game in Python: pick a secret number, let the player "
                            "guess using input(), and print 'Too high', 'Too low', or 'You got it!' using "
                            "if/else. Test it with a friend, deliberately break it, then debug the error "
                            "message back to a working program."
                        ),
                        [
                            ("Function", "A named, reusable block of code that performs a task"),
                            ("Input", "Information a program receives, often from a user"),
                            ("Output", "Information a program produces or displays"),
                            ("Debug", "The process of finding and fixing errors in code"),
                        ],
                        "You run your guessing game and get a red error message. What is the very first thing you should do?",
                        "Read the error message carefully - it usually names the exact line and type of mistake, which is the fastest way to start debugging.",
                        _svg(
                            _bg(),
                            _icon(88, 60, 40, "\U0001F3AE"), _label(88, 102, "Guess the Number", 10),
                            _icon(212, 60, 40, "\u2705"), _label(212, 102, "It Works!", 10),
                        ),
                        "Planning input, logic, and output turns an idea into a working program.",
                    ),
                ],
            },
            {
                "title": "Getting Started in the Cloud",
                "summary": "First cloud accounts and first cloud-hosted mini-projects.",
                "icon": "\u2601\ufe0f",
                "lessons": [
                    _lesson(
                        "Setting Up AWS Educate",
                        "Creating and exploring a free AWS Educate learner account.",
                        [
                            "Register for a free AWS Educate account",
                            "Locate credits, courses, and labs inside the AWS Educate dashboard",
                        ],
                        (
                            "AWS Educate is Amazon's free programme for students: anyone aged 13 or older "
                            "can register with just an email address and get access to around $100 in AWS "
                            "credits plus 600+ hours of cloud courses and guided labs - no credit card "
                            "needed. It's the easiest real door into professional cloud computing, and "
                            "it's the same AWS that powers Netflix, NASA, and major projects right here in "
                            "Kenya through partners like Konza Technopolis."
                        ),
                        (
                            "With a parent or teacher's help, go to the AWS Educate registration page and "
                            "sign up with a school or family email address. Once approved, log in and "
                            "explore the dashboard: find your credit balance, the course catalogue, and the "
                            "badges section. Bookmark one course that looks interesting to start next."
                        ),
                        [
                            ("AWS Educate", "Amazon's free cloud learning programme for students aged 13+"),
                            ("Cloud Credits", "Free credit balance you can use to try real cloud services"),
                            ("Free Tier", "A limited amount of cloud usage offered at no cost"),
                            ("Console", "The web dashboard used to manage and explore cloud services"),
                        ],
                        "Roughly how much free credit does a new AWS Educate account start with, and what is the minimum age to register?",
                        "A new AWS Educate account typically starts with about $100 in free credits, and learners can register from age 13 with just an email address.",
                        _svg(
                            _bg(),
                            _icon(88, 60, 42, "\U0001F393"), _label(88, 104, "AWS Educate", 10),
                            _icon(212, 60, 40, "\U0001F4B3"), _label(212, 104, "$100 Credits", 10),
                        ),
                        "AWS Educate gives students free credits and hundreds of hours of real cloud courses.",
                    ),
                    _lesson(
                        "Cloud Storage in Practice",
                        "Uploading, organising and sharing files using real cloud storage.",
                        [
                            "Upload and organise files in a real cloud storage service",
                            "Share a file safely using a link with the correct permissions",
                        ],
                        (
                            "Cloud storage works like the folders you already know, except the files live "
                            "on a server instead of your device, so you can reach them from any device with "
                            "internet access. When you upload a file, you choose permissions - who is "
                            "allowed to see or edit it. Sharing a link publicly means anyone with the link "
                            "can open it, so it's worth thinking carefully before making something public."
                        ),
                        (
                            "Using a cloud storage tool you have access to, create a folder called "
                            "'Cloud for Kids Projects'. Upload three files (a document, an image, and a "
                            "text file), organise them into sub-folders by type, and generate a share link "
                            "for one file set to 'view only' rather than 'can edit'."
                        ),
                        [
                            ("Upload", "Sending a file from your device to the cloud"),
                            ("Cloud Storage", "Space on remote servers used to save your files"),
                            ("Permissions", "Rules that control who can view or edit a shared file"),
                            ("Bucket", "A named cloud storage container (you'll meet this properly in AWS S3)"),
                        ],
                        "Why would you choose 'view only' instead of 'can edit' when sharing a link to your project file?",
                        "'View only' stops anyone from accidentally - or deliberately - changing or deleting your original file, while still letting them see it.",
                        _svg(
                            _bg(),
                            _icon(88, 60, 36, "\U0001F4C1"), _arrow(150, 60), _icon(212, 60, 42, "\u2601\uFE0F"),
                            _label(150, 108, "Upload & Share", 10),
                        ),
                        "Uploading to the cloud means your files live on a server, reachable from anywhere.",
                    ),
                    _lesson(
                        "Your First Hosted Web Page",
                        "Publishing a simple web page using a free cloud hosting tier.",
                        [
                            "Write a basic web page using HTML",
                            "Publish that page online using a free cloud hosting tier",
                        ],
                        (
                            "HTML is the language used to structure a web page - headings, paragraphs, "
                            "and images. Writing HTML on your own computer only shows the page to you; "
                            "hosting means putting those files on a server that's connected to the internet "
                            "24/7, so anyone with the link can view your page. Deploying is the act of "
                            "publishing your latest version live, and your page's address is its domain."
                        ),
                        (
                            "Write a simple HTML page with your name, a heading, and one paragraph about "
                            "your favourite cloud computing fact. Using a free hosting tier (such as GitHub "
                            "Pages), deploy the page and open the live link on a different device to prove "
                            "it's really online."
                        ),
                        [
                            ("HTML", "The language used to structure the content of a web page"),
                            ("Hosting", "Storing website files on a server that's always connected to the internet"),
                            ("Deploy", "Publishing your latest version of a project live"),
                            ("Domain", "The web address people type to reach your site"),
                        ],
                        "What's the difference between writing an HTML file on your laptop and actually 'hosting' it?",
                        "Writing the file only shows it to you on your own computer. Hosting puts it on a server connected to the internet, so anyone with the link can view it.",
                        _svg(
                            _bg(),
                            _box(65, 35, 170, 65, "#fff", SKY_DARK), _label(150, 55, "yoursite.com", 10),
                            _icon(150, 82, 28, "\U0001F30D"),
                        ),
                        "Hosting puts your web page on a server that's online and reachable 24/7.",
                    ),
                    _lesson(
                        "Intro to Google Cloud Skills Boost",
                        "Exploring guided, hands-on labs in a real cloud console.",
                        [
                            "Complete a guided lab inside Google Cloud Skills Boost",
                            "Compare what you notice between the AWS and Google Cloud consoles",
                        ],
                        (
                            "Google Cloud Skills Boost offers free, step-by-step guided labs that give you "
                            "a temporary real cloud account to practise in, with instructions on one side of "
                            "the screen and the actual cloud console on the other. Trying more than one "
                            "cloud provider - AWS, Google Cloud, Microsoft Azure - helps you notice that "
                            "while the buttons look different, the big ideas (storage, compute, security) "
                            "are the same everywhere, which is called being multi-cloud aware."
                        ),
                        (
                            "Open Google Cloud Skills Boost and start an introductory guided lab (many are "
                            "free). Follow the step-by-step instructions to complete one small task in the "
                            "real console, then write down two things that felt similar to AWS Educate and "
                            "one thing that felt different."
                        ),
                        [
                            ("Guided Lab", "A step-by-step, hands-on exercise inside a real cloud console"),
                            ("Cloud Console", "The web-based control panel for managing cloud resources"),
                            ("Multi-Cloud", "Being comfortable working across more than one cloud provider"),
                        ],
                        "Name one thing that felt the same between AWS Educate and Google Cloud Skills Boost, and one thing that felt different.",
                        "Both use a web console with guided, hands-on labs - but the menus, service names, and visual design differ between AWS and Google Cloud.",
                        _svg(
                            _bg(),
                            _box(45, 42, 90, 50, SKY, SKY_DARK), _label(90, 71, "AWS", 13, "#fff", "800"),
                            _box(165, 42, 90, 50, SUN, SKY_DARK), _label(210, 71, "GCP", 13, INK, "800"),
                            _icon(150, 115, 22, "\U0001F50D"),
                        ),
                        "Different cloud providers look different, but they solve the same big problems.",
                    ),
                ],
            },
            {
                "title": "AWS for Kids: Explore Amazon's Cloud",
                "summary": "A dedicated, hands-on journey into AWS: what it is, its core services, and your first real projects.",
                "icon": "\U0001F7E0",
                "lessons": [
                    _lesson(
                        "What Is AWS and Why Does It Matter?",
                        "Meet Amazon Web Services and discover how much of the internet quietly runs on it.",
                        [
                            "Explain what AWS is and who created it",
                            "Name real apps, companies, or organisations that run on AWS",
                        ],
                        (
                            "AWS stands for Amazon Web Services - the cloud computing arm of Amazon, "
                            "launched in 2006. Instead of every company buying and maintaining its own "
                            "servers, AWS rents out computing power, storage, and hundreds of other "
                            "services over the internet, the way a power company rents out electricity "
                            "instead of everyone building their own power plant. AWS now powers huge chunks "
                            "of the internet, from streaming services and banks to NASA missions, and it has "
                            "a growing presence in Kenya through initiatives like Konza Technopolis and "
                            "programmes such as AWS Educate and AWS re/Start."
                        ),
                        (
                            "Go on an 'AWS Scavenger Hunt': with a guide's help, research five apps or "
                            "organisations you use or know (for example a streaming app, a bank, or a game) "
                            "and find out whether they run on AWS, Google Cloud, or Microsoft Azure. Make a "
                            "simple table of your findings and share one surprising discovery with the "
                            "group."
                        ),
                        [
                            ("AWS", "Amazon Web Services - Amazon's cloud computing platform"),
                            ("Cloud Provider", "A company that rents out computing power and services over the internet"),
                            ("Data Centre Region", "A geographic location where a cloud provider's data centres are grouped"),
                        ],
                        "Why might a company choose to rent computing power from AWS instead of buying and running its own servers?",
                        "Renting from AWS avoids the huge upfront cost of hardware, comes with automatic maintenance, and lets a company scale up or down instantly as demand changes.",
                        _svg(
                            _bg(AWS_BG),
                            _box(100, 32, 100, 75, AWS_ORANGE, AWS_ORANGE_DARK), _label(150, 76, "AWS", 24, "#fff", "800"),
                            _icon(48, 52, 24, "\U0001F3E6"), _icon(252, 52, 24, "\U0001F3AC"),
                            _icon(48, 98, 24, "\U0001F3E5"), _icon(252, 98, 24, "\U0001F3AE"),
                        ),
                        "AWS quietly powers banks, streaming services, games and more, behind the scenes.",
                    ),
                    _lesson(
                        "Meet the Core AWS Services",
                        "Simple, friendly analogies for the AWS services you'll use most often.",
                        [
                            "Describe S3, EC2, Lambda, and RDS using everyday analogies",
                            "Match each service to the job it's best suited for",
                        ],
                        (
                            "AWS has hundreds of services, but four come up again and again. Amazon S3 is "
                            "like an enormous, endlessly expandable storage box for files. Amazon EC2 is "
                            "like renting a computer by the hour, giving you full control to install "
                            "software and run programs. AWS Lambda is like hiring a tiny helper who wakes "
                            "up, does one small job the instant it's needed, then goes back to sleep - you "
                            "only pay for the moment it worked. Amazon RDS is like a perfectly organised "
                            "filing cabinet (a database) that keeps structured information safe, searchable, "
                            "and tidy."
                        ),
                        (
                            "Play a matching game: write S3, EC2, Lambda, and RDS on four cards, and write "
                            "their analogies ('storage box', 'rent-a-computer', 'tiny on-demand helper', "
                            "'organised filing cabinet') on four more. Shuffle and match them, then come up "
                            "with your own one-sentence analogy for each service."
                        ),
                        [
                            ("Amazon S3", "Simple Storage Service - cloud storage for files of almost any size"),
                            ("Amazon EC2", "Elastic Compute Cloud - a rentable virtual computer in the cloud"),
                            ("AWS Lambda", "A service that runs small pieces of code automatically, on demand"),
                            ("Amazon RDS", "Relational Database Service - a managed, organised cloud database"),
                        ],
                        "Which AWS service would you use to store 1,000 photos, and which would you use to run a program that reacts instantly whenever someone uploads one?",
                        "Amazon S3 would store the 1,000 photos, and AWS Lambda would be the tiny helper that reacts instantly whenever a new photo is uploaded.",
                        _svg(
                            _bg(AWS_BG),
                            _box(32, 28, 112, 42, "#fff", AWS_ORANGE), _label(88, 53, "S3", 13, AWS_ORANGE_DARK, "800"),
                            _box(156, 28, 112, 42, "#fff", AWS_ORANGE), _label(212, 53, "EC2", 13, AWS_ORANGE_DARK, "800"),
                            _box(32, 80, 112, 42, "#fff", AWS_ORANGE), _label(88, 105, "Lambda", 13, AWS_ORANGE_DARK, "800"),
                            _box(156, 80, 112, 42, "#fff", AWS_ORANGE), _label(212, 105, "RDS", 13, AWS_ORANGE_DARK, "800"),
                        ),
                        "Four AWS services you'll meet again and again: S3, EC2, Lambda, and RDS.",
                    ),
                    _lesson(
                        "Your AWS Educate Account Tour",
                        "Go deeper into your AWS Educate dashboard: labs, badges, and your credit balance.",
                        [
                            "Find and start a beginner lab from the AWS Educate catalogue",
                            "Earn your first AWS Educate badge",
                        ],
                        (
                            "Your AWS Educate dashboard is more than a sign-up page - it's a learning hub. "
                            "The lab catalogue lists hundreds of guided, hands-on exercises sorted by topic "
                            "and difficulty. As you complete courses and labs, you earn digital badges that "
                            "prove specific skills, and you can keep an eye on your credits balance, the "
                            "free usage AWS has given you to practise with real cloud services safely."
                        ),
                        (
                            "Log in to your AWS Educate account (from the earlier 'Setting Up AWS Educate' "
                            "lesson). Open the lab catalogue, filter for 'beginner', and complete one short "
                            "guided lab start to finish. Keep a one-paragraph journal of what the lab asked "
                            "you to do and what you learned, then check whether a new badge appeared on your "
                            "profile."
                        ),
                        [
                            ("Lab Catalogue", "The searchable list of guided, hands-on exercises in AWS Educate"),
                            ("Badge", "A digital credential that shows you've completed specific AWS skills"),
                            ("Credits Balance", "The amount of free AWS usage still available on your account"),
                        ],
                        "What is one way you can tell AWS Educate that you've finished learning a skill, besides just remembering it yourself?",
                        "Completing courses and labs earns you digital badges on your AWS Educate profile - visible, shareable proof of the skills you've learned.",
                        _svg(
                            _bg(AWS_BG),
                            _box(58, 32, 184, 55, "#fff", AWS_ORANGE), _label(150, 54, "Lab Catalogue", 11),
                            _icon(150, 78, 22, "\U0001F3C6"), _label(150, 115, "Earn Your First Badge", 10),
                        ),
                        "Your AWS Educate dashboard tracks labs completed, badges earned, and credits remaining.",
                    ),
                    _lesson(
                        "Storing Files in the Cloud with Amazon S3",
                        "Create your own S3 bucket and upload your first file to the real cloud.",
                        [
                            "Create an Amazon S3 bucket inside a safe sandbox account",
                            "Upload a file and understand the difference between public and private access",
                        ],
                        (
                            "In Amazon S3, a bucket is a named container that holds your files, called "
                            "objects. Every bucket needs a globally unique name, a bit like a username that "
                            "nobody else in the world can use. When you upload an object, you choose its "
                            "permissions: private means only you (and anyone you specifically allow) can see "
                            "it, while public means anyone on the internet with the link can view it - which "
                            "is powerful, but something to decide on carefully and never by accident."
                        ),
                        (
                            "Inside your AWS Educate sandbox account, create an S3 bucket with a unique "
                            "name (try yourname-cloudforkids-2026). Upload one image or text file as an "
                            "object. Check its permissions, keep it private, and explain in your own words "
                            "what would change if you made it public instead."
                        ),
                        [
                            ("Bucket", "A named container in Amazon S3 that holds your files"),
                            ("Object", "A single file stored inside an S3 bucket"),
                            ("Public Access", "A setting that allows anyone with the link to view a file"),
                            ("Permissions", "Rules that control who can view, upload, or change files"),
                        ],
                        "If you accidentally set your bucket to 'public' instead of 'private', who could suddenly see your files?",
                        "Anyone on the internet with the link could view your files - which is why it's important to double-check permissions before making anything public.",
                        _svg(
                            _bg(AWS_BG),
                            _icon(150, 52, 46, "\U0001FAA3"), _label(150, 96, "Your S3 Bucket", 11),
                            _icon(78, 98, 22, "\U0001F512"), _icon(222, 98, 22, "\U0001F30D"),
                        ),
                        "An S3 bucket is your own named storage container in the cloud.",
                    ),
                    _lesson(
                        "Building Your First Website with AWS",
                        "Turn an S3 bucket into a real, live website address anyone can visit.",
                        [
                            "Enable static website hosting on an S3 bucket",
                            "Visit your own project's live AWS endpoint URL",
                        ],
                        (
                            "A static website is one made of fixed HTML, CSS, and image files that don't "
                            "need a database or server-side program to display - perfect for a personal page "
                            "or portfolio. Amazon S3 can host a static website directly from a bucket: flip "
                            "on 'static website hosting', upload your HTML file as the index page, and AWS "
                            "gives you an endpoint URL where the world can see it. Tools like AWS Amplify "
                            "make this even easier for bigger projects later on."
                        ),
                        (
                            "Take the HTML page you built in 'Your First Hosted Web Page'. Upload it into a "
                            "new S3 bucket, enable static website hosting, and set your file as the index "
                            "document. Open the generated endpoint URL in a browser to see your page live on "
                            "AWS, and share the link with a classmate."
                        ),
                        [
                            ("Static Website", "A website made of fixed files that don't change based on who's viewing it"),
                            ("AWS Amplify", "An AWS service that makes building and hosting web apps easier"),
                            ("Endpoint URL", "The web address AWS gives you to access your hosted content"),
                        ],
                        "What makes a website 'static', and why is that a good fit for hosting directly from an S3 bucket?",
                        "A static site's files don't change based on who's viewing them, so S3 can simply serve the same HTML, CSS and image files to everyone, with no extra server logic needed.",
                        _svg(
                            _bg(AWS_BG),
                            _box(58, 32, 184, 52, "#fff", AWS_ORANGE), _label(150, 54, "your-bucket.s3-website", 9),
                            _icon(150, 98, 30, "\U0001F680"),
                        ),
                        "Flip one setting, and your S3 bucket becomes a live website address.",
                    ),
                    _lesson(
                        "AWS re/Start & Your Future in Cloud Careers",
                        "See the real pathway from today's lesson to a cloud computing career.",
                        [
                            "Describe what the AWS re/Start programme offers",
                            "Map out your own personal roadmap from school to a cloud career",
                        ],
                        (
                            "AWS re/Start is a free, full-time, around 12-week programme that prepares "
                            "people for entry-level cloud careers - covering Linux, Python, networking, "
                            "security, and databases - and it's already running in African countries through "
                            "partners like AmaliTech, with learners earning a free shot at an AWS "
                            "certification exam by the end. For a Cloud for Kids learner, the pathway can "
                            "look like: AWS Educate now, building real projects through secondary school, "
                            "then AWS re/Start or a university Computer Science track, leading toward "
                            "recognised AWS certifications and a cloud computing job."
                        ),
                        (
                            "Build a 'My Cloud Career Roadmap' on one page with four boxes: (1) What I'm "
                            "learning now in Cloud for Kids, (2) Skills I want to build by the end of "
                            "secondary school, (3) A pathway after school - AWS re/Start, a certification, "
                            "or university, (4) A cloud job that interests me and why. Keep it in your "
                            "portfolio to revisit in the Advanced tier capstone."
                        ),
                        [
                            ("AWS re/Start", "A free, full-time programme preparing people for entry-level cloud careers"),
                            ("AWS Certification", "An official credential proving specific AWS skills to employers"),
                            ("Career Pathway", "A planned sequence of learning and experience leading toward a job"),
                        ],
                        "Name one skill AWS re/Start teaches, and one way Cloud for Kids today is already building toward it.",
                        "AWS re/Start teaches skills like Linux, Python, networking, security and databases - all things Cloud for Kids already introduces a little at a time.",
                        _svg(
                            _bg(AWS_BG),
                            _icon(48, 78, 28, "\U0001F3EB"), _arrow(100, 78),
                            _icon(150, 78, 30, "\u2601\uFE0F"), _arrow(200, 78),
                            _icon(252, 78, 32, "\U0001F4BC"),
                            _label(150, 120, "School \u2192 Cloud Skills \u2192 Career", 9),
                        ),
                        "From today's lessons to AWS Educate to AWS re/Start - a real path into a cloud career.",
                    ),
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
                    _lesson(
                        "Databases 101",
                        "How structured data is stored, queried, and secured in the cloud.",
                        [
                            "Design a simple database table structure",
                            "Write a basic query to retrieve specific data",
                        ],
                        (
                            "A database organises structured data into tables made of rows and columns, "
                            "much like a well-designed spreadsheet - for example a 'Students' table with "
                            "columns for name, grade, and favourite subject. A query is a request you write "
                            "(often in a language called SQL) asking the database a specific question, like "
                            "'show me every student in Grade 10'. Cloud databases such as Amazon RDS also "
                            "add automatic backups and security controls so data stays safe even if "
                            "something goes wrong."
                        ),
                        (
                            "Design a table for a school library: columns for Book Title, Author, and "
                            "Available (yes/no). Fill in five sample rows by hand or in a spreadsheet. Then "
                            "write a plain-English 'query' such as 'show me every book that is available', "
                            "and if you have access to a SQL tool, write the real SELECT statement for it."
                        ),
                        [
                            ("Database", "An organised system for storing structured data"),
                            ("Table", "A database structure organised into rows and columns"),
                            ("Query", "A request asking a database a specific question"),
                            ("SQL", "The common language used to write database queries"),
                        ],
                        "Write the plain-English version of a query that would find every library book that is NOT available.",
                        "SELECT * FROM books WHERE available = 'no' - in plain English: 'show me every book that is not available.'",
                        _svg(
                            _bg(PRO_BG),
                            _box(40, 28, 220, 26, "#fff", PRO_BORDER), _label(150, 46, "id | title | author", 9, PRO_TEXT),
                            _box(40, 58, 220, 22, "#fff", PRO_BORDER_SOFT), _label(150, 73, "1  |  Dune  |  Herbert", 9, PRO_TEXT_SOFT),
                            _box(40, 84, 220, 22, "#fff", PRO_BORDER_SOFT), _label(150, 99, "2  |  Emil  |  Herbert", 9, PRO_TEXT_SOFT),
                            _label(150, 124, "QUERY \u2192 SELECT * FROM books", 9, SKY_DARK, "700"),
                        ),
                        "A database organises structured data into rows and columns you can query.",
                        tone="pro",
                    ),
                    _lesson(
                        "Designing a Simple Web App",
                        "Planning a small web app that reads and writes data.",
                        [
                            "Sketch a basic architecture diagram for a web app",
                            "Explain the difference between frontend, backend, and database",
                        ],
                        (
                            "Most web apps have three layers: the frontend (what users see and click, "
                            "built with HTML/CSS/JavaScript), the backend (the server-side logic that "
                            "processes requests and enforces rules), and the database (where information is "
                            "stored long-term). They talk to each other through an API, a defined set of "
                            "rules for requesting and sending data. Drawing an architecture diagram before "
                            "writing any code helps you spot problems early and explain your idea to others."
                        ),
                        (
                            "Pick a simple app idea (a chore tracker, a class attendance app, a reading "
                            "log). Sketch a one-page architecture diagram with three boxes - frontend, "
                            "backend, database - and arrows labelled with what data flows between them (for "
                            "example, 'save new chore' or 'get today's list'). Present your diagram to a "
                            "partner and defend your choices."
                        ),
                        [
                            ("Frontend", "The part of an app users directly see and interact with"),
                            ("Backend", "The server-side logic that processes requests and rules"),
                            ("API", "A defined set of rules for two systems to exchange data"),
                            ("Architecture Diagram", "A visual map of how a system's parts connect"),
                        ],
                        "In your chore tracker idea, what data would flow from the frontend to the backend when a user marks a chore 'done'?",
                        "The chore's identifier and its new 'done' status would be sent from the frontend to the backend, which would then update that record in the database.",
                        _svg(
                            _bg(PRO_BG),
                            _box(18, 50, 72, 40, "#fff", SKY_DARK), _label(54, 74, "Frontend", 10, PRO_TEXT),
                            _arrow(112, 70, size=18, color=PRO_TEXT_SOFT),
                            _box(130, 50, 72, 40, "#fff", SKY_DARK), _label(166, 74, "Backend", 10, PRO_TEXT),
                            _arrow(222, 70, size=18, color=PRO_TEXT_SOFT),
                            _box(232, 50, 52, 40, "#fff", SKY_DARK), _label(258, 70, "Data", 9, PRO_TEXT), _label(258, 82, "base", 9, PRO_TEXT),
                        ),
                        "A typical web app passes data between a frontend, a backend, and a database.",
                        tone="pro",
                    ),
                    _lesson(
                        "Deploying to the Cloud",
                        "Hosting your project so anyone can access it online.",
                        [
                            "Deploy a small web app to a free-tier cloud host",
                            "Explain what it means to push an app to production",
                        ],
                        (
                            "Deploying means taking code that works on your own computer and publishing "
                            "it on a server that's reachable from anywhere, so your project has a real "
                            "domain or endpoint others can visit. The live, publicly reachable version of "
                            "your app is called production, as opposed to the version you're still testing. "
                            "Many cloud providers offer a free tier generous enough to deploy a small "
                            "student project at no cost, which is exactly how most beginner cloud careers "
                            "start."
                        ),
                        (
                            "Take a small app or web page you've already built in this programme. Deploy "
                            "it to a free-tier cloud host (such as AWS, a static hosting service, or a "
                            "platform your facilitator recommends). Confirm it loads correctly from a "
                            "different device or network, and write down the live link in your portfolio."
                        ),
                        [
                            ("Deploy", "Publishing your code to a server others can access"),
                            ("Production", "The live, publicly reachable version of an application"),
                            ("Server", "A computer that runs continuously to serve requests from users"),
                            ("Domain", "The address people use to reach your hosted project"),
                        ],
                        "What's the difference between an app that 'works on my laptop' and one that's actually 'deployed'?",
                        "An app 'working on your laptop' only runs on your own machine, while a 'deployed' app runs on a server with its own address that anyone online can visit.",
                        _svg(
                            _bg(PRO_BG),
                            _box(28, 45, 72, 50, "#fff", PRO_BORDER), _label(64, 73, "Your Code", 9, PRO_TEXT),
                            _arrow(128, 70, size=20, color=PRO_TEXT_SOFT),
                            _box(148, 35, 104, 70, "#fff", SKY_DARK), _label(200, 65, "Cloud Server", 10, PRO_TEXT),
                            _label(200, 88, "(Production)", 8, PRO_TEXT_SOFT),
                        ),
                        "Deploying moves your project from your own machine onto a server everyone can reach.",
                        tone="pro",
                    ),
                ],
            },
            {
                "title": "AI & Cloud Services",
                "summary": "An introductory look at AI services that run on the cloud.",
                "icon": "\U0001F916",
                "lessons": [
                    _lesson(
                        "What Is Cloud AI?",
                        "A friendly introduction to AI services offered by cloud providers.",
                        [
                            "Explain what a managed AI service is in simple terms",
                            "Identify real-world uses of cloud AI, including ethical considerations",
                        ],
                        (
                            "Cloud providers offer managed AI services - pre-built artificial intelligence "
                            "and machine learning tools you can use through simple requests, without having "
                            "to build or train a model (the trained 'brain' behind an AI system) yourself. "
                            "Examples include recognising objects in photos, transcribing speech to text, or "
                            "powering chatbots. These tools are powerful, but it's worth asking critical "
                            "questions too: is the data being used fairly, could the AI be biased, and who "
                            "is responsible if it makes a mistake?"
                        ),
                        (
                            "Research two or three real cloud AI tools (for example an image recognition "
                            "demo, a translation tool, or a chatbot). For each, write down what it does, "
                            "who might use it, and one ethical question it raises - such as privacy, bias, "
                            "or job impact. Discuss your findings as a group."
                        ),
                        [
                            ("AI", "Artificial Intelligence - systems that perform tasks that normally need human intelligence"),
                            ("Machine Learning", "A way of training computer systems to improve from data and experience"),
                            ("Managed Service", "A ready-to-use cloud tool you don't have to build or maintain yourself"),
                            ("Model", "The trained 'brain' behind an AI system's predictions or decisions"),
                        ],
                        "Name one ethical question worth asking before using a cloud AI tool, like a facial recognition service.",
                        "Worth asking: is the training data biased, is personal data handled responsibly, and who is accountable if the system makes a mistake.",
                        _svg(
                            _bg(PRO_BG),
                            _dot(60, 40), _dot(60, 90), _dot(150, 30), _dot(150, 70), _dot(150, 110), _dot(230, 55), _dot(230, 95),
                            _line(60, 40, 150, 30, PRO_BORDER), _line(60, 40, 150, 70, PRO_BORDER), _line(60, 90, 150, 70, PRO_BORDER), _line(60, 90, 150, 110, PRO_BORDER),
                            _line(150, 30, 230, 55, PRO_BORDER), _line(150, 70, 230, 55, PRO_BORDER), _line(150, 70, 230, 95, PRO_BORDER), _line(150, 110, 230, 95, PRO_BORDER),
                        ),
                        "Cloud AI services let you use trained models without building them yourself.",
                        tone="pro",
                    ),
                    _lesson(
                        "Trying a Managed AI Service",
                        "Hands-on with a free-tier AI/ML service in a guided lab.",
                        [
                            "Use a free-tier managed AI service to process a real input",
                            "Describe what happens inside an API call to an AI service",
                        ],
                        (
                            "Trying a managed AI service usually means sending it an input - a photo, a "
                            "sentence, a sound clip - through an API call, and receiving back a result "
                            "called inference: the AI's prediction or analysis. For example, sending a photo "
                            "to an image-recognition service might return 'dog, 94% confidence'. Seeing this "
                            "process firsthand demystifies AI - it's a service like any other, following "
                            "clear rules, just trained on huge amounts of data."
                        ),
                        (
                            "Using a free-tier AI/ML guided lab (such as an AWS Educate lab for image or "
                            "text recognition), submit one sample input and record the result. Write a short "
                            "summary of what input you gave, what output came back, and how confident or "
                            "uncertain the result seemed."
                        ),
                        [
                            ("Managed AI Service", "A ready-to-use AI tool provided by a cloud platform"),
                            ("API Call", "A request sent to a service asking it to do something and return a result"),
                            ("Inference", "The prediction or result an AI model produces for a given input"),
                        ],
                        "If an image recognition service returns 'cat, 60% confidence', what does that confidence number actually mean?",
                        "It means the model estimates a 60% likelihood the image shows a cat - not certainty, so a human may want to double-check borderline results.",
                        _svg(
                            _bg(PRO_BG),
                            _box(15, 55, 62, 30, "#fff", PRO_BORDER), _label(46, 74, "Input", 9, PRO_TEXT),
                            _arrow(92, 70, size=16, color=PRO_TEXT_SOFT),
                            _box(107, 55, 70, 30, "#fff", SKY_DARK), _label(142, 74, "API Call", 9, PRO_TEXT),
                            _arrow(192, 70, size=16, color=PRO_TEXT_SOFT),
                            _box(207, 55, 78, 30, "#fff", PRO_BORDER), _label(246, 74, "Result", 9, PRO_TEXT),
                        ),
                        "A managed AI service takes an input, runs it through a model, and returns a result.",
                        tone="pro",
                    ),
                ],
            },
            {
                "title": "Capstone: Your Cloud Portfolio",
                "summary": "Package your best work into a portfolio for AWS Educate, re/Start or university applications.",
                "icon": "\U0001F393",
                "lessons": [
                    _lesson(
                        "Choosing Your Capstone Project",
                        "Scoping a capstone project that shows off your cloud skills.",
                        [
                            "Scope a capstone project with a clear problem, audience, and tech stack",
                            "Define an MVP (minimum viable product) and a realistic timeline",
                        ],
                        (
                            "A great capstone starts with a real problem and a real audience - 'a chore "
                            "tracker for my family' is more compelling than 'an app that does everything'. "
                            "Scoping means deciding exactly what you will build, what tools (your tech "
                            "stack) you'll use, and what your MVP looks like: the smallest version that "
                            "still solves the problem. From there, a realistic timeline with checkpoints "
                            "keeps the project achievable instead of overwhelming."
                        ),
                        (
                            "Fill out a one-page project-scoping worksheet: Problem (what are you solving "
                            "and for whom?), Tech Stack (what tools/services will you use, such as S3, a "
                            "database, or an AI service?), MVP (the smallest working version), and Timeline "
                            "(3-4 checkpoints with dates). Get feedback from a facilitator or peer before "
                            "finalising."
                        ),
                        [
                            ("Scope", "Deciding exactly what a project will and won't include"),
                            ("MVP", "Minimum Viable Product - the smallest version that still solves the problem"),
                            ("Timeline", "A planned schedule of checkpoints leading to completion"),
                        ],
                        "What is the smallest version (MVP) of your capstone idea that would still be genuinely useful?",
                        "There's no single right answer - a strong MVP solves the core problem with the fewest moving parts, leaving extra features for later.",
                        _svg(
                            _bg(PRO_BG),
                            _box(30, 28, 240, 20, "#fff", PRO_BORDER_SOFT), _label(150, 42, "Problem", 9, PRO_TEXT),
                            _box(30, 53, 240, 20, "#fff", PRO_BORDER_SOFT), _label(150, 67, "Tech Stack", 9, PRO_TEXT),
                            _box(30, 78, 240, 20, "#fff", PRO_BORDER_SOFT), _label(150, 92, "MVP", 9, PRO_TEXT),
                            _box(30, 103, 240, 20, "#fff", PRO_BORDER_SOFT), _label(150, 117, "Timeline", 9, PRO_TEXT),
                        ),
                        "A clear problem, tech stack, MVP, and timeline turn an idea into a plan.",
                        tone="pro",
                    ),
                    _lesson(
                        "Building Your Capstone",
                        "Building and documenting your capstone project.",
                        [
                            "Work through your capstone in planned sprints with clear goals",
                            "Keep a documentation log of decisions, problems, and fixes",
                        ],
                        (
                            "Big projects get built in sprints - short, focused chunks of time with a "
                            "specific goal, rather than trying to do everything at once. Just as important "
                            "as the code itself is documentation: a running log of what you built, why you "
                            "made certain decisions, and how you fixed problems along the way. Many "
                            "developers also use version control (tools that save a history of every change) "
                            "so they can always go back to a working version if something breaks."
                        ),
                        (
                            "Break your capstone into 3-4 sprints, each with one clear goal (for example "
                            "'Sprint 1: set up storage and upload test data'). After each sprint, write a "
                            "short documentation entry: what you built, one problem you hit, and how you "
                            "solved it. Save your work regularly, ideally using a version control tool."
                        ),
                        [
                            ("Sprint", "A short, focused work period with a specific goal"),
                            ("Documentation", "A written record of what was built and why"),
                            ("Version Control", "A tool that tracks and saves the history of changes to a project"),
                        ],
                        "Why is writing down 'what went wrong and how I fixed it' just as valuable as writing the working code?",
                        "Documenting problems and fixes creates a record you - or a future employer - can learn from, and proves you can troubleshoot, a skill just as valuable as writing correct code the first time.",
                        _svg(
                            _bg(PRO_BG),
                            _line(45, 70, 255, 70, PRO_BORDER),
                            _dot(60, 70, 6, SKY_DARK), _dot(120, 70, 6, PRO_BORDER), _dot(180, 70, 6, PRO_BORDER), _dot(240, 70, 6, PRO_BORDER),
                            _label(60, 95, "Sprint 1", 9, PRO_TEXT), _label(120, 95, "Sprint 2", 9, PRO_TEXT),
                            _label(180, 95, "Sprint 3", 9, PRO_TEXT), _label(240, 95, "Sprint 4", 9, PRO_TEXT),
                        ),
                        "Breaking work into sprints with documentation keeps a big project manageable.",
                        tone="pro",
                    ),
                    _lesson(
                        "Presenting Your Portfolio",
                        "Preparing a portfolio and pitch for next steps: AWS Educate, re/Start, or university.",
                        [
                            "Assemble a portfolio showcasing your best cloud computing work",
                            "Deliver a confident, concise pitch about your capstone project",
                        ],
                        (
                            "A portfolio is a curated collection of your best work - lesson projects, labs, "
                            "badges, and your capstone - that tells the story of what you can do, not just "
                            "what you were taught. A pitch is a short, confident explanation of your work "
                            "aimed at a specific audience, often called an elevator pitch because it should "
                            "fit in the time of a short lift ride: what you built, why it matters, and "
                            "what's next (AWS Educate badges, AWS re/Start, or a university Computer Science "
                            "application)."
                        ),
                        (
                            "Build a 3-slide pitch: Slide 1 - who you are and your cloud journey so far; "
                            "Slide 2 - your capstone project (problem, what you built, a screenshot or demo "
                            "link); Slide 3 - your next step (AWS Educate badge, AWS re/Start, or university "
                            "pathway). Practise delivering it out loud in under two minutes, then present it "
                            "to a real audience."
                        ),
                        [
                            ("Portfolio", "A curated collection of your best project work"),
                            ("Pitch", "A short, persuasive explanation of your work and its value"),
                            ("Elevator Pitch", "A pitch short enough to deliver in about a minute or two"),
                        ],
                        "In one sentence, what is your capstone project, who is it for, and what cloud skill does it prove you have?",
                        "There's no single right answer - a strong pitch names the project, the audience it helps, and the specific cloud skill it demonstrates.",
                        _svg(
                            _bg(PRO_BG),
                            _box(90, 28, 120, 82, "#fff", SKY_DARK), _label(150, 52, "PORTFOLIO", 11, SKY_DARK, "800"),
                            _line(112, 68, 188, 68, PRO_BORDER_SOFT),
                            _label(150, 86, "Capstone Project", 8, PRO_TEXT_SOFT), _label(150, 98, "Pitch Ready", 8, PRO_TEXT_SOFT),
                        ),
                        "A strong portfolio and a short, confident pitch open doors to what comes next.",
                        tone="pro",
                    ),
                ],
            },
        ],
    },
]

for _tier_data in TIERS:
    for _course_data in _tier_data["courses"]:
        _course_data["lessons"].append(_build_exam(_course_data["title"], _course_data["lessons"]))

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

                for l_index, lesson_data in enumerate(course_data["lessons"]):
                    Lesson.objects.update_or_create(
                        course=course,
                        slug=slugify(lesson_data["title"]),
                        defaults={
                            "title": lesson_data["title"],
                            "summary": lesson_data["summary"],
                            "content": lesson_data["content"],
                            "duration_minutes": lesson_data.get("duration_minutes", 30),
                            "lesson_type": lesson_data.get("lesson_type", "lesson"),
                            "pass_score_percent": lesson_data.get("pass_score_percent", 70),
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
