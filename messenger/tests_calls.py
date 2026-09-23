from django.contrib.auth import get_user_model
from rest_framework.test import APIClient, APITestCase

from .models import CallSession, CallSessionParticipant, Conversation, ConversationParticipant


User = get_user_model()


class CallLifecycleTests(APITestCase):
    def setUp(self):
        self.caller = User.objects.create_user(username="caller", password="pass12345")
        self.peer = User.objects.create_user(username="peer", password="pass12345")
        self.other = User.objects.create_user(username="other", password="pass12345")

        self.conversation = Conversation.objects.create(
            type=Conversation.Type.GROUP,
            title="Call test",
            created_by=self.caller,
        )
        for user, role in (
            (self.caller, ConversationParticipant.Role.OWNER),
            (self.peer, ConversationParticipant.Role.MEMBER),
            (self.other, ConversationParticipant.Role.MEMBER),
        ):
            ConversationParticipant.objects.create(
                conversation=self.conversation,
                user=user,
                role=role,
            )
        self.client = APIClient()

    def _url(self, suffix="call/"):
        return f"/api/messenger/conversations/{self.conversation.id}/{suffix}"

    def test_group_member_can_leave_without_ending_session(self):
        self.client.force_authenticate(self.caller)
        started = self.client.post(
            self._url(),
            {"video": False, "audio": True},
            format="json",
        )
        self.assertEqual(started.status_code, 200)
        call_id = started.data["data"]["call_id"]

        self.client.force_authenticate(self.peer)
        joined = self.client.get(
            self._url("call/join/") + f"?call_id={call_id}",
        )
        self.assertEqual(joined.status_code, 200)

        self.client.force_authenticate(self.caller)
        left = self.client.post(
            self._url("call/end/"),
            {"call_id": call_id, "reason": "ended"},
            format="json",
        )
        self.assertEqual(left.status_code, 200)
        self.assertTrue(left.data["data"]["active"])

        session = CallSession.objects.get(public_id=call_id)
        self.assertEqual(session.status, CallSession.Status.ACTIVE)
        self.assertTrue(
            CallSessionParticipant.objects.get(call=session, user=self.caller).left_at
        )
        self.assertIsNone(
            CallSessionParticipant.objects.get(call=session, user=self.peer).left_at
        )

        self.client.force_authenticate(self.peer)
        active = self.client.get(self._url("call/active/"))
        self.assertEqual(active.status_code, 200)
        self.assertTrue(active.data["data"]["active"])
        self.assertTrue(active.data["data"]["participant_active"])

        ended = self.client.post(
            self._url("call/end/"),
            {"call_id": call_id, "reason": "ended"},
            format="json",
        )
        self.assertEqual(ended.status_code, 200)
        self.assertFalse(ended.data["data"]["active"])
        self.assertEqual(
            CallSession.objects.get(public_id=call_id).status,
            CallSession.Status.ENDED,
        )

    def test_boolean_strings_are_parsed_as_booleans(self):
        self.client.force_authenticate(self.caller)
        response = self.client.post(
            self._url(),
            {"video": "false", "audio": "false"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["data"]["media"]["video"])
        self.assertFalse(response.data["data"]["media"]["audio"])

        call = CallSession.objects.get(public_id=response.data["data"]["call_id"])
        self.assertFalse(call.is_video)


    def test_group_member_can_decline_without_ending_session(self):
        self.client.force_authenticate(self.caller)
        started = self.client.post(
            self._url(),
            {"video": True, "audio": True},
            format="json",
        )
        self.assertEqual(started.status_code, 200)
        call_id = started.data["data"]["call_id"]

        self.client.force_authenticate(self.peer)
        declined = self.client.post(
            self._url("call/end/"),
            {"call_id": call_id, "reason": "declined"},
            format="json",
        )
        self.assertEqual(declined.status_code, 200)
        self.assertTrue(declined.data["data"]["active"])
        self.assertEqual(
            CallSession.objects.get(public_id=call_id).status,
            CallSession.Status.RINGING,
        )
        self.assertTrue(
            CallSessionParticipant.objects.get(
                call__public_id=call_id,
                user=self.peer,
            ).left_at
        )

        active = self.client.get(self._url("call/active/"))
        self.assertEqual(active.status_code, 200)
        self.assertTrue(active.data["data"]["active"])
        self.assertEqual(active.data["data"]["participant_state"], "left")
