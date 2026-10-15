import base64
import hashlib
import hmac
import json
import time
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import ClassMembership, Classroom, User

from . import livekit
from .models import LiveAttendance, LiveChatMessage, LiveRoom, LiveSession

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
        claims = decode(livekit.join_token("u1", "Amani O.", {"room": "c4k-X-1", "canPublish": False}))
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
        self.assertEqual(claims["name"], "Amani O.")
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
        session = self.go_live()
        LiveAttendance.objects.create(session=session, user=self.kid)
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


class ScheduledLiveClassTests(LiveTestBase):
    def test_teacher_schedules_weekly_live_classes(self):
        self.kid.email = "amani@example.com"
        self.kid.save()
        self.login(self.teacher)
        day = timezone.localdate() + timedelta(days=2)
        self.client.post(reverse("teach:session_add", args=[self.classroom.pk]), {
            "title": "Cloud storage", "date": day.isoformat(), "time": "16:00", "duration_minutes": 60,
            "repeat_weeks": 3, "is_live": "on", "meeting_link": "https://meet.example.com/x",
            "live_link": "own", "passcode": "cloud42", "audience": "class", "chat_enabled": "on",
        })
        sessions = list(self.classroom.sessions.all())
        self.assertEqual(len(sessions), 3)
        self.assertTrue(all(s.is_live and not s.meeting_link for s in sessions))
        meeting = sessions[0].meeting
        self.assertFalse(meeting.is_main)
        self.assertEqual((meeting.title, meeting.passcode), ("Cloud storage", "cloud42"))
        self.assertTrue(all(s.meeting_id == meeting.pk for s in sessions))  # one link for the weekly series
        self.assertNotEqual(meeting.code, self.room.code)
        self.assertEqual(sessions[0].link, reverse("live:room", args=[meeting.code]))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(f"/r/{meeting.code}/", mail.outbox[0].body)
        self.assertIn("passcode to get in is cloud42", mail.outbox[0].body)
        self.assertIn("every week for 3 weeks", mail.outbox[0].body)

        self.login(self.kid)
        page = self.client.get(reverse("dashboard:classes"))
        self.assertContains(page, "cal-chip session live")
        self.assertContains(page, reverse("live:room", args=[meeting.code]))
        self.assertContains(page, "cloud42")

    def test_schedule_on_the_class_link(self):
        self.login(self.teacher)
        day = timezone.localdate() + timedelta(days=2)
        self.client.post(reverse("teach:session_add", args=[self.classroom.pk]), {
            "date": day.isoformat(), "time": "16:00", "duration_minutes": 60, "repeat_weeks": 1, "is_live": "on",
            "live_link": "class",
        })
        ses = self.classroom.sessions.get()
        self.assertIsNone(ses.meeting)
        self.assertEqual(ses.link, reverse("live:room", args=[self.room.code]))

    def test_start_button_shows_near_start_time(self):
        from accounts.models import ClassSession

        ClassSession.objects.create(classroom=self.classroom, starts_at=timezone.now() + timedelta(minutes=10), is_live=True)
        self.login(self.teacher)
        self.assertContains(self.client.get(reverse("teach:class", args=[self.classroom.pk])), "Start now")


class ModerationTests(TestCase):
    def test_filter(self):
        from . import moderation

        self.assertIsNone(moderation.check("Is S3 a cloud storage service?"))
        self.assertEqual(moderation.check("you are a fuuuck"), "language")
        self.assertEqual(moderation.check("wewe ni mjinga"), "language")
        self.assertEqual(moderation.check("sh1t"), "language")
        self.assertEqual(moderation.check("call me 0712 345 678"), "phone")
        self.assertEqual(moderation.check("amani@example.com"), "email")
        self.assertEqual(moderation.check("go to www.example.com"), "link")
        self.assertEqual(moderation.check("add me tiktok.com/x"), "link")
        self.assertIsNone(moderation.check("see https://aws.amazon.com", host=True))
        self.assertIsNone(moderation.check("I scored 100 out of 100 on quiz 3"))
        with override_settings(LIVE_BLOCKED_WORDS=["banana"]):
            self.assertEqual(moderation.check("banana"), "language")


