"""Strict UTF-8 parsers for Agent-facing text APIs.

JSON exchanged by Agent clients must be UTF-8. Reject a declared legacy charset
instead of silently decoding Persian text with a different code page.
"""
from __future__ import annotations

import codecs

from django.conf import settings
from rest_framework.exceptions import ParseError
from rest_framework.parsers import JSONParser, MultiPartParser


class _UTF8RequestParserMixin:
    def parse(self, stream, media_type=None, parser_context=None):
        context = parser_context or {}
        encoding = context.get("encoding") or getattr(settings, "DEFAULT_CHARSET", "utf-8")
        try:
            canonical_encoding = codecs.lookup(str(encoding)).name
        except LookupError as exc:
            raise ParseError("Request body charset must be UTF-8.") from exc

        if canonical_encoding != "utf-8":
            raise ParseError(
                "Agent Messenger request bodies must use UTF-8. "
                "Send Content-Type with charset=utf-8 or omit the charset."
            )

        return super().parse(stream, media_type=media_type, parser_context=context)


class UTF8JSONParser(_UTF8RequestParserMixin, JSONParser):
    """Parse JSON only when the request encoding is UTF-8."""


class UTF8MultiPartParser(_UTF8RequestParserMixin, MultiPartParser):
    """Parse multipart messages/uploads only when text fields are UTF-8."""
