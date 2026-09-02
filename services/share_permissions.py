"""
Fine-grained permission rules for ServiceShare.

Service DELETE is intentionally never granted to share recipients.
"""
from __future__ import annotations

from django.utils.translation import gettext_lazy as _

# Canonical rule keys + defaults (safe defaults = deny mutating actions)
DEFAULT_SHARE_RULES: dict[str, bool] = {
    # visibility
    "can_view": True,
    "can_view_logs": True,           # container / service runtime logs
    "can_view_deploy_logs": True,    # deployment pipeline logs
    "can_view_metrics": True,
    "can_view_db_credentials": False,  # DB password / root_password / secrets
    "can_shell": False,                 # restricted shell on the live service container
    "can_shell_replace": False,          # terminate another active shell session on the service
    "can_shell_advanced": False,         # advanced interactive developer tools such as Laravel Tinker
    # lifecycle
    "can_start": False,
    "can_stop": False,
    "can_restart": False,
    "can_rebuild": False,            # force_rebuild / rebuild image
    "can_purge": False,              # purge runtime (container/images)
    # deploys (recipients may only touch deploys they created when created_by is set)
    "can_deploy_add": False,
    "can_deploy_edit": False,        # edit own deploys only
    "can_deploy_remove": False,      # remove own deploys only
    "can_deploy_select": False,      # select active deploy on service
    # volumes
    "can_volume_add": False,
    "can_volume_edit": False,
    "can_volume_delete": False,
    "can_volume_attach": False,
    "can_volume_detach": False,
    # network on the shared service
    "can_network_change": False,     # change service.network
    # generic service config (name/plan/etc. — still cannot delete service)
    "can_change_config": False,
    # integer: max deploys/builds per day for this recipient (capped at system max)
    "daily_deploy_limit": 50,
}

# Human labels for UI (EN; frontend may translate)
RULE_LABELS: dict[str, str] = {
    "can_view": "View service",
    "can_view_logs": "View service logs",
    "can_view_deploy_logs": "View deploy logs",
    "can_view_metrics": "View metrics",
    "can_view_db_credentials": "View DB credentials",
    "can_shell": "Use restricted service shell",
    "can_shell_replace": "Replace another active shell session",
    "can_shell_advanced": "Use advanced interactive shell tools (for example Tinker)",
    "can_start": "Start",
    "can_stop": "Stop",
    "can_restart": "Restart",
    "can_rebuild": "Rebuild",
    "can_purge": "Purge runtime",
    "can_deploy_add": "Add deploy",
    "can_deploy_edit": "Edit own deploys",
    "can_deploy_remove": "Remove own deploys",
    "can_deploy_select": "Select active deploy",
    "can_deploy_download": "Download deploy zip",
    "can_deploy_edit_others": "Edit others' deploys",
    "can_deploy_remove_others": "Delete others' deploys",
    "can_volume_add": "Add volume",
    "can_volume_edit": "Edit volume",
    "can_volume_delete": "Delete volume",
    "can_volume_attach": "Attach volume",
    "can_volume_detach": "Detach volume",
    "can_network_change": "Change network",
    "can_change_config": "Change service config",
    "daily_deploy_limit": "Daily deploy limit",
}

# Map legacy short keys → canonical
_LEGACY_ALIASES = {
    "can_deploy": "can_rebuild",  # old single deploy flag → rebuild
    "can_attach_volume": "can_volume_attach",
    "can_delete_deploy": "can_deploy_remove",
}


def normalize_rules(raw) -> dict:
    """Merge user-supplied rules with defaults; coerce types; map legacy keys."""
    out = dict(DEFAULT_SHARE_RULES)
    if not isinstance(raw, dict):
        return out
    mapped = {}
    for k, v in raw.items():
        key = _LEGACY_ALIASES.get(k, k)
        mapped[key] = v
    for k, default in DEFAULT_SHARE_RULES.items():
        if k not in mapped:
            continue
        if k == "daily_deploy_limit":
            try:
                n = int(mapped[k])
                out[k] = max(0, min(n, 50))
            except (TypeError, ValueError):
                out[k] = default
        else:
            v = mapped[k]
            if isinstance(v, str):
                out[k] = v.strip().lower() in ("1", "true", "yes", "on")
            else:
                out[k] = bool(v)
    return out


def full_owner_rules() -> dict[str, bool]:
    return {k: True for k in DEFAULT_SHARE_RULES}


# Actions that share recipients must NEVER perform
FORBIDDEN_FOR_RECIPIENTS = frozenset({
    "delete_service",
    "transfer_ownership",
})


class SharePermissionError(PermissionError):
    def __init__(self, message: str = "Permission denied", *, action: str = ""):
        super().__init__(message)
        self.action = action


def assert_share_action(service, user, action: str):
    """
    Raise SharePermissionError if user cannot perform action on service.
    Owners always pass.
    Returns (service, share_or_None).
    """
    from services.api.sharing import user_can_access_service

    if action in FORBIDDEN_FOR_RECIPIENTS:
        # Only true owner
        if str(getattr(service, "user_id", None)) != str(getattr(user, "id", None)):
            raise SharePermissionError(
                str(_("You cannot perform this action on a shared service.")),
                action=action,
            )
        return service, None

    # Map high-level action names to rule keys
    rule_key = action
    allowed, share = user_can_access_service(service, user, action=rule_key)
    if not allowed:
        # Owner path inside user_can_access returns allowed=True for can_view etc.
        # If owner, user_can_access returns (True, None) only when service.user == user
        if str(getattr(service, "user_id", None)) == str(getattr(user, "id", None)):
            return service, None
        raise SharePermissionError(
            str(_("You do not have permission to perform '%(a)s' on this service.") % {"a": action}),
            action=action,
        )
    return service, share


