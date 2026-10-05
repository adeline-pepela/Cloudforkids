"""Kiswahili for wording that is stored in the database (site text, impact numbers, info cards, labs, badges)
and for the titles of the original tiers, courses and lessons. Applied by the migration that adds Kiswahili."""

# English text exactly as stored -> Kiswahili. Merged into the UI translation table.
CONTENT = {
    # site settings (home page)
    "Kenya's first cloud-literacy programme for kids": "Mpango wa kwanza wa Kenya wa elimu ya wingu kwa watoto",
    "Cloud for Kids teaches children aged 7-17 how data, the internet, and the cloud actually work, through school clubs, after-school hubs, and holiday bootcamps aligned to Kenya's CBC/CBE curriculum.":
        "Cloud for Kids huwafundisha watoto wa miaka 7-17 jinsi data, intaneti na wingu vinavyofanya kazi kweli, kupitia klabu za shule, vituo vya baada ya shule na kambi za likizo zinazoendana na mtaala wa CBC/CBE wa Kenya.",
    "Explorer, Foundational, Intermediate, Advanced: a 4-tier pathway from Grade 1 to Grade 12.": "Mgunduzi, Msingi, Kati, Juu: njia ya ngazi 4 kuanzia Darasa la 1 hadi la 12.",
    "Kenya's digital economy is growing faster than its cloud skills": "Uchumi wa kidijitali wa Kenya unakua kwa kasi kuliko ujuzi wa wingu",
    "Why now?": "Kwa nini sasa?",
    "AWS, Microsoft, Samsung and Konza Technopolis are already investing in Kenya's digital skills ecosystem. Cloud for Kids plugs school-age children directly into that pipeline.":
        "AWS, Microsoft, Samsung na Konza Technopolis tayari wanawekeza katika mfumo wa ujuzi wa kidijitali wa Kenya. Cloud for Kids huunganisha watoto wa umri wa shule moja kwa moja na mkondo huo.",
    # about
    "Building Kenya's next generation of cloud-ready digital innovators": "Kujenga kizazi kijacho cha wabunifu wa kidijitali wa Kenya walio tayari kwa wingu",
    "Cloud for Kids is a cloud computing literacy programme for children aged 7 to 17, taught through school partnerships and after-school learning hubs and aligned to Kenya's CBC/CBE curriculum.":
        "Cloud for Kids ni mpango wa elimu ya kompyuta ya wingu kwa watoto wa miaka 7 hadi 17, unaofundishwa kupitia ushirikiano na shule na vituo vya kujifunza baada ya shule, na unaendana na mtaala wa CBC/CBE wa Kenya.",
    "Closing the skills gap at the source": "Kuziba pengo la ujuzi tangu mwanzo",
    "To close Kenya's cloud skills gap at the source by building genuine cloud literacy into childhood education, not just adult retraining.":
        "Kuziba pengo la ujuzi wa wingu la Kenya tangu mwanzo kwa kujenga elimu ya kweli ya wingu katika elimu ya utotoni, si mafunzo ya watu wazima tu.",
    "Every Kenyan child, cloud-ready by 2030: confident to build, store, share and protect what they create online.":
        "Kila mtoto wa Kenya, tayari kwa wingu ifikapo 2030: mwenye ujasiri wa kujenga, kuhifadhi, kushiriki na kulinda anachounda mtandaoni.",
    "Every Kenyan child, cloud-ready by 2030.": "Kila mtoto wa Kenya, tayari kwa wingu ifikapo 2030.",
    "Building Kenya's cloud-ready generation, one classroom, one hub, one child at a time.": "Kujenga kizazi cha Kenya kilicho tayari kwa wingu, darasa moja, kituo kimoja, mtoto mmoja kwa wakati.",
    "Kenya, starting with an urban and peri-urban pilot": "Kenya, tukianza na majaribio mijini na pembezoni mwa miji",
    "We aim to reply within 2 working days": "Tunalenga kujibu ndani ya siku 2 za kazi",
    # impact stats
    "of Kenyan firms cite cloud computing as their #1 skills shortage": "ya kampuni za Kenya zinataja kompyuta ya wingu kuwa pengo lao kuu la ujuzi",
    "of public-school teachers struggle to use classroom technology": "ya walimu wa shule za umma hupata shida kutumia teknolojia darasani",
    "of Kenyan schools are internet-connected": "ya shule za Kenya zina mtandao wa intaneti",
    "of Kenya's population is under 15, a huge, underserved cohort": "ya wakazi wa Kenya wana chini ya miaka 15, kundi kubwa lisilohudumiwa vya kutosha",
    "years old: upper primary to senior secondary": "miaka: shule ya msingi ya juu hadi sekondari ya juu",
    "tiers: Explorer, Foundational, Intermediate, Advanced": "ngazi: Mgunduzi, Msingi, Kati, Juu",
    "mapped to CBC/CBE and the STEM pathway": "inaendana na CBC/CBE na njia ya STEM",
    "of Kenyan firms name cloud as their top skills shortage": "ya kampuni za Kenya hutaja wingu kuwa pengo lao kuu la ujuzi",
    # info cards
    "Hands-on first": "Kwanza kwa vitendo", "Short lessons, activities and quizzes. Learners build and try things, not just read about them.": "Masomo mafupi, shughuli na maswali. Wanafunzi hujenga na kujaribu vitu, si kusoma tu.",
    "Works offline": "Hufanya kazi bila intaneti", "Unplugged activities mean learning continues where connectivity is limited.": "Shughuli zisizotumia kompyuta humaanisha kujifunza kunaendelea mahali penye mtandao hafifu.",
    "Curriculum aligned": "Inaendana na mtaala", "Built around CBC/CBE and the new Senior School STEM pathway.": "Imejengwa kuzunguka CBC/CBE na njia mpya ya STEM ya Sekondari ya Juu.",
    "Safe & kind online": "Salama na wema mtandaoni", "Digital citizenship is part of every tier, from strong passwords to kind words.": "Uraia wa kidijitali ni sehemu ya kila ngazi, kuanzia nenosiri imara hadi maneno ya wema.",
    "First cloud-specific literacy programme": "Mpango wa kwanza wa elimu ya wingu pekee", "First cloud-specific (not just general coding) literacy programme for kids in Kenya.": "Mpango wa kwanza wa elimu ya wingu mahsusi (si uandishi wa programu tu) kwa watoto wa Kenya.",
    "Aligned to CBC/CBE": "Unaendana na CBC/CBE", "Directly aligned to CBC/CBE and the new Senior School STEM pathway.": "Unaendana moja kwa moja na CBC/CBE na njia mpya ya STEM ya Sekondari ya Juu.",
    "A feeder pipeline": "Mkondo wa kuingiza", "A feeder pipeline into AWS Educate, AWS re/Start, and university Computer Science, complementing, not competing with, the existing ecosystem.": "Mkondo unaoelekeza kwenye AWS Educate, AWS re/Start na Sayansi ya Kompyuta chuoni, ukisaidiana na mfumo uliopo, si kushindana nao.",
    "Built for real connectivity": "Imejengwa kwa hali halisi ya mtandao", "Built around Kenya's real connectivity realities with a hybrid offline/online model.": "Imejengwa kuzingatia hali halisi ya mtandao Kenya kwa mfumo mseto wa bila mtandao/mtandaoni.",
    "Parents & guardians": "Wazazi na walezi", "Give your child a head start in a high-demand field.": "Mpe mtoto wako mwanzo mzuri katika taaluma yenye uhitaji mkubwa.",
    "Schools": "Shule", "Ready-made lessons and quizzes that fit your timetable.": "Masomo na maswali tayari yanayofaa ratiba yako.",
    "Facilitators": "Wawezeshaji", "Clear lesson plans and activities to run with a class or club.": "Mipango ya masomo na shughuli zilizo wazi za kuendesha na darasa au klabu.",
    "Partners & donors": "Washirika na wafadhili", "Help fund and grow a cloud-ready generation.": "Saidia kufadhili na kukuza kizazi kilicho tayari kwa wingu.",
    "Head of Curriculum": "Mkuu wa Mtaala", "Head of Partnerships": "Mkuu wa Ushirikiano", "Lead Facilitator": "Mwezeshaji Mkuu",
    "Inputs": "Pembejeo", "Curriculum, trained facilitators, partner schools and hubs, and seed funding.": "Mtaala, wawezeshaji waliofunzwa, shule na vituo washirika, na mtaji wa kuanzia.",
    "Activities": "Shughuli", "In-school clubs, after-school hub sessions, holiday bootcamps, and teacher training.": "Klabu shuleni, vipindi vya vituo baada ya shule, kambi za likizo, na mafunzo ya walimu.",
    "Outputs": "Matokeo ya moja kwa moja", "Learners trained per tier, facilitators & teachers trained, partner schools and hubs established.": "Wanafunzi waliofunzwa kwa kila ngazi, wawezeshaji na walimu waliofunzwa, shule na vituo washirika vilivyoanzishwa.",
    "Outcomes": "Matokeo", "Improved digital & cloud literacy, stronger STEM pathway readiness, increased interest in cloud careers.": "Elimu bora ya kidijitali na wingu, utayari mkubwa wa njia ya STEM, hamu kubwa ya taaluma za wingu.",
    "Impact": "Athari", "A stronger, cloud-skilled Kenyan youth talent pipeline, and a narrower urban-rural digital divide.": "Mkondo imara wa vipaji vya vijana wa Kenya wenye ujuzi wa wingu, na pengo dogo la kidijitali kati ya mijini na vijijini.",
    "Parents asking which tier fits their child": "Wazazi wanaouliza ni ngazi gani inamfaa mtoto wao", "Schools interested in joining the pilot": "Shule zinazotaka kujiunga na majaribio",
    "Teachers who want to facilitate a club": "Walimu wanaotaka kuendesha klabu", "Partners, donors and investors": "Washirika, wafadhili na wawekezaji",
    "General Consultant": "Mshauri Mkuu", "Programme design, curriculum strategy, and investor relations.": "Muundo wa mpango, mkakati wa mtaala, na uhusiano na wawekezaji.",
    # labs
    "Send It to the Cloud": "Itume kwenye Wingu", "Save a photo to the cloud and watch where it travels.": "Hifadhi picha kwenye wingu uone inasafiri wapi.", "How the cloud stores things": "Jinsi wingu linavyohifadhi vitu",
    "Robot Block Coder": "Kuandika Programu kwa Vipande vya Roboti", "Snap blocks together to guide the robot to the cloud.": "Unganisha vipande ili kuongoza roboti hadi wingu.", "Sequences and coding thinking": "Mfuatano na fikra za uandishi wa programu",
    "Password Power-Up": "Nguvu ya Nenosiri", "Build a super-strong password and see how long it would take to crack.": "Tengeneza nenosiri imara sana uone lingechukua muda gani kulivunja.", "Staying safe online": "Kuwa salama mtandaoni",
    "Cloud Services Match": "Oanisha Huduma za Wingu", "Match each cloud service to the job it does best.": "Oanisha kila huduma ya wingu na kazi inayoifanya vizuri zaidi.", "Storage, servers, databases and functions": "Hifadhi, seva, hifadhidata na kazi",
    "Build & Publish a Web Page": "Tengeneza na Uchapishe Ukurasa wa Wavuti", "Write a tiny web page, preview it, then publish it to a pretend cloud address.": "Andika ukurasa mdogo wa wavuti, uutazame, kisha uuchapishe kwenye anwani ya wingu ya kujifanya.", "Hosting a website": "Kuhifadhi tovuti",
    # badges
    "First Lesson": "Somo la Kwanza", "Completed your very first lesson.": "Umekamilisha somo lako la kwanza kabisa.", "Rising Cloud": "Wingu Linalopanda", "Completed 5 lessons.": "Umekamilisha masomo 5.",
    "Cloud Champion": "Bingwa wa Wingu", "Completed 15 lessons across the programme.": "Umekamilisha masomo 15 katika mpango.", "Lab Explorer": "Mgunduzi wa Maabara", "Finished your first Practice Lab.": "Umemaliza Maabara yako ya kwanza ya Mazoezi.",
    "Lab Master": "Bingwa wa Maabara", "Finished every Practice Lab.": "Umemaliza kila Maabara ya Mazoezi.", "3-Day Streak": "Mfululizo wa Siku 3", "Learned three days in a row.": "Umejifunza siku tatu mfululizo.",
    "7-Day Streak": "Mfululizo wa Siku 7", "Learned seven days in a row.": "Umejifunza siku saba mfululizo.",
}

