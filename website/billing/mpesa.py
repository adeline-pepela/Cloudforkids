"""M-Pesa through Safaricom's Daraja API: Express (STK Push) to collect plan payments, B2C to send money out,
and the account balance query. No extra package is needed.

Settings (from .env):
  MPESA_ENV              sandbox (default) or production
  MPESA_CONSUMER_KEY     from your Daraja app
  MPESA_CONSUMER_SECRET  from your Daraja app
  MPESA_SHORTCODE        the Paybill number (or the Head Office / store number for a Till)
  MPESA_PASSKEY          the Lipa Na M-Pesa Online passkey
  MPESA_TILL_NUMBER      only for a Buy Goods Till: the till that receives the money
  MPESA_CALLBACK_TOKEN   a long random string; it is part of the callback address so outsiders cannot guess it
  MPESA_ACCOUNT_REFERENCE  the account name the payer sees on the PIN prompt (12 characters at most)
  MPESA_INITIATOR_NAME     B2C / balance: the API operator's username from the M-Pesa org portal
  MPESA_SECURITY_CREDENTIAL  B2C / balance: that operator's password encrypted with Safaricom's certificate

Safaricom sends results to SITE_URL + /plans/pay/..., so SITE_URL must be the public https address.
Daraja rejects callback addresses containing words like "mpesa", "safaricom", "sql" or "query", so the paths avoid them.
"""

import base64
import json
import logging
import re
import urllib.error
import urllib.request

from django.conf import settings
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

logger = logging.getLogger(__name__)

BASE_URLS = {"sandbox": "https://sandbox.safaricom.co.ke", "production": "https://api.safaricom.co.ke"}
TOKEN_CACHE_KEY = "mpesa-access-token"


class MpesaError(Exception):
    pass


def configured():
    return all(
        getattr(settings, name, "")
        for name in ("MPESA_CONSUMER_KEY", "MPESA_CONSUMER_SECRET", "MPESA_SHORTCODE", "MPESA_PASSKEY", "MPESA_CALLBACK_TOKEN")
    )


def normalize_phone(raw):
    """07XXXXXXXX, 01XXXXXXXX, +2547XXXXXXXX or 2547XXXXXXXX -> 2547XXXXXXXX (or 2541...). None if it is not a Kenyan mobile."""
    digits = re.sub(r"[\s\-()]", "", raw or "").lstrip("+")
    if re.fullmatch(r"0[17]\d{8}", digits):
        digits = "254" + digits[1:]
    elif re.fullmatch(r"[17]\d{8}", digits):
        digits = "254" + digits
    return digits if re.fullmatch(r"254[17]\d{8}", digits) else None


def payouts_configured():
    return configured() and bool(settings.MPESA_INITIATOR_NAME and settings.MPESA_SECURITY_CREDENTIAL)


def _site_url(name):
    return settings.SITE_URL.rstrip("/") + reverse(name, args=[settings.MPESA_CALLBACK_TOKEN])


def callback_url():
    return _site_url("billing:mpesa_callback")


def _base():
    return BASE_URLS.get(settings.MPESA_ENV, BASE_URLS["sandbox"])


