"""The Explorer tier (Grade 1 to 3, ages 7 to 8): play-based first steps, written in English and Kiswahili.

`install(Tier, Course, Lesson)` works with real or historical models, adds the tier once, and puts it first in the
pathway. Lessons use the same HTML structure as every other lesson, so quizzes, exams and gating work unchanged.
"""

from django.utils.html import escape

from .exams import build_exam_content

ICON = {
    "phone": "f4e2", "laptop": "f455", "tablet": "f5ab", "mouse": "f498", "keyboard": "f450", "cloud": "f29e", "shield": "f52f",
    "robot": "f6b1", "puzzle": "f502", "image": "f429", "lock": "f47a", "heart": "f415", "list": "f475", "repeat": "f130",
    "palette": "f4b0", "music": "f49e", "disk": "f40b", "globe": "f3ef", "smile": "f324", "book": "f192", "pencil": "f4c9",
    "thumbs": "f406", "eye": "f33e", "chat": "f713",
}
BI = {
    "phone": "phone-fill", "laptop": "laptop-fill", "tablet": "tablet-fill", "mouse": "mouse-fill", "keyboard": "keyboard-fill",
    "cloud": "cloud-fill", "shield": "shield-check", "robot": "robot", "puzzle": "puzzle-fill", "image": "image-fill", "lock": "lock-fill",
    "heart": "heart-fill", "list": "list-ol", "repeat": "arrow-repeat", "palette": "palette-fill", "music": "music-note-beamed",
    "disk": "hdd-fill", "globe": "globe2", "smile": "emoji-smile-fill", "book": "book-fill", "pencil": "pencil-fill", "thumbs": "hand-thumbs-up-fill",
    "eye": "eye-fill", "chat": "chat-heart-fill",
}
LABELS = {
    "en": dict(learn="What You'll Learn", idea="The Big Idea", fact="Did You Know?", activity="Try It Yourself", real="Real-World Connection",
               words="Word Bank", words_hint="(tap a card to flip)", pictures="Picture the Ideas", check="Quick Check", reveal="Reveal a model answer",
               quiz="Quiz Time"),
    "sw": dict(learn="Utakachojifunza", idea="Wazo Kuu", fact="Je, Unajua?", activity="Jaribu Mwenyewe", real="Katika Maisha Halisi", words="Maneno Muhimu",
               words_hint="(gusa kadi kuigeuza)", pictures="Tazama Mawazo kwa Picha", check="Jaribio Fupi", reveal="Onyesha jibu la mfano", quiz="Wakati wa Maswali"),
}

TIER = {
    "name": "Explorer", "name_sw": "Mgunduzi", "slug": "explorer", "grade_range": "Grade 1-3",
    "cbc": "Digital Literacy (Core Competency), Lower Primary",
    "summary": "Play-based first steps for ages 7 and 8: meet computers, stay safe online and learn to give clear instructions.",
    "summary_sw": "Hatua za kwanza kwa kucheza kwa umri wa miaka 7 na 8: kutana na kompyuta, kuwa salama mtandaoni na kujifunza kutoa maagizo wazi.",
    "description": "Explorer is for the youngest learners. Everything is short, visual and hands-on, with unplugged activities that need no computer. "
                   "Learners meet computers, practise tapping and typing, find out where their pictures live, learn to stay safe and kind online, "
                   "and take their first steps in coding by giving clear instructions.",
    "icon": "balloon-fill",
}

