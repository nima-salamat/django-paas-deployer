"""Server-side provisioning helpers for the optional Matrix E2EE integration.

The homeserver administrator token never leaves this module. Matrix account
passwords are encrypted with a dedicated Fernet key; browser clients receive
only a device-scoped Matrix access token after a normal Matrix login creates a
real device record.
"""
from __future__ import annotations

import logging
import re
import secrets
from urllib.parse import quote, urlparse

import requests
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .models import MatrixDevice, MatrixIdentity

logger = logging.getLogger("messenger.matrix")
User = get_user_model()

DEVICE_ID_RE = re.compile(r"^[A-Z0-9._=-]{4,255}$")
ROOM_ID_RE = re.compile(r"^![^:\s]+:[^:\s]+$")
ALGORITHM = "m.megolm.v1.aes-sha2"


class MatrixServiceError(Exception):
    """Safe, user-displayable error; never contains a token or response body."""

    def __init__(self, message: str, status_code: int = 503):
        super().__init__(message)
        self.status_code = status_code


def _config():
    base_url = (getattr(settings, "MATRIX_HOMESERVER_URL", "") or "").strip().rstrip("/")
    domain = (getattr(settings, "MATRIX_HOMESERVER_DOMAIN", "") or "").strip().lower()
    admin_token = (getattr(settings, "MATRIX_ADMIN_ACCESS_TOKEN", "") or "").strip()
    encryption_key = (getattr(settings, "MATRIX_IDENTITY_ENCRYPTION_KEY", "") or "").strip()
    parsed = urlparse(base_url)
    if not base_url or not domain or not admin_token or not encryption_key:
        raise MatrixServiceError("Secure chat is not configured on this deployment.")
    if parsed.scheme != "https" and not (
        settings.DEBUG and parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}
    ):
        raise MatrixServiceError("Secure chat requires a trusted HTTPS Matrix homeserver.")
    if not parsed.hostname or parsed.username or parsed.password:
        raise MatrixServiceError("Matrix homeserver configuration is invalid.")
    try:
        fernet = Fernet(encryption_key.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        raise MatrixServiceError("Matrix identity encryption key is invalid or missing.")
    return base_url, domain, admin_token, fernet


def matrix_is_configured() -> bool:
    try:
        _config()
    except MatrixServiceError:
        return False
    return True


def _url(path: str) -> str:
    base_url, _, _, _ = _config()
    return f"{base_url}/{path.lstrip('/')}"


def matrix_request(method: str, path: str, *, access_token: str | None = None,
                   admin: bool = False, unauthenticated: bool = False,
                   json_body=None, timeout: float = 8.0):
    base_url, _, admin_token, _ = _config()
    headers = {"Accept": "application/json"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    elif admin:
        headers["Authorization"] = f"Bearer {admin_token}"
    elif not unauthenticated:
        raise MatrixServiceError("A Matrix user session is required.")
    try:
        response = requests.request(
            method=method.upper(),
            url=f"{base_url}/{path.lstrip('/')}",
            headers=headers,
            json=json_body,
            timeout=timeout,
        )
    except requests.RequestException:
        logger.warning("Matrix request failed (method=%s path=%s)", method.upper(), path.split("?")[0])
        raise MatrixServiceError("The Matrix homeserver is unavailable.")
    if response.status_code >= 400:
        # Do not log the response payload: Synapse errors may echo request data.
        logger.warning(
            "Matrix request rejected (method=%s path=%s status=%s)",
            method.upper(),
            path.split("?")[0],
            response.status_code,
        )
        if response.status_code in (401, 403):
            raise MatrixServiceError("Matrix authorization failed; secure chat is unavailable.")
        if response.status_code == 429:
            raise MatrixServiceError("Matrix is temporarily rate limiting requests.", 429)
        if response.status_code == 404:
            raise MatrixServiceError("The requested Matrix resource does not exist.", 404)
        raise MatrixServiceError("The Matrix homeserver rejected the secure-chat operation.")
    if not response.content:
        return {}
    try:
        data = response.json()
    except ValueError:
        raise MatrixServiceError("The Matrix homeserver returned an invalid response.")
    if not isinstance(data, dict):
        raise MatrixServiceError("The Matrix homeserver returned an invalid response.")
    return data


def _decrypt_identity_password(identity: MatrixIdentity) -> str:
    _, _, _, fernet = _config()
    try:
        return fernet.decrypt(identity.encrypted_password.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeEncodeError, ValueError):
        logger.error("Unable to decrypt Matrix identity credential for user_id=%s", identity.user_id)
        raise MatrixServiceError(
            "The Matrix identity key has changed or the stored credential is invalid. "
            "Secure chat remains unavailable until an administrator repairs the configuration."
        )


def ensure_matrix_identity(user) -> tuple[MatrixIdentity, str]:
    """Create a local Matrix account once, then return identity + decrypted password.

    The Django user row serializes concurrent first-time provisioning requests.
    Remote credentials are never logged or returned to callers of this helper.
    """
    base_url, domain, admin_token, fernet = _config()
    with transaction.atomic():
        locked_user = User.objects.select_for_update().get(pk=user.pk)
        identity = MatrixIdentity.objects.filter(user=locked_user).first()
        if identity:
            return identity, _decrypt_identity_password(identity)

        localpart = f"pd_{locked_user.uuid.lower()}"
        matrix_user_id = f"@{localpart}:{domain}"
        password = secrets.token_urlsafe(48)
        encrypted_password = fernet.encrypt(password.encode("utf-8")).decode("ascii")
        path = f"/_synapse/admin/v2/users/{quote(matrix_user_id, safe='')}"
        headers = {"Authorization": f"Bearer {admin_token}", "Accept": "application/json"}
        try:
            response = requests.put(
                f"{base_url}{path}",
                headers=headers,
                json={
                    "password": password,
                    "displayname": (locked_user.username or "Paas Deployer")[:100],
                    "admin": False,
                    "deactivated": False,
                },
                timeout=8.0,
            )
        except requests.RequestException:
            logger.warning("Matrix identity provisioning transport failed for Django user_id=%s", locked_user.pk)
            raise MatrixServiceError("The Matrix homeserver is unavailable.")
        if response.status_code >= 400:
            logger.warning(
                "Matrix identity provisioning failed for Django user_id=%s status=%s",
                locked_user.pk,
                response.status_code,
            )
            # Never overwrite an unexpected pre-existing identity: it may carry
            # cryptographic history that this database does not know about.
            if response.status_code == 409:
                raise MatrixServiceError(
                    "A Matrix identity already exists without a local mapping; administrator reconciliation is required."
                )
            raise MatrixServiceError("The Matrix identity could not be provisioned.")
        try:
            identity = MatrixIdentity.objects.create(
                user=locked_user,
                matrix_user_id=matrix_user_id,
                encrypted_password=encrypted_password,
            )
        except Exception:
            # Best-effort cleanup for an account created remotely but not
            # committed locally; do not shadow the original exception.
            try:
                matrix_request(
                    "DELETE",
                    f"/_synapse/admin/v1/deactivate/{quote(matrix_user_id, safe='')}",
                    admin=True,
                    json_body={"erase": False},
                )
            except Exception:
                logger.exception("Failed to clean up an orphan Matrix identity for Django user_id=%s", locked_user.pk)
            raise
        return identity, password


def create_device_session(user, device_id: str, display_name: str = "") -> dict:
    if not isinstance(device_id, str) or not DEVICE_ID_RE.fullmatch(device_id):
        raise MatrixServiceError("Device ID is invalid.", 400)
    display_name = str(display_name or "Paas Deployer browser")[:100].strip()
    identity, password = ensure_matrix_identity(user)
    device, _ = MatrixDevice.objects.get_or_create(
        user=user,
        device_id=device_id,
        defaults={"display_name": display_name},
    )
    if device.revoked_at is not None:
        raise MatrixServiceError(
            "This Matrix device was revoked. Create a new device to continue.",
            410,
        )
    if device.display_name != display_name:
        device.display_name = display_name
        device.save(update_fields=("display_name", "last_seen_at"))
    login_data = matrix_request(
        "POST",
        "/_matrix/client/v3/login",
        access_token=None,
        unauthenticated=True,
        json_body={
            "type": "m.login.password",
            "identifier": {"type": "m.id.user", "user": identity.matrix_user_id},
            "password": password,
            "device_id": device_id,
            "initial_device_display_name": display_name,
        },
    )
    access_token = login_data.get("access_token")
    returned_user_id = login_data.get("user_id")
    returned_device_id = login_data.get("device_id")
    if (
        not isinstance(access_token, str)
        or not access_token
        or returned_user_id != identity.matrix_user_id
        or returned_device_id != device_id
    ):
        logger.error("Matrix login response did not match expected user/device (django_user_id=%s)", user.pk)
        raise MatrixServiceError("Matrix did not create the expected device session.")
    device.last_seen_at = timezone.now()
    device.save(update_fields=("last_seen_at",))
    base_url, _, _, _ = _config()
    return {
        "homeserver_url": base_url,
        "user_id": identity.matrix_user_id,
        "device_id": device_id,
        "access_token": access_token,
    }


def whoami(access_token: str) -> dict:
    if not isinstance(access_token, str) or not access_token or len(access_token) > 4096:
        raise MatrixServiceError("A valid Matrix device session is required.", 401)
    data = matrix_request("GET", "/_matrix/client/v3/account/whoami", access_token=access_token)
    user_id, device_id = data.get("user_id"), data.get("device_id")
    if not isinstance(user_id, str) or not user_id or not isinstance(device_id, str) or not device_id:
        raise MatrixServiceError("Matrix session is not bound to a device.", 401)
    return {"user_id": user_id, "device_id": device_id}


def verify_device_session(user, access_token: str) -> tuple[MatrixIdentity, MatrixDevice]:
    session = whoami(access_token)
    try:
        identity = MatrixIdentity.objects.get(user=user)
    except MatrixIdentity.DoesNotExist:
        raise MatrixServiceError("This account has no provisioned Matrix identity.", 403)
    if identity.matrix_user_id != session["user_id"]:
        raise MatrixServiceError("Matrix session belongs to a different account.", 403)
    try:
        device = MatrixDevice.objects.get(
            user=user,
            device_id=session["device_id"],
            revoked_at__isnull=True,
        )
    except MatrixDevice.DoesNotExist:
        raise MatrixServiceError("This Matrix device is not registered or has been revoked.", 403)
    return identity, device


def revoke_device(user, device_id: str) -> None:
    try:
        identity = MatrixIdentity.objects.get(user=user)
        device = MatrixDevice.objects.get(user=user, device_id=device_id)
    except (MatrixIdentity.DoesNotExist, MatrixDevice.DoesNotExist):
        raise MatrixServiceError("Matrix device not found.", 404)
    if device.revoked_at is not None:
        return
    matrix_request(
        "DELETE",
        f"/_synapse/admin/v2/users/{quote(identity.matrix_user_id, safe='')}/devices/{quote(device_id, safe='')}",
        admin=True,
        json_body={},
    )
    device.revoked_at = timezone.now()
    device.save(update_fields=("revoked_at", "last_seen_at"))


def encrypted_room_state(access_token: str, room_id: str) -> dict:
    if not isinstance(room_id, str) or not ROOM_ID_RE.fullmatch(room_id):
        raise MatrixServiceError("Matrix room ID is invalid.", 400)
    return matrix_request(
        "GET",
        f"/_matrix/client/v3/rooms/{quote(room_id, safe='')}/state/m.room.encryption/",
        access_token=access_token,
    )


def room_memberships(access_token: str, room_id: str) -> dict[str, str]:
    data = matrix_request(
        "GET",
        f"/_matrix/client/v3/rooms/{quote(room_id, safe='')}/members",
        access_token=access_token,
    )
    memberships = {}
    for event in data.get("chunk", []):
        if not isinstance(event, dict):
            continue
        user_id = event.get("state_key")
        membership = (event.get("content") or {}).get("membership")
        if isinstance(user_id, str) and isinstance(membership, str):
            memberships[user_id] = membership
    return memberships


def verify_encrypted_room_binding(user, access_token: str, room_id: str,
                                  expected_matrix_user_ids: list[str],
                                  space_id: str | None = None) -> tuple[MatrixIdentity, MatrixDevice]:
    identity, device = verify_device_session(user, access_token)
    encryption = encrypted_room_state(access_token, room_id)
    if encryption.get("algorithm") != ALGORITHM:
        raise MatrixServiceError("The Matrix room is not using the required end-to-end encryption algorithm.", 400)
    memberships = room_memberships(access_token, room_id)
    if memberships.get(identity.matrix_user_id) != "join":
        raise MatrixServiceError("The current Matrix device is not a joined member of this room.", 403)
    for expected_user_id in set(expected_matrix_user_ids):
        if memberships.get(expected_user_id) not in {"join", "invite"}:
            raise MatrixServiceError(
                "The encrypted room does not contain every intended participant.",
                400,
            )
    if space_id:
        if not ROOM_ID_RE.fullmatch(space_id):
            raise MatrixServiceError("Matrix space ID is invalid.", 400)
        parent = matrix_request(
            "GET",
            f"/_matrix/client/v3/rooms/{quote(room_id, safe='')}/state/m.space.parent/{quote(space_id, safe='')}",
            access_token=access_token,
        )
        space_memberships = room_memberships(access_token, space_id)
        if space_memberships.get(identity.matrix_user_id) != "join":
            raise MatrixServiceError("The current Matrix device is not a joined member of the requested space.", 403)
        parent_content = parent
        if not isinstance(parent_content.get("via"), list) or not parent_content["via"]:
            raise MatrixServiceError("The room is not properly linked to the requested Matrix space.", 400)
    return identity, device


def matrix_user_ids_for_users(requester, users: list):
    """Provision identities for active invitees; never returns passwords/tokens."""
    output = []
    for target in users:
        if target.pk == requester.pk:
            target_identity, _ = ensure_matrix_identity(target)
        else:
            target_identity, _ = ensure_matrix_identity(target)
        output.append({"user_id": target.pk, "matrix_user_id": target_identity.matrix_user_id})
    return output