def _request(url, payload=None, headers=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        logger.warning("Daraja %s answered %s: %s", url, exc.code, body)
        try:
            detail = json.loads(body)
        except ValueError:
            detail = {}
        raise MpesaError(detail.get("errorMessage") or detail.get("ResponseDescription") or f"M-Pesa error {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        logger.warning("Daraja %s could not be reached: %s", url, exc)
        raise MpesaError("M-Pesa could not be reached. Please try again in a minute.") from exc


def access_token():
    token = cache.get(TOKEN_CACHE_KEY)
    if token:
        return token
    pair = f"{settings.MPESA_CONSUMER_KEY}:{settings.MPESA_CONSUMER_SECRET}".encode()
    data = _request(
        f"{_base()}/oauth/v1/generate?grant_type=client_credentials",
        headers={"Authorization": "Basic " + base64.b64encode(pair).decode()},
    )
    token = data.get("access_token")
    if not token:
        raise MpesaError("M-Pesa did not issue an access token. Check the consumer key and secret.")
    cache.set(TOKEN_CACHE_KEY, token, max(60, int(data.get("expires_in", 3599)) - 120))
    return token


def _password(timestamp):
    return base64.b64encode(f"{settings.MPESA_SHORTCODE}{settings.MPESA_PASSKEY}{timestamp}".encode()).decode()


def _timestamp():
    return timezone.localtime().strftime("%Y%m%d%H%M%S")  # Africa/Nairobi, as Daraja expects


def stk_push(phone, amount, reference, description):
    """Ask Safaricom to show the payer an M-Pesa PIN prompt. Returns (merchant_request_id, checkout_request_id).
    The payer sees MPESA_ACCOUNT_REFERENCE as the account; `reference` (our payment number) is only used without it."""
    timestamp = _timestamp()
    till = getattr(settings, "MPESA_TILL_NUMBER", "")
    data = _request(
        f"{_base()}/mpesa/stkpush/v1/processrequest",
        {
            "BusinessShortCode": settings.MPESA_SHORTCODE,
            "Password": _password(timestamp),
            "Timestamp": timestamp,
            "TransactionType": "CustomerBuyGoodsOnline" if till else "CustomerPayBillOnline",
            "Amount": int(amount),
            "PartyA": phone,
            "PartyB": till or settings.MPESA_SHORTCODE,
            "PhoneNumber": phone,
            "CallBackURL": callback_url(),
            "AccountReference": (settings.MPESA_ACCOUNT_REFERENCE or reference)[:12],
            "TransactionDesc": description[:13],
        },
        headers={"Authorization": f"Bearer {access_token()}"},
    )
    if str(data.get("ResponseCode")) != "0" or not data.get("CheckoutRequestID"):
        raise MpesaError(data.get("ResponseDescription") or data.get("errorMessage") or "M-Pesa did not accept the request.")
    return data.get("MerchantRequestID", ""), data["CheckoutRequestID"]


def stk_query(checkout_request_id):
    """Ask Safaricom how a request ended. Returns (result_code, result_desc); result_code is None while still waiting."""
    timestamp = _timestamp()
    try:
        data = _request(
            f"{_base()}/mpesa/stkpushquery/v1/query",
            {
                "BusinessShortCode": settings.MPESA_SHORTCODE,
                "Password": _password(timestamp),
                "Timestamp": timestamp,
                "CheckoutRequestID": checkout_request_id,
            },
            headers={"Authorization": f"Bearer {access_token()}"},
        )
    except MpesaError as exc:
        # Daraja answers with an error while the payer has not finished yet ("The transaction is being processed").
        if "process" in str(exc).lower():
            return None, str(exc)
        raise
    code = data.get("ResultCode")
    if code is None or str(code) in STILL_PROCESSING_CODES:
        return None, data.get("ResultDesc", "")
    return str(code), data.get("ResultDesc", "")


def parse_callback(body):
    """The parts of Safaricom's callback we need, or None if it is not an STK callback."""
    try:
        stk = body["Body"]["stkCallback"]
    except (KeyError, TypeError):
        return None
    items = {i.get("Name"): i.get("Value") for i in (stk.get("CallbackMetadata") or {}).get("Item", []) if isinstance(i, dict)}
    return {
        "merchant_request_id": stk.get("MerchantRequestID", ""),
        "checkout_request_id": stk.get("CheckoutRequestID", ""),
        "result_code": str(stk.get("ResultCode", "")),
        "result_desc": stk.get("ResultDesc", ""),
        "receipt": str(items.get("MpesaReceiptNumber") or ""),
        "amount": items.get("Amount"),
        "phone": str(items.get("PhoneNumber") or ""),
    }


# Result codes that mean the payer cancelled the prompt or never answered it (anything else non-zero is a failure).
CANCELLED_CODES = {"1032", "1037"}
# A status query answered with this means the payer has not finished yet.
STILL_PROCESSING_CODES = {"4999"}


# ---------------- B2C: sending money from the shortcode to a phone ----------------

B2C_MIN, B2C_MAX = 10, 150000  # KES per transaction, Safaricom's limits
B2C_COMMANDS = ("BusinessPayment", "SalaryPayment", "PromotionPayment")


def b2c_send(phone, amount, remarks, occasion, originator_id, command="BusinessPayment"):
    """Send money to an M-Pesa number. Returns Safaricom's ConversationID; the outcome arrives later at the result URL."""
    data = _request(
        f"{_base()}/mpesa/b2c/v3/paymentrequest",
        {
            "OriginatorConversationID": originator_id,
            "InitiatorName": settings.MPESA_INITIATOR_NAME,
            "SecurityCredential": settings.MPESA_SECURITY_CREDENTIAL,
            "CommandID": command,
            "Amount": int(amount),
            "PartyA": settings.MPESA_SHORTCODE,
            "PartyB": phone,
            "Remarks": (remarks or "Payout")[:100],
            "QueueTimeOutURL": _site_url("billing:b2c_timeout"),
            "ResultURL": _site_url("billing:b2c_result"),
            "Occasion": (occasion or "")[:100],
        },
        headers={"Authorization": f"Bearer {access_token()}"},
    )
    if str(data.get("ResponseCode")) != "0":
        raise MpesaError(data.get("ResponseDescription") or data.get("errorMessage") or "M-Pesa did not accept the payout.")
    return data.get("ConversationID", "")


def balance_request(originator_id=""):
    """Ask for the shortcode's account balances. The answer arrives later at the balance result URL."""
    data = _request(
        f"{_base()}/mpesa/accountbalance/v1/query",
        {
            "Initiator": settings.MPESA_INITIATOR_NAME,
            "SecurityCredential": settings.MPESA_SECURITY_CREDENTIAL,
            "CommandID": "AccountBalance",
            "PartyA": settings.MPESA_SHORTCODE,
            "IdentifierType": "4",
            "Remarks": "Balance check",
            "QueueTimeOutURL": _site_url("billing:balance_timeout"),
            "ResultURL": _site_url("billing:balance_result"),
        },
        headers={"Authorization": f"Bearer {access_token()}"},
    )
    if str(data.get("ResponseCode")) != "0":
        raise MpesaError(data.get("ResponseDescription") or data.get("errorMessage") or "M-Pesa did not accept the balance request.")
    return data.get("ConversationID", "")


def parse_result(body):
    """The parts of a B2C / balance result we need, or None if it is not one."""
    try:
        result = body["Result"]
    except (KeyError, TypeError):
        return None
    params = (result.get("ResultParameters") or {}).get("ResultParameter") or []
    if isinstance(params, dict):  # a single parameter comes without the list
        params = [params]
    return {
        "result_code": str(result.get("ResultCode", "")),
        "result_desc": str(result.get("ResultDesc", "")),
        "originator_id": str(result.get("OriginatorConversationID", "")),
        "conversation_id": str(result.get("ConversationID", "")),
        "transaction_id": str(result.get("TransactionID", "")),
        "params": {p.get("Key"): p.get("Value") for p in params if isinstance(p, dict)},
    }


def parse_balances(text):
    """'Working Account&KES&700.00&700.00&0.00&0.00|Utility Account&KES&...' -> {"Working Account": 700.0, ...}."""
    balances = {}
    for part in str(text or "").split("|"):
        fields = part.split("&")
        if len(fields) >= 3:
            try:
                balances[fields[0].strip()] = float(fields[2])
            except ValueError:
                pass
    return balances