# Each lesson: (key icons for the picture, objectives, big idea, fact, activity, real world, vocab, picture chips, quick check, quiz)
LESSONS = {
    "what-is-a-computer": {
        "icons": ["phone", "laptop", "tablet"], "duration": 20,
        "en": dict(
            title="What Is a Computer?", summary="Meet computers and find out what they do.",
            caption="Phones, laptops and tablets are all computers.",
            goals=["Name three things that are computers", "Say what a computer does: it follows instructions"],
            idea="A computer is a machine that follows instructions. Phones, tablets and laptops are computers, and so are some toys and the machines in shops. "
                 "A computer cannot think by itself. People give it instructions, called a program, and it does exactly what the instructions say.",
            fact="The first computers were as big as a whole room! Today a computer can fit in your pocket.",
            activity="Play 'Computer or not?' at home or in class. Point at things: a phone, a chair, a radio, a tablet, a cup. Which ones follow instructions? Talk about it with a friend.",
            real="When a shopkeeper takes mobile money on a phone, the phone is a computer following instructions.",
            vocab=[("Computer", "A machine that follows instructions"), ("Program", "A list of instructions for a computer"), ("Screen", "The part you look at to see pictures and words")],
            chips=[("phone", "Phone"), ("laptop", "Laptop"), ("tablet", "Tablet")],
            check=("Can a computer think by itself?", "No. It only follows the instructions people give it."),
            quiz=[("What is a computer?", "A machine that follows instructions", ["A kind of fruit", "A type of shoe", "A very small animal"], "A computer follows instructions that people give it."),
                  ("Which of these is a computer?", "A phone", ["A banana", "A chair", "A pencil"], "A phone follows instructions, so it is a computer."),
                  ("What do we call a list of instructions for a computer?", "A program", ["A picture", "A song", "A snack"], "A list of instructions is called a program.")],
        ),
        "sw": dict(
            title="Kompyuta ni Nini?", summary="Kutana na kompyuta na ujue zinafanya nini.",
            caption="Simu, kompyuta mpakato na tableti zote ni kompyuta.",
            goals=["Taja vitu vitatu ambavyo ni kompyuta", "Eleza kompyuta hufanya nini: hufuata maagizo"],
            idea="Kompyuta ni mashine inayofuata maagizo. Simu, tableti na kompyuta mpakato ni kompyuta, na hata baadhi ya vitu vya kuchezea na mashine za dukani. "
                 "Kompyuta haiwezi kufikiri yenyewe. Watu huipa maagizo, yanayoitwa programu, nayo hufanya hasa yale maagizo yanavyosema.",
            fact="Kompyuta za kwanza zilikuwa kubwa kama chumba kizima! Leo kompyuta inaweza kutoshea mfukoni mwako.",
            activity="Cheza 'Kompyuta au sio?' nyumbani au darasani. Onyesha vitu: simu, kiti, redio, tableti, kikombe. Ni vipi vinavyofuata maagizo? Zungumza na rafiki yako.",
            real="Mwenye duka anapopokea pesa kwa simu, simu hiyo ni kompyuta inayofuata maagizo.",
            vocab=[("Kompyuta", "Mashine inayofuata maagizo"), ("Programu", "Orodha ya maagizo kwa ajili ya kompyuta"), ("Skrini", "Sehemu unayoitazama kuona picha na maneno")],
            chips=[("phone", "Simu"), ("laptop", "Kompyuta mpakato"), ("tablet", "Tableti")],
            check=("Je, kompyuta inaweza kufikiri yenyewe?", "Hapana. Hufuata tu maagizo ambayo watu huipa."),
            quiz=[("Kompyuta ni nini?", "Mashine inayofuata maagizo", ["Aina ya tunda", "Aina ya kiatu", "Mnyama mdogo sana"], "Kompyuta hufuata maagizo ambayo watu huipa."),
                  ("Kipi kati ya hivi ni kompyuta?", "Simu", ["Ndizi", "Kiti", "Penseli"], "Simu hufuata maagizo, kwa hiyo ni kompyuta."),
                  ("Orodha ya maagizo kwa kompyuta inaitwaje?", "Programu", ["Picha", "Wimbo", "Kitafunio"], "Orodha ya maagizo inaitwa programu.")],
        ),
    },
    "tap-click-and-type": {
        "icons": ["mouse", "keyboard", "tablet"], "duration": 20,
        "en": dict(
            title="Tap, Click and Type", summary="Learn how to talk to a computer with your fingers.",
            caption="You can tap, click or type to tell a computer what to do.",
            goals=["Tell the mouse, keyboard and touchscreen apart", "Know when to tap, click and type"],
            idea="We talk to computers with our hands. On a touchscreen you tap with a finger. With a mouse you move the pointer and click. "
                 "With a keyboard you press the keys to type letters and numbers. Go slowly and press one thing at a time.",
            fact="A keyboard has more than 100 keys, but most words use only a few of them.",
            activity="Draw a keyboard on paper. Pretend to type your first name with your fingers, one key at a time. Then draw a mouse and show how it moves the pointer.",
            real="At the bus stop, people tap their phones to pay or to look up the time. They are tapping and typing too.",
            vocab=[("Mouse", "A small tool you move to control the pointer"), ("Keyboard", "Keys you press to type letters and numbers"), ("Touchscreen", "A screen you control by touching it")],
            chips=[("mouse", "Mouse"), ("keyboard", "Keyboard"), ("tablet", "Touchscreen")],
            check=("Which one would you use to write your name?", "The keyboard, by pressing the letter keys one by one."),
            quiz=[("Which part do you use to type letters?", "The keyboard", ["The mouse", "The screen cover", "The charger"], "A keyboard has the keys for letters and numbers."),
                  ("How do you choose something on a touchscreen?", "Tap it with your finger", ["Shout at it", "Shake it", "Blow on it"], "On a touchscreen you tap with a finger."),
                  ("What does a mouse help you do?", "Move the pointer and click", ["Print a photo", "Make a sound", "Charge the computer"], "A mouse moves the pointer and lets you click.")],
        ),
        "sw": dict(
            title="Bonyeza, Gusa na Andika", summary="Jifunze jinsi ya kuzungumza na kompyuta kwa vidole vyako.",
            caption="Unaweza kugusa, kubonyeza au kuandika ili kuiambia kompyuta ifanye nini.",
            goals=["Tofautisha kipanya, kibodi na skrini ya kugusa", "Jua wakati wa kugusa, kubonyeza na kuandika"],
            idea="Tunazungumza na kompyuta kwa mikono yetu. Kwenye skrini ya kugusa unagusa kwa kidole. Kwa kipanya unasogeza kielekezi na kubonyeza. "
                 "Kwa kibodi unabonyeza vitufe kuandika herufi na namba. Nenda polepole na bonyeza kitu kimoja kwa wakati.",
            fact="Kibodi ina vitufe zaidi ya 100, lakini maneno mengi hutumia vichache tu.",
            activity="Chora kibodi kwenye karatasi. Jifanye unaandika jina lako la kwanza kwa vidole, kitufe kimoja kimoja. Kisha chora kipanya na uonyeshe jinsi kinavyosogeza kielekezi.",
            real="Kituoni cha basi, watu hugusa simu zao kulipa au kuangalia saa. Nao wanagusa na kuandika pia.",
            vocab=[("Kipanya", "Kifaa kidogo unachosogeza kuongoza kielekezi"), ("Kibodi", "Vitufe unavyobonyeza kuandika herufi na namba"), ("Skrini ya kugusa", "Skrini unayoiongoza kwa kuigusa")],
            chips=[("mouse", "Kipanya"), ("keyboard", "Kibodi"), ("tablet", "Skrini ya kugusa")],
            check=("Ungetumia kipi kuandika jina lako?", "Kibodi, kwa kubonyeza vitufe vya herufi moja baada ya nyingine."),
            quiz=[("Ni sehemu gani unayotumia kuandika herufi?", "Kibodi", ["Kipanya", "Kifuniko cha skrini", "Chaja"], "Kibodi ina vitufe vya herufi na namba."),
                  ("Unachaguaje kitu kwenye skrini ya kugusa?", "Kukigusa kwa kidole", ["Kukipigia kelele", "Kukitikisa", "Kukipuliza"], "Kwenye skrini ya kugusa unagusa kwa kidole."),
                  ("Kipanya kinakusaidia kufanya nini?", "Kusogeza kielekezi na kubonyeza", ["Kuchapisha picha", "Kutoa sauti", "Kuchaji kompyuta"], "Kipanya husogeza kielekezi na hukuruhusu kubonyeza.")],
        ),
    },
    "where-do-my-pictures-live": {
        "icons": ["image", "disk", "cloud"], "duration": 25,
        "en": dict(
            title="Where Do My Pictures Live?", summary="Find out where your photos and drawings are kept, and what the cloud is.",
            caption="Pictures can live in a device, and also in the cloud.",
            goals=["Say that computers keep things in storage", "Explain the cloud in your own words"],
            idea="When you take a photo, the computer keeps it in storage, like a cupboard inside the device. The cloud is a very big, safe cupboard in a faraway building full of computers. "
                 "The internet is the road that carries your picture there. Because the cloud is far away, you can open the same picture on another phone or tablet.",
            fact="Cloud computers sit in big cool buildings called data centres. There are thousands of them in the world!",
            activity="Draw a picture. Put it in a box (your device). Make a second copy and give it to a friend to keep safe (the cloud). Now ask: if the first drawing gets lost, can you still get it back?",
            real="When a family in Kisumu saves photos to the cloud, a cousin in Nairobi can look at them on another phone.",
            vocab=[("Storage", "A place where a computer keeps things"), ("Cloud", "Computers far away that keep your things safe"), ("Internet", "The big web that connects computers everywhere")],
            chips=[("image", "Picture"), ("disk", "Storage"), ("cloud", "Cloud")],
            check=("Why is it good to keep a copy in the cloud?", "If your device breaks or is lost, your picture is still safe and you can get it back."),
            quiz=[("Where does a computer keep your pictures?", "In storage", ["In the keyboard", "In the speaker", "In the charger"], "Computers keep your things in storage."),
                  ("What is the cloud?", "Computers far away that keep your things safe", ["A cloud in the sky", "A soft pillow", "A kind of rain"], "The cloud is made of computers far away that store things safely."),
                  ("What connects computers all around the world?", "The internet", ["A rope", "A bicycle", "A radio tower only"], "The internet connects computers everywhere.")],
        ),
        "sw": dict(
            title="Picha Zangu Huishi Wapi?", summary="Jua picha na michoro yako huhifadhiwa wapi, na wingu ni nini.",
            caption="Picha zinaweza kukaa kwenye kifaa, na pia kwenye wingu.",
            goals=["Sema kwamba kompyuta huhifadhi vitu kwenye hifadhi", "Eleza wingu kwa maneno yako mwenyewe"],
            idea="Unapopiga picha, kompyuta huihifadhi kwenye hifadhi, kama kabati ndani ya kifaa. Wingu ni kabati kubwa sana na salama kwenye jengo la mbali lililojaa kompyuta. "
                 "Intaneti ni barabara inayobeba picha yako huko. Kwa kuwa wingu liko mbali, unaweza kufungua picha ile ile kwenye simu au tableti nyingine.",
            fact="Kompyuta za wingu hukaa kwenye majengo makubwa yenye ubaridi yanayoitwa vituo vya data. Duniani kuna maelfu yake!",
            activity="Chora picha. Iweke kwenye sanduku (kifaa chako). Tengeneza nakala ya pili umpe rafiki akuhifadhie salama (wingu). Sasa uliza: kama mchoro wa kwanza ukipotea, bado unaweza kuupata tena?",
            real="Familia ya Kisumu inapohifadhi picha kwenye wingu, binamu wa Nairobi anaweza kuzitazama kwenye simu nyingine.",
            vocab=[("Hifadhi", "Mahali ambapo kompyuta huweka vitu"), ("Wingu", "Kompyuta za mbali zinazohifadhi vitu vyako salama"), ("Intaneti", "Mtandao mkubwa unaounganisha kompyuta kila mahali")],
            chips=[("image", "Picha"), ("disk", "Hifadhi"), ("cloud", "Wingu")],
            check=("Kwa nini ni vizuri kuweka nakala kwenye wingu?", "Kifaa chako kikiharibika au kupotea, picha yako bado iko salama na unaweza kuirudisha."),
            quiz=[("Kompyuta huhifadhi picha zako wapi?", "Kwenye hifadhi", ["Kwenye kibodi", "Kwenye spika", "Kwenye chaja"], "Kompyuta huhifadhi vitu vyako kwenye hifadhi."),
                  ("Wingu ni nini?", "Kompyuta za mbali zinazohifadhi vitu vyako salama", ["Wingu angani", "Mto laini wa kulalia", "Aina ya mvua"], "Wingu limetengenezwa kwa kompyuta za mbali zinazohifadhi vitu kwa usalama."),
                  ("Ni nini kinachounganisha kompyuta duniani kote?", "Intaneti", ["Kamba", "Baiskeli", "Mnara wa redio tu"], "Intaneti huunganisha kompyuta kila mahali.")],
        ),
    },
    "staying-safe-and-kind-online": {
        "icons": ["shield", "lock", "heart"], "duration": 25,
        "en": dict(
            title="Staying Safe and Kind Online", summary="Simple rules to keep you safe, and to be kind to others online.",
            caption="Be safe, keep secrets secret and be kind.",
            goals=["Know what to keep private", "Know who to tell when something feels wrong"],
            idea="The internet is fun, and we keep it fun by staying safe and kind. Keep your password and your home address secret. Never share them with someone you only know online. "
                 "If something online makes you scared or sad, tell a grown-up you trust straight away. And be kind: type only the words you would say to a friend's face.",
            fact="A strong password is long and mixes words, numbers and a symbol. Never use your name alone.",
            activity="Play 'Secret or Share?'. A grown-up reads things out: your password, a joke, your home address, a drawing you made, your phone number. Show a lock for secret and a thumbs-up for OK to share.",
            real="Just like we do not give the house key to a stranger, we do not give our passwords to anyone except a parent.",
            vocab=[("Password", "A secret word that keeps your account safe"), ("Private", "Things you keep to yourself, like your address"), ("Kind", "Using friendly words and actions")],
            chips=[("shield", "Safe"), ("lock", "Private"), ("heart", "Kind")],
            check=("What will you do if something online makes you feel scared?", "Tell a grown-up I trust straight away."),
            quiz=[("Who should you tell if something online makes you scared?", "A grown-up you trust", ["Nobody", "A stranger online", "Only your toys"], "Always tell a grown-up you trust."),
                  ("Which of these should you keep secret?", "Your password", ["Your favourite colour", "A drawing you like", "A funny joke"], "A password keeps your account safe, so keep it secret."),
                  ("How should we talk to people online?", "Kindly, like in real life", ["Rudely", "With angry shouting", "By teasing them"], "We are kind online, just like we are kind in real life.")],
        ),
        "sw": dict(
            title="Kuwa Salama na Mwema Mtandaoni", summary="Sheria rahisi za kukuweka salama na kuwa mwema kwa wengine mtandaoni.",
            caption="Kuwa salama, weka siri kuwa siri na uwe mwema.",
            goals=["Jua nini cha kuweka siri", "Jua nani wa kumwambia kitu kikionekana si sawa"],
            idea="Intaneti inafurahisha, na tunaifanya iendelee kufurahisha kwa kuwa salama na wema. Weka nenosiri lako na anwani ya nyumbani kuwa siri. Usiwape kamwe mtu unayemjua mtandaoni tu. "
                 "Kitu mtandaoni kikikuogopesha au kukuhuzunisha, mwambie mtu mzima unayemwamini mara moja. Na uwe mwema: andika maneno ambayo ungemwambia rafiki yako uso kwa uso.",
            fact="Nenosiri imara ni refu na lina maneno, namba na alama. Usitumie jina lako peke yake.",
            activity="Cheza 'Siri au Shiriki?'. Mtu mzima anasoma vitu: nenosiri lako, mzaha, anwani ya nyumbani, mchoro uliochora, namba yako ya simu. Onyesha kufuli kwa siri na kidole gumba juu kwa inafaa kushiriki.",
            real="Kama hatumpi mgeni ufunguo wa nyumba, hatumpi mtu yeyote nenosiri letu isipokuwa mzazi.",
            vocab=[("Nenosiri", "Neno la siri linalolinda akaunti yako"), ("Siri", "Mambo unayoweka kwako, kama anwani yako"), ("Wema", "Kutumia maneno na vitendo vya urafiki")],
            chips=[("shield", "Salama"), ("lock", "Siri"), ("heart", "Wema")],
            check=("Utafanya nini kitu mtandaoni kikikuogopesha?", "Nitamwambia mtu mzima ninayemwamini mara moja."),
            quiz=[("Unapaswa kumwambia nani kitu mtandaoni kikikuogopesha?", "Mtu mzima unayemwamini", ["Hakuna mtu", "Mgeni mtandaoni", "Vitu vyako vya kuchezea tu"], "Mwambie kila wakati mtu mzima unayemwamini."),
                  ("Kipi kati ya hivi unapaswa kuweka siri?", "Nenosiri lako", ["Rangi unayoipenda", "Mchoro unaoupenda", "Mzaha wa kuchekesha"], "Nenosiri hulinda akaunti yako, kwa hiyo liweke siri."),
                  ("Tunapaswa kuzungumzaje na watu mtandaoni?", "Kwa wema, kama maisha halisi", ["Kwa dharau", "Kwa kupiga kelele za hasira", "Kwa kuwatania"], "Tunakuwa wema mtandaoni, kama tunavyokuwa wema maishani.")],
        ),
    },
    "giving-clear-instructions": {
        "icons": ["list", "robot", "puzzle"], "duration": 20,
        "en": dict(
            title="Giving Clear Instructions", summary="Learn how steps in the right order make a job work.",
            caption="Steps in the right order are called an algorithm.",
            goals=["Say what an algorithm is", "Put steps in the right order"],
            idea="Coders write instructions that a computer can follow. A list of steps in the right order is called an algorithm. If the steps are mixed up, the job does not work. "
                 "For washing hands the order is: wet your hands, add soap, rub, rinse, dry. Computers need every step to be clear and in order.",
            fact="A robot will do exactly what you say, even if it is silly. If you tell it to walk into a wall, it will!",
            activity="Be the robot! A friend gives you steps to cross the room. Only move when the step is clear, like 'take two steps forward'. Swap places. Which instructions were easy to follow?",
            real="A recipe for making chapati is an algorithm. If you add the water after baking, the chapati will not turn out right.",
            vocab=[("Instruction", "A clear thing to do"), ("Step", "One small part of a job"), ("Algorithm", "A list of steps in the right order")],
            chips=[("list", "Steps"), ("robot", "Robot"), ("puzzle", "Order")],
            check=("Why do the steps have to be in the right order?", "If they are mixed up, the job will not work."),
            quiz=[("What is an algorithm?", "A list of steps in the right order", ["A kind of dance", "A loud noise", "A new game console"], "An algorithm is steps in the right order."),
                  ("What happens if the steps are in the wrong order?", "The job may not work", ["It always works better", "Nothing changes", "The computer gets tired"], "Steps in the wrong order can stop the job from working."),
                  ("What is the first step to wash your hands?", "Wet your hands", ["Dry your hands", "Put on your shoes", "Walk away from the tap"], "You wet your hands first, then add soap.")],
        ),
        "sw": dict(
            title="Kutoa Maagizo Wazi", summary="Jifunze jinsi hatua zilizopangwa vizuri zinavyofanya kazi ifanikiwe.",
            caption="Hatua zilizo kwa mpangilio sahihi huitwa algorithimu.",
            goals=["Sema algorithimu ni nini", "Panga hatua kwa mpangilio sahihi"],
            idea="Waandishi wa programu huandika maagizo ambayo kompyuta inaweza kufuata. Orodha ya hatua kwa mpangilio sahihi inaitwa algorithimu. Hatua zikichanganyika, kazi haifanyiki. "
                 "Kunawa mikono mpangilio ni: lowesha mikono, weka sabuni, sugua, suuza, kausha. Kompyuta huhitaji kila hatua iwe wazi na kwa mpangilio.",
            fact="Roboti itafanya hasa unachosema, hata kama ni kitu cha kipumbavu. Ukiiambia itembee kwenye ukuta, itatembea!",
            activity="Kuwa roboti! Rafiki anakupa hatua za kuvuka chumba. Sogea tu hatua ikiwa wazi, kama 'chukua hatua mbili mbele'. Badilishaneni nafasi. Ni maagizo gani yalikuwa rahisi kufuata?",
            real="Mapishi ya chapati ni algorithimu. Ukiongeza maji baada ya kuoka, chapati haitatoka vizuri.",
            vocab=[("Agizo", "Kitu wazi cha kufanya"), ("Hatua", "Sehemu ndogo ya kazi"), ("Algorithimu", "Orodha ya hatua kwa mpangilio sahihi")],
            chips=[("list", "Hatua"), ("robot", "Roboti"), ("puzzle", "Mpangilio")],
            check=("Kwa nini hatua lazima ziwe kwa mpangilio sahihi?", "Zikichanganyika, kazi haitafanyika."),
            quiz=[("Algorithimu ni nini?", "Orodha ya hatua kwa mpangilio sahihi", ["Aina ya ngoma", "Kelele kubwa", "Kifaa kipya cha michezo"], "Algorithimu ni hatua kwa mpangilio sahihi."),
                  ("Nini hutokea hatua zikiwa kwa mpangilio usio sahihi?", "Kazi inaweza isifanyike", ["Kila mara hufanya vizuri zaidi", "Hakuna kinachobadilika", "Kompyuta huchoka"], "Hatua zisizo kwa mpangilio zinaweza kuzuia kazi kufanyika."),
                  ("Hatua ya kwanza ya kunawa mikono ni ipi?", "Lowesha mikono yako", ["Kausha mikono yako", "Vaa viatu vyako", "Ondoka kwenye bomba"], "Unalowesha mikono kwanza, kisha unaweka sabuni.")],
        ),
    },
    "patterns-and-repeats": {
        "icons": ["repeat", "palette", "music"], "duration": 20,
        "en": dict(
            title="Patterns and Repeats", summary="Spot patterns and learn why coders love to repeat.",
            caption="A pattern is something that repeats again and again.",
            goals=["Find the next part of a pattern", "Say why coders use repeats"],
            idea="A pattern is something that repeats, like clap, stomp, clap, stomp. Coders use repeats too. Instead of writing 'step forward' ten times, they write it once and say 'repeat 10 times'. "
                 "This saves time and makes the instructions short and neat. Patterns are everywhere: in music, in cloth, in the days of the week.",
            fact="Many beautiful kitenge and kikoi cloths are made from patterns that repeat over and over.",
            activity="Make a pattern with beads, stones or colour pencils: red, blue, red, blue. Ask a friend what comes next. Then make a harder one with three colours.",
            real="A drummer repeats the same beat many times. A computer game repeats the same code to move the clouds again and again.",
            vocab=[("Pattern", "Something that repeats in the same order"), ("Repeat", "Do something again and again"), ("Loop", "A coding word for repeat")],
            chips=[("repeat", "Repeat"), ("palette", "Pattern"), ("music", "Beat")],
            check=("Why is 'repeat 10 times' better than writing the same step ten times?", "It is shorter, quicker to write and easier to read."),
            quiz=[("What comes next? Red, blue, red, blue, red, ...", "Blue", ["Red", "Green", "Yellow"], "The pattern is red, blue, so blue comes next."),
                  ("What does repeat mean?", "Do it again and again", ["Do it only once", "Throw it away", "Hide it"], "Repeat means doing something again and again."),
                  ("Why do coders use repeats?", "So they do not write the same step many times", ["Because computers love noise", "To make the screen dark", "To use up the battery"], "Repeats make code shorter and neater.")],
        ),
        "sw": dict(
            title="Michoro na Kurudia", summary="Tambua michoro na ujifunze kwa nini waandishi wa programu hupenda kurudia.",
            caption="Mchoro ni kitu kinachojirudia tena na tena.",
            goals=["Tafuta sehemu inayofuata ya mchoro", "Sema kwa nini waandishi wa programu hutumia kurudia"],
            idea="Mchoro ni kitu kinachojirudia, kama piga makofi, kanyaga, piga makofi, kanyaga. Waandishi wa programu hutumia kurudia pia. Badala ya kuandika 'songa mbele' mara kumi, wanaandika mara moja na kusema 'rudia mara 10'. "
                 "Hii huokoa muda na kufanya maagizo yawe mafupi na nadhifu. Michoro iko kila mahali: kwenye muziki, kwenye vitambaa, kwenye siku za wiki.",
            fact="Vitenge na kikoi vingi vizuri vimetengenezwa kwa michoro inayojirudia tena na tena.",
            activity="Tengeneza mchoro kwa shanga, mawe au kalamu za rangi: nyekundu, buluu, nyekundu, buluu. Muulize rafiki nini kinafuata. Kisha tengeneza mgumu zaidi wenye rangi tatu.",
            real="Mpiga ngoma hurudia mdundo ule ule mara nyingi. Mchezo wa kompyuta hurudia msimbo ule ule kusogeza mawingu tena na tena.",
            vocab=[("Mchoro", "Kitu kinachojirudia kwa mpangilio ule ule"), ("Rudia", "Fanya kitu tena na tena"), ("Kitanzi", "Neno la uandishi wa programu kwa kurudia")],
            chips=[("repeat", "Rudia"), ("palette", "Mchoro"), ("music", "Mdundo")],
            check=("Kwa nini 'rudia mara 10' ni bora kuliko kuandika hatua ile ile mara kumi?", "Ni fupi, ni haraka kuandika na ni rahisi kusoma."),
            quiz=[("Nini kinafuata? Nyekundu, buluu, nyekundu, buluu, nyekundu, ...", "Buluu", ["Nyekundu", "Kijani", "Njano"], "Mchoro ni nyekundu, buluu, kwa hiyo buluu inafuata."),
                  ("Kurudia kunamaanisha nini?", "Kufanya tena na tena", ["Kufanya mara moja tu", "Kutupa", "Kuficha"], "Kurudia ni kufanya kitu tena na tena."),
                  ("Kwa nini waandishi wa programu hutumia kurudia?", "Ili wasiandike hatua ile ile mara nyingi", ["Kwa sababu kompyuta hupenda kelele", "Kufanya skrini iwe giza", "Kumaliza betri"], "Kurudia hufanya msimbo uwe mfupi na nadhifu.")],
        ),
    },
}

