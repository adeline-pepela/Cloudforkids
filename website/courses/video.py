"""Lesson videos: YouTube links and uploaded files."""

import re
from urllib.parse import parse_qs, urlparse

from django.core.exceptions import ValidationError

MAX_VIDEO_MB = 200
ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtube-nocookie.com", "www.youtube-nocookie.com"}


def youtube_id(url):
    """The 11-character video id from a watch, share, shorts, live or embed address; '' if it is not a YouTube link."""
    try:
        parts = urlparse((url or "").strip())
    except ValueError:
        return ""
    host = (parts.hostname or "").lower()
    found = ""
    if host == "youtu.be":
        found = parts.path.strip("/").split("/")[0]
    elif host in YOUTUBE_HOSTS:
        segments = [p for p in parts.path.split("/") if p]
        if parts.path.rstrip("/") == "/watch":
            found = (parse_qs(parts.query).get("v") or [""])[0]
        elif len(segments) >= 2 and segments[0] in ("embed", "shorts", "live", "v"):
            found = segments[1]
    return found if ID.match(found) else ""


def validate_video_size(upload):
    if upload.size > MAX_VIDEO_MB * 1024 * 1024:
        raise ValidationError(f"Videos can be at most {MAX_VIDEO_MB} MB. Upload a smaller file or add a YouTube link instead.")
