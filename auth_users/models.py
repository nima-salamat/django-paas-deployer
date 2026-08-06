from django.db import models
from django.core.exceptions import ValidationError
from users.models import User
import string
import random
from django.utils import timezone
from datetime import timedelta

TEXT = string.ascii_letters + string.digits


def get_random_code(n):
    return "".join(random.choices(TEXT, k=n))


def get_random_code_8():
    return get_random_code(8)


class LoginSettings(models.Model):
    """
    Singleton-style settings model to fully customize authentication flows.
    Only one active row should exist (use get_solo() or admin).
    """

    # ---------- Allowed identifiers for login / signup ----------
    allow_username = models.BooleanField(
        default=True,
        help_text="Allow username as an identifier",
    )
    allow_email = models.BooleanField(
        default=True,
        help_text="Allow email as an identifier",
    )
    allow_phone = models.BooleanField(
        default=True,
        help_text="Allow phone number as an identifier",
    )

    # ---------- Required factors ----------
    require_password = models.BooleanField(
        default=True,
        help_text="If True, password is required when the user has one set",
    )
    require_otp = models.BooleanField(
        default=True,
        help_text="If True, a one-time code (OTP) is required",
    )
    password_as_second_factor = models.BooleanField(
        default=True,
        help_text=(
            "If True and user has a password, after OTP ask for password (2FA). "
            "If False, password alone can be enough when require_otp=False"
        ),
    )

    # ---------- Signup / auto-create behaviour ----------
    allow_auto_signup = models.BooleanField(
        default=True,
        help_text="If user does not exist, automatically create the account",
    )
    auto_activate_on_signup = models.BooleanField(
        default=False,
        help_text=(
            "If True, newly created users become active immediately. "
            "If False, user stays inactive until admin activates or verification completes"
        ),
    )
    require_password_on_signup = models.BooleanField(
        default=True,
        help_text="When creating a new user, force them to set a password",
    )
    activate_after_successful_otp = models.BooleanField(
        default=True,
        help_text="After a valid OTP, set is_active=True (and mark email/phone verified)",
    )

    # ---------- Recovery (forgot username) ----------
    allow_username_recovery = models.BooleanField(
        default=True,
        help_text="Enable 'forgot username' flow",
    )
    recovery_via_email = models.BooleanField(
        default=True,
        help_text="Allow recovery by sending OTP to email",
    )
    recovery_via_phone = models.BooleanField(
        default=True,
        help_text="Allow recovery by sending OTP to phone",
    )

    # ---------- OTP settings ----------
    otp_length = models.PositiveSmallIntegerField(default=8)
    otp_expire_minutes = models.PositiveSmallIntegerField(default=5)
    otp_max_attempts = models.PositiveSmallIntegerField(
        default=5,
        help_text="Max wrong OTP attempts before code is invalidated",
    )

    # ---------- Misc ----------
    is_active = models.BooleanField(
        default=True,
        help_text="Only one settings row should be active",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Login Settings"
        verbose_name_plural = "Login Settings"

    def __str__(self):
        return f"LoginSettings (active={self.is_active})"

    def clean(self):
        if not any([self.allow_username, self.allow_email, self.allow_phone]):
            raise ValidationError(
                "At least one identifier (username/email/phone) must be allowed."
            )
        if self.require_otp is False and self.require_password is False:
            raise ValidationError(
                "At least one of require_otp or require_password must be True."
            )
        if self.allow_username_recovery and not any(
            [self.recovery_via_email, self.recovery_via_phone]
        ):
            raise ValidationError(
                "Username recovery is enabled but no recovery channel is selected."
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        if self.is_active:
            LoginSettings.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls):
        """Return the active settings or create a sensible default."""
        obj = cls.objects.filter(is_active=True).first()
        if obj is None:
            obj = cls.objects.create(is_active=True)
        return obj

    def get_allowed_identifiers(self):
        ids = []
        if self.allow_username:
            ids.append("username")
        if self.allow_email:
            ids.append("email")
        if self.allow_phone:
            ids.append("phone_number")
        return ids

    def needs_otp(self):
        return self.require_otp

    def needs_password(self, user=None):
        """
        Decide whether password is required for this user.
        - If password_as_second_factor and user already has a password -> yes
        - If require_password and user has password -> yes
        """
        if user is None:
            return self.require_password
        has_password = bool(user.has_usable_password())
        if not has_password:
            return False
        if self.password_as_second_factor:
            return True
        return self.require_password


class AuthCode(models.Model):
    """
    One-time password / verification code.
    Also used for username recovery.
    """

    PURPOSE_LOGIN = "login"
    PURPOSE_SIGNUP = "signup"
    PURPOSE_RECOVERY = "recovery"
    PURPOSE_CHOICES = [
        (PURPOSE_LOGIN, "Login / Verify"),
        (PURPOSE_SIGNUP, "Signup"),
        (PURPOSE_RECOVERY, "Username Recovery"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="auth_codes",
        null=True,
        blank=True,
        help_text="Null only for recovery when we only know email/phone",
    )
    contact = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Email or phone used when user is not yet resolved (recovery)",
    )
    purpose = models.CharField(
        max_length=20,
        choices=PURPOSE_CHOICES,
        default=PURPOSE_LOGIN,
    )
    code = models.CharField(max_length=16, default=get_random_code_8)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "purpose"]),
            models.Index(fields=["contact", "purpose"]),
        ]

    def __str__(self):
        target = self.user.username if self.user else self.contact
        return f"AuthCode({target}, {self.purpose}, {self.code})"

    def is_expired(self):
        settings = LoginSettings.get_solo()
        expire_time = self.updated_at + timedelta(minutes=settings.otp_expire_minutes)
        return timezone.now() > expire_time

    def is_not_expired(self):
        return not self.is_expired()

    def is_locked(self):
        settings = LoginSettings.get_solo()
        return self.attempts >= settings.otp_max_attempts

    def update_code(self):
        settings = LoginSettings.get_solo()
        length = settings.otp_length or 8
        self.code = get_random_code(length)
        self.attempts = 0
        self.save(update_fields=["code", "attempts", "updated_at"])
        return self.code

    @classmethod
    def create_or_refresh(cls, *, user=None, contact="", purpose=PURPOSE_LOGIN):
        """
        Get or create a code for the given user/contact+purpose and refresh if expired.
        """
        if user is None and not contact:
            raise ValueError("Either user or contact must be provided")

        lookup = {"purpose": purpose}
        if user:
            lookup["user"] = user
        else:
            lookup["contact"] = contact
            lookup["user"] = None

        instance, created = cls.objects.get_or_create(**lookup)
        if created or instance.is_expired() or instance.is_locked():
            instance.update_code()
        return instance

    @classmethod
    def validate(cls, *, user=None, contact="", code="", purpose=PURPOSE_LOGIN):
        """
        Validate a code. Returns (is_valid: bool, instance_or_None).
        Increments attempts on failure.
        """
        if not code:
            return False, None

        lookup = {"purpose": purpose}
        if user:
            lookup["user"] = user
        else:
            lookup["contact"] = contact
            lookup["user"] = None

        try:
            instance = cls.objects.get(**lookup)
        except cls.DoesNotExist:
            return False, None

        if instance.is_expired() or instance.is_locked():
            return False, instance

        if instance.code == code:
            return True, instance

        instance.attempts += 1
        instance.save(update_fields=["attempts"])
        return False, instance

    def consume(self):
        """Delete the code after successful use."""
        self.delete()