COURSES = [
    {"slug": "my-digital-world", "icon": "tablet-fill",
     "en": ("My Digital World", "Meet computers, learn to tap and type, find out where your pictures live and how to stay safe."),
     "sw": ("Dunia Yangu ya Kidijitali", "Kutana na kompyuta, jifunze kugusa na kuandika, jua picha zako zinaishi wapi na jinsi ya kuwa salama."),
     "lessons": ["what-is-a-computer", "tap-click-and-type", "where-do-my-pictures-live", "staying-safe-and-kind-online"]},
    {"slug": "little-coders", "icon": "robot",
     "en": ("Little Coders", "Play games that teach you to give clear instructions, just like a coder."),
     "sw": ("Wanakodi Wadogo", "Cheza michezo inayokufundisha kutoa maagizo wazi, kama mwandishi wa programu."),
     "lessons": ["giving-clear-instructions", "patterns-and-repeats"]},
]


def _svg(icons):
    glyphs = "".join(
        f'<text x="{x}" y="70" font-size="44" text-anchor="middle" dominant-baseline="middle" fill="var(--sky-dark)" font-family="bootstrap-icons">&#x{ICON[name].upper()};</text>'
        for x, name in zip((70, 150, 230), icons)
    )
    return ('<svg viewBox="0 0 300 140" xmlns="http://www.w3.org/2000/svg" class="lesson-visual-svg" role="img" aria-label="lesson illustration">'
            '<rect x="1" y="1" width="298" height="138" rx="18" fill="var(--sky-light)"/>' + glyphs + "</svg>")