class ClassActivityTests(LiveTestBase):
    def setUp(self):
        super().setUp()
        self.session = self.go_live()
        self.kid_att = LiveAttendance.objects.create(session=self.session, user=self.kid)
        self.host_att = LiveAttendance.objects.create(session=self.session, user=self.teacher, is_host=True)

    def url(self, name):
        return reverse(f"live:{name}", args=[self.room.code])

    def sent(self):
        return [(c.args[1]["room"], json.loads(base64.b64decode(c.args[1]["data"]))) for c in self.api.call_args_list if c.args[0] == "SendData"]

    def test_chat_is_filtered_saved_and_passed_on(self):
        from django.core.cache import cache

        cache.clear()
        self.login(self.kid)
        self.assertTrue(self.client.post(self.url("chat"), {"text": "Hello class"}).json()["ok"])
        room_name, data = self.sent()[-1]
        self.assertEqual(room_name, self.session.livekit_name)
        self.assertEqual(data["msg"]["text"], "Hello class")
        self.assertEqual(data["msg"]["name"], "Amani O.")
        response = self.client.post(self.url("chat"), {"text": "my number is 0712345678"})
        self.assertEqual(response.status_code, 429)  # too fast
        cache.clear()
        response = self.client.post(self.url("chat"), {"text": "my number is 0712345678"})
        self.assertEqual(response.status_code, 400)
        flagged = self.session.chat.get(flagged=True)
        self.assertEqual(flagged.reason, "phone")
        self.assertEqual(self.sent()[-1][1]["type"], "flag")  # the teacher is told
        # chat history comes with the token, without blocked messages
        state = self.client.post(self.url("token")).json()["state"]
        self.assertEqual([m["text"] for m in state["chat"]], ["Hello class"])

    def test_chat_off_and_outsiders(self):
        self.room.chat_enabled = False
        self.room.save()
        self.login(self.kid)
        self.assertEqual(self.client.post(self.url("chat"), {"text": "hi"}).status_code, 403)
        self.login(self.outsider)
        self.assertEqual(self.client.post(self.url("chat"), {"text": "hi"}).status_code, 403)

    def test_poll(self):
        self.login(self.teacher)
        data = self.client.post(self.url("control"), {"action": "poll_start", "question": "Which is cloud storage?", "options": ["S3", "A pen", ""]}).json()
        poll_id = data["poll"]["id"]
        self.assertEqual(data["poll"]["options"], ["S3", "A pen"])
        self.login(self.kid)
        self.client.post(self.url("vote"), {"poll": poll_id, "choice": 0})
        self.client.post(self.url("vote"), {"poll": poll_id, "choice": 1})  # changing your mind is fine
        self.assertEqual(self.sent()[-1][1]["poll"]["counts"], [0, 1])
        self.assertEqual(self.client.post(self.url("vote"), {"poll": poll_id, "choice": 5}).status_code, 400)
        self.login(self.teacher)
        self.assertTrue(self.client.post(self.url("control"), {"action": "poll_close"}).json()["poll"]["closed"])
        self.login(self.kid)
        self.assertEqual(self.client.post(self.url("vote"), {"poll": poll_id, "choice": 0}).status_code, 409)

    def test_launch_lesson_and_results(self):
        from courses.models import Lesson, QuizResult

        lesson = Lesson.objects.first()
        self.login(self.teacher)
        data = self.client.post(self.url("control"), {"action": "launch", "lesson": lesson.pk}).json()
        self.assertEqual(data["launch"]["url"], lesson.get_absolute_url())
        self.assertEqual(self.sent()[-1][1]["type"], "launch")
        QuizResult.objects.create(learner=self.kid, lesson=lesson, score_percent=80, passed=True)
        rows = self.client.get(self.url("results")).json()["rows"]
        self.assertEqual(rows[0]["name"], "Amani O.")
        self.assertEqual(rows[0]["score"], 80)
        self.assertTrue(rows[0]["here"])
        self.login(self.kid)
        self.assertEqual(self.client.post(self.url("token")).json()["state"]["launch"]["id"], data["launch"]["id"])

    def test_breakout_groups(self):
        second = User.objects.create_user("zawadi", password=PASSWORD, role="learner", first_name="Zawadi")
        ClassMembership.objects.create(classroom=self.classroom, learner=second)
        LiveAttendance.objects.create(session=self.session, user=second)
        self.api.side_effect = lambda method, payload, grant: (
            {"participants": [{"identity": f"u{u.pk}"} for u in (self.teacher, self.kid, second)]} if method == "ListParticipants" else {}
        )
        self.login(self.teacher)
        data = self.client.post(self.url("control"), {"action": "groups_start", "count": "2"}).json()
        self.assertEqual(data["groups"]["count"], 2)
        self.assertEqual(len(self.calls("CreateRoom")), 2)
        self.assertEqual(sorted(len(v) for v in data["groups"]["members"].values()), [1, 1])
        self.kid_att.refresh_from_db()
        # The learner's next token is for their group room, where they may talk
        self.login(self.kid)
        token = self.client.post(self.url("token")).json()
        claims = decode(token["token"])
        self.assertEqual(claims["video"]["room"], self.session.room_name(self.kid_att.group))
        self.assertTrue(claims["video"]["canPublish"])
        self.assertEqual(token["group"], self.kid_att.group)
        # The teacher visits a group, then brings everyone back
        self.login(self.teacher)
        self.assertTrue(self.client.post(self.url("control"), {"action": "groups_visit", "group": "1"}).json()["move"])
        data = self.client.post(self.url("control"), {"action": "groups_end"}).json()
        self.assertTrue(data["move"])
        self.assertEqual(LiveAttendance.objects.filter(group__gt=0).count(), 0)
        moved = {r for r, d in self.sent() if d.get("type") == "move"}
        self.assertEqual(moved - {self.session.livekit_name}, {self.session.room_name(1), self.session.room_name(2)})

    @override_settings(LIVE_RECORDING_BUCKET="c4k", LIVE_RECORDING_ACCESS_KEY="AK", LIVE_RECORDING_SECRET="SK",
                       LIVE_RECORDING_ENDPOINT="https://acct.r2.cloudflarestorage.com", LIVE_RECORDING_REGION="auto")
    def test_recording_teacher_only_and_playback(self):
        self.api.side_effect = lambda method, payload, grant, **kw: {"egress_id": "EG_1"} if method == "StartTrackCompositeEgress" else {}
        self.login(self.teacher)
        self.assertTrue(self.client.post(self.url("control"), {"action": "record_start", "audio": "TR_a", "video": "TR_v"}).json()["settings"]["rec"])
        started = self.calls("StartTrackCompositeEgress")[0]
        self.assertEqual((started["audio_track_id"], started["video_track_id"]), ("TR_a", "TR_v"))
        self.assertEqual(started["file_outputs"][0]["s3"]["bucket"], "c4k")
        # LiveKit reports the finished file
        WebhookTests.post_event(self, {"event": "egress_ended", "egressInfo": {
            "egressId": "EG_1", "status": "EGRESS_COMPLETE", "fileResults": [{"filename": "live/x.mp4", "duration": "65000000000", "size": "1000"}]}})
        rec = self.session.recordings.get()
        self.assertEqual((rec.status, rec.duration_seconds, rec.filepath), ("ready", 65, "live/x.mp4"))
        self.room.refresh_from_db()
        self.assertFalse(self.room.recording)
        self.login(self.kid)
        response = self.client.get(reverse("live:recording", args=[rec.pk]))
        self.assertTrue(response["Location"].startswith("https://acct.r2.cloudflarestorage.com/c4k/live/x.mp4?X-Amz-Algorithm=AWS4-HMAC-SHA256"))
        self.assertIn("X-Amz-Signature=", response["Location"])
        self.login(self.outsider)
        self.assertEqual(self.client.get(reverse("live:recording", args=[rec.pk])).status_code, 404)

    def test_recording_needs_storage(self):
        self.login(self.teacher)
        self.assertEqual(self.client.post(self.url("control"), {"action": "record_start"}).status_code, 400)

    def test_teacher_room_page_lists_lessons(self):
        self.login(self.teacher)
        response = self.client.get(self.url("room"))
        self.assertContains(response, "Open a lesson or quiz for everyone")
        self.assertContains(response, "Recording is not switched on")
        self.assertTrue(response.context["config"]["lessons"])

    def test_report_page(self):
        LiveChatMessage.objects.create(session=self.session, user=self.kid, text="bad", flagged=True, reason="language")
        self.login(self.teacher)
        response = self.client.get(reverse("live:report", args=[self.session.pk]))
        self.assertContains(response, "Blocked (language)")
        self.assertContains(response, "Came")
        self.login(self.kid)
        self.assertEqual(self.client.get(reverse("live:report", args=[self.session.pk])).status_code, 404)

    def test_plan_required(self):
        with override_settings(LIVE_CLASSES_REQUIRE_PLAN=True):
            self.login(self.kid)
            self.assertEqual(self.client.post(self.url("token")).status_code, 402)
            self.assertContains(self.client.get(self.url("room")), "part of a plan", status_code=402)
            from billing import services as billing
            from billing.models import Plan

            billing.grant(self.kid, Plan.objects.get(slug="starter"))
            self.assertEqual(self.client.post(self.url("token")).status_code, 200)


