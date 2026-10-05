from django.db import migrations

TERMS = """
<p>Welcome to Cloud for Kids. These terms explain how the programme works and what we expect from everyone who uses it.
By creating an account you agree to them. If you are a child, please read them with a parent or guardian.</p>

<h2>1. Who can use Cloud for Kids</h2>
<ul>
  <li>Learners are children and young people aged 7 to 17. Learners under 13 need a parent or guardian to approve their account.</li>
  <li>Parents and guardians can follow the progress of their own children.</li>
  <li>Facilitators and teachers run classes. New facilitator accounts are checked and approved by our team before they can use classes.</li>
</ul>

<h2>2. Your account</h2>
<ul>
  <li>Give true information and keep your password private. Do not share your account.</li>
  <li>You are responsible for what happens on your account. Tell us at once if you think someone else has used it.</li>
  <li>We may suspend an account that breaks these terms or puts others at risk.</li>
</ul>

<h2>3. Being kind and safe online</h2>
<ul>
  <li>Be kind. Do not bully, tease or share anything unkind, rude or unsafe.</li>
  <li>Do not share personal details such as your home address, phone number or passwords with other users.</li>
  <li>Learners cannot send messages to other users. Teachers and parents may message each other about learning.</li>
  <li>If something worries you, tell a parent, a teacher or us straight away.</li>
</ul>

<h2>4. Learning content</h2>
<p>Lessons, quizzes, labs and badges belong to Cloud for Kids or its partners. You may use them for your own learning and for teaching your own class,
but you may not copy them to sell or publish elsewhere. Practice Labs are simulations: nothing you do in them affects real cloud accounts or costs money.</p>

<h2>5. Free to use</h2>
<p>Cloud for Kids is free for learners at the moment. If this ever changes we will tell parents first and will never charge a child.</p>

<h2>6. Our responsibility</h2>
<p>We work hard to keep the site correct and available, but we cannot promise it will always be free of errors or interruptions.
Learning progress and badges are provided to encourage learning and are not a school qualification.</p>

<h2>7. Changes and contact</h2>
<p>We may update these terms. If the changes are important we will tell you on the site or by email. Questions? Use the Contact page.</p>
"""

PRIVACY = """
<p>Cloud for Kids takes children's privacy seriously. This policy explains what we collect, why, who sees it, and your rights under
Kenya's Data Protection Act, 2019. It is written to be read by parents and by young people.</p>

<h2>1. What we collect</h2>
<ul>
  <li><strong>Account details:</strong> name, username, email address (a parent's email for learners under 13), password (stored scrambled, never readable), role and phone number if given.</li>
  <li><strong>Learner profile:</strong> date of birth, grade, school, county, parent or guardian contact details and a short "about me", if the family chooses to add them.</li>
  <li><strong>Learning activity:</strong> lessons finished, quiz and exam scores, labs, badges, streaks and the dates and times of activity.</li>
  <li><strong>Class information:</strong> which classes a learner has joined and assignments set by teachers.</li>
  <li><strong>Messages</strong> sent by teachers to parents or learners, and messages sent to us through the Contact form.</li>
</ul>
<p>We do <strong>not</strong> collect photos, location, payment details or anything from a child's device beyond what is needed to run the site.
We do not show advertising and we never sell personal data.</p>

<h2>2. Why we use it</h2>
<ul>
  <li>To run the learning platform: sign-in, progress, quizzes and badges.</li>
  <li>To let parents and teachers follow progress and support the learner.</li>
  <li>To send emails about the account: password resets, approvals, assignments and, unless switched off, progress summaries and reminders.</li>
  <li>To improve the programme and to report overall results (for example the number of learners and lessons completed) to partners. These reports contain totals, not names.</li>
</ul>

<h2>3. Children under 13</h2>
<p>A learner under 13 can only use Cloud for Kids after a parent or guardian has approved the account. We email the parent a link that explains what we collect.
Until the parent approves, the account stays locked. If the parent declines, we delete the account and its data.</p>

<h2>4. Who can see a learner's information</h2>
<ul>
  <li>The learner.</li>
  <li>Parents or guardians who link to the child using the child's family code.</li>
  <li>Facilitators and teachers, but only for learners who joined their class with the class code.</li>
  <li>A small number of Cloud for Kids administrators who look after the platform.</li>
  <li>Our service providers who run the website, database and email delivery for us. They may only use the data to provide those services.</li>
</ul>
<p>Other learners can never see a learner's progress or personal details.</p>

<h2>5. How long we keep it</h2>
<p>We keep account and learning data while the account is active. If an account is deleted, its personal data is removed from our systems,
except what we must keep to meet the law or to keep totals for reports.</p>

<h2>6. Keeping data safe</h2>
<p>Connections to the site are encrypted, passwords are stored scrambled, access is limited by role, and sign-in attempts and password resets are rate limited.
No system is perfect, so please choose a strong password and never share it.</p>

<h2>7. Your rights</h2>
<p>Parents, guardians and young people can ask us to show what we hold, correct it, stop emails, or delete the account.
Email notifications can be switched off with the link at the bottom of any reminder email. To use your other rights, contact us through the Contact page
and we will reply within 30 days.</p>

<h2>8. Changes</h2>
<p>If we change this policy in a way that matters, we will tell you on the site or by email before it takes effect.</p>
"""


def seed(apps, schema_editor):
    Page = apps.get_model("core", "LegalPage")
    Page.objects.get_or_create(slug="terms", defaults={"title": "Terms of Use", "body": TERMS.strip()})
    Page.objects.get_or_create(slug="privacy", defaults={"title": "Privacy Policy", "body": PRIVACY.strip()})


class Migration(migrations.Migration):
    dependencies = [("core", "0007_consent_and_legal")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