def lesson_html(data, icons, lang):
    L = LABELS[lang]
    e = escape
    vocab = "".join(f'<details class="vocab-card"><summary>{e(t)}</summary><p>{e(d)}</p></details>' for t, d in data["vocab"])
    chips = "".join(
        f'<div class="concept-chip"><span class="chip-emoji"><i class="bi bi-{BI[i]}" aria-hidden="true"></i></span><span class="chip-label">{e(label)}</span></div>'
        for i, label in data["chips"]
    )
    questions = ""
    for prompt, right, wrong, explain in data["quiz"]:
        options = "".join(f'<button type="button" class="mcq-option" data-index="{n}">{e(text)}</button>' for n, text in enumerate([right] + wrong))
        questions += (f'<div class="mcq-question" data-correct="0"><p class="mcq-prompt">{e(prompt)}</p><div class="mcq-options">{options}</div>'
                      f'<div class="mcq-explain"><strong>{e(right)}</strong> - {e(explain)}</div></div>')
    goals = "".join(f"<li>{e(g)}</li>" for g in data["goals"])
    q, a = data["check"]
    return f'''<div class="lesson-content tone-fun">
  <div class="lesson-visual">
    {_svg(icons)}
    <p class="visual-caption">{e(data["caption"])}</p>
  </div>

  <div class="lesson-section">
    <h5 class="section-head"><i class="bi bi-bullseye" aria-hidden="true"></i> {L["learn"]}</h5>
    <ul class="objective-list">{goals}</ul>
  </div>

  <div class="lesson-section">
    <h5 class="section-head"><i class="bi bi-cpu-fill" aria-hidden="true"></i> {L["idea"]}</h5>
    <p>{e(data["idea"])}</p>
  </div>

  <div class="lesson-section fact-box">
    <span class="box-emoji"><i class="bi bi-lightbulb-fill" aria-hidden="true"></i></span>
    <p><strong>{L["fact"]}</strong> {e(data["fact"])}</p>
  </div>

  <div class="lesson-section activity-card">
    <h5 class="section-head"><i class="bi bi-tools" aria-hidden="true"></i> {L["activity"]}</h5>
    <p>{e(data["activity"])}</p>
  </div>

  <div class="lesson-section realworld-box">
    <span class="box-emoji"><i class="bi bi-globe-europe-africa" aria-hidden="true"></i></span>
    <p><strong>{L["real"]}:</strong> {e(data["real"])}</p>
  </div>

  <div class="lesson-section">
    <h5 class="section-head"><i class="bi bi-journal-bookmark-fill" aria-hidden="true"></i> {L["words"]} <span class="hint-text">{L["words_hint"]}</span></h5>
    <div class="vocab-grid">{vocab}</div>
  </div>

  <div class="lesson-section">
    <h5 class="section-head"><i class="bi bi-image-fill" aria-hidden="true"></i> {L["pictures"]}</h5>
    <div class="illustration-grid">{chips}</div>
  </div>

  <div class="lesson-section quiz-card">
    <h5 class="section-head"><i class="bi bi-check-circle-fill" aria-hidden="true"></i> {L["check"]}</h5>
    <p>{e(q)}</p>
    <details class="quiz-reveal">
      <summary>{L["reveal"]}</summary>
      <p>{e(a)}</p>
    </details>
  </div>

  <div class="lesson-section">
    <h5 class="section-head"><i class="bi bi-pencil-square" aria-hidden="true"></i> {L["quiz"]}</h5>
    <div class="mcq-block">{questions}</div>
  </div>
</div>
'''


