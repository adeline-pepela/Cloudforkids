"""The class chat filter. Learners are children, so the rules are strict: no rude words (English or Kiswahili), and no
phone numbers, email addresses or links, so nobody can pass on contact details or send classmates off the platform.
Admins can add words with the LIVE_BLOCKED_WORDS setting. Blocked messages are saved (flagged) for review, never shown.
"""

import re

from django.conf import settings

# Kept short and obvious on purpose. Matching ignores case, repeated letters and common look-alike characters.
BLOCKED_WORDS = {
    # English
    "fuck", "fucking", "fucker", "motherfucker", "shit", "bullshit", "bitch", "bastard", "asshole", "arsehole", "dick",
    "dickhead", "cock", "pussy", "cunt", "slut", "whore", "porn", "porno", "nude", "nudes", "sex", "sexy", "boobs",
    "penis", "vagina", "rape", "nigga", "nigger", "faggot", "retard", "kill yourself", "kys", "stfu",
    # Kiswahili and Sheng
    "kuma", "kumamako", "kumanyoko", "malaya", "msenge", "mkundu", "matako", "mboro", "mavi", "fala",
    "mjinga", "shenzi", "mshenzi", "nyoko", "kutombwa", "tomba", "kutomba",
}

LOOKALIKES = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s", "!": "i"})
PHONE = re.compile(r"(?:\+?\d[\s\-.]?){9,}")
EMAIL = re.compile(r"[\w.+-]+\s*(?:@|\(at\))\s*[\w-]+\s*(?:\.|\(dot\))\s*\w+", re.I)
LINK = re.compile(r"(?:https?://|www\.)\S+|\b[\w-]+\.(?:com|net|org|co|ke|io|me|ly|gg|app|tv|xyz|info)\b(?:/\S*)?", re.I)
HANDLE = re.compile(r"(?:^|\s)@\w{3,}")


def _normalise(text):
    text = text.lower().translate(LOOKALIKES)
    text = re.sub(r"(.)\1{2,}", r"\1", text)  # "fuuuuck" -> "fuck"
    return text


def _words():
    return BLOCKED_WORDS | {w.strip().lower() for w in settings.LIVE_BLOCKED_WORDS if w.strip()}


def check(text, host=False):
    """None when the message may be shown, otherwise a short reason ('language', 'phone', 'email', 'link')."""
    clean = _normalise(text)
    squashed = re.sub(r"[^a-z ]", "", clean)
    joined = squashed.replace(" ", "")
    for word in _words():
        if " " in word:
            if word in squashed:
                return "language"
        elif re.search(rf"\b{re.escape(word)}\b", squashed) or (len(word) >= 5 and word in joined):
            return "language"
    if host:
        return None  # teachers share links and their contacts on purpose
    if PHONE.search(text):
        return "phone"
    if EMAIL.search(text):
        return "email"
    if LINK.search(text) or HANDLE.search(text):
        return "link"
    return None


REASONS = {
    "language": "Please use kind words. Your message was not sent.",
    "phone": "Phone numbers can't be shared in class chat. Your message was not sent.",
    "email": "Email addresses can't be shared in class chat. Your message was not sent.",
    "link": "Links and usernames can't be shared in class chat. Your message was not sent.",
}