class AfterClassTests(LiveTestBase):
    def test_end_gives_badges_xp_and_tells_parents_of_absent_learners(self):
        from accounts.models import ParentLink
        from courses.models import LearnerBadge
        from dashboard.stats import learner_stats

        absent = User.objects.create_user("juma", password=PASSWORD, role="learner", first_name="Juma")
        ClassMembership.objects.create(classroom=self.classroom, learner=absent)
        parent = User.objects.create_user("mama", password=PASSWORD, role="parent", email="mama@example.com")
        ParentLink.objects.create(parent=parent, child=absent)
        session = self.go_live()
        LiveSession.objects.filter(pk=session.pk).update(started_at=timezone.now() - timedelta(minutes=45))
        LiveAttendance.objects.create(session=session, user=self.kid)
        self.login(self.teacher)
        self.client.post(reverse("live:control", args=[self.room.code]), {"action": "end"})
        self.assertTrue(LearnerBadge.objects.filter(learner=self.kid, badge__name="Live Learner").exists())
        self.assertEqual(learner_stats(self.kid)["xp"], 20)
        self.assertEqual([m.to for m in mail.outbox], [["mama@example.com"]])
        self.assertIn("missed", mail.outbox[0].subject)
        # Ending again (or the webhook arriving later) does not send twice
        from .services import finish_session, run_followups

        finish_session(LiveSession.objects.get(pk=session.pk))
        run_followups()
        self.assertEqual(len(mail.outbox), 1)

    def test_short_test_calls_send_nothing(self):
        absent = User.objects.create_user("juma", password=PASSWORD, role="learner", email="juma@example.com")
        ClassMembership.objects.create(classroom=self.classroom, learner=absent)
        self.go_live()
        self.login(self.teacher)
        self.client.post(reverse("live:control", args=[self.room.code]), {"action": "end"})
        self.assertEqual(len(mail.outbox), 0)

    def test_forgotten_class_is_finished_by_the_cron(self):
        session = self.go_live()
        LiveSession.objects.filter(pk=session.pk).update(started_at=timezone.now() - timedelta(hours=5))
        from .services import run_followups

        self.assertEqual(run_followups(), 1)
        session.refresh_from_db()
        self.assertTrue(session.followup_done)
        self.assertIsNotNone(session.ended_at)

    def test_reminder_once_before_a_scheduled_live_class(self):
        import io

        from django.core.management import call_command

        from accounts.models import ClassSession

        self.kid.email = "amani@example.com"
        self.kid.save()
        ClassSession.objects.create(classroom=self.classroom, starts_at=timezone.now() + timedelta(minutes=20), is_live=True)
        ClassSession.objects.create(classroom=self.classroom, starts_at=timezone.now() + timedelta(hours=3), is_live=True)
        call_command("send_notifications", "--live", stdout=io.StringIO())
        call_command("send_notifications", "--live", stdout=io.StringIO())
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(f"/r/{self.room.code}/", mail.outbox[0].body)


