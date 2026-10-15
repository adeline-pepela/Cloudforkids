"""Sealing API keys at rest. The encryption key comes from ASSISTANT_KEY_SECRET, or SECRET_KEY when that is not set,
so changing it makes saved keys unreadable (the settings page then asks for them again)."""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


class KeyUnreadable(Exception):
    pass


def _fernet():
    secret = getattr(settings, "ASSISTANT_KEY_SECRET", "") or settings.SECRET_KEY
    digest = hashlib.sha256(f"c4k-assistant-keys:{secret}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def seal(text):
    return _fernet().encrypt(text.encode()).decode()


def unseal(token):
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError) as err:
        raise KeyUnreadable("This key can no longer be read (the server's secret changed). Add it again.") from err


def fingerprint(provider, model, key):
    """What a successful test is tied to, so Save only accepts the exact key and model that passed."""
    return hashlib.sha256(f"{provider}|{model}|{key}".encode()).hexdigest()
