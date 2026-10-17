"""Django email backend that sends through the Resend HTTP API (https://resend.com/docs/api-reference/emails/send-email).

Set RESEND_API_KEY (and EMAIL_FROM) in .env. No extra package is needed.

- Busy (429) or server errors are retried a few times with a growing pause, so a burst of emails is not lost.
- Addresses that bounced or marked us as spam (EmailSuppression) are skipped.
- Replies go to EMAIL_REPLY_TO, or else the contact email in Site settings.
- Every email is written to the email log (core.EmailLog) with Resend's id, which the webhook uses to record delivery.
"""

import json
import logging
import time
import urllib.error
import urllib.request

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)
API_URL = "https://api.resend.com/emails"
ATTEMPTS = 4
RETRY_CODES = {429, 500, 502, 503, 504}


class ResendEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        sent = 0
        for message in email_messages:
            try:
                sent += bool(self._send(message))
            except Exception:
                logger.exception("Resend could not send '%s' to %s", message.subject, message.to)
                if not self.fail_silently:
                    raise
        return sent

    def _send(self, message):
        from .models import EmailLog, EmailSuppression

        blocked = EmailSuppression.blocked(list(message.to) + list(message.cc))
        to = [a for a in message.to if a.strip().lower() not in blocked]
        cc = [a for a in message.cc if a.strip().lower() not in blocked]
        html = next((content for content, mimetype in getattr(message, "alternatives", []) if mimetype == "text/html"), "")
        log = EmailLog(
            to=", ".join(list(message.to) + list(message.cc))[:500], subject=message.subject[:300],
            kind=getattr(message, "c4k_kind", "") or "", user_id=getattr(message, "c4k_user_id", None),
            text_body=message.body, html_body=html, headers=dict(message.extra_headers or {}),
        )
        if not to:
            log.status, log.error = EmailLog.Status.SKIPPED, "Every address is on the blocked list"
            _save(log)
            return False
        payload = {
            "from": message.from_email or settings.DEFAULT_FROM_EMAIL,
            "to": to,
            "subject": message.subject,
            "text": message.body,
            "reply_to": list(message.reply_to) or _default_reply_to(),
        }
        if cc:
            payload["cc"] = cc
        if html:
            payload["html"] = html
        if message.extra_headers:
            payload["headers"] = dict(message.extra_headers)
        try:
            log.resend_id, log.attempts = self._post(payload)
        except Exception as err:
            log.status, log.error = EmailLog.Status.FAILED, str(err)[:2000]
            _save(log)
            raise
        _save(log)
        return True

    def _post(self, payload):
        """POST to Resend, retrying busy or server errors. Returns (Resend's email id, attempts used)."""
        body = json.dumps(payload).encode("utf-8")
        for attempt in range(1, ATTEMPTS + 1):
            request = urllib.request.Request(API_URL, data=body, method="POST", headers={
                "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                "Content-Type": "application/json",
                "User-Agent": "cloudforkids/1.0",
            })
            try:
                with urllib.request.urlopen(request, timeout=15) as response:
                    return json.loads(response.read() or b"{}").get("id", ""), attempt
            except urllib.error.HTTPError as err:
                detail = err.read().decode("utf-8", "ignore")
                if err.code not in RETRY_CODES or attempt == ATTEMPTS:
                    raise RuntimeError(f"Resend returned {err.code}: {detail}") from err
                wait = _retry_after(err) or 2 ** (attempt - 1)
            except (urllib.error.URLError, TimeoutError) as err:
                if attempt == ATTEMPTS:
                    raise RuntimeError(f"Could not reach Resend: {err}") from err
                wait = 2 ** (attempt - 1)
            logger.warning("Resend busy or unreachable, retrying in %ss (attempt %s of %s)", wait, attempt, ATTEMPTS)
            time.sleep(min(wait, 10))


def _retry_after(err):
    try:
        return float(err.headers.get("retry-after", ""))
    except (TypeError, ValueError):
        return None


def _default_reply_to():
    address = getattr(settings, "EMAIL_REPLY_TO", "")
    if not address:
        from .models import SiteSetting

        address = SiteSetting.load().contact_email
    return [address] if address else []


def _save(log):
    try:
        log.save()
    except Exception:  # the email itself matters more than its log line
        logger.exception("Could not write the email log for '%s'", log.subject)
