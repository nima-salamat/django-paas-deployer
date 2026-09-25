import logging

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from auth_users.authentication import SessionJWTAuthentication
from auth_users.models import AuthCode, UserContactChange
from auth_users.services import send_otp
from auth_users.session_auth import invalidate_all_sessions

User = get_user_model()
logger = logging.getLogger(__name__)


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (forwarded.split(",", 1)[0].strip() if forwarded else request.META.get("REMOTE_ADDR")) or None


def _mask(value: str) -> str:
    if "@" in value:
        local, domain = value.split("@", 1)
        return f"{local[:1]}***@{domain}"
    return f"***{value[-4:]}" if len(value) > 4 else "***"


class ContactChangeBase(APIView):
    authentication_classes = [SessionJWTAuthentication]
    permission_classes = [IsAuthenticated]


class ContactChangeRequestAPIView(ContactChangeBase):
    """Start an email/phone change; the current user remains unchanged."""

    def post(self, request):
        supplied = []
        email = str(request.data.get("email") or "").strip().lower()
        phone = str(request.data.get("phone_number") or "").strip()
        if email:
            supplied.append((UserContactChange.Field.EMAIL, email, "email"))
        if phone:
            supplied.append((UserContactChange.Field.PHONE, phone, "phone_number"))
        if len(supplied) != 1:
            return Response(
                {"detail": "Provide exactly one new email or phone_number."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        field, target, channel = supplied[0]
        current = str(getattr(request.user, channel, None) or "").strip().lower()
        compare_target = target.lower() if field == UserContactChange.Field.EMAIL else target
        if current and current == compare_target:
            return Response({"detail": "This is already your current contact."}, status=400)

        try:
            with transaction.atomic():
                locked_user = User.objects.select_for_update().get(pk=request.user.pk)
                if User.objects.exclude(pk=locked_user.pk).filter(**{channel: target}).exists():
                    return Response({"detail": "That contact is already in use."}, status=400)
                # AuthCode is intentionally one active code per user/purpose.
                # Cancel every older contact transaction so an OTP can never
                # be associated with a different pending change.
                UserContactChange.objects.filter(
                    user=locked_user,
                    status=UserContactChange.Status.PENDING,
                ).update(
                    status=UserContactChange.Status.CANCELLED,
                    cancelled_at=timezone.now(),
                )
                change = UserContactChange.objects.create(
                    user=locked_user,
                    field=field,
                    old_value=str(getattr(locked_user, channel, None) or ""),
                    new_value=target,
                    requested_ip=_client_ip(request),
                    user_agent=(request.META.get("HTTP_USER_AGENT", "") or "")[:500],
                )
        except IntegrityError:
            return Response({"detail": "That contact is already in use."}, status=400)

        try:
            send_otp(
                user=request.user,
                contact=target,
                channel="email" if field == UserContactChange.Field.EMAIL else "phone",
                purpose=AuthCode.PURPOSE_CONTACT_CHANGE,
            )
        except Exception:
            logger.exception("Contact-change OTP dispatch failed change_id=%s", change.public_id)
            UserContactChange.objects.filter(
                pk=change.pk,
                status=UserContactChange.Status.PENDING,
            ).update(status=UserContactChange.Status.CANCELLED, cancelled_at=timezone.now())
            return Response(
                {"detail": "The verification code could not be sent. Please try again."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {
                "change_id": str(change.public_id),
                "field": field,
                "destination": _mask(target),
                "detail": "Verification code sent. The contact changes after confirmation.",
            },
            status=status.HTTP_202_ACCEPTED,
        )


class ContactChangeConfirmAPIView(ContactChangeBase):
    """Apply a pending contact change only after its destination OTP verifies."""

    def post(self, request, change_id):
        code = str(request.data.get("code") or "").strip()
        change = UserContactChange.objects.filter(
            public_id=change_id,
            user=request.user,
            status=UserContactChange.Status.PENDING,
        ).first()
        if change is None:
            return Response({"detail": "Pending contact change not found."}, status=404)
        valid, auth_code = AuthCode.validate(
            user=request.user,
            contact=change.new_value,
            code=code,
            purpose=AuthCode.PURPOSE_CONTACT_CHANGE,
        )
        if not valid:
            return Response({"detail": "Verification code is incorrect or expired."}, status=400)

        field = change.field
        target = change.new_value
        try:
            with transaction.atomic():
                locked_change = UserContactChange.objects.select_for_update().get(pk=change.pk)
                if locked_change.status != UserContactChange.Status.PENDING:
                    return Response({"detail": "Contact change is no longer pending."}, status=409)
                user = User.objects.select_for_update().get(pk=request.user.pk)
                if User.objects.exclude(pk=user.pk).filter(**{field: target}).exists():
                    locked_change.status = UserContactChange.Status.CANCELLED
                    locked_change.cancelled_at = timezone.now()
                    locked_change.save(update_fields=["status", "cancelled_at"])
                    return Response({"detail": "That contact is already in use."}, status=400)
                setattr(user, field, target)
                setattr(user, "email_verified" if field == UserContactChange.Field.EMAIL else "phone_number_verified", True)
                try:
                    user.full_clean()
                except ValidationError:
                    return Response({"detail": "The new contact value is invalid."}, status=400)
                user.save(update_fields=[field, "email_verified" if field == UserContactChange.Field.EMAIL else "phone_number_verified"])
                locked_change.status = UserContactChange.Status.VERIFIED
                locked_change.verified_at = timezone.now()
                locked_change.save(update_fields=["status", "verified_at"])
                if auth_code:
                    auth_code.delete()
                transaction.on_commit(lambda: invalidate_all_sessions(user.id))
        except IntegrityError:
            return Response({"detail": "That contact is already in use."}, status=400)

        return Response({"detail": f"{field} updated successfully.", "sessions_revoked": True})
