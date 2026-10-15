import base64
import hashlib
import hmac
import json
import time
from datetime import timedelta
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import ClassMembership, Classroom, User

from . import livekit
from .models import LiveAttendance, LiveRoom, LiveSession

PASSWORD = "pw-12345-Zq"
LK = dict(LIVEKIT_URL="wss://c4k-test.livekit.cloud", LIVEKIT_API_KEY="APIkey123", LIVEKIT_API_SECRET="s" * 40)


def decode(token):
    header, claims, signature = token.split(".")
    expected = hmac.new(LK["LIVEKIT_API_SECRET"].encode(), f"{header}.{claims}".encode(), hashlib.sha256).digest()
    assert hmac.compare_digest(expected, livekit._unb64(signature)), "bad signature"
    return json.loads(livekit._unb64(claims))


@override_settings(**LK)
class LiveTestBase(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("mwalimu", password=PASSWORD, role="facilitator", first_name="Grace", last_name="Wanjiru")
        self.kid = User.objects.create_user("amani", password=PASSWORD, role="learner", first_name="Amani", last_name="Otieno")
        self.outsider = User.objects.create_user("baraka", password=PASSWORD, role="learner", first_name="Baraka")
        self.classroom = Classroom.objects.create(facilitator=self.teacher, name="Grade 6 Cloud Club")
        ClassMembership.objects.create(classroom=self.classroom, learner=self.kid)
        self.room = LiveRoom.objects.create(classroom=self.classroom)
        patcher = mock.patch.object(livekit, "_call", return_value={})
        self.api = patcher.start()
        self.addCleanup(patcher.stop)

    def go_live(self):
        return LiveSession.objects.create(room=self.room, started_by=self.teacher)

    def login(self, user):
        self.client.login(username=user.username, password=PASSWORD)

    def calls(self, method):
        return [c.args[1] for c in self.api.call_args_list if c.args[0] == method]


class TokenTests(TestCase):
    @override_settings(**LK)
    def test_join_token_is_signed_with_the_grant(self):
        claims = decode(livekit.join_token("u1", "Amani O", {"room": "c4k-X-1", "canPublish": False}))
        self.assertEqual(claims["iss"], "APIkey123")
        self.assertEqual(claims["sub"], "u1")
        self.assertEqual(claims["video"], {"roomJoin": True, "room": "c4k-X-1", "canPublish": False})
        self.assertGreater(claims["exp"], time.time())

    @override_settings(**LK)
    def test_webhook_signature_and_body_hash_are_checked(self):
        body = b'{"event":"room_finished"}'
        digest = base64.b64encode(hashlib.sha256(body).digest()).decode()
        good = livekit._sign({"iss": "APIkey123", "exp": int(time.time()) + 60, "sha256": digest})
        self.assertEqual(livekit.verify_webhook(body, f"Bearer {good}"), {"event": "room_finished"})
        self.assertIsNone(livekit.verify_webhook(b'{"event":"other"}', good))
        self.assertIsNone(livekit.verify_webhook(body, good[:-3] + "abc"))
        self.assertIsNone(livekit.verify_webhook(body, ""))

    @override_settings(LIVEKIT_URL="wss://x.livekit.cloud/")
    def test_server_url(self):
        self.assertEqual(livekit.server_url(), "https://x.livekit.cloud")


class AccessTests(LiveTestBase):
    def test_short_link_sends_visitors_to_log_in(self):
        response = self.client.get(f"/r/{self.room.code.lower()}/", follow=True)
        self.assertEqual(response.redirect_chain[0][0], reverse("live:room", args=[self.room.code]))
        self.assertIn(reverse("accounts:login"), response.redirect_chain[-1][0])

    def test_learner_outside_the_class_is_turned_away(self):
        self.go_live()
        self.login(self.outsider)
        self.assertEqual(self.client.get(reverse("live:room", args=[self.room.code])).status_code, 403)
        self.assertEqual(self.client.post(reverse("live:token", args=[self.room.code])).status_code, 403)

    def test_learner_waits_until_the_teacher_starts(self):
        self.login(self.kid)
        response = self.client.get(reverse("live:room", args=[self.room.code]))
        self.assertContains(response, "has not started the live class yet")
        self.assertFalse(self.client.get(reverse("live:status", args=[self.room.code])).json()["live"])

    def test_learner_joins_muted_without_rights_to_change_themselves(self):
        session = self.go_live()
        self.login(self.kid)
        self.assertContains(self.client.get(reverse("live:room", args=[self.room.code])), "Join the class")
        data = self.client.post(reverse("live:token", args=[self.room.code])).json()
        claims = decode(data["token"])
        self.assertEqual(data["url"], LK["LIVEKIT_URL"])
        self.assertEqual(claims["sub"], f"u{self.kid.pk}")
        self.assertEqual(claims["name"], "Amani O")
        self.assertFalse(claims["video"]["canPublish"])
        self.assertFalse(claims["video"]["canUpdateOwnMetadata"])
        self.assertNotIn("roomAdmin", claims["video"])
        self.assertEqual(claims["video"]["room"], session.livekit_name)
        self.assertTrue(LiveAttendance.objects.filter(session=session, user=self.kid, is_host=False).exists())

    def test_teacher_gets_admin_token(self):
        self.go_live()
        self.login(self.teacher)
        claims = decode(self.client.post(reverse("live:token", args=[self.room.code])).json()["token"])
        self.assertTrue(claims["video"]["roomAdmin"])
        self.assertTrue(claims["video"]["canPublish"])
        self.assertEqual(claims["name"], "Grace Wanjiru")

    def test_locked_room_keeps_new_learners_out_but_lets_them_back(self):
        session = self.go_live()
        self.room.locked = True
        self.room.save()
        self.login(self.kid)
        self.assertEqual(self.client.post(reverse("live:token", args=[self.room.code])).status_code, 403)
        LiveAttendance.objects.create(session=session, user=self.kid)
        self.assertEqual(self.client.post(reverse("live:token", args=[self.room.code])).status_code, 200)

    def test_removed_learner_cannot_rejoin_this_session(self):
        session = self.go_live()
        LiveAttendance.objects.create(session=session, user=self.kid, removed=True)
        self.login(self.kid)
        self.assertEqual(self.client.get(reverse("live:room", args=[self.room.code])).status_code, 403)
        self.assertEqual(self.client.post(reverse("live:token", args=[self.room.code])).status_code, 403)

    @override_settings(LIVEKIT_URL="")
    def test_not_set_up(self):
        self.login(self.teacher)
        self.assertContains(self.client.get(reverse("live:room", args=[self.room.code])), "not switched on yet")

    def test_forgotten_session_expires(self):
        session = self.go_live()
        LiveSession.objects.filter(pk=session.pk).update(started_at=timezone.now() - timedelta(hours=5))
        self.assertIsNone(self.room.current_session)


class TeacherControlTests(LiveTestBase):
    def test_start_creates_session_and_livekit_room(self):
        self.login(self.teacher)
        response = self.client.post(reverse("live:start", args=[self.classroom.pk]))
        self.assertRedirects(response, reverse("live:room", args=[self.room.code]))
        session = self.room.current_session
        created = self.calls("CreateRoom")[0]
        self.assertEqual(created["name"], session.livekit_name)
        self.assertEqual(json.loads(created["metadata"])["open_mic"], False)
        # Pressing start again rejoins the same class
        self.client.post(reverse("live:start", args=[self.classroom.pk]))
        self.assertEqual(LiveSession.objects.count(), 1)

    def test_only_the_class_teacher_can_start(self):
        other = User.objects.create_user("other", password=PASSWORD, role="facilitator")
        self.login(other)
        self.assertEqual(self.client.post(reverse("live:start", args=[self.classroom.pk])).status_code, 404)

    def test_teacher_class_page_shows_link(self):
        self.login(self.teacher)
        response = self.client.get(reverse("teach:class", args=[self.classroom.pk]))
        self.assertContains(response, f"/r/{self.room.code}/")
        self.assertContains(response, "Start live class")

    def test_allow_and_stop_speaking(self):
        session = self.go_live()
        LiveAttendance.objects.create(session=session, user=self.kid)
        self.login(self.teacher)
        url = reverse("live:control", args=[self.room.code])
        self.assertTrue(self.client.post(url, {"action": "allow_speak", "identity": f"u{self.kid.pk}"}).json()["ok"])
        update = self.calls("UpdateParticipant")[-1]
        self.assertTrue(update["permission"]["can_publish"])
        self.assertEqual(update["permission"]["can_publish_sources"], ["MICROPHONE"])
        self.assertEqual(update["attributes"], {"hand": ""})
        self.assertTrue(LiveAttendance.objects.get(user=self.kid).can_speak)
        self.client.post(url, {"action": "stop_speak", "identity": f"u{self.kid.pk}"})
        self.assertFalse(self.calls("UpdateParticipant")[-1]["permission"]["can_publish"])

    def test_learners_cannot_use_teacher_controls(self):
        self.go_live()
        self.login(self.kid)
        response = self.client.post(reverse("live:control", args=[self.room.code]), {"action": "end"})
        self.assertEqual(response.status_code, 403)

    def test_settings_change_reaches_everyone(self):
        session = self.go_live()
        LiveAttendance.objects.create(session=session, user=self.kid)
        self.api.side_effect = lambda method, payload, grant: (
            {"participants": [{"identity": f"u{self.teacher.pk}"}, {"identity": f"u{self.kid.pk}"}]} if method == "ListParticipants" else {}
        )
        self.login(self.teacher)
        data = self.client.post(reverse("live:control", args=[self.room.code]), {"action": "set", "setting": "open_mic", "value": "1"}).json()
        self.assertTrue(data["settings"]["open_mic"])
        self.assertTrue(json.loads(self.calls("UpdateRoomMetadata")[0]["metadata"])["open_mic"])
        updates = self.calls("UpdateParticipant")
        self.assertEqual([u["identity"] for u in updates], [f"u{self.kid.pk}"])  # the teacher is left alone
        self.assertTrue(updates[0]["permission"]["can_publish"])

    def test_remove_and_end(self):
        session = self.go_live()
        LiveAttendance.objects.create(session=session, user=self.kid)
        self.login(self.teacher)
        url = reverse("live:control", args=[self.room.code])
        self.client.post(url, {"action": "remove", "identity": f"u{self.kid.pk}"})
        self.assertTrue(LiveAttendance.objects.get(user=self.kid).removed)
        self.assertEqual(self.calls("RemoveParticipant")[0]["identity"], f"u{self.kid.pk}")
        self.client.post(url, {"action": "end"})
        session.refresh_from_db()
        self.assertIsNotNone(session.ended_at)
        self.assertEqual(self.calls("DeleteRoom")[0]["room"], session.livekit_name)
        self.assertIsNone(self.room.current_session)

    def test_learner_raises_hand(self):
        self.go_live()
        self.login(self.kid)
        self.assertTrue(self.client.post(reverse("live:hand", args=[self.room.code]), {"up": "1"}).json()["up"])
        update = self.calls("UpdateParticipant")[0]
        self.assertEqual(update["identity"], f"u{self.kid.pk}")
        self.assertTrue(update["attributes"]["hand"])


class WebhookTests(LiveTestBase):
    def post_event(self, event):
        body = json.dumps(event).encode()
        digest = base64.b64encode(hashlib.sha256(body).digest()).decode()
        auth = livekit._sign({"iss": "APIkey123", "exp": int(time.time()) + 60, "sha256": digest})
        return self.client.post(reverse("live:webhook"), body, content_type="application/webhook+json", HTTP_AUTHORIZATION=auth)

    def test_attendance_time_and_room_finished(self):
        session = self.go_live()
        att = LiveAttendance.objects.create(session=session, user=self.kid)
        room = {"name": session.livekit_name}
        participant = {"identity": f"u{self.kid.pk}"}
        self.assertEqual(self.post_event({"event": "participant_joined", "room": room, "participant": participant}).status_code, 200)
        LiveAttendance.objects.filter(pk=att.pk).update(last_joined_at=timezone.now() - timedelta(minutes=30))
        self.post_event({"event": "participant_left", "room": room, "participant": participant})
        att.refresh_from_db()
        self.assertAlmostEqual(att.seconds, 1800, delta=5)
        self.post_event({"event": "room_finished", "room": room})
        session.refresh_from_db()
        self.assertIsNotNone(session.ended_at)

    def test_unsigned_webhook_is_refused(self):
        response = self.client.post(reverse("live:webhook"), b"{}", content_type="application/json")
        self.assertEqual(response.status_code, 401)
