"""The wording of every email, in English and Kiswahili.

Each entry has a `category` (None = an account email that is always sent; otherwise the person can turn it off on their
email settings page), the text per language, and `sample` values for the admin preview page. Text uses {placeholders}
filled by core.notify. `bullet` formats one bullet from a dict of values; `stats` are the labels of the number tiles.
"""

DAYS = {"en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        "sw": ["Jumatatu", "Jumanne", "Jumatano", "Alhamisi", "Ijumaa", "Jumamosi", "Jumapili"]}
MONTHS = {"en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
          "sw": ["Januari", "Februari", "Machi", "Aprili", "Mei", "Juni", "Julai", "Agosti", "Septemba", "Oktoba", "Novemba", "Desemba"]}

CATEGORIES = {
    "progress": ("Progress reports", "Ripoti za maendeleo", "Weekly and monthly summaries of how your child is doing",
                 "Muhtasari wa kila wiki na kila mwezi wa jinsi mtoto wako anavyoendelea"),
    "reminders": ("Reminders", "Vikumbusho", "Study nudges after a few quiet days, and reminders before a live class",
                  "Vikumbusho vya kusoma baada ya siku chache bila kusoma, na kabla ya darasa la moja kwa moja"),
    "class": ("Class updates", "Habari za darasa", "New assignments, live class dates, teacher messages and missed classes",
              "Kazi mpya, tarehe za madarasa ya moja kwa moja, ujumbe wa mwalimu na madarasa yaliyokosekana"),
    "celebrations": ("Celebrations", "Sherehe", "New badges, finished courses and certificates",
                     "Beji mpya, kozi zilizokamilika na vyeti"),
    "news": ("News from Cloud for Kids", "Habari kutoka Cloud for Kids", "Occasional announcements, such as open days and new courses",
             "Matangazo ya mara kwa mara, kama siku za wazi na kozi mpya"),
}


def lang_of(code):
    return "sw" if (code or "").startswith("sw") else "en"


def day(dt, lang):
    """'Monday 19 October' / 'Jumatatu 19 Oktoba'."""
    return f"{DAYS[lang][dt.weekday()]} {dt.day} {MONTHS[lang][dt.month - 1]}"


def short_day(dt, lang):
    """'Mon 19 Oct' / 'Jumatatu 19 Okt'."""
    return f"{DAYS[lang][dt.weekday()][:3] if lang == 'en' else DAYS[lang][dt.weekday()]} {dt.day} {MONTHS[lang][dt.month - 1][:3]}"


def long_date(d, lang):
    """'19 October 2026' / '19 Oktoba 2026'."""
    return f"{d.day} {MONTHS[lang][d.month - 1]} {d.year}"


def month_name(d, lang):
    return f"{MONTHS[lang][d.month - 1]} {d.year}"


def ago(dt, now, lang):
    """'today', 'yesterday', '3 days ago' / 'leo', 'jana', 'siku 3 zilizopita'; 'never' when there is no date."""
    if dt is None:
        return "never" if lang == "en" else "bado"
    days = (now.date() - dt.date()).days
    if days <= 0:
        return "today" if lang == "en" else "leo"
    if days == 1:
        return "yesterday" if lang == "en" else "jana"
    if days < 14:
        return f"{days} days ago" if lang == "en" else f"siku {days} zilizopita"
    return f"{days // 7} weeks ago" if lang == "en" else f"wiki {days // 7} zilizopita"


CHROME = {
    "en": {
        "button_fallback": "Button not working? Copy this address into your browser:",
        "footer": "Cloud for Kids · Every Kenyan child, cloud-ready by 2030.",
        "why": "You get this email because of your Cloud for Kids account.",
        "settings": "Email settings",
        "stop": "Stop emails like this",
        "header_alt": "Cloud for Kids: learn the cloud, one step at a time",
    },
    "sw": {
        "button_fallback": "Kitufe hakifanyi kazi? Nakili anwani hii kwenye kivinjari chako:",
        "footer": "Cloud for Kids · Kila mtoto wa Kenya, tayari kwa wingu ifikapo 2030.",
        "why": "Unapokea barua pepe hii kwa sababu ya akaunti yako ya Cloud for Kids.",
        "settings": "Mipangilio ya barua pepe",
        "stop": "Acha barua pepe kama hii",
        "header_alt": "Cloud for Kids: jifunze kuhusu wingu, hatua kwa hatua",
    },
}


EMAILS = {
    # ---------------------------------------------------------------- account
    "welcome_learner": {
        "category": None,
        "en": {"subject": "Welcome to Cloud for Kids", "heading": "You're in!",
               "paragraphs": ["Welcome to Cloud for Kids, {name}!",
                              "Start your first lesson, try a Practice Lab and keep your learning streak going."],
               "cta": "Start learning"},
        "sw": {"subject": "Karibu Cloud for Kids", "heading": "Umeingia!",
               "paragraphs": ["Karibu Cloud for Kids, {name}!",
                              "Anza somo lako la kwanza, jaribu Maabara ya Mazoezi na uendeleze mfululizo wako wa kujifunza."],
               "cta": "Anza kujifunza"},
        "sample": {"name": "Amani"},
    },
    "welcome_parent": {
        "category": None,
        "en": {"subject": "Welcome to Cloud for Kids", "heading": "You're in!",
               "paragraphs": ["Welcome, {name}. Your parent account is ready.",
                              "Ask your child to open My Profile and read out their family code. Then use Add a child to follow their progress from 0 to 100%."],
               "cta": "Add my child"},
        "sw": {"subject": "Karibu Cloud for Kids", "heading": "Umeingia!",
               "paragraphs": ["Karibu, {name}. Akaunti yako ya mzazi iko tayari.",
                              "Mwombe mtoto wako afungue Wasifu Wangu na akusomee msimbo wa familia. Kisha tumia Ongeza mtoto ili ufuatilie maendeleo yake kutoka 0 hadi 100%."],
               "cta": "Ongeza mtoto wangu"},
        "sample": {"name": "Wanjiku"},
    },
    "welcome_facilitator": {
        "category": None,
        "en": {"subject": "Welcome to Cloud for Kids", "heading": "You're in!",
               "paragraphs": ["Welcome, {name}. Your facilitator account has been created.",
                              "Our team checks every new facilitator before class tools are switched on. This usually takes a day or two. We will email you as soon as you are approved."],
               "cta": "Open Cloud for Kids"},
        "sw": {"subject": "Karibu Cloud for Kids", "heading": "Umeingia!",
               "paragraphs": ["Karibu, {name}. Akaunti yako ya mwezeshaji imeundwa.",
                              "Timu yetu humkagua kila mwezeshaji mpya kabla ya kuwasha zana za darasa. Kwa kawaida huchukua siku moja au mbili. Tutakutumia barua pepe mara tu utakapoidhinishwa."],
               "cta": "Fungua Cloud for Kids"},
        "sample": {"name": "Grace"},
    },
    "confirm_line": {  # added to a welcome email while the address is not confirmed yet
        "category": None,
        "en": {"paragraphs": ["Please confirm this is your email address, so we can reach you about your account."], "cta": "Confirm my email"},
        "sw": {"paragraphs": ["Tafadhali thibitisha kuwa hii ni anwani yako ya barua pepe, ili tuweze kuwasiliana nawe kuhusu akaunti yako."], "cta": "Thibitisha barua pepe yangu"},
        "sample": {},
    },
    "confirm_email": {
        "category": None,
        "en": {"subject": "Confirm your email for Cloud for Kids", "heading": "Is this your email?",
               "paragraphs": ["Hi {name}, please confirm that {email} is your email address. It keeps your account safe and makes sure password resets reach you."],
               "cta": "Confirm my email", "note": "Did not sign up for Cloud for Kids? You can ignore this email."},
        "sw": {"subject": "Thibitisha barua pepe yako ya Cloud for Kids", "heading": "Je, hii ni barua pepe yako?",
               "paragraphs": ["Habari {name}, tafadhali thibitisha kuwa {email} ni anwani yako ya barua pepe. Hii inaweka akaunti yako salama na kuhakikisha unapokea viungo vya kubadilisha nenosiri."],
               "cta": "Thibitisha barua pepe yangu", "note": "Hukujisajili na Cloud for Kids? Unaweza kupuuza barua pepe hii."},
        "sample": {"name": "Amani", "email": "amani@example.com"},
    },
    "password_changed": {
        "category": None,
        "en": {"subject": "Your Cloud for Kids password was changed", "heading": "Your password was changed",
               "paragraphs": ["Hi {name}, the password for your Cloud for Kids account ({username}) was changed on {when}.",
                              "If this was you, there is nothing else to do."],
               "cta": "This wasn't me: reset my password",
               "note": "If you did not change it, reset your password now and tell us by replying to this email."},
        "sw": {"subject": "Nenosiri lako la Cloud for Kids limebadilishwa", "heading": "Nenosiri lako limebadilishwa",
               "paragraphs": ["Habari {name}, nenosiri la akaunti yako ya Cloud for Kids ({username}) lilibadilishwa {when}.",
                              "Ikiwa ni wewe, huhitaji kufanya chochote zaidi."],
               "cta": "Si mimi: badilisha nenosiri langu",
               "note": "Ikiwa hukulibadilisha, badilisha nenosiri lako sasa na utujulishe kwa kujibu barua pepe hii."},
        "sample": {"name": "Amani", "username": "amani", "when": "Monday 19 October at 16:20"},
    },
    "consent_request": {
        "category": None,
        "en": {"subject": "Please approve {child}'s Cloud for Kids account", "heading": "{child} would like to join Cloud for Kids",
               "paragraphs": ["Hello{parent},",
                              "{child_full} has asked to join Cloud for Kids, a cloud-computing learning programme for children in Kenya. Because they are under 13, we need your permission before the account can be used.",
                              "The next page explains what we collect and why. You can approve or decline there. If you do nothing, the account stays locked."],
               "cta": "Review and decide", "note": "If you do not know this child or did not expect this email, just ignore it."},
        "sw": {"subject": "Tafadhali idhinisha akaunti ya {child} ya Cloud for Kids", "heading": "{child} angependa kujiunga na Cloud for Kids",
               "paragraphs": ["Habari{parent},",
                              "{child_full} ameomba kujiunga na Cloud for Kids, programu ya kujifunza kompyuta ya wingu kwa watoto nchini Kenya. Kwa kuwa ana umri wa chini ya miaka 13, tunahitaji ruhusa yako kabla akaunti haijatumika.",
                              "Ukurasa unaofuata unaeleza tunachokusanya na kwa nini. Unaweza kukubali au kukataa hapo. Usipofanya chochote, akaunti itabaki imefungwa."],
               "cta": "Kagua na uamue", "note": "Ikiwa humjui mtoto huyu au hukutarajia barua pepe hii, ipuuze tu."},
        "sample": {"child": "Amani", "child_full": "Amani Otieno", "parent": " Wanjiku"},
    },
    "consent_approved": {
        "category": None,
        "en": {"subject": "{child} can now use Cloud for Kids", "heading": "Thank you for approving",
               "paragraphs": ["{child}'s account is now active and can log in with the username {username}.",
                              "Want to follow their progress? Create a free parent account, choose Parent / Guardian, and link with the family code on your child's profile page."],
               "cta": "Create a parent account"},
        "sw": {"subject": "{child} sasa anaweza kutumia Cloud for Kids", "heading": "Asante kwa kuidhinisha",
               "paragraphs": ["Akaunti ya {child} sasa iko hai na anaweza kuingia kwa jina la mtumiaji {username}.",
                              "Ungependa kufuatilia maendeleo yake? Fungua akaunti ya mzazi bila malipo, chagua Mzazi / Mlezi, na uunganishe kwa msimbo wa familia ulio kwenye ukurasa wa wasifu wa mtoto wako."],
               "cta": "Fungua akaunti ya mzazi"},
        "sample": {"child": "Amani", "username": "amani"},
    },
    "consent_declined": {
        "category": None,
        "en": {"subject": "Cloud for Kids account declined", "heading": "The account has been removed",
               "paragraphs": ["As you asked, we have deleted the Cloud for Kids account request and the details that came with it. Nothing else is kept."]},
        "sw": {"subject": "Akaunti ya Cloud for Kids imekataliwa", "heading": "Akaunti imeondolewa",
               "paragraphs": ["Kama ulivyoomba, tumefuta ombi la akaunti ya Cloud for Kids pamoja na taarifa zilizokuja nalo. Hakuna kingine kilichohifadhiwa."]},
        "sample": {},
    },
    "admin_new_facilitator": {
        "category": None,
        "en": {"subject": "New facilitator waiting for approval", "heading": "A facilitator needs approval",
               "paragraphs": ["{name} ({email}) signed up as a facilitator or teacher."], "cta": "Review in the admin"},
        "sw": {"subject": "Mwezeshaji mpya anasubiri kuidhinishwa", "heading": "Mwezeshaji anahitaji kuidhinishwa",
               "paragraphs": ["{name} ({email}) amejisajili kama mwezeshaji au mwalimu."], "cta": "Kagua kwenye utawala"},
        "sample": {"name": "Grace Wanjiru", "email": "grace@example.com"},
    },
    "teacher_approved": {
        "category": None,
        "en": {"subject": "Your facilitator account is approved", "heading": "You're approved!",
               "paragraphs": ["Good news, {name}. You can now create classes, share join codes and follow your learners' progress."],
               "cta": "Open my dashboard"},
        "sw": {"subject": "Akaunti yako ya mwezeshaji imeidhinishwa", "heading": "Umeidhinishwa!",
               "paragraphs": ["Habari njema, {name}. Sasa unaweza kuunda madarasa, kushiriki misimbo ya kujiunga na kufuatilia maendeleo ya wanafunzi wako."],
               "cta": "Fungua dashibodi yangu"},
        "sample": {"name": "Grace"},
    },
    "parent_linked_parent": {
        "category": None,
        "en": {"subject": "You are now following {child}", "heading": "You're connected",
               "paragraphs": ["You are now following {child}'s learning on Cloud for Kids. You will see every lesson, quiz, badge and certificate on your family dashboard.",
                              "Every Sunday evening we send a short summary of the week. You can change which emails you get at any time."],
               "cta": "See {child}'s progress"},
        "sw": {"subject": "Sasa unamfuatilia {child}", "heading": "Mmeunganishwa",
               "paragraphs": ["Sasa unafuatilia masomo ya {child} kwenye Cloud for Kids. Utaona kila somo, jaribio, beji na cheti kwenye dashibodi yako ya familia.",
                              "Kila Jumapili jioni tunatuma muhtasari mfupi wa wiki. Unaweza kubadilisha barua pepe unazopokea wakati wowote."],
               "cta": "Ona maendeleo ya {child}"},
        "sample": {"child": "Amani"},
    },
    "parent_linked_learner": {
        "category": None,
        "en": {"subject": "{parent} can now see your progress", "heading": "A parent is following you",
               "paragraphs": ["{parent} used your family code and can now see your lessons, quizzes, badges and certificates on Cloud for Kids.",
                              "If you do not know who this is, tell your teacher or a parent straight away."]},
        "sw": {"subject": "{parent} sasa anaweza kuona maendeleo yako", "heading": "Mzazi anakufuatilia",
               "paragraphs": ["{parent} ametumia msimbo wako wa familia na sasa anaweza kuona masomo, majaribio, beji na vyeti vyako kwenye Cloud for Kids.",
                              "Ikiwa humjui ni nani, mwambie mwalimu wako au mzazi mara moja."]},
        "sample": {"parent": "Wanjiku Otieno"},
    },

    # ---------------------------------------------------------------- classes
    "assignment_learner": {
        "category": "class",
        "en": {"subject": "New assignment from {teacher}: {course}", "heading": "New assignment",
               "paragraphs": ["Your teacher set a new assignment for {classroom}: {course}.{due}"], "cta": "Open Cloud for Kids",
               "due": " Please finish it by {date}.", "teacher_note": "Message from the teacher: {note}"},
        "sw": {"subject": "Kazi mpya kutoka kwa {teacher}: {course}", "heading": "Kazi mpya",
               "paragraphs": ["Mwalimu wako ametoa kazi mpya kwa {classroom}: {course}.{due}"], "cta": "Fungua Cloud for Kids",
               "due": " Tafadhali imalize kabla ya {date}.", "teacher_note": "Ujumbe kutoka kwa mwalimu: {note}"},
        "sample": {"teacher": "Grace", "course": "My Digital World", "classroom": "Grade 6 Cloud Club", "date": "23 October 2026"},
    },
    "assignment_parent": {
        "category": "class",
        "en": {"subject": "New assignment from {teacher}: {course}", "heading": "New assignment",
               "paragraphs": ["{child}'s teacher set a new assignment for {classroom}: {course}.{due}"], "cta": "Open Cloud for Kids",
               "due": " Please finish it by {date}.", "teacher_note": "Message from the teacher: {note}"},
        "sw": {"subject": "Kazi mpya kutoka kwa {teacher}: {course}", "heading": "Kazi mpya",
               "paragraphs": ["Mwalimu wa {child} ametoa kazi mpya kwa {classroom}: {course}.{due}"], "cta": "Fungua Cloud for Kids",
               "due": " Tafadhali imalizwe kabla ya {date}.", "teacher_note": "Ujumbe kutoka kwa mwalimu: {note}"},
        "sample": {"child": "Amani", "teacher": "Grace", "course": "My Digital World", "classroom": "Grade 6 Cloud Club", "date": "23 October 2026"},
    },
    "live_scheduled_learner": {
        "category": "class",
        "en": {"subject": "Live class: {classroom} on {short}", "heading": "A live class is coming up",
               "paragraphs": ["Your teacher scheduled a live online class for {classroom}{topic} on {when} at {time} (Kenyan time).{repeat}",
                              "Open the link a few minutes early. Learners join with their microphone and camera off and raise a hand to speak.{passcode}"],
               "cta": "Open the live class", "repeat": " It repeats every week for {n} weeks.", "passcode_line": " The passcode to get in is {code}."},
        "sw": {"subject": "Darasa la moja kwa moja: {classroom} {short}", "heading": "Darasa la moja kwa moja linakuja",
               "paragraphs": ["Mwalimu wako amepanga darasa la moja kwa moja mtandaoni kwa {classroom}{topic} {when} saa {time} (saa za Kenya).{repeat}",
                              "Fungua kiungo dakika chache mapema. Wanafunzi hujiunga kipaza sauti na kamera zikiwa zimezimwa, na huinua mkono ili kuzungumza.{passcode}"],
               "cta": "Fungua darasa", "repeat": " Linarudiwa kila wiki kwa wiki {n}.", "passcode_line": " Nambari ya siri ya kuingia ni {code}."},
        "sample": {"classroom": "Grade 6 Cloud Club", "topic": " (Intro to storage)", "short": "Mon 19 Oct", "when": "Monday 19 October", "time": "16:00", "repeat": "", "passcode": ""},
    },
    "live_scheduled_parent": {
        "category": "class",
        "en": {"subject": "Live class: {classroom} on {short}", "heading": "A live class is coming up",
               "paragraphs": ["{child}'s teacher scheduled a live online class for {classroom}{topic} on {when} at {time} (Kenyan time).{repeat}",
                              "Learners join with their microphone and camera off and raise a hand to speak.{passcode}"],
               "cta": "Open the live class", "repeat": " It repeats every week for {n} weeks.", "passcode_line": " The passcode to get in is {code}."},
        "sw": {"subject": "Darasa la moja kwa moja: {classroom} {short}", "heading": "Darasa la moja kwa moja linakuja",
               "paragraphs": ["Mwalimu wa {child} amepanga darasa la moja kwa moja mtandaoni kwa {classroom}{topic} {when} saa {time} (saa za Kenya).{repeat}",
                              "Wanafunzi hujiunga kipaza sauti na kamera zikiwa zimezimwa, na huinua mkono ili kuzungumza.{passcode}"],
               "cta": "Fungua darasa", "repeat": " Linarudiwa kila wiki kwa wiki {n}.", "passcode_line": " Nambari ya siri ya kuingia ni {code}."},
        "sample": {"child": "Amani", "classroom": "Grade 6 Cloud Club", "topic": "", "short": "Mon 19 Oct", "when": "Monday 19 October", "time": "16:00", "repeat": "", "passcode": ""},
    },
    "live_reminder_learner": {
        "category": "reminders",
        "en": {"subject": "Live class at {time}: {title}", "heading": "Your live class starts soon",
               "paragraphs": ["Your live class for {classroom} starts at {time} today.",
                              "Open the link a few minutes early and use headphones if you have them.{passcode}"],
               "cta": "Join the live class", "passcode_line": " The passcode is {code}."},
        "sw": {"subject": "Darasa la moja kwa moja saa {time}: {title}", "heading": "Darasa lako linaanza hivi karibuni",
               "paragraphs": ["Darasa lako la {classroom} linaanza saa {time} leo.",
                              "Fungua kiungo dakika chache mapema na utumie vipokea sauti ikiwa unavyo.{passcode}"],
               "cta": "Jiunge na darasa", "passcode_line": " Nambari ya siri ni {code}."},
        "sample": {"classroom": "Grade 6 Cloud Club", "title": "Grade 6 Cloud Club", "time": "16:00", "passcode": ""},
    },
    "live_reminder_parent": {
        "category": "reminders",
        "en": {"subject": "Live class at {time}: {title}", "heading": "A live class starts soon",
               "paragraphs": ["{child}'s live class for {classroom} starts at {time} today.",
                              "Learners do best with a quiet spot and headphones if you have them.{passcode}"],
               "cta": "Open the live class", "passcode_line": " The passcode is {code}."},
        "sw": {"subject": "Darasa la moja kwa moja saa {time}: {title}", "heading": "Darasa linaanza hivi karibuni",
               "paragraphs": ["Darasa la {child} la {classroom} linaanza saa {time} leo.",
                              "Wanafunzi hufanya vizuri zaidi wakiwa mahali tulivu na wakiwa na vipokea sauti ikiwa mnavyo.{passcode}"],
               "cta": "Fungua darasa", "passcode_line": " Nambari ya siri ni {code}."},
        "sample": {"child": "Amani", "classroom": "Grade 6 Cloud Club", "title": "Grade 6 Cloud Club", "time": "16:00", "passcode": ""},
    },
    "missed_live": {
        "category": "class",
        "en": {"subject": "{child} missed today's live class", "heading": "Missed live class",
               "paragraphs": ["{child} did not join the live class for {classroom} on {when} at {time}.",
                              "If something got in the way (internet, a device, or another activity), the teacher's next live class is on the class calendar. You can also message the teacher from your family dashboard."],
               "cta": "Open the family dashboard"},
        "sw": {"subject": "{child} amekosa darasa la leo", "heading": "Darasa lililokosekana",
               "paragraphs": ["{child} hakujiunga na darasa la moja kwa moja la {classroom} {when} saa {time}.",
                              "Ikiwa kuna kitu kilichozuia (mtandao, kifaa, au shughuli nyingine), darasa lijalo la mwalimu liko kwenye kalenda ya darasa. Unaweza pia kumtumia mwalimu ujumbe kutoka kwenye dashibodi yako ya familia."],
               "cta": "Fungua dashibodi ya familia"},
        "sample": {"child": "Amani", "classroom": "Grade 6 Cloud Club", "when": "Monday 19 October", "time": "16:00"},
    },
    "message": {
        "category": "class",
        "en": {"subject": "Message from {sender}: {topic}", "heading": "{topic}", "paragraphs": ["{sender_full} wrote:"], "cta": "Open my messages"},
        "sw": {"subject": "Ujumbe kutoka kwa {sender}: {topic}", "heading": "{topic}", "paragraphs": ["{sender_full} aliandika:"], "cta": "Fungua jumbe zangu"},
        "sample": {"sender": "Grace", "sender_full": "Grace Wanjiru", "topic": "Hello class"},
    },

    # ---------------------------------------------------------------- progress and reminders
    "weekly": {
        "category": "progress",
        "en": {"subject": "Your child's week on Cloud for Kids", "heading": "Here is the week, {name}",
               "paragraphs": ["A quick look at how your child is doing:"], "cta": "See the full report",
               "bullet": "{child}: {percent}% of the path done, {week} finished this week, {streak}-day streak{score}. Last active {last}.",
               "score": ", quiz average {n}%", "stats": ["of path done", "done this week", "day streak"]},
        "sw": {"subject": "Wiki ya mtoto wako kwenye Cloud for Kids", "heading": "Hii ndiyo wiki, {name}",
               "paragraphs": ["Mtazamo mfupi wa jinsi mtoto wako anavyoendelea:"], "cta": "Ona ripoti kamili",
               "bullet": "{child}: {percent}% ya njia imekamilika, {week} vimekamilika wiki hii, mfululizo wa siku {streak}{score}. Mara ya mwisho alikuwa hai {last}.",
               "score": ", wastani wa majaribio {n}%", "stats": ["ya njia imekamilika", "vimekamilika wiki hii", "siku mfululizo"]},
        "sample": {"name": "Wanjiku", "bullets": [{"child": "Amani", "percent": 42, "week": 3, "streak": 4, "score": 86, "last": "today"}],
                   "stats": ["42%", 3, 4]},
    },
    "monthly": {
        "category": "progress",
        "en": {"subject": "{month} on Cloud for Kids", "heading": "{month}: the month in review",
               "paragraphs": ["Hello {name}, here is what your child achieved in {month}."], "cta": "See the full report",
               "bullet": "{child}: lessons finished {lessons}, labs {labs}, new badges {badges}, certificates {certs}. Now {percent}% of the path is done{score}.",
               "score": " (quiz average {n}%)", "stats": ["lessons this month", "labs this month", "new badges"],
               "quiet": "{child} did not study this month. One short lesson a day is a great way to start again."},
        "sw": {"subject": "{month} kwenye Cloud for Kids", "heading": "{month}: muhtasari wa mwezi",
               "paragraphs": ["Habari {name}, haya ndiyo mafanikio ya mtoto wako mwezi {month}."], "cta": "Ona ripoti kamili",
               "bullet": "{child}: masomo {lessons} na maabara {labs} yamekamilika, beji mpya {badges}, vyeti {certs}, sasa {percent}% ya njia{score}.",
               "score": " (wastani wa majaribio {n}%)", "stats": ["masomo mwezi huu", "maabara mwezi huu", "beji mpya"],
               "quiet": "{child} hakusoma mwezi huu. Somo moja fupi kila siku ni njia nzuri ya kuanza tena."},
        "sample": {"name": "Wanjiku", "month": "September 2026",
                   "bullets": [{"child": "Amani", "lessons": 12, "labs": 3, "badges": 2, "certs": 1, "percent": 58, "score": 81}],
                   "stats": [12, 3, 2]},
    },
    "nudge_learner": {
        "category": "reminders",
        "en": {"subject": "A little nudge from Cloud for Kids", "heading": "Time for a short lesson?",
               "paragraphs": ["You have not studied for {days} days. Keep the streak alive with one short lesson."], "cta": "Open Cloud for Kids"},
        "sw": {"subject": "Kikumbusho kidogo kutoka Cloud for Kids", "heading": "Wakati wa somo fupi?",
               "paragraphs": ["Hujasoma kwa siku {days}. Endeleza mfululizo wako kwa somo moja fupi."], "cta": "Fungua Cloud for Kids"},
        "sample": {"days": 5},
    },
    "nudge_parent": {
        "category": "reminders",
        "en": {"subject": "A little nudge from Cloud for Kids", "heading": "Time for a short lesson?",
               "paragraphs": ["{child} has not studied for {days} days. Keep the streak alive with one short lesson."], "cta": "Open Cloud for Kids"},
        "sw": {"subject": "Kikumbusho kidogo kutoka Cloud for Kids", "heading": "Wakati wa somo fupi?",
               "paragraphs": ["{child} hajasoma kwa siku {days}. Msaidie kuendeleza mfululizo wake kwa somo moja fupi."], "cta": "Fungua Cloud for Kids"},
        "sample": {"child": "Amani", "days": 5},
    },
    "nudge_start_learner": {
        "category": "reminders",
        "en": {"subject": "A little nudge from Cloud for Kids", "heading": "Time for a short lesson?",
               "paragraphs": ["You have not finished a lesson yet. A first 10-minute lesson is the best way to start."], "cta": "Open Cloud for Kids"},
        "sw": {"subject": "Kikumbusho kidogo kutoka Cloud for Kids", "heading": "Wakati wa somo fupi?",
               "paragraphs": ["Bado hujamaliza somo lolote. Somo la kwanza la dakika 10 ndiyo njia bora ya kuanza."], "cta": "Fungua Cloud for Kids"},
        "sample": {},
    },
    "nudge_start_parent": {
        "category": "reminders",
        "en": {"subject": "A little nudge from Cloud for Kids", "heading": "Time for a short lesson?",
               "paragraphs": ["{child} has not finished a lesson yet. A first 10-minute lesson is the best way to start."], "cta": "Open Cloud for Kids"},
        "sw": {"subject": "Kikumbusho kidogo kutoka Cloud for Kids", "heading": "Wakati wa somo fupi?",
               "paragraphs": ["{child} bado hajamaliza somo lolote. Somo la kwanza la dakika 10 ndiyo njia bora ya kuanza."], "cta": "Fungua Cloud for Kids"},
        "sample": {"child": "Amani"},
    },
    "plan_ending_learner": {
        "category": None,
        "en": {"subject": "Your {plan} plan ends {when}", "heading": "Time to renew?",
               "paragraphs": ["Your {plan} plan ends on {date}. Renew now to keep lessons, quizzes and labs open without a break."], "cta": "Renew {plan}",
               "tomorrow": "tomorrow", "in_days": "in {n} days"},
        "sw": {"subject": "Mpango wako wa {plan} unaisha {when}", "heading": "Wakati wa kurejesha?",
               "paragraphs": ["Mpango wako wa {plan} unaisha {date}. Urejeshe sasa ili masomo, majaribio na maabara yabaki wazi bila kukatizwa."], "cta": "Rejesha {plan}",
               "tomorrow": "kesho", "in_days": "baada ya siku {n}"},
        "sample": {"plan": "Core", "when": "tomorrow", "date": "Tuesday 20 October"},
    },
    "plan_ending_parent": {
        "category": None,
        "en": {"subject": "{child}'s {plan} plan ends {when}", "heading": "Time to renew?",
               "paragraphs": ["{child}'s {plan} plan ends on {date}. Renew now to keep lessons, quizzes and labs open without a break."], "cta": "Renew {plan}",
               "tomorrow": "tomorrow", "in_days": "in {n} days"},
        "sw": {"subject": "Mpango wa {plan} wa {child} unaisha {when}", "heading": "Wakati wa kurejesha?",
               "paragraphs": ["Mpango wa {plan} wa {child} unaisha {date}. Urejeshe sasa ili masomo, majaribio na maabara yabaki wazi bila kukatizwa."], "cta": "Rejesha {plan}",
               "tomorrow": "kesho", "in_days": "baada ya siku {n}"},
        "sample": {"child": "Amani", "plan": "Core", "when": "tomorrow", "date": "Tuesday 20 October"},
    },
    "plan_ended_learner": {
        "category": None,
        "en": {"subject": "Your {plan} plan has ended", "heading": "The plan has ended",
               "paragraphs": ["Your {plan} plan ended today, so lessons are locked for now. Progress, badges and certificates are all kept. Renew any time to carry on."],
               "cta": "Renew {plan}"},
        "sw": {"subject": "Mpango wako wa {plan} umeisha", "heading": "Mpango umeisha",
               "paragraphs": ["Mpango wako wa {plan} umeisha leo, kwa hivyo masomo yamefungwa kwa sasa. Maendeleo, beji na vyeti vyote vimehifadhiwa. Rejesha wakati wowote ili kuendelea."],
               "cta": "Rejesha {plan}"},
        "sample": {"plan": "Core"},
    },
    "plan_ended_parent": {
        "category": None,
        "en": {"subject": "{child}'s {plan} plan has ended", "heading": "The plan has ended",
               "paragraphs": ["{child}'s {plan} plan ended today, so lessons are locked for now. Progress, badges and certificates are all kept. Renew any time to carry on."],
               "cta": "Renew {plan}"},
        "sw": {"subject": "Mpango wa {plan} wa {child} umeisha", "heading": "Mpango umeisha",
               "paragraphs": ["Mpango wa {plan} wa {child} umeisha leo, kwa hivyo masomo yamefungwa kwa sasa. Maendeleo, beji na vyeti vyote vimehifadhiwa. Rejesha wakati wowote ili kuendelea."],
               "cta": "Rejesha {plan}"},
        "sample": {"child": "Amani", "plan": "Core"},
    },

    # ---------------------------------------------------------------- celebrations
    "badges_learner": {
        "category": "celebrations",
        "en": {"subject": "You earned a new badge: {first}", "heading": "Badge unlocked!",
               "paragraphs": ["Well done, {name}! You just earned:"], "cta": "See my achievements",
               "bullet": "{badge}: {description}",
               "course_done": "You finished every lesson in {course}. That is a big achievement!"},
        "sw": {"subject": "Umepata beji mpya: {first}", "heading": "Beji imefunguliwa!",
               "paragraphs": ["Hongera, {name}! Umepata:"], "cta": "Ona mafanikio yangu",
               "bullet": "{badge}: {description}",
               "course_done": "Umemaliza kila somo katika {course}. Hayo ni mafanikio makubwa!"},
        "sample": {"name": "Amani", "first": "Rising Cloud",
                   "bullets": [{"badge": "Rising Cloud", "description": "Completed 5 lessons."}]},
    },
    "badges_parent": {
        "category": "celebrations",
        "en": {"subject": "{child} earned a new badge: {first}", "heading": "Something to celebrate",
               "paragraphs": ["{child} just earned:"], "cta": "See {child}'s progress",
               "bullet": "{badge}: {description}",
               "course_done": "{child} finished every lesson in {course}. A word of praise goes a long way!"},
        "sw": {"subject": "{child} amepata beji mpya: {first}", "heading": "Kuna jambo la kusherehekea",
               "paragraphs": ["{child} amepata:"], "cta": "Ona maendeleo ya {child}",
               "bullet": "{badge}: {description}",
               "course_done": "{child} amemaliza kila somo katika {course}. Neno la pongezi lina nguvu kubwa!"},
        "sample": {"child": "Amani", "first": "Rising Cloud",
                   "bullets": [{"badge": "Rising Cloud", "description": "Completed 5 lessons."}]},
    },
    "certificate_learner": {
        "category": "celebrations",
        "en": {"subject": "Your certificate for {course} is ready", "heading": "Congratulations, {name}!",
               "paragraphs": ["You finished {course} and earned a {level}.",
                              "Open it to print it or save it as a PDF. Anyone can check it is real with the code {code}."],
               "cta": "Open my certificate"},
        "sw": {"subject": "Cheti chako cha {course} kiko tayari", "heading": "Hongera, {name}!",
               "paragraphs": ["Umemaliza {course} na umepata {level}.",
                              "Kifungue ili ukichapishe au ukihifadhi kama PDF. Mtu yeyote anaweza kuthibitisha kuwa ni halali kwa msimbo {code}."],
               "cta": "Fungua cheti changu"},
        "sample": {"name": "Amani", "course": "My Digital World", "level": "Verified Certificate of Achievement", "code": "C4K7Q2XZ"},
    },
    "certificate_parent": {
        "category": "celebrations",
        "en": {"subject": "{child} earned a certificate for {course}", "heading": "A certificate for {child}!",
               "paragraphs": ["{child} finished {course} and earned a {level}.",
                              "You can print it or save it as a PDF. Anyone can check it is real with the code {code}."],
               "cta": "Open the certificate"},
        "sw": {"subject": "{child} amepata cheti cha {course}", "heading": "Cheti kwa {child}!",
               "paragraphs": ["{child} amemaliza {course} na amepata {level}.",
                              "Unaweza kukichapisha au kukihifadhi kama PDF. Mtu yeyote anaweza kuthibitisha kuwa ni halali kwa msimbo {code}."],
               "cta": "Fungua cheti"},
        "sample": {"child": "Amani", "course": "My Digital World", "level": "Verified Certificate of Achievement", "code": "C4K7Q2XZ"},
    },

    # ---------------------------------------------------------------- billing
    "receipt": {
        "category": None,
        "en": {"subject": "Payment received: {plan} plan", "heading": "Thank you! The plan is active",
               "paid": "We received KES {amount} for {child}'s {plan} plan.", "free": "{child}'s {plan} plan is free with {discount_note}.",
               "until": "It is active until {date}.", "gift": "This plan is a gift from {sponsor}.", "gift_message": " Their message: “{message}”",
               "paragraphs": [], "cta": "See the receipt",
               "receipt_no": "Receipt number: {n}", "mpesa_code": "M-Pesa code: {n}", "discount": "{note}: KES {n} off"},
        "sw": {"subject": "Malipo yamepokelewa: mpango wa {plan}", "heading": "Asante! Mpango uko hai",
               "paid": "Tumepokea KES {amount} kwa mpango wa {plan} wa {child}.", "free": "Mpango wa {plan} wa {child} ni bure kupitia {discount_note}.",
               "until": "Uko hai hadi {date}.", "gift": "Mpango huu ni zawadi kutoka kwa {sponsor}.", "gift_message": " Ujumbe wao: “{message}”",
               "paragraphs": [], "cta": "Ona risiti",
               "receipt_no": "Nambari ya risiti: {n}", "mpesa_code": "Msimbo wa M-Pesa: {n}", "discount": "{note}: punguzo la KES {n}"},
        "sample": {"plan": "Core", "_paragraphs": ["We received KES 4,000 for Amani's Core plan.", "It is active until 19 November 2026."],
                   "_paragraphs_sw": ["Tumepokea KES 4,000 kwa mpango wa Core wa Amani.", "Uko hai hadi 19 Novemba 2026."]},
    },
    "sponsor_thanks": {
        "category": None,
        "en": {"subject": "Thank you for sponsoring a learner", "heading": "Thank you, {sponsor}!",
               "paragraphs": ["Your gift of KES {amount} gives {child} the {plan} plan on Cloud for Kids.{until}"], "cta": "See the receipt",
               "until": " It is active until {date}."},
        "sw": {"subject": "Asante kwa kumfadhili mwanafunzi", "heading": "Asante, {sponsor}!",
               "paragraphs": ["Zawadi yako ya KES {amount} inampa {child} mpango wa {plan} kwenye Cloud for Kids.{until}"], "cta": "Ona risiti",
               "until": " Uko hai hadi {date}."},
        "sample": {"sponsor": "Uncle Juma", "amount": "4,000", "child": "Amani", "plan": "Core", "until": ""},
    },
    "payment_failed": {
        "category": None,
        "en": {"subject": "Your payment for the {plan} plan did not go through", "heading": "The payment did not go through",
               "paragraphs": ["We did not receive the KES {amount} M-Pesa payment for {child}'s {plan} plan. {reason}",
                              "No money was taken. You can try again in a minute: make sure the phone is on, has enough M-Pesa balance, and enter your PIN when asked."],
               "cta": "Try again", "cancelled": "The request was cancelled on the phone.", "timeout": "The request was not answered in time.",
               "other": "M-Pesa said: {detail}."},
        "sw": {"subject": "Malipo yako ya mpango wa {plan} hayakufanikiwa", "heading": "Malipo hayakufanikiwa",
               "paragraphs": ["Hatukupokea malipo ya M-Pesa ya KES {amount} kwa mpango wa {plan} wa {child}. {reason}",
                              "Hakuna pesa iliyokatwa. Unaweza kujaribu tena baada ya dakika moja: hakikisha simu imewashwa, ina salio la kutosha la M-Pesa, na uweke PIN yako unapoombwa."],
               "cta": "Jaribu tena", "cancelled": "Ombi lilighairiwa kwenye simu.", "timeout": "Ombi halikujibiwa kwa wakati.",
               "other": "M-Pesa ilisema: {detail}."},
        "sample": {"amount": "4,000", "child": "Amani", "plan": "Core", "reason": "The request was cancelled on the phone."},
    },

    # ---------------------------------------------------------------- written by an admin (the assistant's announcements)
    "announcement": {
        "category": "news",
        "en": {"subject": "{subject}", "heading": "{heading}", "paragraphs": []},
        "sw": {"subject": "{subject}", "heading": "{heading}", "paragraphs": []},
        "sample": {"subject": "Open day on Saturday", "heading": "Open day on Saturday",
                   "_paragraphs": ["Come and see what the children have built this term.", "Saturday at 10:00, Sunrise Primary computer lab."]},
    },
}

# What the admin preview page calls each email, grouped for display.
GROUPS = [
    ("Account", ["welcome_learner", "welcome_parent", "welcome_facilitator", "confirm_email", "password_changed", "consent_request",
                 "consent_approved", "consent_declined", "teacher_approved", "admin_new_facilitator", "parent_linked_parent",
                 "parent_linked_learner"]),
    ("Classes", ["assignment_learner", "assignment_parent", "live_scheduled_learner", "live_scheduled_parent", "live_reminder_learner",
                 "live_reminder_parent", "missed_live", "message"]),
    ("Progress and reminders", ["weekly", "monthly", "nudge_learner", "nudge_parent", "nudge_start_learner", "nudge_start_parent",
                                "plan_ending_learner", "plan_ending_parent", "plan_ended_learner", "plan_ended_parent"]),
    ("Celebrations", ["badges_learner", "badges_parent", "certificate_learner", "certificate_parent"]),
    ("Payments", ["receipt", "sponsor_thanks", "payment_failed"]),
    ("Announcements", ["announcement"]),
]


def text(kind, lang, field, **values):
    """One extra string of an entry (e.g. 'due' or 'tomorrow'), formatted."""
    return EMAILS[kind][lang][field].format(**values)