TIERS = {
    "foundational": ("Msingi", "Utangulizi wa vitendo, bila kompyuta, wa jinsi data, hifadhi na wingu vinavyofanya kazi kweli."),
    "intermediate": ("Kati", "Majukwaa ya wingu na uandishi wa programu kwa vitendo: akaunti za kwanza, programu za kwanza, uchapishaji wa kwanza."),
    "advanced": ("Juu", "Kompyuta ya wingu inayotegemea miradi: kuhifadhi tovuti, hifadhidata na huduma za awali za AI/wingu."),
}

COURSES = {
    "what-is-the-cloud-really": ("Wingu ni Nini Hasa?", "Shughuli zisizotumia kompyuta zinazoeleza data, hifadhi na mitandao kwa vitu vya kila siku."),
    "my-first-digital-projects": ("Miradi Yangu ya Kwanza ya Kidijitali", "Miradi rahisi ya ubunifu inayojenga ujasiri wa kutumia vifaa vya kidijitali."),
    "coding-foundations": ("Misingi ya Uandishi wa Programu", "Kutoka uandishi wa vipande hadi programu halisi za Python."),
    "getting-started-in-the-cloud": ("Kuanza Katika Wingu", "Akaunti za kwanza za wingu na miradi midogo ya kwanza iliyohifadhiwa kwenye wingu."),
    "aws-for-kids-explore-amazons-cloud": ("AWS kwa Watoto: Gundua Wingu la Amazon", "Safari ya vitendo katika AWS: ni nini, huduma zake kuu, na miradi yako halisi ya kwanza."),
    "cloud-databases-web-apps": ("Hifadhidata za Wingu na Programu za Wavuti", "Tengeneza na uhifadhi programu rahisi ya wavuti yenye hifadhidata."),
    "ai-cloud-services": ("AI na Huduma za Wingu", "Utangulizi wa huduma za AI zinazofanya kazi kwenye wingu."),
    "capstone-your-cloud-portfolio": ("Mradi wa Mwisho: Jalada Lako la Wingu", "Kusanya kazi zako bora kuwa jalada la AWS Educate, re/Start au maombi ya chuo."),
}

