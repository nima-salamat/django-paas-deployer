from __future__ import annotations
import hmac
from django.utils import timezone
from rest_framework import authentication
from rest_framework.exceptions import AuthenticationFailed
from .models import Agent, AgentCredential
from .security import client_ip,stable_token_hash,token_hash


def authenticate_agent_token(raw: str, *, ip: str = ""):
    """Resolve an Agent access token to (agent, user, credential)."""
    raw = str(raw or "").strip()
    if not raw:
        raise AuthenticationFailed("Invalid Agent credential.")
    digest = stable_token_hash(raw)
    legacy_digest = token_hash(raw)
    prefix = raw[:20]
    now = timezone.now()
    candidates = AgentCredential.objects.select_related("agent", "agent__user").filter(
        token_prefix=prefix,
        token_type=AgentCredential.TokenType.ACCESS,
        revoked_at__isnull=True,
    )
    credential = next(
        (item for item in candidates if hmac.compare_digest(item.token_hash, digest) or hmac.compare_digest(item.token_hash, legacy_digest)),
        None,
    )
    if credential is None:
        raise AuthenticationFailed("Invalid Agent credential.")
    if not credential.is_active(now):
        raise AuthenticationFailed("Agent credential is expired or revoked.")
    agent = credential.agent
    if agent.status != Agent.Status.ACTIVE:
        raise AuthenticationFailed("Agent is disabled or revoked.")
    user = agent.user
    if not user or not user.is_active:
        raise AuthenticationFailed("The underlying PassDeployer user is inactive.")
    if credential.last_used_at is None or (now - credential.last_used_at).total_seconds() >= 60:
        updates = {"last_used_at": now, "updated_at": now}
        if str(ip or ""):
            updates["last_used_ip"] = str(ip)
        AgentCredential.objects.filter(pk=credential.pk).update(**updates)
        Agent.objects.filter(pk=agent.pk).update(last_used_at=now, updated_at=now)
        credential.last_used_at = now
        agent.last_used_at = now
    return agent, user, credential


class AgentTokenAuthentication(authentication.BaseAuthentication):
    keyword="Bearer"
    def authenticate(self,request):
        header=str(request.META.get("HTTP_AUTHORIZATION") or "").strip()
        if not header:return None
        parts=header.split()
        if len(parts)!=2 or parts[0].lower()!=self.keyword.lower(): raise AuthenticationFailed("Use Authorization: Bearer <agent-access-token>.")
        raw=parts[1].strip()
        agent,user,credential=authenticate_agent_token(raw, ip=client_ip(request))
        request.agent=agent; request.agent_credential=credential; request.agent_token=credential
        return user,credential
