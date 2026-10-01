from __future__ import annotations
from .manifest import api_base_url

def build_openapi(agent, *, request=None):
    origin = api_base_url(request).rsplit("/agent/v1", 1)[0] if request else "/"
    idem = {"name":"Idempotency-Key","in":"header","required":False,"schema":{"type":"string","maxLength":255},"description":"24-hour idempotency key for retry-safe mutations."}
    return {
        "openapi":"3.0.3",
        "info":{"title":"PassDeployer Agent API","version":"v1","description":"Scoped control-plane facade over existing PassDeployer application services; no host shell or raw Docker API."},
        "servers":[{"url":origin or "/"}],
        "security":[{"AgentBearer":[]}],
        "components":{
            "securitySchemes":{"AgentBearer":{"type":"http","scheme":"bearer","bearerFormat":"PassDeployer Agent access token"}},
            "parameters":{"IdempotencyKey":idem},
            "schemas":{
                "Error":{"type":"object","required":["result","code","detail","request_id","retryable","failure_domain","resource_effect","certainty"],"properties":{
                    "result":{"type":"string","enum":["error"]},"code":{"type":"string"},"detail":{"type":"string"},"request_id":{"type":"string","format":"uuid","nullable":True},
                    "retryable":{"type":"boolean"},"failure_domain":{"type":"string"},"visibility":{"type":"string"},"resource_effect":{"type":"string"},"certainty":{"type":"string"}}},
                "Service":{"type":"object","required":["id","name","status","desired_state"],"properties":{
                    "id":{"type":"string","format":"uuid"},"name":{"type":"string"},"owner":{"type":"object"},"plan":{"type":"object","nullable":True},
                    "platform":{"type":"string"},"source_kind":{"type":"string"},"desired_state":{"type":"string"},"status":{"type":"string"},
                    "active_revision":{"type":"object","nullable":True},"deployment":{"type":"object","nullable":True},"network":{"type":"object","nullable":True},
                    "processes":{"type":"array","items":{"type":"object"}},"endpoints":{"type":"array","items":{"type":"object"}},"volumes":{"type":"array","items":{"type":"object"}}}},
                "Deployment":{"type":"object","required":["id","service_id","status"],"properties":{
                    "id":{"type":"string","format":"uuid"},"release_id":{"type":"string","format":"uuid"},"service_id":{"type":"string","format":"uuid"},
                    "revision_id":{"type":"string","format":"uuid","nullable":True},"status":{"type":"string"},"stage":{"type":"string"},"progress":{"type":"integer"},
                    "status_message":{"type":"string"},"error_message":{"type":"string"},"execution_task_id":{"type":"string","nullable":True}}},
                "DeploymentLogEvent":{"type":"object","properties":{
                    "timestamp":{"type":"string","format":"date-time"},"level":{"type":"string","nullable":True},"source":{"type":"string","enum":["deployment"]},
                    "stage":{"type":"string","nullable":True},"event_type":{"type":"string","nullable":True},"message":{"type":"string"},
                    "deployment_id":{"type":"string","format":"uuid"},"service_id":{"type":"string","format":"uuid"}}},
                "RuntimeLogEvent":{"type":"object","properties":{
                    "timestamp":{"type":"string","format":"date-time"},"level":{"type":"string","nullable":True},"source":{"type":"string","enum":["runtime"]},
                    "stream":{"type":"string"},"message":{"type":"string"},"service_id":{"type":"string","format":"uuid"},"deployment_id":{"type":"string","nullable":True},"cursor":{"type":"string","nullable":True}}},
                "ShellCommandResult":{"type":"object","properties":{
                    "result":{"type":"string"},"command":{"type":"string"},"exit_code":{"type":"integer"},"stdout":{"type":"string"},"stderr":{"type":"string"},"duration_ms":{"type":"integer"},"cwd":{"type":"string"},"session_id":{"type":"string","format":"uuid"}}}
            },
            "responses":{"Error":{"description":"Structured Agent API error","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}}}
        },
        "paths":{
            "/agent/v1":{"get":{"summary":"Read Agent identity","responses":{"200":{"description":"Identity"}}}},
            "/agent/v1/auth/exchange":{"post":{"security":[],"summary":"Exchange one-use enrollment credential","requestBody":{"required":True,"content":{"application/json":{"schema":{"type":"object","required":["enrollment_token"],"properties":{"enrollment_token":{"type":"string"}}},"example":{"enrollment_token":"pd_enroll_…"}}}},"responses":{"201":{"description":"Bearer access credential"},"401":{"$ref":"#/components/responses/Error"}}}},
            "/agent/v1/auth/me":{"get":{"summary":"Read current Agent and credential metadata"}},
            "/agent/v1/capabilities":{"get":{"summary":"Discover enabled scopes and capabilities"}},
            "/agent/v1/agent.md":{"get":{"summary":"Generate Agent-specific AGENT.md with short-lived enrollment credential"}},
            "/agent/v1/openapi.json":{"get":{"summary":"Get this OpenAPI document"}},
            "/agent/v1/services":{"get":{"summary":"List accessible services"},"post":{"summary":"Create owned service","parameters":[idem],"requestBody":{"content":{"application/json":{"schema":{"type":"object","required":["name","plan","network"],"properties":{"name":{"type":"string"},"plan":{"type":"string","format":"uuid"},"network":{"type":"string","format":"uuid"}}},"example":{"name":"my-app","plan":"00000000-0000-0000-0000-000000000001","network":"00000000-0000-0000-0000-000000000002"}}}}}}},
            "/agent/v1/services/from-plan":{"post":{"summary":"Create service from existing plan","parameters":[idem]}},
            "/agent/v1/services/{service_id}":{"get":{"summary":"Inspect service"},"patch":{"summary":"Update service","parameters":[idem]},"delete":{"summary":"Delete owner service","parameters":[idem]}},
            "/agent/v1/services/{service_id}/start":{"post":{"summary":"Start service","parameters":[idem]}},
            "/agent/v1/services/{service_id}/stop":{"post":{"summary":"Stop service","parameters":[idem]}},
            "/agent/v1/services/{service_id}/restart":{"post":{"summary":"Restart service","parameters":[idem]}},
            "/agent/v1/services/{service_id}/purge-runtime":{"post":{"summary":"Purge service runtime","parameters":[idem]}},
            "/agent/v1/services/{service_id}/status":{"get":{"summary":"Read live service status through existing runtime boundary"}},
            "/agent/v1/services/{service_id}/logs":{"get":{"summary":"Read runtime service logs"}},
            "/agent/v1/services/{service_id}/logs/export":{"get":{"summary":"Export runtime service logs"}},
            "/agent/v1/services/{service_id}/configuration":{"get":{"summary":"Read safe service configuration"},"patch":{"summary":"Update configuration","parameters":[idem]}},
            "/agent/v1/services/{service_id}/environment":{"get":{"summary":"Read environment with secrets masked"},"post":{"summary":"Set environment value","parameters":[idem]},"delete":{"summary":"Disable environment value","parameters":[idem]}},
            "/agent/v1/services/{service_id}/secrets":{"get":{"summary":"Read secret metadata only"},"post":{"summary":"Create or rotate secret","parameters":[idem]},"delete":{"summary":"Disable secret","parameters":[idem]}},
            "/agent/v1/services/{service_id}/endpoints":{"get":{"summary":"Read endpoints"},"post":{"summary":"Manage endpoint","parameters":[idem]},"delete":{"summary":"Disable endpoint","parameters":[idem]}},
            "/agent/v1/services/{service_id}/networks":{"get":{"summary":"Read network attachments"},"post":{"summary":"Attach network","parameters":[idem]},"delete":{"summary":"Detach network","parameters":[idem]}},
            "/agent/v1/services/{service_id}/revisions":{"get":{"summary":"List immutable revisions"}},
            "/agent/v1/services/{service_id}/revisions/{revision_id}":{"get":{"summary":"Inspect immutable revision"}},
            "/agent/v1/services/{service_id}/revisions/{revision_id}/rollback":{"post":{"summary":"Rollback through existing revision boundary","parameters":[idem]}},
            "/agent/v1/services/{service_id}/shell":{"get":{"summary":"Read restricted shell capability and policy"}},
            "/agent/v1/services/{service_id}/shell/sessions":{"post":{"summary":"Create restricted service-container shell session"}},
            "/agent/v1/services/{service_id}/shell/sessions/{session_id}/commands":{"post":{"summary":"Execute command through existing shell security policy","requestBody":{"content":{"application/json":{"schema":{"type":"object","required":["command"],"properties":{"command":{"type":"string"},"confirm":{"type":"boolean"},"dry_run":{"type":"boolean"}}},"example":{"command":"python manage.py migrate","confirm":False}}}}},"responses":{"200":{"description":"Command result","content":{"application/json":{"schema":{"$ref":"#/components/schemas/ShellCommandResult"}}}}}}},
            "/agent/v1/services/{service_id}/shell/sessions/{session_id}/close":{"post":{"summary":"Close shell session"}},
            "/agent/v1/services/{service_id}/shell/replace":{"post":{"summary":"Replace shell session after confirmation"}},
            "/agent/v1/services/{service_id}/shell/files":{"post":{"summary":"Use existing restricted file operation boundary"}},
            "/agent/v1/plans":{"get":{"summary":"List plans"}},
            "/agent/v1/plans/{plan_id}":{"get":{"summary":"Inspect plan"}},
            "/agent/v1/plans/manage":{"post":{"summary":"Create plan; existing staff/admin permission required","parameters":[idem]}},
            "/agent/v1/plans/manage/{plan_id}":{"patch":{"summary":"Update plan; existing staff/admin permission required","parameters":[idem]},"delete":{"summary":"Delete unused plan","parameters":[idem]}},
            "/agent/v1/networks":{"get":{"summary":"List owned private networks"},"post":{"summary":"Create private network","parameters":[idem]}},
            "/agent/v1/networks/{network_id}":{"get":{"summary":"Inspect network"},"patch":{"summary":"Update network","parameters":[idem]},"delete":{"summary":"Delete network","parameters":[idem]}},
            "/agent/v1/volumes":{"get":{"summary":"List volumes through existing volume authorization"},"post":{"summary":"Create volume through existing quota checks","parameters":[idem]}},
            "/agent/v1/volumes/{volume_id}":{"get":{"summary":"Inspect volume"},"patch":{"summary":"Update volume","parameters":[idem]},"delete":{"summary":"Delete volume","parameters":[idem]}},
            "/agent/v1/deployments":{"get":{"summary":"List accessible deployments"},"post":{"summary":"Create deployment metadata","parameters":[idem]}},
            "/agent/v1/deployments/{deployment_id}":{"get":{"summary":"Inspect deployment"},"delete":{"summary":"Delete deployment","parameters":[idem]}},
            "/agent/v1/deployments/{deployment_id}/upload":{"post":{"summary":"Upload ZIP source archive","parameters":[idem]}},
            "/agent/v1/deployments/{deployment_id}/start":{"post":{"summary":"Start deployment","parameters":[idem]}},
            "/agent/v1/deployments/{deployment_id}/cancel":{"post":{"summary":"Cancel deployment","parameters":[idem]}},
            "/agent/v1/deployments/{deployment_id}/redeploy":{"post":{"summary":"Redeploy","parameters":[idem]}},
            "/agent/v1/deployments/{deployment_id}/rebuild":{"post":{"summary":"Rebuild deployment","parameters":[idem]}},
            "/agent/v1/deployments/{deployment_id}/rollback":{"post":{"summary":"Rollback deployment to immutable revision","parameters":[idem]}},
            "/agent/v1/deployments/{deployment_id}/logs":{"get":{"summary":"Read deployment lifecycle/build logs"}},
            "/agent/v1/deployments/{deployment_id}/logs/export":{"get":{"summary":"Export deployment lifecycle logs"}}
        },
        "x-agent":{"agent_id":str(agent.pk),"enabled_scopes":sorted(agent.scopes or []),"deployment_inputs":{"archive_zip":True,"database_native":True,"git":False,"existing_image":False},"log_sources_are_separate":True}
    }