def install(Tier, Course, Lesson):
    """Add the Explorer tier (once) and make it the first step of the pathway. Returns True if anything was added."""
    if Tier.objects.filter(slug=TIER["slug"]).exists():
        return False
    for tier in Tier.objects.all():  # make room at the start
        tier.order += 1
        tier.save(update_fields=["order"])
    tier = Tier.objects.create(
        name=TIER["name"], name_sw=TIER["name_sw"], slug=TIER["slug"], grade_range=TIER["grade_range"], cbc_alignment=TIER["cbc"],
        summary=TIER["summary"], summary_sw=TIER["summary_sw"], description=TIER["description"], icon=TIER["icon"], order=0,
    )
    for c_order, spec in enumerate(COURSES):
        course = Course.objects.create(
            tier=tier, title=spec["en"][0], title_sw=spec["sw"][0], slug=spec["slug"], summary=spec["en"][1], summary_sw=spec["sw"][1],
            icon=spec["icon"], order=c_order,
        )
        en_exam, sw_exam, pending = [], [], []
        for order, key in enumerate(spec["lessons"]):
            item = LESSONS[key]
            en, sw = item["en"], item["sw"]
            pending.append(Lesson(
                course=course, title=en["title"], title_sw=sw["title"], slug=key, summary=en["summary"], summary_sw=sw["summary"],
                content=lesson_html(en, item["icons"], "en"), content_sw=lesson_html(sw, item["icons"], "sw"),
                duration_minutes=item["duration"], order=order, lesson_type="lesson", pass_score_percent=70,
            ))
        # the module exam: every quiz question of the course, in both languages
        from .exams import QUESTION

        for lang, bucket in (("en", en_exam), ("sw", sw_exam)):
            for key in spec["lessons"]:
                bucket.extend(QUESTION.findall(lesson_html(LESSONS[key][lang], LESSONS[key]["icons"], lang)))
        title_en, title_sw = spec["en"][0], spec["sw"][0]

        class _Titled:  # build_exam_content only needs the course title
            def __init__(self, title):
                self.title = title

        pending.append(Lesson(
            course=course, title=f"Full Module Exam: {title_en}", title_sw=f"Mtihani wa Kozi: {title_sw}", slug=f"full-module-exam-{spec['slug']}",
            summary=f"Check everything you learned in {title_en}.", summary_sw=f"Pima ulichojifunza katika {title_sw}.",
            content=build_exam_content(_Titled(title_en), en_exam, "en"), content_sw=build_exam_content(_Titled(title_sw), sw_exam, "sw"),
            duration_minutes=max(10, len(en_exam) * 2), order=len(spec["lessons"]), lesson_type="exam", pass_score_percent=70,
        ))
        Lesson.objects.bulk_create(pending)  # bulk: no per-lesson signal, the exam is added explicitly above
    return True