# lesson slug -> Kiswahili title (exam titles are built from the course title)
LESSONS = {
    "where-does-your-data-live": "Data Yako Inaishi Wapi?", "networks-the-internet": "Mitandao na Intaneti", "data-storage-basics": "Misingi ya Data na Hifadhi",
    "being-safe-and-kind-online": "Kuwa Salama na Mwema Mtandaoni", "typing-files-101": "Kuandika na Mafaili 101", "intro-to-scratch": "Utangulizi wa Scratch",
    "show-what-you-know": "Onyesha Unachojua", "from-scratch-to-python": "Kutoka Scratch hadi Python", "variables-loops": "Vigeu na Vitanzi",
    "building-a-simple-program": "Kutengeneza Programu Rahisi", "setting-up-aws-educate": "Kusanidi AWS Educate", "cloud-storage-in-practice": "Hifadhi ya Wingu kwa Vitendo",
    "your-first-hosted-web-page": "Ukurasa Wako wa Kwanza wa Wavuti Uliohifadhiwa", "intro-to-google-cloud-skills-boost": "Utangulizi wa Google Cloud Skills Boost",
    "what-is-aws-and-why-does-it-matter": "AWS ni Nini na Kwa Nini ni Muhimu?", "meet-the-core-aws-services": "Kutana na Huduma Kuu za AWS", "your-aws-educate-account-tour": "Ziara ya Akaunti Yako ya AWS Educate",
    "storing-files-in-the-cloud-with-amazon-s3": "Kuhifadhi Mafaili kwenye Wingu kwa Amazon S3", "building-your-first-website-with-aws": "Kutengeneza Tovuti Yako ya Kwanza kwa AWS",
    "aws-restart-your-future-in-cloud-careers": "AWS re/Start na Mustakabali Wako katika Taaluma za Wingu", "databases-101": "Hifadhidata 101", "designing-a-simple-web-app": "Kubuni Programu Rahisi ya Wavuti",
    "deploying-to-the-cloud": "Kuchapisha Kwenye Wingu", "what-is-cloud-ai": "AI ya Wingu ni Nini?", "trying-a-managed-ai-service": "Kujaribu Huduma ya AI Inayosimamiwa",
    "choosing-your-capstone-project": "Kuchagua Mradi Wako wa Mwisho", "building-your-capstone": "Kutengeneza Mradi Wako wa Mwisho", "presenting-your-portfolio": "Kuwasilisha Jalada Lako",
}
