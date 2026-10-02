from __future__ import annotations
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from core.base.BaseModel import BaseModel
from .scopes import default_agent_scopes, validate_scopes

class Agent(BaseModel):
    class Status(models.TextChoices):
        ACTIVE="active","Active"; DISABLED="disabled","Disabled"; REVOKED="revoked","Revoked"
    class ProvisioningSource(models.TextChoices):
        DASHBOARD="dashboard","Dashboard"
        API_ENROLLMENT="api_enrollment","API enrollment"
        LEGACY="legacy","Legacy / unspecified"
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name="agents")
    name=models.CharField(max_length=100)
    description=models.TextField(blank=True,default="")
    status=models.CharField(max_length=16,choices=Status.choices,default=Status.ACTIVE,db_index=True)
    provisioning_source=models.CharField(max_length=24,choices=ProvisioningSource.choices,default=ProvisioningSource.LEGACY,db_index=True)
    scopes=models.JSONField(default=default_agent_scopes,blank=True)
    metadata=models.JSONField(default=dict,blank=True)
    last_used_at=models.DateTimeField(null=True,blank=True,db_index=True)
    disabled_at=models.DateTimeField(null=True,blank=True); revoked_at=models.DateTimeField(null=True,blank=True)
    class Meta:
        ordering=("user_id","name","created_at")
        constraints=[models.UniqueConstraint(fields=("user","name"),name="uniq_agent_user_name")]
        indexes=[models.Index(fields=("user","status")),models.Index(fields=("status","-last_used_at"))]
    def clean(self):
        super().clean()
        try:self.scopes=validate_scopes(self.scopes)
        except ValueError as exc:raise ValidationError({"scopes":str(exc)}) from exc
    def __str__(self): return f"{self.name} ({self.user})"

    def save(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        try:
            self.scopes = sorted(validate_scopes(self.scopes or []))
        except ValueError as exc:
            raise ValidationError({"scopes": str(exc)}) from exc
        return super().save(*args, **kwargs)


class AgentCredential(BaseModel):
    class TokenType(models.TextChoices): ACCESS="access","Access token"
    agent=models.ForeignKey(Agent,on_delete=models.CASCADE,related_name="credentials")
    token_prefix=models.CharField(max_length=32,db_index=True)
    token_hash=models.CharField(max_length=64,unique=True,editable=False)
    token_type=models.CharField(max_length=16,choices=TokenType.choices,default=TokenType.ACCESS)
    expires_at=models.DateTimeField(null=True,blank=True,db_index=True); revoked_at=models.DateTimeField(null=True,blank=True,db_index=True)
    last_used_at=models.DateTimeField(null=True,blank=True,db_index=True); last_used_ip=models.GenericIPAddressField(null=True,blank=True)
    metadata=models.JSONField(default=dict,blank=True)
    class Meta:
        ordering=("-created_at",); indexes=[models.Index(fields=("agent","revoked_at","expires_at")),models.Index(fields=("token_prefix","revoked_at"))]
    def is_active(self,now=None): now=now or timezone.now(); return self.revoked_at is None and (self.expires_at is None or self.expires_at>now)
    def __str__(self): return f"{self.agent.name} · {self.token_prefix}"

class AgentEnrollmentToken(BaseModel):
    agent=models.ForeignKey(Agent,on_delete=models.CASCADE,related_name="enrollments")
    token_prefix=models.CharField(max_length=32,db_index=True); token_hash=models.CharField(max_length=64,unique=True,editable=False)
    expires_at=models.DateTimeField(db_index=True); used_at=models.DateTimeField(null=True,blank=True,db_index=True); issued_from_ip=models.GenericIPAddressField(null=True,blank=True)
    class Meta:
        ordering=("-created_at",); indexes=[models.Index(fields=("agent","used_at","expires_at"))]
    def is_usable(self,now=None): now=now or timezone.now(); return self.used_at is None and self.expires_at>now and self.agent.status==Agent.Status.ACTIVE and self.agent.user.is_active

class AgentAuditEvent(BaseModel):
    agent=models.ForeignKey(Agent,null=True,blank=True,on_delete=models.SET_NULL,related_name="audit_events")
    user=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL,related_name="agent_audit_events")
    credential=models.ForeignKey(AgentCredential,null=True,blank=True,on_delete=models.SET_NULL,related_name="audit_events")
    action=models.CharField(max_length=96,db_index=True); resource_type=models.CharField(max_length=64,blank=True,default=""); resource_id=models.CharField(max_length=255,blank=True,default="")
    request_id=models.CharField(max_length=64,db_index=True); occurred_at=models.DateTimeField(auto_now_add=True,db_index=True); success=models.BooleanField(default=False,db_index=True)
    http_status=models.PositiveSmallIntegerField(null=True,blank=True); error_code=models.CharField(max_length=96,blank=True,default="")
    failure_domain=models.CharField(max_length=32,blank=True,default=""); retryability=models.CharField(max_length=16,blank=True,default="")
    visibility=models.CharField(max_length=16,blank=True,default="client"); resource_effect=models.CharField(max_length=32,blank=True,default="unchanged"); certainty=models.CharField(max_length=16,blank=True,default="known")
    duration_ms=models.PositiveIntegerField(null=True,blank=True); metadata=models.JSONField(default=dict,blank=True)
    class Meta:
        ordering=("-occurred_at","-id"); indexes=[models.Index(fields=("agent","-occurred_at")),models.Index(fields=("user","-occurred_at")),models.Index(fields=("resource_type","resource_id","-occurred_at"))]

class AgentIdempotencyRecord(BaseModel):
    class State(models.TextChoices): PROCESSING="processing","Processing"; COMPLETE="complete","Complete"
    agent=models.ForeignKey(Agent,on_delete=models.CASCADE,related_name="idempotency_records")
    key=models.CharField(max_length=255); method=models.CharField(max_length=16); path=models.CharField(max_length=512); request_hash=models.CharField(max_length=64)
    state=models.CharField(max_length=16,choices=State.choices,default=State.PROCESSING); status_code=models.PositiveSmallIntegerField(null=True,blank=True); response_body=models.JSONField(null=True,blank=True); expires_at=models.DateTimeField(db_index=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=("agent","key"),name="uniq_agent_idempotency_key")]; indexes=[models.Index(fields=("agent","expires_at"))]
