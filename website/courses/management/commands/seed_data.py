from django.core.management.base import BaseCommand
from django.utils.text import slugify

from accounts.models import User
from core.models import Partner
from courses.models import Badge, Course, Lesson, Tier


def _lesson(title, summary, objectives, big_idea, activity, vocab, quiz):
    """Build a full, detailed lesson record: (title, summary, content)."""
    obj_lines = "\n".join(f"- {o}" for o in objectives)
    vocab_lines = "\n".join(f"- {term}: {definition}" for term, definition in vocab)
    content = (
        f"\U0001F3AF WHAT YOU'LL LEARN\n{obj_lines}\n\n"
        f"\U0001F9E0 THE BIG IDEA\n{big_idea}\n\n"
        f"\U0001F6E0\uFE0F TRY IT YOURSELF\n{activity}\n\n"
        f"\U0001F4DA WORD BANK\n{vocab_lines}\n\n"
        f"\u2705 QUICK CHECK\n{quiz}"
    )
    return (title, summary, content)


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
                    ),
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

                for l_index, (title, summary, content) in enumerate(course_data["lessons"]):
                    Lesson.objects.update_or_create(
                        course=course,
                        slug=slugify(title),
                        defaults={
                            "title": title,
                            "summary": summary,
                            "content": content,
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
