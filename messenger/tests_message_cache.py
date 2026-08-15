"""
Tests for the Redis hot-cache of recent messages.

These tests are designed to run with a real Redis (the same instance used by
django-redis).  If Redis is unavailable the tests that need it are skipped
so CI without Redis still passes the rest of the suite.
"""
from __future__ import annotations

from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import Conversation, ConversationParticipant, Message, MessageReaction
from .message_cache import MessageCacheService, _redis, _ids_key, _meta_key, _msg_key

User = get_user_model()


def redis_available() -> bool:
    r = _redis()
    if not r:
        return False
    try:
        return bool(r.ping())
    except Exception:
        return False


@override_settings(MESSAGE_CACHE_SIZE=5, MESSAGE_CACHE_TTL=300)
class MessageCacheServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.u1 = User.objects.create_user(username="alice", password="x")
        cls.u2 = User.objects.create_user(username="bob", password="x")
        cls.conv = Conversation.objects.create(type=Conversation.Type.DIRECT)
        ConversationParticipant.objects.create(
            conversation=cls.conv, user=cls.u1, role="member"
        )
        ConversationParticipant.objects.create(
            conversation=cls.conv, user=cls.u2, role="member"
        )

    def setUp(self):
        if not redis_available():
            self.skipTest("Redis not available")
        MessageCacheService.invalidate_chat_cache(self.conv.id)

    def tearDown(self):
        if redis_available():
            MessageCacheService.invalidate_chat_cache(self.conv.id)

    def _make_msgs(self, n=7):
        msgs = []
        for i in range(n):
            m = Message.objects.create(
                conversation=self.conv,
                sender=self.u1,
                body=f"msg-{i}",
            )
            msgs.append(m)
        return msgs

    # 1. Cache miss → populate → hit
    def test_cache_miss_then_hit(self):
        msgs = self._make_msgs(5)
        # Nothing cached yet
        self.assertIsNone(
            MessageCacheService.get_cached_messages(self.conv.id, None, 5)
        )
        MessageCacheService.cache_messages(self.conv.id, msgs)
        result = MessageCacheService.get_cached_messages(self.conv.id, None, 5)
        self.assertIsNotNone(result)
        data, has_more, next_before = result
        self.assertEqual(len(data), 5)
        self.assertFalse(has_more)
        self.assertEqual([d["body"] for d in data], [f"msg-{i}" for i in range(5)])

    # 2. Range inside cache
    def test_range_inside_cache(self):
        msgs = self._make_msgs(5)
        MessageCacheService.cache_messages(self.conv.id, msgs)
        # before_id = last msg → should return the previous ones
        before = msgs[-1].id
        result = MessageCacheService.get_cached_messages(self.conv.id, before, 3)
        self.assertIsNotNone(result)
        data, has_more, _ = result
        self.assertEqual(len(data), 3)
        self.assertTrue(has_more)  # more older messages exist in the window

    # 3. Range outside cache → miss
    def test_range_outside_cache(self):
        msgs = self._make_msgs(5)
        MessageCacheService.cache_messages(self.conv.id, msgs)
        # before_id smaller than min_id → miss
        min_id = msgs[0].id
        result = MessageCacheService.get_cached_messages(self.conv.id, min_id, 3)
        # is_range_cached returns False when before_id <= min_id
        self.assertIsNone(result)

    # 4. add_message slides the window
    def test_add_message_slides_window(self):
        msgs = self._make_msgs(5)
        MessageCacheService.cache_messages(self.conv.id, msgs)
        new = Message.objects.create(
            conversation=self.conv, sender=self.u1, body="newest"
        )
        MessageCacheService.add_message(new)
        meta = MessageCacheService.get_meta(self.conv.id)
        self.assertEqual(meta["count"], 5)  # still size 5
        self.assertEqual(meta["max_id"], new.id)
        # oldest should have been evicted
        result = MessageCacheService.get_cached_messages(self.conv.id, None, 5)
        bodies = [d["body"] for d in result[0]]
        self.assertNotIn("msg-0", bodies)
        self.assertIn("newest", bodies)

    # 5. edit inside cache
    def test_update_message_in_cache(self):
        msgs = self._make_msgs(3)
        MessageCacheService.cache_messages(self.conv.id, msgs)
        target = msgs[1]
        target.body = "edited"
        target.is_edited = True
        target.save(update_fields=["body", "is_edited", "updated_at"])
        MessageCacheService.update_message(target)
        result = MessageCacheService.get_cached_messages(self.conv.id, None, 3)
        bodies = {d["id"]: d for d in result[0]}
        self.assertEqual(bodies[target.id]["body"], "edited")
        self.assertTrue(bodies[target.id]["is_edited"])

    # 6. edit outside cache → no-op (no error)
    def test_update_message_outside_cache(self):
        msgs = self._make_msgs(3)
        MessageCacheService.cache_messages(self.conv.id, msgs)
        # Create an old message that is not in the window (simulate by
        # invalidating and only caching the newest 2)
        MessageCacheService.invalidate_chat_cache(self.conv.id)
        MessageCacheService.cache_messages(self.conv.id, msgs[-2:])
        # update the oldest (not in cache)
        old = msgs[0]
        old.body = "should-not-appear"
        old.save(update_fields=["body", "updated_at"])
        MessageCacheService.update_message(old)  # must not raise
        result = MessageCacheService.get_cached_messages(self.conv.id, None, 5)
        bodies = [d["body"] for d in result[0]]
        self.assertNotIn("should-not-appear", bodies)

    # 7. delete inside cache
    def test_delete_message_in_cache(self):
        msgs = self._make_msgs(4)
        MessageCacheService.cache_messages(self.conv.id, msgs)
        MessageCacheService.delete_message(self.conv.id, msgs[1].id)
        meta = MessageCacheService.get_meta(self.conv.id)
        self.assertEqual(meta["count"], 3)
        result = MessageCacheService.get_cached_messages(self.conv.id, None, 5)
        ids = [d["id"] for d in result[0]]
        self.assertNotIn(msgs[1].id, ids)

    # 8. rebuild after redis flush
    def test_rebuild_after_flush(self):
        msgs = self._make_msgs(4)
        MessageCacheService.cache_messages(self.conv.id, msgs)
        MessageCacheService.invalidate_chat_cache(self.conv.id)
        self.assertIsNone(MessageCacheService.get_meta(self.conv.id))
        MessageCacheService.rebuild_chat_cache(self.conv.id)
        meta = MessageCacheService.get_meta(self.conv.id)
        self.assertIsNotNone(meta)
        self.assertEqual(meta["count"], 4)

    # 9. Redis failure is soft (no exception bubbles)
    def test_redis_failure_is_soft(self):
        with mock.patch(
            "messenger.message_cache._redis", return_value=None
        ):
            # All public methods must tolerate missing Redis
            MessageCacheService.cache_messages(self.conv.id, [])
            MessageCacheService.add_message(
                Message(id=999, conversation_id=self.conv.id)
            )
            MessageCacheService.update_message(
                Message(id=999, conversation_id=self.conv.id)
            )
            MessageCacheService.delete_message(self.conv.id, 999)
            self.assertIsNone(
                MessageCacheService.get_cached_messages(self.conv.id, None, 5)
            )

    # 10. Concurrent adds keep meta consistent
    def test_concurrent_adds_meta(self):
        msgs = self._make_msgs(3)
        MessageCacheService.cache_messages(self.conv.id, msgs)
        extra = []
        for i in range(4):
            m = Message.objects.create(
                conversation=self.conv, sender=self.u1, body=f"extra-{i}"
            )
            MessageCacheService.add_message(m)
            extra.append(m)
        meta = MessageCacheService.get_meta(self.conv.id)
        self.assertEqual(meta["count"], 5)  # MESSAGE_CACHE_SIZE
        self.assertEqual(meta["max_id"], extra[-1].id)
