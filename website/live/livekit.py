"""A small LiveKit client: signed join tokens, the room server API (Twirp over HTTPS) and webhook checks.

Written with the standard library only, like billing/mpesa.py, so there is no extra package to install.
Docs: https://docs.livekit.io/home/get-started/authentication/ and https://docs.livekit.io/reference/server/server-apis/
"""

import base64
import datetime
import hashlib
import hmac
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

TOKEN_TTL = 6 * 60 * 60  # long enough for a class plus reconnects
ADMIN_TTL = 10 * 60


class LiveKitError(Exception):
    pass


def configured():
    return all(getattr(settings, name, "") for name in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"))


def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(claims):
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64(json.dumps(claims, separators=(",", ":")).encode())
    signature = hmac.new(settings.LIVEKIT_API_SECRET.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
    return f"{header}.{body}.{_b64(signature)}"


def join_token(identity, name, grant, metadata=""):
    """A token the browser uses to join one room. `grant` holds LiveKit video grant keys (roomJoin is added here)."""
    now = int(time.time())
    return _sign({
        "iss": settings.LIVEKIT_API_KEY, "sub": identity, "name": name, "metadata": metadata,
        "nbf": now - 10, "exp": now + TOKEN_TTL, "video": {"roomJoin": True, **grant},
    })


def server_url():
    """wss://project.livekit.cloud -> https://project.livekit.cloud (the server API lives on the same host)."""
    url = settings.LIVEKIT_URL.rstrip("/")
    if url.startswith("wss://"):
        return "https://" + url[6:]
    if url.startswith("ws://"):
        return "http://" + url[5:]
    return url


def _call(method, payload, grant, service="RoomService"):
    now = int(time.time())
    token = _sign({"iss": settings.LIVEKIT_API_KEY, "nbf": now - 10, "exp": now + ADMIN_TTL, "video": grant})
    req = urllib.request.Request(
        f"{server_url()}/twirp/livekit.{service}/{method}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        logger.warning("LiveKit %s answered %s: %s", method, exc.code, body)
        try:
            detail = json.loads(body).get("msg", "")
        except ValueError:
            detail = ""
        raise LiveKitError(detail or f"LiveKit error {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        logger.warning("LiveKit %s could not be reached: %s", method, exc)
        raise LiveKitError("The live class service could not be reached. Please try again.") from exc


def _admin(method, room, payload):
    return _call(method, {"room": room, **payload}, {"roomAdmin": True, "room": room})


def create_room(name, metadata, max_participants, empty_timeout=10 * 60):
    return _call("CreateRoom", {
        "name": name, "metadata": metadata, "max_participants": max_participants,
        "empty_timeout": empty_timeout,  # close the room this long after everyone has left
        "departure_timeout": 60,
    }, {"roomCreate": True})


def delete_room(name):
    return _call("DeleteRoom", {"room": name}, {"roomCreate": True})


def update_room_metadata(name, metadata):
    return _admin("UpdateRoomMetadata", name, {"metadata": metadata})


def list_participants(name):
    return _admin("ListParticipants", name, {}).get("participants", [])


def update_participant(name, identity, permission=None, attributes=None):
    payload = {"identity": identity}
    if permission is not None:
        payload["permission"] = permission
    if attributes is not None:
        payload["attributes"] = attributes
    return _admin("UpdateParticipant", name, payload)


def mute_track(name, identity, track_sid):
    return _admin("MutePublishedTrack", name, {"identity": identity, "track_sid": track_sid, "muted": True})


def remove_participant(name, identity):
    return _admin("RemoveParticipant", name, {"identity": identity})


def send_data(name, payload, to=None, topic="c4k"):
    """Send a message from the server to everyone in a room (or only to the identities in `to`)."""
    body = {
        "data": base64.b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode(),
        "kind": "RELIABLE", "topic": topic,
    }
    if to:
        body["destination_identities"] = list(to)
    return _admin("SendData", name, body)


# ---------------- recording (Egress) to S3-compatible storage ----------------

def recording_configured():
    return configured() and all(
        getattr(settings, name, "") for name in ("LIVE_RECORDING_BUCKET", "LIVE_RECORDING_ACCESS_KEY", "LIVE_RECORDING_SECRET")
    )


def start_recording(room, audio_track, video_track, filepath):
    """Record one audio and one video track (the teacher's) to an MP4 in the bucket. Returns LiveKit's egress id."""
    s3 = {
        "access_key": settings.LIVE_RECORDING_ACCESS_KEY, "secret": settings.LIVE_RECORDING_SECRET,
        "region": settings.LIVE_RECORDING_REGION, "bucket": settings.LIVE_RECORDING_BUCKET,
    }
    if settings.LIVE_RECORDING_ENDPOINT:
        s3.update(endpoint=settings.LIVE_RECORDING_ENDPOINT, force_path_style=True)
    payload = {"room_name": room, "file_outputs": [{"file_type": "MP4", "filepath": filepath, "s3": s3}]}
    if audio_track:
        payload["audio_track_id"] = audio_track
    if video_track:
        payload["video_track_id"] = video_track
    info = _call("StartTrackCompositeEgress", payload, {"roomRecord": True, "room": room}, service="Egress")
    egress_id = info.get("egress_id") or info.get("egressId")
    if not egress_id:
        raise LiveKitError("Recording did not start.")
    return egress_id


def stop_recording(egress_id):
    return _call("StopEgress", {"egress_id": egress_id}, {"roomRecord": True}, service="Egress")


def recording_url(key, expires=3600):
    """A link that plays a private recording for an hour (AWS Signature Version 4, query-string form)."""
    region = settings.LIVE_RECORDING_REGION or "auto"
    bucket = settings.LIVE_RECORDING_BUCKET
    path_key = urllib.parse.quote(key.lstrip("/"), safe="/~")
    if settings.LIVE_RECORDING_ENDPOINT:
        parsed = urllib.parse.urlparse(settings.LIVE_RECORDING_ENDPOINT)
        host, path = parsed.netloc, f"/{bucket}/{path_key}"
        scheme = parsed.scheme or "https"
    else:
        host, path, scheme = f"{bucket}.s3.{region}.amazonaws.com", f"/{path_key}", "https"
    now = datetime.datetime.now(datetime.timezone.utc)
    stamp, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    scope = f"{day}/{region}/s3/aws4_request"
    query = {
        "X-Amz-Algorithm": "AWS4-HMAC-SHA256", "X-Amz-Credential": f"{settings.LIVE_RECORDING_ACCESS_KEY}/{scope}",
        "X-Amz-Date": stamp, "X-Amz-Expires": str(expires), "X-Amz-SignedHeaders": "host",
    }
    canonical_query = "&".join(f"{urllib.parse.quote(k, safe='~')}={urllib.parse.quote(v, safe='~')}" for k, v in sorted(query.items()))
    canonical = "\n".join(["GET", path, canonical_query, f"host:{host}", "", "host", "UNSIGNED-PAYLOAD"])
    to_sign = "\n".join(["AWS4-HMAC-SHA256", stamp, scope, hashlib.sha256(canonical.encode()).hexdigest()])

    def _h(key_bytes, msg):
        return hmac.new(key_bytes, msg.encode(), hashlib.sha256).digest()

    signing_key = _h(_h(_h(_h(f"AWS4{settings.LIVE_RECORDING_SECRET}".encode(), day), region), "s3"), "aws4_request")
    signature = hmac.new(signing_key, to_sign.encode(), hashlib.sha256).hexdigest()
    return f"{scheme}://{host}{path}?{canonical_query}&X-Amz-Signature={signature}"


def verify_webhook(body, auth_header):
    """The event LiveKit posted, or None when the signature or the body hash does not match."""
    token = (auth_header or "").removeprefix("Bearer ").strip()
    try:
        header, claims, signature = token.split(".")
        expected = hmac.new(settings.LIVEKIT_API_SECRET.encode(), f"{header}.{claims}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _unb64(signature)):
            return None
        data = json.loads(_unb64(claims))
    except (ValueError, TypeError):
        return None
    if data.get("iss") != settings.LIVEKIT_API_KEY or data.get("exp", 0) < time.time() - 60:
        return None
    digest = base64.b64encode(hashlib.sha256(body).digest()).decode()
    if not hmac.compare_digest(digest, data.get("sha256", "")):
        return None
    try:
        return json.loads(body)
    except ValueError:
        return None