class MeetingTests(LiveTestBase):
    def meeting(self, **kw):
        return LiveRoom.objects.create(classroom=self.classroom, is_main=False, title="Revision", **kw)

    def test_passcode_gate(self):
        m = self.meeting(passcode="Cloud42")
        LiveSession.objects.create(room=m, started_by=self.teacher)
        self.login(self.kid)
        url = reverse("live:room", args=[m.code])
        self.assertContains(self.client.get(url), "This meeting has a passcode")
        self.assertEqual(self.client.post(reverse("live:token", args=[m.code])).status_code, 403)
        response = self.client.post(reverse("live:unlock", args=[m.code]), {"passcode": "wrong"})
        self.assertEqual(response["Location"], url + "?wrong=1")
        self.assertContains(self.client.get(response["Location"]), "That passcode is not right")
        self.client.post(reverse("live:unlock", args=[m.code]), {"passcode": " cloud42 "})  # case and spaces do not matter
        self.assertContains(self.client.get(url), "Join the class")
        self.assertEqual(self.client.post(reverse("live:token", args=[m.code])).status_code, 200)
        # the teacher never needs it
        self.login(self.teacher)
        self.assertNotContains(self.client.get(url), "This meeting has a passcode")

    def test_passcode_tries_are_limited(self):
        from django.core.cache import cache

        cache.clear()
        m = self.meeting(passcode="Cloud42")
        self.login(self.kid)
        for _ in range(10):
            self.client.post(reverse("live:unlock", args=[m.code]), {"passcode": "nope"})
        self.client.post(reverse("live:unlock", args=[m.code]), {"passcode": "Cloud42"})
        self.assertFalse(self.client.session.get(f"live-pass-{m.pk}"))

    def test_waiting_room(self):
        m = self.meeting(waiting_room=True)
        session = LiveSession.objects.create(room=m, started_by=self.teacher)
        self.login(self.kid)
        self.assertTrue(self.client.post(reverse("live:token", args=[m.code])).json()["waiting"])
        self.assertEqual(self.calls("SendData")[0]["destination_identities"], [f"u{self.teacher.pk}"])
        self.assertEqual(self.client.post(reverse("live:chat", args=[m.code]), {"text": "hi"}).status_code, 403)
        self.login(self.teacher)
        waiting = self.client.get(reverse("live:lobby", args=[m.code])).json()["waiting"]
        self.assertEqual([(w["name"], w["member"]) for w in waiting], [("Amani O.", True)])
        self.client.post(reverse("live:control", args=[m.code]), {"action": "admit", "identity": f"u{self.kid.pk}"})
        self.login(self.kid)
        self.assertIn("token", self.client.post(reverse("live:token", args=[m.code])).json())
        # denied learners stay out
        second = User.objects.create_user("zawadi", password=PASSWORD, role="learner")
        ClassMembership.objects.create(classroom=self.classroom, learner=second)
        self.login(second)
        self.client.post(reverse("live:token", args=[m.code]))
        self.login(self.teacher)
        self.client.post(reverse("live:control", args=[m.code]), {"action": "deny", "identity": f"u{second.pk}"})
        self.login(second)
        self.assertEqual(self.client.post(reverse("live:token", args=[m.code])).status_code, 403)
        self.assertTrue(LiveAttendance.objects.get(session=session, user=second).removed)

    def test_open_to_any_learner(self):
        m = self.meeting(audience="anyone")
        LiveSession.objects.create(room=m, started_by=self.teacher)
        self.login(self.outsider)
        self.assertEqual(self.client.post(reverse("live:token", args=[m.code])).status_code, 200)
        # the class's own link stays class-only
        self.go_live()
        self.assertEqual(self.client.post(reverse("live:token", args=[self.room.code])).status_code, 403)

    def test_meetings_page_create_edit_start_delete(self):
        from accounts.models import ClassSession

        self.login(self.teacher)
        url = reverse("teach:meetings", args=[self.classroom.pk])
        self.client.post(url, {"title": "Exam revision", "passcode": "abc", "audience": "class", "chat_enabled": "on"})
        self.assertFalse(LiveRoom.objects.filter(is_main=False).exists())  # passcode too short
        self.client.post(url, {"title": "Exam revision", "passcode": "abcd1", "audience": "class", "chat_enabled": "on", "waiting_room": "on"})
        m = LiveRoom.objects.get(is_main=False)
        self.assertTrue(m.waiting_room)
        page = self.client.get(url)
        self.assertContains(page, f"/r/{m.code}/")
        self.assertContains(page, "abcd1")
        self.client.post(reverse("teach:meeting_edit", args=[self.classroom.pk, m.pk]), {"title": "Exam revision", "passcode": "", "audience": "anyone"})
        m.refresh_from_db()
        self.assertEqual((m.passcode, m.audience, m.waiting_room), ("", "anyone", False))
        self.assertRedirects(self.client.post(reverse("live:start_room", args=[m.code])), reverse("live:room", args=[m.code]))
        self.assertEqual(self.calls("CreateRoom")[0]["name"], m.current_session.livekit_name)
        self.client.post(reverse("live:control", args=[m.code]), {"action": "end"})
        ClassSession.objects.create(classroom=self.classroom, starts_at=timezone.now() + timedelta(days=1), is_live=True, meeting=m)
        self.client.post(reverse("teach:meeting_delete", args=[self.classroom.pk, m.pk]))
        self.assertFalse(LiveRoom.objects.filter(pk=m.pk).exists())
        self.assertFalse(ClassSession.objects.exists())
        # the class link cannot be deleted
        self.assertEqual(self.client.post(reverse("teach:meeting_delete", args=[self.classroom.pk, self.room.pk])).status_code, 404)
