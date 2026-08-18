"""Messenger API — profile."""
from __future__ import annotations

import secrets
import logging
import mimetypes
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Q, Count, Prefetch
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from ..models import (
    Contact, Block, Conversation, ConversationParticipant, Message,
    MessageReaction, MessageAttachment, GroupInviteLink,
    ProfilePhotoPrivacy, ProfilePhotoAllowed, MessageReadReceipt, UserBio,
    JoinRequest, PinnedMessage, CallSession,
)
from ..serializers import (
    UserMiniSerializer, MessageSerializer, ConversationListSerializer,
    ConversationDetailSerializer, ContactSerializer,
    GroupInviteLinkSerializer, ProfilePhotoSerializer, ProfilePhotoPrivacySerializer,
    build_message_list_context, build_user_mini_context,
)
from ..utils import validate_messenger_file, detect_kind, users_blocked, can_see_profile_photo
from .common import ok, err, _attach_list_side_data, get_or_create_dm, logger

User = get_user_model()
class MyProfilePhotosAPIView(APIView):
    """
    Reads existing users.Profile images only.
    Upload / reorder / delete stays in the users Profile UI — messenger does not own photos.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from users.models import Profile
        photos = (
            Profile.objects.filter(user=request.user)
            .exclude(image="")
            .filter(image__isnull=False)
            .order_by("order", "id")
        )
        privacy, _ = ProfilePhotoPrivacy.objects.get_or_create(user=request.user)
        return ok(data={
            "photos": ProfilePhotoSerializer(photos, many=True, context={"request": request}).data,
            "privacy": ProfilePhotoPrivacySerializer(privacy).data,
        })


class ProfilePhotoPrivacyAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        privacy, _ = ProfilePhotoPrivacy.objects.get_or_create(user=request.user)
        scope = request.data.get("scope")
        if scope in dict(ProfilePhotoPrivacy.Scope.choices):
            privacy.scope = scope
            privacy.save(update_fields=["scope", "updated_at"])
        if "allowed_user_ids" in request.data and isinstance(request.data["allowed_user_ids"], list):
            privacy.allowed_users.all().delete()
            for uid in request.data["allowed_user_ids"][:200]:
                try:
                    u = User.objects.get(pk=uid)
                    ProfilePhotoAllowed.objects.create(privacy=privacy, user=u)
                except User.DoesNotExist:
                    pass
        return ok(data=ProfilePhotoPrivacySerializer(privacy).data)


class UserProfileAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        try:
            user = User.objects.get(pk=user_id, is_active=True)
        except User.DoesNotExist:
            return err("Not found", status.HTTP_404_NOT_FOUND)
        context = build_user_mini_context(request.user, [user], request=request)
        data = UserMiniSerializer(user, context={"request": request, **context}).data
        if can_see_profile_photo(request.user, user):
            from users.models import Profile
            photos = (
                Profile.objects.filter(user=user)
                .exclude(image="")
                .filter(image__isnull=False)
                .order_by("order", "id")
            )
            data["photos"] = ProfilePhotoSerializer(photos, many=True, context={"request": request}).data
        else:
            data["photos"] = []
        return ok(data=data)



class UserByUsernameAPIView(APIView):
    """Look up a user by exact username — used for @mention click navigation.

    Returns the same payload as UserProfileAPIView so the client can show the
    profile panel without adding the user to contacts.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        username = (request.query_params.get("username") or "").strip().lstrip("@")
        if not username:
            return err("username required")
        try:
            user = User.objects.get(username__iexact=username, is_active=True)
        except User.DoesNotExist:
            return err("User not found", status.HTTP_404_NOT_FOUND)
        context = build_user_mini_context(request.user, [user], request=request)
        data = UserMiniSerializer(user, context={"request": request, **context}).data
        if can_see_profile_photo(request.user, user):
            from users.models import Profile
            photos = (
                Profile.objects.filter(user=user)
                .exclude(image="")
                .filter(image__isnull=False)
                .order_by("order", "id")
            )
            data["photos"] = ProfilePhotoSerializer(photos, many=True, context={"request": request}).data
        else:
            data["photos"] = []
        return ok(data=data)


class UserBioAPIView(APIView):
    """Get or set the current user's bio (Telegram-style 'about' field).

    GET  /me/bio/         -> {text: "..."}
    PATCH /me/bio/        -> {text: "new bio"}  (max 255 chars)
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        bio, _ = UserBio.objects.get_or_create(user=request.user)
        return ok(data={"text": bio.text or ""})

    def patch(self, request):
        text = str(request.data.get("text") or "")[:255]
        bio, _ = UserBio.objects.get_or_create(user=request.user)
        bio.text = text
        bio.save(update_fields=["text", "updated_at"])
        return ok("Bio updated", data={"text": bio.text})



class ProfileUpdateBroadcastAPIView(APIView):
    """Notify all conversations the current user is part of that their profile
    has changed (avatar, bio, etc).

    POST /me/profile-broadcast/  -> 200 OK

    Called by the frontend after the user updates their profile photo, bio,
    or username. The backend fans out a `profile.update` WebSocket event to
    every conversation + the user's own personal channel.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            from ..consumers import broadcast_profile_update
            broadcast_profile_update(request.user.id)
        except Exception:
            pass
        return ok("Broadcast sent")


# ------------------------------------------------------------# Voice / video calls (custom UI + Jitsi media transport)
# ---------------------------------------------------------------------------

import json as _json
from django.utils import timezone as _tz