def can_mutate_deploy(deploy, user, *, action: str = "can_deploy_edit") -> bool:
    """
    Service owner: always True.
    Share recipient:
      - can_deploy_edit / can_deploy_remove → only deploys they created
      - can_deploy_edit_others / can_deploy_remove_others → any deploy on the service
      - can_deploy_download / can_deploy_select → no ownership check (action itself is enough)
    """
    service = getattr(deploy, "service", None)
    if service is None:
        return False
    if str(service.user_id) == str(user.id):
        return True

    from services.api.sharing import user_can_access_service

    own_actions = {
        "can_deploy_edit": "can_deploy_edit",
        "can_deploy_remove": "can_deploy_remove",
    }
    others_actions = {
        "can_deploy_edit": "can_deploy_edit_others",
        "can_deploy_remove": "can_deploy_remove_others",
    }
    open_actions = {"can_deploy_download", "can_deploy_select", "can_deploy_add"}

    if action in open_actions:
        allowed, _share = user_can_access_service(service, user, action=action)
        return bool(allowed)

    # Prefer "others" permission if set; else own-only
    others_key = others_actions.get(action)
    own_key = own_actions.get(action, action)

    if others_key:
        allowed_others, _ = user_can_access_service(service, user, action=others_key)
        if allowed_others:
            return True

    allowed_own, _ = user_can_access_service(service, user, action=own_key)
    if not allowed_own:
        return False
    created_by_id = getattr(deploy, "created_by_id", None)
    if created_by_id is None:
        return False
    return str(created_by_id) == str(user.id)


def redact_db_secrets(cfg: dict | None) -> dict:
    """Strip sensitive keys from deploy/service config for unauthorized viewers."""
    if not isinstance(cfg, dict):
        return {}
    secret_keys = {
        "password",
        "root_password",
        "ROOT_PASSWORD",
        "PASSWORD",
        "MYSQL_ROOT_PASSWORD",
        "MYSQL_PASSWORD",
        "POSTGRES_PASSWORD",
        "MONGO_INITDB_ROOT_PASSWORD",
        "REDIS_PASSWORD",
        "secret",
        "SECRET",
        "secret_key",
        "SECRET_KEY",
        "api_key",
        "API_KEY",
        "token",
        "TOKEN",
    }
    out = {}
    for k, v in cfg.items():
        if k in secret_keys or str(k).lower().endswith("password"):
            out[k] = "********" if v not in (None, "") else v
        elif isinstance(v, dict):
            out[k] = redact_db_secrets(v)
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# Presets for UI (one-click profiles)
# ---------------------------------------------------------------------------
RULE_PRESETS: dict[str, dict[str, bool]] = {
    "viewer": normalize_rules({
        "can_view": True,
        "can_view_logs": True,
        "can_view_deploy_logs": True,
        "can_view_metrics": True,
    }),
    "operator": normalize_rules({
        "can_view": True,
        "can_view_logs": True,
        "can_view_deploy_logs": True,
        "can_view_metrics": True,
        "can_start": True,
        "can_stop": True,
        "can_restart": True,
        "can_rebuild": True,
    }),
    "developer": normalize_rules({
        "can_view": True,
        "can_view_logs": True,
        "can_view_deploy_logs": True,
        "can_view_metrics": True,
        "can_start": True,
        "can_stop": True,
        "can_restart": True,
        "can_rebuild": True,
        "can_shell": True,
        "can_shell_advanced": True,
        "can_deploy_add": True,
        "can_deploy_edit": True,
        "can_deploy_remove": True,
        "can_deploy_select": True,
        "can_deploy_download": True,
        "can_deploy_edit_others": False,
        "can_deploy_remove_others": False,
        "can_volume_attach": True,
        "can_volume_detach": True,
        "can_change_config": True,
    }),
    "ops": normalize_rules({
        "can_view": True,
        "can_view_logs": True,
        "can_view_deploy_logs": True,
        "can_view_metrics": True,
        "can_view_db_credentials": True,
        "can_start": True,
        "can_stop": True,
        "can_restart": True,
        "can_rebuild": True,
        "can_shell": True,
        "can_shell_advanced": True,
        "can_purge": True,
        "can_deploy_add": True,
        "can_deploy_edit": True,
        "can_deploy_remove": True,
        "can_deploy_select": True,
        "can_volume_add": True,
        "can_volume_edit": True,
        "can_volume_delete": True,
        "can_volume_attach": True,
        "can_volume_detach": True,
        "can_network_change": True,
        "can_change_config": True,
    }),
}


def user_is_group_admin(user, group_id) -> bool:
    """True if user is active owner/admin of the messenger group."""
    from messenger.models import ConversationParticipant
    part = ConversationParticipant.objects.filter(
        conversation_id=group_id,
        user=user,
        left_at__isnull=True,
    ).only("role").first()
    if not part:
        return False
    return part.role in (
        ConversationParticipant.Role.OWNER,
        ConversationParticipant.Role.ADMIN,
    )
