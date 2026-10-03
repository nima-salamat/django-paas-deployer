from __future__ import annotations

from .manifest import api_base_url
from .contracts import CONTRACTS, contracts_for_agent


def _field_schema(field):
    """Translate a DRF serializer field into an OpenAPI schema."""
    from rest_framework import serializers

    nullable = bool(getattr(field, "allow_null", False))
    if isinstance(field, serializers.FileField):
        schema = {"type": "string", "format": "binary"}
    elif isinstance(field, serializers.UUIDField):
        schema = {"type": "string", "format": "uuid"}
    elif isinstance(field, serializers.PrimaryKeyRelatedField):
        model = getattr(getattr(field, "queryset", None), "model", None)
        pk = getattr(getattr(model, "_meta", None), "pk", None)
        schema = {"type": "string"}
        if getattr(pk, "get_internal_type", lambda: "")() == "UUIDField":
            schema["format"] = "uuid"
    elif isinstance(field, serializers.ChoiceField):
        schema = {"type": "string", "enum": list(field.choices.keys())}
    elif isinstance(field, serializers.BooleanField):
        schema = {"type": "boolean"}
    elif isinstance(field, serializers.IntegerField):
        schema = {"type": "integer"}
    elif isinstance(field, (serializers.FloatField, serializers.DecimalField)):
        schema = {"type": "number"}
    elif isinstance(field, serializers.DateTimeField):
        schema = {"type": "string", "format": "date-time"}
    elif isinstance(field, serializers.DateField):
        schema = {"type": "string", "format": "date"}
    elif isinstance(field, serializers.TimeField):
        schema = {"type": "string", "format": "time"}
    elif isinstance(field, serializers.ListSerializer):
        schema = {
            "type": "array",
            "items": _field_schema(field.child),
        }
    elif isinstance(field, serializers.ListField):
        schema = {
            "type": "array",
            "items": _field_schema(field.child),
        }
    elif isinstance(field, serializers.DictField):
        schema = {
            "type": "object",
            "additionalProperties": _field_schema(field.child)
            if field.child is not None
            else True,
        }
    elif isinstance(field, serializers.JSONField):
        schema = {"type": "object", "additionalProperties": True}
    elif isinstance(field, serializers.BaseSerializer):
        nested = {}
        for name, nested_field in field.fields.items():
            if getattr(nested_field, "write_only", False):
                continue
            nested[name] = _field_schema(nested_field)
        schema = {"type": "object", "properties": nested}
    else:
        schema = {"type": "string"}

    for attr in ("max_length", "min_length", "max_value", "min_value"):
        value = getattr(field, attr, None)
        if value is not None:
            key = attr
            if attr == "max_value":
                key = "maximum"
            elif attr == "min_value":
                key = "minimum"
            elif attr == "max_length":
                key = "maxLength"
            elif attr == "min_length":
                key = "minLength"
            schema[key] = value

    regex = getattr(getattr(field, "regex", None), "pattern", None)
    if regex:
        schema["pattern"] = regex

    if not getattr(field, "allow_blank", True) and schema.get("type") == "string":
        schema.setdefault("minLength", 1)

    default = getattr(field, "default", None)
    from rest_framework.fields import empty
    if default is not empty and not callable(default):
        if isinstance(default, (str, int, float, bool)) or default is None:
            schema["default"] = default
        else:
            schema["default"] = str(default)

    if nullable:
        schema["nullable"] = True
    if getattr(field, "read_only", False):
        schema["readOnly"] = True
    if getattr(field, "write_only", False):
        schema["writeOnly"] = True
    if getattr(field, "help_text", None):
        schema["description"] = str(field.help_text)

    return schema


def _serializer_schema(serializer_cls, *, instance=False, exclude=(), description=None, writable=False):
    """Build an object schema from the real DRF serializer fields."""
    serializer = serializer_cls(instance=object()) if instance else serializer_cls()
    properties = {}
    required = []
    excluded = set(exclude)
    for name, field in serializer.fields.items():
        if name in excluded:
            continue
        if writable and getattr(field, "read_only", False):
            continue
        if writable and getattr(field, "write_only", False) and instance:
            continue
        schema = _field_schema(field)
        if instance:
            schema.pop("readOnly", None)
        properties[name] = schema
        if writable and getattr(field, "required", False):
            required.append(name)
    result = {"type": "object", "properties": properties}
    if required:
        result["required"] = sorted(set(required))
    if description:
        result["description"] = description
    return result


def _json_body(schema, *, example=None, description=None):
    media = {"schema": schema}
    if example is not None:
        media["example"] = example
    body = {"required": True, "content": {"application/json": media}}
    if description:
        body["description"] = description
    return body


def _parameter(name, location, schema, *, required=False, description=None):
    result = {
        "name": name,
        "in": location,
        "required": required,
        "schema": schema,
    }
    if description:
        result["description"] = description
    return result


def _merge_query_parameters(operation, parameters):
    existing = {
        (item.get("in"), item.get("name"))
        for item in operation.setdefault("parameters", [])
        if isinstance(item, dict)
    }
    for item in parameters:
        key = (item.get("in"), item.get("name"))
        if key not in existing:
            operation["parameters"].append(item)
            existing.add(key)


def _operation_id(path, method):
    import re
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", path.strip("/")).strip("_")
    return f"agent_{method.lower()}_{slug}"


def _path_parameters(path):
    import re
    params = []
    for name in re.findall(r"\{([^}]+)\}", path):
        params.append(
            _parameter(
                name,
                "path",
                {"type": "string", "format": "uuid"},
                required=True,
                description=f"PassDeployer {name.replace('_', ' ')}.",
            )
        )
    return params


def _auth_error_responses(error_ref):
    return {
        "400": {"description": "Invalid request", "content": {"application/json": {"schema": error_ref}}},
        "401": {"description": "Authentication required or invalid credential", "content": {"application/json": {"schema": error_ref}}},
        "403": {"description": "Insufficient Agent scope or existing user/share permission", "content": {"application/json": {"schema": error_ref}}},
        "404": {"description": "Resource not found", "content": {"application/json": {"schema": error_ref}}},
        "409": {"description": "Conflict, invalid state, idempotency conflict, or confirmation required", "content": {"application/json": {"schema": error_ref}}},
        "413": {"description": "Payload or upload too large", "content": {"application/json": {"schema": error_ref}}},
        "422": {"description": "Unsupported capability or configuration", "content": {"application/json": {"schema": error_ref}}},
        "429": {"description": "Rate limited", "content": {"application/json": {"schema": error_ref}}},
        "500": {"description": "Internal/runtime error", "content": {"application/json": {"schema": error_ref}}},
    }


def _add_operation_metadata(operation, contract, agent, *, response=None, response_status=None, sensitive=False, confirmation=False, tags=None, description=None):
    scopes = set(agent.scopes or [])
    operation.setdefault("operationId", _operation_id(contract.path, contract.method))
    operation.setdefault("summary", f"{contract.method} {contract.path}")
    if description:
        operation["description"] = description
    if tags:
        operation["tags"] = list(tags)
    operation["x-required-scopes"] = list(contract.scopes)
    operation["x-required-any-scopes"] = list(contract.any_scopes)
    operation["x-mutating"] = contract.mutating
    operation["x-idempotent"] = contract.idempotent
    operation["x-throttle-scope"] = contract.throttle_scope
    operation["x-enabled-for-agent"] = (
        set(contract.scopes).issubset(scopes)
        and (not contract.any_scopes or bool(set(contract.any_scopes) & scopes))
    )
    operation["security"] = [] if contract.path == "/agent/v1/auth/exchange" else [{"AgentBearer": []}]
    parameters = operation.setdefault("parameters", [])
    existing = {(p.get("in"), p.get("name")) for p in parameters if isinstance(p, dict)}
    for p in _path_parameters(contract.path):
        if (p["in"], p["name"]) not in existing:
            parameters.append(p)
            existing.add((p["in"], p["name"]))
    if contract.idempotent and ("header", "Idempotency-Key") not in existing:
        parameters.append({"$ref": "#/components/parameters/IdempotencyKey"})
    if sensitive:
        operation["x-sensitive-response"] = True
    if confirmation:
        operation["x-confirmation-required"] = True
    if response_status is not None and response is not None:
        response_entry = {
            "description": response.get("description", "Successful operation"),
        }
        if response_status != 204:
            response_entry["content"] = {
                "application/json": {
                    "schema": {"$ref": f"#/components/schemas/{response['schema']}"}
                }
            }
        operation.setdefault("responses", {})[str(response_status)] = response_entry
    responses = operation.setdefault("responses", {})
    errors = _auth_error_responses({"$ref": "#/components/schemas/Error"})
    for status, value in errors.items():
        responses.setdefault(status, value)

def build_openapi(agent, *, request=None):
    origin = api_base_url(request).rsplit("/agent/v1", 1)[0] if request else "/"
    idempotency = {
        "name": "Idempotency-Key",
        "in": "header",
        "required": False,
        "schema": {"type": "string", "maxLength": 255},
        "description": "24-hour idempotency key for retry-safe mutating requests.",
    }
    error_ref = {"$ref": "#/components/schemas/Error"}
    paths = {
        "/agent/v1/": {
            "get": {"summary": "Read Agent identity", "responses": {"200": {"description": "Identity"}}},
        },
        "/agent/v1/skills": {
            "get": {
                "summary": "List Skill playbooks enabled for this Agent",
                "responses": {
                    "200": {
                        "description": "Scope-filtered Skill index",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/SkillIndex"}
                            }
                        }
                    }
                }
            }
        },
        "/agent/v1/skills/{skill_name}": {
            "get": {
                "summary": "Get one scope-aware Skill playbook",
                "parameters": [
                    {
                        "name": "skill_name",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"}
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Markdown Skill playbook",
                        "content": {"text/markdown": {"schema": {"type": "string"}}}
                    },
                    "403": {"$ref": "#/components/responses/Error"},
                    "404": {"$ref": "#/components/responses/Error"}
                }
            }
        },
        "/agent/v1/auth/exchange": {
            "post": {
                "security": [],
                "summary": "Exchange a one-use enrollment credential",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["enrollment_token"],
                                "properties": {"enrollment_token": {"type": "string"}},
                            },
                            "example": {"enrollment_token": "pd_enroll_<one-time-value>"},
                        }
                    },
                },
                "responses": {
                    "201": {"description": "Bearer access credential"},
                    "401": {"$ref": "#/components/responses/Error"},
                },
            }
        },
        "/agent/v1/auth/me": {"get": {"summary": "Read Agent and credential metadata"}},
        "/agent/v1/capabilities": {"get": {"summary": "Discover enabled Agent capabilities"}},
        "/agent/v1/agent.md": {"get": {"summary": "Generate Agent-specific AGENT.md with one-use enrollment credential"}},
        "/agent/v1/openapi.json": {"get": {"summary": "Get this OpenAPI document"}},
        "/agent/v1/services": {
            "get": {"summary": "List accessible services"},
            "post": {
                "summary": "Create owned service",
                "parameters": [idempotency],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["name", "plan", "network"],
                                "properties": {
                                    "name": {"type": "string"},
                                    "plan": {"type": "string", "format": "uuid"},
                                    "network": {"type": "string", "format": "uuid"},
                                },
                            },
                            "example": {
                                "name": "my-app",
                                "plan": "00000000-0000-0000-0000-000000000001",
                                "network": "00000000-0000-0000-0000-000000000002",
                            },
                        }
                    },
                },
            },
        },
        "/agent/v1/services/from-plan": {
            "post": {"summary": "Create service from existing plan", "parameters": [idempotency]}
        },
        "/agent/v1/services/{service_id}": {
            "get": {"summary": "Inspect service"},
            "patch": {"summary": "Update service", "parameters": [idempotency]},
            "delete": {"summary": "Delete owner service", "parameters": [idempotency]},
        },
        "/agent/v1/services/{service_id}/start": {"post": {"summary": "Start service", "parameters": [idempotency]}},
        "/agent/v1/services/{service_id}/stop": {"post": {"summary": "Stop service", "parameters": [idempotency]}},
        "/agent/v1/services/{service_id}/restart": {"post": {"summary": "Restart service", "parameters": [idempotency]}},
        "/agent/v1/services/{service_id}/rebuild": {"post": {"summary": "Rebuild service runtime from the active revision", "parameters": [idempotency]}},
        "/agent/v1/services/{service_id}/purge-runtime": {"post": {"summary": "Purge service runtime", "parameters": [idempotency]}},
        "/agent/v1/services/{service_id}/status": {"get": {"summary": "Read service status through existing runtime boundary"}},
        "/agent/v1/services/{service_id}/metrics": {
            "get": {
                "summary": "Read observed runtime CPU/RAM usage and plan limits",
                "responses": {
                    "200": {
                        "description": "Observed runtime metrics",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ServiceMetrics"}
                            }
                        }
                    }
                }
            }
        },
        "/agent/v1/services/{service_id}/logs": {
            "get": {
                "summary": "Read runtime service logs",
                "parameters": [
                    {"name": "cursor", "in": "query", "schema": {"type": "string"}},
                    {"name": "from", "in": "query", "schema": {"type": "string", "format": "date-time"}},
                    {"name": "to", "in": "query", "schema": {"type": "string", "format": "date-time"}},
                    {"name": "level", "in": "query", "schema": {"type": "string"}},
                    {"name": "stream", "in": "query", "schema": {"type": "string"}},
                    {"name": "q", "in": "query", "schema": {"type": "string"}},
                    {"name": "limit", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 500}},
                ],
            }
        },
        "/agent/v1/services/{service_id}/logs/export": {"get": {"summary": "Export runtime service logs"}},
        "/agent/v1/services/{service_id}/configuration": {
            "get": {"summary": "Read safe service configuration"},
            "patch": {"summary": "Update service configuration", "parameters": [idempotency]},
        },
        "/agent/v1/services/{service_id}/environment": {
            "get": {"summary": "Read environment with secrets masked"},
            "post": {"summary": "Set environment value", "parameters": [idempotency]},
            "delete": {"summary": "Disable environment value", "parameters": [idempotency]},
        },
        "/agent/v1/services/{service_id}/secrets": {
            "get": {"summary": "Read secret metadata only"},
            "post": {"summary": "Create or rotate secret", "parameters": [idempotency]},
            "delete": {"summary": "Disable secret", "parameters": [idempotency]},
        },
        "/agent/v1/services/{service_id}/endpoints": {
            "get": {"summary": "Read endpoints"},
            "post": {"summary": "Manage endpoint", "parameters": [idempotency]},
            "delete": {"summary": "Disable endpoint", "parameters": [idempotency]},
        },
        "/agent/v1/services/{service_id}/databases": {
            "get": {"summary": "Read database bindings through the existing boundary"},
            "post": {"summary": "Create/update database binding", "parameters": [idempotency]},
            "delete": {"summary": "Remove database binding", "parameters": [idempotency]},
        },
        "/agent/v1/services/{service_id}/database-credentials": {
            "get": {
                "summary": "Read database connection credentials for the owning user only",
                "parameters": [
                    {
                        "name": "reveal",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "boolean", "default": False},
                        "description": "When true, return the decrypted database password. Requires the dedicated high-risk scope."
                    }
                ]
            }
        },
        "/agent/v1/services/{service_id}/networks": {
            "get": {"summary": "Read network attachments"},
            "post": {"summary": "Attach network", "parameters": [idempotency]},
            "delete": {"summary": "Detach network", "parameters": [idempotency]},
        },
        "/agent/v1/services/{service_id}/revisions": {"get": {"summary": "List immutable revisions"}},
        "/agent/v1/services/{service_id}/revisions/{revision_id}": {"get": {"summary": "Inspect immutable revision"}},
        "/agent/v1/services/{service_id}/revisions/{revision_id}/rollback": {
            "post": {"summary": "Rollback through existing revision boundary", "parameters": [idempotency]}
        },
        "/agent/v1/services/{service_id}/shell": {"get": {"summary": "Read restricted shell capability and policy"}},
        "/agent/v1/services/{service_id}/shell/sessions": {"post": {"summary": "Create restricted service-container shell session"}},
        "/agent/v1/services/{service_id}/shell/sessions/{session_id}/commands": {
            "post": {
                "summary": "Execute command through the existing shell security policy",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["command"],
                                "properties": {
                                    "command": {"type": "string"},
                                    "confirm": {"type": "boolean", "default": False},
                                    "dry_run": {"type": "boolean", "default": False},
                                },
                            },
                            "example": {"command": "python manage.py migrate", "confirm": False},
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Command result",
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ShellCommandResult"}}},
                    }
                },
            }
        },
        "/agent/v1/services/{service_id}/shell/sessions/{session_id}/close": {
            "post": {"summary": "Close restricted shell session"}
        },
        "/agent/v1/services/{service_id}/shell/replace": {
            "post": {"summary": "Replace shell session after explicit confirmation"}
        },
        "/agent/v1/services/{service_id}/shell/files": {
            "post": {"summary": "Use the existing restricted file operation boundary"}
        },
        "/agent/v1/plans": {"get": {"summary": "List plans"}},
        "/agent/v1/plans/{plan_id}": {"get": {"summary": "Inspect plan"}},
        "/agent/v1/plans/{plan_id}/apply": {"post": {"summary": "Create service from this plan", "parameters": [idempotency]}},
        "/agent/v1/plans/manage": {
            "post": {"summary": "Create plan; existing staff/admin permission required", "parameters": [idempotency]}
        },
        "/agent/v1/plans/manage/{plan_id}": {
            "patch": {"summary": "Update plan; existing staff/admin permission required", "parameters": [idempotency]},
            "delete": {"summary": "Delete unused plan; existing staff/admin permission required", "parameters": [idempotency]},
        },
        "/agent/v1/networks": {
            "get": {"summary": "List owned private networks"},
            "post": {"summary": "Create private network", "parameters": [idempotency]},
        },
        "/agent/v1/networks/{network_id}": {
            "get": {"summary": "Inspect private network"},
            "patch": {"summary": "Update private network", "parameters": [idempotency]},
            "delete": {"summary": "Delete private network", "parameters": [idempotency]},
        },
        "/agent/v1/volumes": {
            "get": {"summary": "List volumes through existing volume authorization"},
            "post": {"summary": "Create volume through existing quota checks", "parameters": [idempotency]},
        },
        "/agent/v1/volumes/{volume_id}": {
            "get": {"summary": "Inspect volume"},
            "patch": {"summary": "Update volume through existing protection rules", "parameters": [idempotency]},
            "delete": {"summary": "Delete volume through existing protection rules", "parameters": [idempotency]},
        },
        "/agent/v1/deployments/help": {
            "get": {"summary": "Get complete deployment configuration, platform and lifecycle help"}
        },
        "/agent/v1/deployments/inspect": {
            "post": {
                "summary": "Inspect a ZIP and return detected platform/configuration suggestions",
                "requestBody": {
                    "required": True,
                    "content": {
                        "multipart/form-data": {
                            "schema": {
                                "type": "object",
                                "required": ["file"],
                                "properties": {"file": {"type": "string", "format": "binary"}}
                            }
                        }
                    }
                }
            }
        },
        "/agent/v1/deployments": {
            "get": {"summary": "List accessible deployments"},
            "post": {
                "summary": "Create deployment metadata",
                "parameters": [idempotency],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["service"],
                                "properties": {
                                    "service": {"type": "string", "format": "uuid"},
                                    "source": {"type": "string", "enum": ["archive", "zip", "database", "database_native"]},
                                    "config": {"type": "object", "description": "Use GET /agent/v1/deployments/help for the complete contract and per-platform defaults/schema."}
                                }
                            }
                        }
                    }
                }
            },
        },
        "/agent/v1/deployments/{deployment_id}": {
            "get": {"summary": "Inspect deployment"},
            "delete": {"summary": "Delete deployment", "parameters": [idempotency]},
        },
        "/agent/v1/deployments/{deployment_id}/upload": {
            "post": {
                "summary": "Upload ZIP source archive",
                "parameters": [idempotency],
                "requestBody": {
                    "required": True,
                    "content": {
                        "multipart/form-data": {
                            "schema": {
                                "type": "object",
                                "required": ["file"],
                                "properties": {"file": {"type": "string", "format": "binary"}},
                            }
                        }
                    },
                },
            }
        },
        "/agent/v1/deployments/{deployment_id}/start": {"post": {"summary": "Start deployment", "parameters": [idempotency]}},
        "/agent/v1/deployments/{deployment_id}/cancel": {"post": {"summary": "Cancel deployment", "parameters": [idempotency]}},
        "/agent/v1/deployments/{deployment_id}/redeploy": {"post": {"summary": "Redeploy deployment", "parameters": [idempotency]}},
        "/agent/v1/deployments/{deployment_id}/rebuild": {"post": {"summary": "Rebuild deployment", "parameters": [idempotency]}},
        "/agent/v1/deployments/{deployment_id}/rollback": {"post": {"summary": "Rollback deployment to immutable revision", "parameters": [idempotency]}},
        "/agent/v1/deployments/{deployment_id}/logs": {
            "get": {"summary": "Read deployment lifecycle/build logs"}
        },
        "/agent/v1/deployments/{deployment_id}/logs/export": {
            "get": {"summary": "Export deployment lifecycle logs"}
        },
    }

    # Build request schemas from the real serializers instead of maintaining
    # a second hand-written model definition.
    from services.serializers import ServiceSerializer, PrivateNetworkSerializer, VolumeSerializer
    from plans.serializers import PlanSerializer
    from deploy.serializers import DeploySerializer
    from services.models import Service, ServiceEnvironmentVariable, ServiceEndpoint
    from agent.scopes import HIGH_RISK_SCOPES
    from .throttling import AgentRateThrottle

    service_create = _serializer_schema(ServiceSerializer, exclude={"user"}, writable=True)
    service_create.setdefault("required", [])
    service_create["required"] = sorted(set(service_create["required"]) | {"name", "plan", "network"})
    service_create["description"] = (
        "Fields accepted by the existing ServiceSerializer for Agent-owned "
        "service creation. User ownership is assigned from the authenticated Agent user. "
        "The Agent facade additionally requires a Private Network."
    )
    service_update = _serializer_schema(ServiceSerializer, instance=True, exclude={"user"}, writable=True)
    service_update["required"] = []
    service_update["description"] = "Writable service fields after applying the existing Service serializer read-only rules."

    network_create = _serializer_schema(PrivateNetworkSerializer, writable=True)
    network_create["description"] = "Private network fields accepted by the existing user-facing network serializer."
    network_update = _serializer_schema(PrivateNetworkSerializer, instance=True, writable=True)
    network_update["required"] = []

    volume_create = _serializer_schema(VolumeSerializer, exclude={"user"}, writable=True)
    volume_create.setdefault("required", [])
    volume_create["required"] = sorted(set(volume_create["required"]) | {"service"})
    volume_create["description"] = "Volume fields accepted by the existing VolumeSerializer; the Agent facade requires a Service."
    volume_update = _serializer_schema(VolumeSerializer, instance=True, exclude={"user"}, writable=True)
    volume_update["required"] = []

    plan_create = _serializer_schema(PlanSerializer, writable=True)
    plan_update = _serializer_schema(PlanSerializer, instance=True, writable=True)
    plan_update["required"] = []

    deployment_create = _serializer_schema(DeploySerializer, exclude={"zip_file"}, writable=True)
    deployment_create.setdefault("required", [])
    deployment_create["required"] = sorted(set(deployment_create["required"]) | {"service"})
    deployment_create["properties"]["source"] = {
        "type": "string",
        "enum": ["archive", "zip", "database", "database_native"],
        "default": "archive",
        "description": "Agent deployment input kind. Git and existing-image inputs are not first-class Agent inputs.",
    }
    deployment_create["description"] = (
        "Deployment metadata accepted by DeploySerializer plus the Agent-level source selector. "
        "Use /deployments/help for platform-specific configuration."
    )

    source_kind_values = [value for value, _label in Service.SourceKind.choices]

    schemas = {
        "AgentExchangeRequest": {
            "type": "object",
            "required": ["enrollment_token"],
            "properties": {
                "enrollment_token": {
                    "type": "string",
                    "minLength": 1,
                    "description": "The short-lived enrollment credential intentionally supplied to this Agent. Exchange it exactly once.",
                },
                "client": {
                    "type": "string",
                    "maxLength": 100,
                    "description": "Optional client identifier recorded as sanitized metadata.",
                },
            },
        },
        "AgentExchangeResponse": {
            "type": "object",
            "required": ["result", "token", "token_type", "expires_at", "agent", "scopes"],
            "properties": {
                "result": {"type": "string", "enum": ["success"]},
                "token": {"type": "string", "description": "Bearer access credential. Treat as secret material."},
                "token_type": {"type": "string", "enum": ["Bearer"]},
                "expires_at": {"type": "string", "format": "date-time"},
                "agent": {"type": "object", "properties": {"id": {"type": "string", "format": "uuid"}, "name": {"type": "string"}}},
                "scopes": {"type": "array", "items": {"type": "string"}},
            },
        },
        "AgentIdentity": {
            "type": "object",
            "properties": {
                "result": {"type": "string"},
                "api_version": {"type": "string"},
                "agent": {"$ref": "#/components/schemas/AgentSummary"},
                "user": {"type": "object"},
                "scopes": {"type": "array", "items": {"type": "string"}},
                "links": {"type": "object", "additionalProperties": {"type": "string"}},
            },
        },
        "AgentSummary": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "format": "uuid"},
                "name": {"type": "string"},
                "description": {"type": "string", "nullable": True},
                "status": {"type": "string"},
            },
        },
        "AgentMe": {
            "type": "object",
            "properties": {
                "result": {"type": "string"},
                "agent_id": {"type": "string", "format": "uuid"},
                "name": {"type": "string"},
                "user": {"type": "object"},
                "scopes": {"type": "array", "items": {"type": "string"}},
                "credential": {"type": "object", "properties": {
                    "id": {"type": "string", "format": "uuid"},
                    "prefix": {"type": "string"},
                    "expires_at": {"type": "string", "format": "date-time"},
                    "last_used_at": {"type": "string", "format": "date-time", "nullable": True},
                }},
            },
        },
        "Error": {
            "type": "object",
            "required": ["result", "code", "detail", "request_id", "retryable", "failure_domain", "resource_effect", "certainty"],
            "properties": {
                "result": {"type": "string", "enum": ["error"]},
                "code": {"type": "string"},
                "detail": {"type": "string"},
                "request_id": {"type": "string", "format": "uuid", "nullable": True},
                "retryable": {"type": "boolean"},
                "failure_domain": {"type": "string"},
                "visibility": {"type": "string"},
                "resource_effect": {"type": "string"},
                "certainty": {"type": "string"},
                "missing_scopes": {"type": "array", "items": {"type": "string"}},
                "supported_inputs": {"type": "array", "items": {"type": "string"}},
                "errors": {"type": "object", "additionalProperties": True},
            },
        },
        "ServiceCreateRequest": service_create,
        "ServiceUpdateRequest": service_update,
        "ServiceFromPlanRequest": {
            "type": "object",
            "description": "Service creation fields plus optional automatic network creation. The plan must be supplied for this endpoint.",
            "properties": {
                **service_create.get("properties", {}),
                "create_network": {"type": "boolean", "default": False},
                "network_name": {"type": "string", "maxLength": 255, "description": "Used only when create_network=true."},
            },
            "required": sorted((set(service_create.get("required", [])) - {"network"}) | {"plan", "name"}),
        },
        "PlanApplyRequest": {
            "type": "object",
            "description": "Optional service fields for applying the plan identified by the URL.",
            "properties": {
                **service_create.get("properties", {}),
                "create_network": {"type": "boolean", "default": False},
                "network_name": {"type": "string", "maxLength": 255},
            },
            "required": sorted(set(service_create.get("required", [])) - {"network", "plan"}),
        },
        "NetworkCreateRequest": network_create,
        "NetworkUpdateRequest": network_update,
        "VolumeCreateRequest": volume_create,
        "VolumeUpdateRequest": volume_update,
        "PlanCreateRequest": plan_create,
        "PlanUpdateRequest": plan_update,
        "DeploymentCreateRequest": deployment_create,
        "ConfigurationPatchRequest": {
            "type": "object",
            "properties": {
                "source_kind": {"type": "string", "enum": source_kind_values},
                "source_config": {"type": "object", "additionalProperties": True},
                "build_config": {"type": "object", "additionalProperties": True},
                "runtime_config": {"type": "object", "additionalProperties": True},
                "desired_state": {"type": "string", "enum": ["running", "stopped"]},
            },
            "additionalProperties": False,
            "description": "Declarative service configuration. Secret-like values are rejected here and must use secret resources.",
        },
        "EnvironmentMutationRequest": {
            "type": "object",
            "required": ["key"],
            "properties": {
                "key": {"type": "string", "pattern": "^[A-Za-z_][A-Za-z0-9_]{0,127}$"},
                "scope": {
                    "type": "string",
                    "enum": [value for value, _label in ServiceEnvironmentVariable.Scope.choices],
                    "default": ServiceEnvironmentVariable.Scope.RUNTIME,
                },
                "is_secret": {"type": "boolean", "default": False},
                "value": {"type": "string"},
            },
        },
        "SecretMutationRequest": {
            "type": "object",
            "required": ["key", "value"],
            "properties": {
                "key": {"type": "string", "pattern": "^[A-Za-z_][A-Za-z0-9_]{0,127}$"},
                "value": {"type": "string", "writeOnly": True},
                "note": {"type": "string"},
                "description": {"type": "string", "maxLength": 255},
            },
        },
        "EndpointMutationRequest": {
            "type": "object",
            "required": ["name", "target_port"],
            "properties": {
                "name": {"type": "string"},
                "process": {"type": "string", "format": "uuid", "nullable": True},
                "target_port": {"type": "integer", "minimum": 1, "maximum": 65535},
                "published_port": {"type": "integer", "minimum": 1, "maximum": 65535, "nullable": True},
                "protocol": {
                    "type": "string",
                    "enum": [value for value, _label in ServiceEndpoint.Protocol.choices],
                    "default": ServiceEndpoint.Protocol.HTTP,
                },
                "exposure": {
                    "type": "string",
                    "enum": [value for value, _label in ServiceEndpoint.Exposure.choices],
                    "default": ServiceEndpoint.Exposure.PUBLIC,
                },
                "hostname": {"type": "string"},
                "path": {"type": "string"},
                "tls": {"type": "boolean", "default": False},
                "enabled": {"type": "boolean", "default": True},
                "metadata": {"type": "object", "additionalProperties": True},
            },
        },
        "NetworkAttachmentRequest": {
            "type": "object",
            "required": ["network"],
            "properties": {
                "network": {"type": "string", "format": "uuid"},
                "alias": {"type": "string", "maxLength": 128},
                "internal": {"type": "boolean", "default": False},
                "metadata": {"type": "object", "additionalProperties": True},
            },
        },
        "DatabaseBindingRequest": {
            "type": "object",
            "required": ["database"],
            "properties": {
                "database": {"type": "string", "format": "uuid"},
                "alias": {"type": "string", "maxLength": 64, "default": "default"},
                "env_prefix": {"type": "string", "maxLength": 32, "default": "DB"},
                "access_mode": {"type": "string", "maxLength": 16, "default": "rw"},
                "metadata": {"type": "object", "additionalProperties": True},
            },
        },
        "DatabaseCredentialResponse": {
            "type": "object",
            "properties": {
                "result": {"type": "string"},
                "service_id": {"type": "string", "format": "uuid"},
                "policy": {"type": "object", "additionalProperties": True},
                "results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "id": {"type": "string", "format": "uuid"},
                            "alias": {"type": "string"},
                            "database": {"type": "object", "additionalProperties": True},
                            "credentials": {
                                "type": "object",
                                "properties": {
                                    "username": {"type": "string"},
                                    "password": {"type": "string", "nullable": True, "x-sensitive": True},
                                    "root_password": {"type": "string", "nullable": True, "x-sensitive": True},
                                    "password_available": {"type": "boolean"},
                                    "revealed": {"type": "boolean"},
                                },
                            },
                        },
                    },
                },
            },
        },
        "ShellSessionCreateRequest": {
            "type": "object",
            "properties": {
                "workdir": {"type": "string", "description": "Optional restricted workspace directory."},
            },
        },
        "ShellSessionResponse": {
            "type": "object",
            "properties": {
                "result": {"type": "string"},
                "session_id": {"type": "string", "format": "uuid"},
                "token": {"type": "string", "x-sensitive": True},
                "token_type": {"type": "string", "enum": ["Shell"]},
                "platform": {"type": "string"},
                "cwd": {"type": "string"},
                "expires_at": {"type": "string", "format": "date-time"},
            },
        },
        "ShellCommandRequest": {
            "type": "object",
            "required": ["command"],
            "properties": {
                "command": {"type": "string", "minLength": 1},
                "confirm": {"type": "boolean", "default": False},
                "dry_run": {"type": "boolean", "default": False},
                "token": {"type": "string", "writeOnly": True, "description": "Optional body fallback for X-Shell-Token."},
            },
        },
        "ShellCommandResult": {
            "type": "object",
            "properties": {
                "result": {"type": "string"},
                "command": {"type": "string"},
                "exit_code": {"type": "integer"},
                "stdout": {"type": "string"},
                "stderr": {"type": "string"},
                "duration_ms": {"type": "integer", "nullable": True},
                "cwd": {"type": "string"},
                "session_id": {"type": "string", "format": "uuid", "nullable": True},
                "dry_run": {"type": "boolean"},
                "risk": {"type": "string", "nullable": True},
            },
        },
        "ShellFileRequest": {
            "type": "object",
            "required": ["action", "path"],
            "properties": {
                "action": {"type": "string", "enum": ["read", "write", "delete", "rename", "create", "create_folder", "upload"]},
                "path": {"type": "string", "minLength": 1},
                "token": {"type": "string", "writeOnly": True},
                "new_name": {"type": "string", "description": "Required for rename."},
                "content": {"type": "string", "description": "Required for write; maximum 256 KiB after UTF-8 encoding."},
                "file": {"type": "string", "format": "binary", "description": "Required for upload."},
            },
        },
        "ShellFileResponse": {
            "type": "object",
            "additionalProperties": True,
        },
        "Revision": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "format": "uuid"},
                "revision": {"type": "integer"},
                "state": {"type": "string"},
                "created_at": {"type": "string", "format": "date-time"},
                "activated_at": {"type": "string", "format": "date-time", "nullable": True},
                "source": {"type": "object", "additionalProperties": True},
                "build": {"type": "object", "additionalProperties": True},
                "runtime": {"type": "object", "additionalProperties": True},
                "environment": {"type": "object", "additionalProperties": True},
                "processes": {"type": "array"},
                "endpoints": {"type": "array"},
                "volumes": {"type": "array"},
                "networks": {"type": "array"},
                "secret_keys": {"type": "array", "items": {"type": "string"}},
            },
        },
        "ListResponse": {
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "next": {"type": "string", "format": "uri", "nullable": True},
                "previous": {"type": "string", "format": "uri", "nullable": True},
                "results": {"type": "array"},
            },
        },
    }

    # Accurate response shape for the Agent service payload.
    result_service = {
        "type": "object",
        "properties": {
            "id": {"type": "string", "format": "uuid"},
            "name": {"type": "string"},
            "owner": {"type": "object", "properties": {
                "id": {"type": "string", "format": "uuid"},
                "username": {"type": "string", "nullable": True},
            }},
            "plan": {"type": "object", "nullable": True, "additionalProperties": True},
            "platform": {"type": "string"},
            "service_host": {"type": "string", "nullable": True},
            "source_kind": {"type": "string"},
            "desired_state": {"type": "string"},
            "status": {"type": "string"},
            "read_only": {"type": "boolean"},
            "active_revision": {"type": "object", "nullable": True, "additionalProperties": True},
            "deployment": {"$ref": "#/components/schemas/Deployment"},
            "network": {"type": "object", "nullable": True, "additionalProperties": True},
            "urls": {"type": "object", "additionalProperties": True},
            "processes": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
            "endpoints": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
            "volumes": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
            "timestamps": {"type": "object", "additionalProperties": True},
        },
    }
    schemas["Service"] = result_service
    schemas["Deployment"] = {
        "type": "object",
        "properties": {
            "id": {"type": "string", "format": "uuid"},
            "release_id": {"type": "string"},
            "name": {"type": "string"},
            "service_id": {"type": "string", "format": "uuid"},
            "revision_id": {"type": "string", "format": "uuid", "nullable": True},
            "version": {"type": "string"},
            "status": {"type": "string"},
            "stage": {"type": "string"},
            "progress": {"type": "integer"},
            "status_message": {"type": "string", "nullable": True},
            "error_message": {"type": "string", "nullable": True},
            "rollback_status": {"type": "string", "nullable": True},
            "health_status": {"type": "string", "nullable": True},
            "container_status": {"type": "string", "nullable": True},
            "image_status": {"type": "string", "nullable": True},
            "volume_status": {"type": "string", "nullable": True},
            "network_status": {"type": "string", "nullable": True},
            "source_revision": {"type": "string", "nullable": True},
            "image_ref": {"type": "string", "nullable": True},
            "image_digest": {"type": "string", "nullable": True},
            "runtime_revision_id": {"type": "string", "format": "uuid", "nullable": True},
            "zip_file": {"type": "boolean"},
            "created_by": {"type": "string", "nullable": True},
            "execution_task_id": {"type": "string", "nullable": True},
            "started_at": {"type": "string", "format": "date-time", "nullable": True},
            "completed_at": {"type": "string", "format": "date-time", "nullable": True},
            "created_at": {"type": "string", "format": "date-time"},
            "updated_at": {"type": "string", "format": "date-time"},
        },
    }

    schemas["EnvironmentEntry"] = {
        "type": "object",
        "properties": {
            "key": {"type": "string"},
            "scope": {"type": "string"},
            "is_secret": {"type": "boolean"},
            "value": {"type": "string", "description": "Plain environment values or *** for secret-backed entries."},
        },
    }
    schemas["SecretMetadata"] = {
        "type": "object",
        "properties": {
            "key": {"type": "string"},
            "current_version": {"type": "integer"},
            "description": {"type": "string", "nullable": True},
            "enabled": {"type": "boolean"},
        },
    }
    schemas["Endpoint"] = {"type": "object", "additionalProperties": True}
    schemas["NetworkAttachment"] = {"type": "object", "additionalProperties": True}
    schemas["DatabaseBinding"] = {"type": "object", "additionalProperties": True}

    # Detailed operation descriptions and request/query/response contracts.
    operation_specs = {
        ("/agent/v1/auth/exchange", "POST"): {
            "schema": "AgentExchangeResponse", "status": 201, "tags": ["Identity"],
            "body": _json_body(
                {"$ref": "#/components/schemas/AgentExchangeRequest"},
                example={"enrollment_token": "pd_enroll_<one-time-value>", "client": "chatgpt"},
            ),
            "description": (
                "Exchange the short-lived, single-use enrollment credential intentionally "
                "issued to this Agent. The credential is expected to be used for bootstrap "
                "authentication. The response contains a normal Bearer credential. Do not "
                "print or disclose either credential."
            ),
        },
        ("/agent/v1/", "GET"): {
            "schema": "AgentIdentity", "status": 200, "tags": ["Identity"],
            "description": "Read the authenticated Agent identity and discovery links.",
        },
        ("/agent/v1/auth/me", "GET"): {
            "schema": "AgentMe", "status": 200, "tags": ["Identity"],
            "description": "Read the current Agent, owning user and access-credential metadata.",
        },
        ("/agent/v1/capabilities", "GET"): {
            "schema": "AgentCapabilities", "status": 200, "tags": ["Identity"],
            "description": "Discover the operations enabled by this Agent's scopes and current policy.",
        },
        ("/agent/v1/openapi.json", "GET"): {
            "schema": "OpenAPI", "status": 200, "tags": ["Identity"],
            "description": "Fetch the complete machine-readable contract for this Agent API.",
        },
        ("/agent/v1/agent.md", "GET"): {
            "schema": "Markdown", "status": 200, "tags": ["Identity"],
            "description": "Generate the Agent-specific bootstrap guide containing a short-lived enrollment credential.",
        },
        ("/agent/v1/services", "GET"): {
            "schema": "ServiceListResponse", "status": 200, "tags": ["Services"],
            "queries": [
                _parameter("q_search", "query", {"type": "string"}),
                _parameter("q", "query", {"type": "string"}),
                _parameter("search", "query", {"type": "string"}),
                _parameter("status", "query", {"type": "string"}),
                _parameter("page", "query", {"type": "integer", "minimum": 1}),
                _parameter("page_size", "query", {"type": "integer", "minimum": 1, "maximum": 100}),
            ],
            "description": "List services visible to the authenticated user through the existing Agent/service visibility rules.",
        },
        ("/agent/v1/services", "POST"): {
            "schema": "Service", "status": 201, "tags": ["Services"],
            "body": _json_body({"$ref": "#/components/schemas/ServiceCreateRequest"}),
            "description": "Create an owned Service. The authenticated user supplies ownership implicitly; the Agent facade requires a Private Network.",
        },
        ("/agent/v1/services/from-plan", "POST"): {
            "schema": "Service", "status": 201, "tags": ["Services"],
            "body": _json_body({"$ref": "#/components/schemas/ServiceFromPlanRequest"}),
            "description": "Create a Service from an existing Plan. Supply either an existing network or create_network=true with an optional network_name.",
        },
        ("/agent/v1/services/{service_id}", "GET"): {"schema": "Service", "status": 200, "tags": ["Services"], "description": "Inspect one accessible Service."},
        ("/agent/v1/services/{service_id}", "PATCH"): {
            "schema": "Service", "status": 200, "tags": ["Services"],
            "body": _json_body({"$ref": "#/components/schemas/ServiceUpdateRequest"}),
            "description": "Update writable Service fields subject to existing ownership/share rules and service-transition protections.",
        },
        ("/agent/v1/services/{service_id}", "DELETE"): {"schema": "Service", "status": 200, "tags": ["Services"], "description": "Delete an owned Service. Existing runtime/state protections still apply."},
        ("/agent/v1/services/{service_id}/start", "POST"): {"schema": "Service", "status": 200, "tags": ["Services"], "description": "Set the Service desired state to running through the existing runtime boundary.", "async": True},
        ("/agent/v1/services/{service_id}/stop", "POST"): {"schema": "Service", "status": 200, "tags": ["Services"], "description": "Set the Service desired state to stopped through the existing runtime boundary.", "async": True},
        ("/agent/v1/services/{service_id}/restart", "POST"): {"schema": "Service", "status": 200, "tags": ["Services"], "description": "Request an ordered runtime restart without creating a new revision.", "async": True},
        ("/agent/v1/services/{service_id}/rebuild", "POST"): {"schema": "Service", "status": 200, "tags": ["Services"], "description": "Rebuild the Service runtime from the active revision with force_rebuild.", "async": True},
        ("/agent/v1/services/{service_id}/purge-runtime", "POST"): {"schema": "Service", "status": 200, "tags": ["Services"], "description": "Purge the current service runtime through the existing runtime boundary.", "async": True},
        ("/agent/v1/services/{service_id}/status", "GET"): {"schema": "Service", "status": 200, "tags": ["Services"], "description": "Read observed Service runtime status."},
        ("/agent/v1/services/{service_id}/metrics", "GET"): {"schema": "ServiceMetrics", "status": 200, "tags": ["Services"], "description": "Read observed runtime CPU/RAM metrics and immutable Plan limits."},
        ("/agent/v1/services/{service_id}/logs", "GET"): {
            "schema": "RuntimeLogsResponse", "status": 200, "tags": ["Service Logs"],
            "queries": [
                _parameter("cursor", "query", {"type": "string"}),
                _parameter("from", "query", {"type": "string", "format": "date-time"}),
                _parameter("to", "query", {"type": "string", "format": "date-time"}),
                _parameter("level", "query", {"type": "string"}),
                _parameter("stream", "query", {"type": "string"}),
                _parameter("q", "query", {"type": "string"}),
                _parameter("direction", "query", {"type": "string", "enum": ["older", "newer"]}),
                _parameter("limit", "query", {"type": "integer", "minimum": 1, "maximum": 500, "default": 100}),
            ],
            "description": "Read runtime application logs using bounded cursor/time/text filters.",
        },
        ("/agent/v1/services/{service_id}/logs/export", "GET"): {
            "schema": "FileDownload", "status": 200, "tags": ["Service Logs"],
            "queries": [
                _parameter("from", "query", {"type": "string", "format": "date-time"}),
                _parameter("to", "query", {"type": "string", "format": "date-time"}),
                _parameter("level", "query", {"type": "string"}),
                _parameter("stream", "query", {"type": "string"}),
                _parameter("q", "query", {"type": "string"}),
                _parameter("format", "query", {"type": "string", "enum": ["txt", "jsonl"], "default": "txt"}),
                _parameter("limit", "query", {"type": "integer", "minimum": 1, "maximum": 10000, "default": 5000}),
            ],
            "description": "Export a bounded runtime-log representation as text or JSON Lines.",
        },
        ("/agent/v1/services/{service_id}/configuration", "GET"): {"schema": "ServiceConfiguration", "status": 200, "tags": ["Service Configuration"], "description": "Read declarative service source/build/runtime configuration with secrets redacted."},
        ("/agent/v1/services/{service_id}/configuration", "PATCH"): {
            "schema": "ConfigurationMutationResponse", "status": 200, "tags": ["Service Configuration"],
            "body": _json_body({"$ref": "#/components/schemas/ConfigurationPatchRequest"}),
            "description": "Update declarative source/build/runtime configuration. Secret-like values are rejected and must use secrets or secret-backed environment values.",
        },
        ("/agent/v1/services/{service_id}/environment", "GET"): {"schema": "EnvironmentResponse", "status": 200, "tags": ["Service Configuration"], "description": "Read enabled environment variables; secret-backed values are masked."},
        ("/agent/v1/services/{service_id}/environment", "POST"): {
            "schema": "EnvironmentEntry", "status": 200, "tags": ["Service Configuration"],
            "body": _json_body({"$ref": "#/components/schemas/EnvironmentMutationRequest"}),
            "description": "Create or update one environment variable.",
        },
        ("/agent/v1/services/{service_id}/environment", "DELETE"): {
            "schema": "Empty", "status": 204, "tags": ["Service Configuration"],
            "queries": [_parameter("key", "query", {"type": "string"}, required=True)],
            "description": "Delete one environment variable by key.",
        },
        ("/agent/v1/services/{service_id}/secrets", "GET"): {"schema": "SecretsResponse", "status": 200, "tags": ["Service Configuration"], "description": "Read secret metadata only. Plaintext values are not returned."},
        ("/agent/v1/services/{service_id}/secrets", "POST"): {
            "schema": "SecretMetadata", "status": 200, "tags": ["Service Configuration"],
            "body": _json_body({"$ref": "#/components/schemas/SecretMutationRequest"}),
            "description": "Create or rotate a service secret. The secret value is write-only.",
            "sensitive_request": True,
        },
        ("/agent/v1/services/{service_id}/secrets", "DELETE"): {
            "schema": "ObjectResult", "status": 200, "tags": ["Service Configuration"],
            "queries": [_parameter("key", "query", {"type": "string"}, required=True)],
            "description": "Disable a service secret by key.",
        },
        ("/agent/v1/services/{service_id}/endpoints", "GET"): {"schema": "EndpointListResponse", "status": 200, "tags": ["Service Configuration"], "description": "List Service endpoints."},
        ("/agent/v1/services/{service_id}/endpoints", "POST"): {
            "schema": "Endpoint", "status": 200, "tags": ["Service Configuration"],
            "body": _json_body({"$ref": "#/components/schemas/EndpointMutationRequest"}),
            "description": "Create or update an endpoint. Target and published ports must be 1..65535.",
        },
        ("/agent/v1/services/{service_id}/endpoints", "DELETE"): {
            "schema": "Empty", "status": 204, "tags": ["Service Configuration"],
            "queries": [_parameter("name", "query", {"type": "string"}, required=True)],
            "description": "Delete an endpoint by name.",
        },
        ("/agent/v1/services/{service_id}/networks", "GET"): {"schema": "NetworkAttachmentListResponse", "status": 200, "tags": ["Service Configuration"], "description": "List explicit Service network attachments."},
        ("/agent/v1/services/{service_id}/networks", "POST"): {
            "schema": "NetworkAttachment", "status": 200, "tags": ["Service Configuration"],
            "body": _json_body({"$ref": "#/components/schemas/NetworkAttachmentRequest"}),
            "description": "Attach an owned Private Network to a Service.",
        },
        ("/agent/v1/services/{service_id}/networks", "DELETE"): {
            "schema": "Empty", "status": 204, "tags": ["Service Configuration"],
            "queries": [_parameter("network", "query", {"type": "string", "format": "uuid"}, required=True)],
            "description": "Detach a Service network attachment by network ID.",
        },
        ("/agent/v1/services/{service_id}/databases", "GET"): {"schema": "DatabaseBindingListResponse", "status": 200, "tags": ["Database"], "description": "List managed database bindings attached to the Service."},
        ("/agent/v1/services/{service_id}/databases", "POST"): {
            "schema": "DatabaseBinding", "status": 200, "tags": ["Database"],
            "body": _json_body({"$ref": "#/components/schemas/DatabaseBindingRequest"}),
            "description": "Attach or update a managed DatabaseResource binding.",
        },
        ("/agent/v1/services/{service_id}/databases", "DELETE"): {
            "schema": "Empty", "status": 204, "tags": ["Database"],
            "queries": [_parameter("alias", "query", {"type": "string", "default": "default"}, required=True)],
            "description": "Delete a database binding by alias.",
        },
        ("/agent/v1/services/{service_id}/database-credentials", "GET"): {
            "schema": "DatabaseCredentialResponse", "status": 200, "tags": ["Database"],
            "queries": [_parameter("reveal", "query", {"type": "boolean", "default": False}, description="Set true to reveal decrypted password/root_password. Requires the dedicated high-risk scope and existing can_view_db_credentials authorization.")],
            "description": "Read database connection metadata. reveal=true may return plaintext credentials; treat the response as secret material and never log or display it.",
            "sensitive": True,
        },
        ("/agent/v1/services/{service_id}/revisions", "GET"): {"schema": "RevisionListResponse", "status": 200, "tags": ["Revisions"], "description": "List immutable Service revisions."},
        ("/agent/v1/services/{service_id}/revisions/{revision_id}", "GET"): {"schema": "Revision", "status": 200, "tags": ["Revisions"], "description": "Inspect one immutable Service revision."},
        ("/agent/v1/services/{service_id}/revisions/{revision_id}/rollback", "POST"): {"schema": "ObjectResult", "status": 200, "tags": ["Revisions"], "description": "Activate the selected immutable revision through the existing rollback boundary.", "async": True},
        ("/agent/v1/services/{service_id}/shell", "GET"): {"schema": "ShellInfo", "status": 200, "tags": ["Service Shell"], "description": "Read shell availability, command catalog and protocol policy for the Service."},
        ("/agent/v1/services/{service_id}/shell/sessions", "POST"): {
            "schema": "ShellSessionResponse", "status": 201, "tags": ["Service Shell"],
            "body": _json_body({"$ref": "#/components/schemas/ShellSessionCreateRequest"}),
            "description": "Create a restricted service-runtime shell session. This is not host shell access.",
            "sensitive": True,
        },
        ("/agent/v1/services/{service_id}/shell/sessions/{session_id}/commands", "POST"): {
            "schema": "ShellCommandResult", "status": 200, "tags": ["Service Shell"],
            "body": _json_body({"$ref": "#/components/schemas/ShellCommandRequest"}),
            "description": "Execute a command through the existing restricted shell validator. Interactive commands require the PTY transport. Destructive commands require confirmation.",
            "sensitive_request": True,
        },
        ("/agent/v1/services/{service_id}/shell/sessions/{session_id}/close", "POST"): {
            "schema": "ObjectResult", "status": 200, "tags": ["Service Shell"],
            "description": "Close the authenticated restricted shell session.",
            "sensitive_request": True,
        },
        ("/agent/v1/services/{service_id}/shell/replace", "POST"): {
            "schema": "ShellSessionResponse", "status": 201, "tags": ["Service Shell"],
            "body": _json_body(
                {"type": "object", "properties": {"confirm": {"type": "boolean", "enum": [True]}, "workdir": {"type": "string"}}},
                example={"confirm": True},
            ),
            "description": "Replace the active restricted shell session. Explicit confirm=true is required.",
            "confirmation": True,
            "sensitive": True,
        },
        ("/agent/v1/services/{service_id}/shell/files", "POST"): {
            "schema": "ShellFileResponse", "status": 200, "tags": ["Service Shell"],
            "body": _json_body({"$ref": "#/components/schemas/ShellFileRequest"}),
            "description": "Read or mutate files inside the restricted service workspace. Upload uses multipart/form-data with file.",
            "sensitive_request": True,
        },
        ("/agent/v1/plans", "GET"): {
            "schema": "PlanListResponse", "status": 200, "tags": ["Plans"],
            "queries": [
                _parameter("q", "query", {"type": "string"}),
                _parameter("q_search", "query", {"type": "string"}),
                _parameter("platform", "query", {"type": "string"}),
                _parameter("plan_type", "query", {"type": "string"}),
                _parameter("page", "query", {"type": "integer", "minimum": 1}),
                _parameter("page_size", "query", {"type": "integer", "minimum": 1, "maximum": 100}),
            ],
            "description": "List Plans using the existing Plan administration filters.",
        },
        ("/agent/v1/plans/{plan_id}", "GET"): {"schema": "Plan", "status": 200, "tags": ["Plans"], "description": "Inspect a Plan."},
        ("/agent/v1/plans/{plan_id}/apply", "POST"): {
            "schema": "Service", "status": 201, "tags": ["Plans"],
            "body": _json_body({"$ref": "#/components/schemas/PlanApplyRequest"}),
            "description": "Create a Service from the Plan identified by the URL. A body plan, when supplied, must match the URL plan_id.",
        },
        ("/agent/v1/plans/manage", "POST"): {
            "schema": "Plan", "status": 201, "tags": ["Plans"],
            "body": _json_body({"$ref": "#/components/schemas/PlanCreateRequest"}),
            "description": "Create a Plan. Requires existing staff/superuser authorization and the plans.manage rule.",
        },
        ("/agent/v1/plans/manage/{plan_id}", "PATCH"): {
            "schema": "Plan", "status": 200, "tags": ["Plans"],
            "body": _json_body({"$ref": "#/components/schemas/PlanUpdateRequest"}),
            "description": "Update a Plan. Requires existing staff/superuser authorization and the plans.manage rule.",
        },
        ("/agent/v1/plans/manage/{plan_id}", "DELETE"): {"schema": "ObjectResult", "status": 200, "tags": ["Plans"], "description": "Delete a Plan through the existing management boundary."},
        ("/agent/v1/networks", "GET"): {"schema": "NetworkListResponse", "status": 200, "tags": ["Networks"], "description": "List owned Private Networks."},
        ("/agent/v1/networks", "POST"): {
            "schema": "Network", "status": 201, "tags": ["Networks"],
            "body": _json_body({"$ref": "#/components/schemas/NetworkCreateRequest"}),
            "description": "Create an owned Private Network.",
        },
        ("/agent/v1/networks/{network_id}", "GET"): {"schema": "Network", "status": 200, "tags": ["Networks"], "description": "Inspect a Private Network."},
        ("/agent/v1/networks/{network_id}", "PATCH"): {
            "schema": "Network", "status": 200, "tags": ["Networks"],
            "body": _json_body({"$ref": "#/components/schemas/NetworkUpdateRequest"}),
            "description": "Update an owned Private Network.",
        },
        ("/agent/v1/networks/{network_id}", "DELETE"): {"schema": "ObjectResult", "status": 200, "tags": ["Networks"], "description": "Delete a Private Network when existing service-attachment protections permit it."},
        ("/agent/v1/volumes", "GET"): {
            "schema": "VolumeListResponse", "status": 200, "tags": ["Volumes"],
            "queries": [
                _parameter("service", "query", {"type": "string", "format": "uuid"}),
                _parameter("unused", "query", {"type": "boolean"}),
                _parameter("page", "query", {"type": "integer", "minimum": 1}),
                _parameter("page_size", "query", {"type": "integer", "minimum": 1, "maximum": 100}),
            ],
            "description": "List accessible Volumes. Volumes remain quota-owned while soft-detached.",
        },
        ("/agent/v1/volumes", "POST"): {
            "schema": "Volume", "status": 201, "tags": ["Volumes"],
            "body": _json_body({"$ref": "#/components/schemas/VolumeCreateRequest"}),
            "description": "Create a Volume subject to Service mutability, attachment and storage-quota checks.",
        },
        ("/agent/v1/volumes/{volume_id}", "GET"): {"schema": "Volume", "status": 200, "tags": ["Volumes"], "description": "Inspect a Volume."},
        ("/agent/v1/volumes/{volume_id}", "PATCH"): {
            "schema": "Volume", "status": 200, "tags": ["Volumes"],
            "body": _json_body({"$ref": "#/components/schemas/VolumeUpdateRequest"}),
            "description": "Update a Volume subject to runtime, provisioning, attachment and quota protections.",
        },
        ("/agent/v1/volumes/{volume_id}", "DELETE"): {"schema": "ObjectResult", "status": 200, "tags": ["Volumes"], "description": "Delete a Volume subject to existing mount/runtime protections."},
        ("/agent/v1/deployments/help", "GET"): {"schema": "DeploymentHelp", "status": 200, "tags": ["Deployments"], "description": "Read dynamic platform schemas, deployment inputs, tenant-configurable keys and lifecycle rules. Use this before constructing complex deployment config."},
        ("/agent/v1/deployments/inspect", "POST"): {
            "schema": "DeploymentInspectResponse", "status": 200, "tags": ["Deployments"],
            "multipart": True,
            "description": "Inspect a ZIP archive before deployment. multipart/form-data field file is required.",
        },
        ("/agent/v1/deployments", "GET"): {
            "schema": "DeploymentListResponse", "status": 200, "tags": ["Deployments"],
            "queries": [
                _parameter("service_id", "query", {"type": "string", "format": "uuid"}),
                _parameter("status", "query", {"type": "string"}),
                _parameter("stage", "query", {"type": "string"}),
                _parameter("q", "query", {"type": "string"}),
                _parameter("created_by", "query", {"type": "string"}),
                _parameter("from", "query", {"type": "string", "format": "date-time"}),
                _parameter("to", "query", {"type": "string", "format": "date-time"}),
                _parameter("ordering", "query", {"type": "string", "default": "-created_at"}),
                _parameter("page", "query", {"type": "integer", "minimum": 1}),
                _parameter("page_size", "query", {"type": "integer", "minimum": 1, "maximum": 100}),
            ],
            "description": "List accessible Deployments with lifecycle/search/time filters.",
        },
        ("/agent/v1/deployments", "POST"): {
            "schema": "Deployment", "status": 201, "tags": ["Deployments"],
            "body": _json_body({"$ref": "#/components/schemas/DeploymentCreateRequest"}),
            "description": "Create deployment metadata. Use /deployments/help first for platform configuration and create the ZIP upload separately when needed.",
        },
        ("/agent/v1/deployments/{deployment_id}", "GET"): {"schema": "Deployment", "status": 200, "tags": ["Deployments"], "description": "Inspect a Deployment."},
        ("/agent/v1/deployments/{deployment_id}", "DELETE"): {"schema": "ObjectResult", "status": 200, "tags": ["Deployments"], "description": "Delete a Deployment through the existing deployment ownership boundary."},
        ("/agent/v1/deployments/{deployment_id}/upload", "POST"): {
            "schema": "Deployment", "status": 200, "tags": ["Deployments"],
            "multipart": True,
            "description": "Upload a valid ZIP source archive using multipart/form-data field file. The backend enforces its configured ZIP size limit.",
        },
        ("/agent/v1/deployments/{deployment_id}/start", "POST"): {"schema": "Deployment", "status": 200, "tags": ["Deployments"], "description": "Queue execution of the selected deployment.", "async": True},
        ("/agent/v1/deployments/{deployment_id}/cancel", "POST"): {"schema": "Deployment", "status": 200, "tags": ["Deployments"], "description": "Request cancellation through the deployment state machine.", "async": True},
        ("/agent/v1/deployments/{deployment_id}/redeploy", "POST"): {"schema": "Deployment", "status": 200, "tags": ["Deployments"], "description": "Repeat deployment execution for the selected deployment.", "async": True},
        ("/agent/v1/deployments/{deployment_id}/rebuild", "POST"): {"schema": "Deployment", "status": 200, "tags": ["Deployments"], "description": "Rebuild the existing deployment/runtime path.", "async": True},
        ("/agent/v1/deployments/{deployment_id}/rollback", "POST"): {"schema": "Deployment", "status": 200, "tags": ["Deployments"], "description": "Rollback through the existing immutable-revision boundary.", "async": True},
        ("/agent/v1/deployments/{deployment_id}/logs", "GET"): {
            "schema": "DeploymentLogsResponse", "status": 200, "tags": ["Deployment Logs"],
            "queries": [
                _parameter("before", "query", {"type": "string", "format": "date-time"}),
                _parameter("after", "query", {"type": "string", "format": "date-time"}),
                _parameter("q", "query", {"type": "string"}),
                _parameter("level", "query", {"type": "string"}),
                _parameter("stage", "query", {"type": "string"}),
                _parameter("event_type", "query", {"type": "string"}),
                _parameter("from", "query", {"type": "string", "format": "date-time"}),
                _parameter("to", "query", {"type": "string", "format": "date-time"}),
                _parameter("limit", "query", {"type": "integer", "minimum": 1, "maximum": 200, "default": 10}),
            ],
            "description": "Read deployment lifecycle/build logs with bounded cursor/time/filter controls.",
        },
        ("/agent/v1/deployments/{deployment_id}/logs/export", "GET"): {
            "schema": "FileDownload", "status": 200, "tags": ["Deployment Logs"],
            "queries": [
                _parameter("q", "query", {"type": "string"}),
                _parameter("level", "query", {"type": "string"}),
                _parameter("stage", "query", {"type": "string"}),
                _parameter("event_type", "query", {"type": "string"}),
                _parameter("from", "query", {"type": "string", "format": "date-time"}),
                _parameter("to", "query", {"type": "string", "format": "date-time"}),
                _parameter("format", "query", {"type": "string", "enum": ["txt", "jsonl"], "default": "txt"}),
                _parameter("limit", "query", {"type": "integer", "minimum": 1, "maximum": 5000, "default": 5000}),
            ],
            "description": "Export a bounded deployment lifecycle log file.",
        },
    }

    for (key, spec) in operation_specs.items():
        path_key, method_key = key
        operation = paths.get(path_key, {}).get(method_key.lower())
        if operation is None:
            continue
        if spec.get("body"):
            operation["requestBody"] = spec["body"]
        if spec.get("multipart"):
            file_schema = {
                "type": "object",
                "required": ["file"],
                "properties": {
                    "file": {"type": "string", "format": "binary"},
                },
            }
            operation["requestBody"] = {
                "required": True,
                "content": {
                    "multipart/form-data": {"schema": file_schema},
                },
                "description": spec.get("description"),
            }
        if spec.get("queries"):
            _merge_query_parameters(operation, spec["queries"])
        if spec.get("schema") == "FileDownload":
            operation.setdefault("responses", {})[str(spec["status"])] = {
                "description": spec.get("description", "File download"),
                "content": {
                    "text/plain": {"schema": {"type": "string"}},
                    "application/x-ndjson": {"schema": {"type": "string"}},
                },
            }
        elif spec.get("schema") == "Markdown":
            operation.setdefault("responses", {})[str(spec["status"])] = {
                "description": spec.get("description", "Markdown document"),
                "content": {"text/markdown": {"schema": {"type": "string"}}},
            }
        elif spec.get("status") == 204:
            operation.setdefault("responses", {})["204"] = {
                "description": spec.get("description", "No content"),
            }
        else:
            _add_operation_metadata(
                operation,
                next((c for c in CONTRACTS if c.path == path_key and c.method == method_key), None),
                agent,
                response={"schema": spec["schema"], "description": spec.get("description", "Successful operation")},
                response_status=spec["status"],
                sensitive=spec.get("sensitive", False),
                confirmation=spec.get("confirmation", False),
                tags=spec.get("tags"),
                description=spec.get("description"),
            )
        if spec.get("async"):
            operation["x-async"] = True
            operation["x-follow-up"] = "Poll the deployment or service status/log endpoints until the requested state is observed."
        if spec.get("sensitive_request"):
            operation["x-sensitive-request"] = True

    # The shell file endpoint supports both JSON text/file-manager operations
    # and multipart upload operations.
    shell_files = paths["/agent/v1/services/{service_id}/shell/files"]["post"]
    shell_files["requestBody"] = {
        "required": True,
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/ShellFileRequest"},
                "example": {"action": "read", "path": "app/settings.py"},
            },
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["action", "path", "file"],
                    "properties": {
                        "action": {"type": "string", "enum": ["upload"]},
                        "path": {"type": "string"},
                        "token": {"type": "string", "writeOnly": True},
                        "file": {"type": "string", "format": "binary"},
                    },
                },
            },
        },
        "description": "Use JSON for read/write/create/delete/rename operations. Use multipart/form-data with file for upload.",
    }

    # Request header alternatives for shell-session authentication.
    shell_token = _parameter(
        "X-Shell-Token",
        "header",
        {"type": "string"},
        description="Temporary restricted shell-session credential.",
    )
    for p in (
        "/agent/v1/services/{service_id}/shell/sessions/{session_id}/commands",
        "/agent/v1/services/{service_id}/shell/sessions/{session_id}/close",
        "/agent/v1/services/{service_id}/shell/files",
    ):
        op = paths[p]["post"]
        _merge_query_parameters(op, [shell_token])

    # Ensure every registered contract gets operation metadata, path parameters,
    # security, success/error responses, and an operationId even when it has no
    # hand-authored request specification yet.
    for contract in CONTRACTS:
        operation = paths.get(contract.path, {}).get(contract.method.lower())
        if operation is None:
            continue
        _add_operation_metadata(
            operation,
            contract,
            agent,
            response=None,
            tags=operation.get("tags"),
            description=operation.get("description") or (
                f"PassDeployer Agent operation for {contract.method} {contract.path}. "
                "Use /capabilities and this OpenAPI document for the exact enabled contract."
            ),
        )

    # Rich response schemas used by the operation specifications.
    schemas.update({
        "ServiceListResponse": {
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "next": {"type": "string", "format": "uri", "nullable": True},
                "previous": {"type": "string", "format": "uri", "nullable": True},
                "results": {"type": "array", "items": {"$ref": "#/components/schemas/Service"}},
            },
        },
        "PlanListResponse": {
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "next": {"type": "string", "format": "uri", "nullable": True},
                "previous": {"type": "string", "format": "uri", "nullable": True},
                "results": {"type": "array", "items": {"$ref": "#/components/schemas/Plan"}},
            },
        },
        "NetworkListResponse": {
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "next": {"type": "string", "format": "uri", "nullable": True},
                "previous": {"type": "string", "format": "uri", "nullable": True},
                "results": {"type": "array", "items": {"$ref": "#/components/schemas/Network"}},
            },
        },
        "VolumeListResponse": {
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "next": {"type": "string", "format": "uri", "nullable": True},
                "previous": {"type": "string", "format": "uri", "nullable": True},
                "results": {"type": "array", "items": {"$ref": "#/components/schemas/Volume"}},
            },
        },
        "DeploymentListResponse": {
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "next": {"type": "string", "format": "uri", "nullable": True},
                "previous": {"type": "string", "format": "uri", "nullable": True},
                "results": {"type": "array", "items": {"$ref": "#/components/schemas/Deployment"}},
            },
        },
        "AgentCapabilities": {"type": "object", "additionalProperties": True},
        "OpenAPI": {"type": "object", "additionalProperties": True},
        "Markdown": {"type": "string"},
        "Empty": {"type": "object", "description": "No response body.", "nullable": True},
        "ObjectResult": {"type": "object", "additionalProperties": True},
        "Network": _serializer_schema(PrivateNetworkSerializer),
        "Volume": _serializer_schema(VolumeSerializer),
        "Plan": _serializer_schema(PlanSerializer),
        "DeploymentHelp": {"type": "object", "additionalProperties": True},
        "DeploymentInspectResponse": {"type": "object", "additionalProperties": True},
        "ServiceConfiguration": {"type": "object", "additionalProperties": True},
        "ConfigurationMutationResponse": {"type": "object", "additionalProperties": True},
        "EnvironmentResponse": {"type": "object", "properties": {"results": {"type": "array", "items": {"$ref": "#/components/schemas/EnvironmentEntry"}}}},
        "SecretsResponse": {"type": "object", "properties": {"results": {"type": "array", "items": {"$ref": "#/components/schemas/SecretMetadata"}}}},
        "EndpointListResponse": {"type": "object", "properties": {"results": {"type": "array", "items": {"$ref": "#/components/schemas/Endpoint"}}}},
        "NetworkAttachmentListResponse": {"type": "object", "properties": {"results": {"type": "array", "items": {"$ref": "#/components/schemas/NetworkAttachment"}}}},
        "DatabaseBindingListResponse": {"type": "object", "properties": {"results": {"type": "array", "items": {"$ref": "#/components/schemas/DatabaseBinding"}}}},
        "RevisionListResponse": {"type": "object", "properties": {"results": {"type": "array", "items": {"$ref": "#/components/schemas/Revision"}}}},
        "RuntimeLogsResponse": {"type": "object", "properties": {"result": {"type": "string"}, "source": {"type": "string", "enum": ["runtime"]}, "service_id": {"type": "string", "format": "uuid"}, "events": {"type": "array", "items": {"$ref": "#/components/schemas/RuntimeLogEvent"}}, "next_cursor": {"type": "string", "nullable": True}, "prev_cursor": {"type": "string", "nullable": True}, "has_more_older": {"type": "boolean"}, "has_more_newer": {"type": "boolean"}, "count": {"type": "integer"}}},
        "DeploymentLogsResponse": {"type": "object", "properties": {"result": {"type": "string"}, "source": {"type": "string", "enum": ["deployment"]}, "deploy": {"$ref": "#/components/schemas/Deployment"}, "logs": {"type": "array", "items": {"$ref": "#/components/schemas/DeploymentLogEvent"}}, "next_before": {"type": "string", "nullable": True}, "next_after": {"type": "string", "nullable": True}, "latest_after": {"type": "string", "nullable": True}, "has_more_older": {"type": "boolean"}, "has_more_newer": {"type": "boolean"}, "direction": {"type": "string", "enum": ["backward", "forward"]}, "log_store_available": {"type": "boolean", "nullable": True}}},
        "FileDownload": {"type": "string", "format": "binary"},
        "ShellInfo": {"type": "object", "additionalProperties": True},
        "Skill": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "title": {"type": "string"},
                "summary": {"type": "string"},
                "url": {"type": "string", "format": "uri"},
                "required_scopes": {"type": "array", "items": {"type": "string"}},
                "required_any_scopes": {"type": "array", "items": {"type": "string"}}
            }
        },
        "SkillIndex": {
            "type": "object",
            "properties": {
                "result": {"type": "string", "enum": ["success"]},
                "api_version": {"type": "string"},
                "skills": {"type": "array", "items": {"$ref": "#/components/schemas/Skill"}}
            }
        },
    })


    result = {
        "openapi": "3.0.3",
        "info": {
            "title": "PassDeployer Agent API",
            "version": "v1",
            "description": "Scoped control-plane facade over existing PassDeployer application and runtime boundaries.",
        },
        "servers": [{"url": origin or "/"}],
        "security": [{"AgentBearer": []}],
        "components": {
            "securitySchemes": {
                "AgentBearer": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "PassDeployer Agent access token",
                }
            },
            "parameters": {"IdempotencyKey": idempotency},
            "schemas": {
                "Error": {
                    "type": "object",
                    "required": ["result", "code", "detail", "request_id", "retryable", "failure_domain", "resource_effect", "certainty"],
                    "properties": {
                        "result": {"type": "string", "enum": ["error"]},
                        "code": {"type": "string"},
                        "detail": {"type": "string"},
                        "request_id": {"type": "string", "format": "uuid", "nullable": True},
                        "retryable": {"type": "boolean"},
                        "failure_domain": {"type": "string"},
                        "visibility": {"type": "string"},
                        "resource_effect": {"type": "string"},
                        "certainty": {"type": "string"},
                    },
                },
                "Service": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "format": "uuid"},
                        "name": {"type": "string"},
                        "platform": {"type": "string"},
                        "status": {"type": "string"},
                        "desired_state": {"type": "string"},
                        "active_revision": {"type": "object", "nullable": True},
                        "deployment": {"type": "object", "nullable": True},
                    },
                },
                "Deployment": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "format": "uuid"},
                        "release_id": {"type": "string", "format": "uuid"},
                        "service_id": {"type": "string", "format": "uuid"},
                        "revision_id": {"type": "string", "format": "uuid", "nullable": True},
                        "status": {"type": "string"},
                        "stage": {"type": "string"},
                        "progress": {"type": "integer"},
                    },
                },
                "DeploymentLogEvent": {
                    "type": "object",
                    "properties": {
                        "timestamp": {"type": "string", "format": "date-time"},
                        "source": {"type": "string", "enum": ["deployment"]},
                        "level": {"type": "string", "nullable": True},
                        "stage": {"type": "string", "nullable": True},
                        "event_type": {"type": "string", "nullable": True},
                        "message": {"type": "string"},
                        "deployment_id": {"type": "string", "format": "uuid"},
                        "service_id": {"type": "string", "format": "uuid"},
                    },
                },
                "RuntimeLogEvent": {
                    "type": "object",
                    "properties": {
                        "timestamp": {"type": "string", "format": "date-time"},
                        "source": {"type": "string", "enum": ["runtime"]},
                        "stream": {"type": "string"},
                        "level": {"type": "string", "nullable": True},
                        "message": {"type": "string"},
                        "service_id": {"type": "string", "format": "uuid"},
                        "deployment_id": {"type": "string", "nullable": True},
                        "cursor": {"type": "string", "nullable": True},
                    },
                },
                "ServiceMetrics": {
                    "type": "object",
                    "properties": {
                        "result": {"type": "string"},
                        "service_id": {"type": "string", "format": "uuid"},
                        "observed_at": {"type": "string", "format": "date-time"},
                        "runtime": {
                            "type": "object",
                            "properties": {
                                "backend": {"type": "string"},
                                "running": {"type": "boolean"},
                                "metrics_available": {"type": "boolean", "nullable": True},
                                "metrics_reason": {"type": "string", "nullable": True}
                            }
                        },
                        "usage": {
                            "type": "object",
                            "properties": {
                                "cpu_percent": {"type": "number", "nullable": True},
                                "cpu_cores": {"type": "number", "nullable": True},
                                "memory_percent": {"type": "number", "nullable": True},
                                "memory_usage_bytes": {"type": "number", "nullable": True}
                            }
                        },
                        "limits": {
                            "type": "object",
                            "properties": {
                                "cpu_vcpu": {"type": "number", "nullable": True},
                                "memory_mb": {"type": "integer", "nullable": True},
                                "memory_limit_bytes": {"type": "number", "nullable": True},
                                "cpu_limit_cores": {"type": "number", "nullable": True}
                            }
                        }
                    }
                },
                "ShellCommandResult": {
                    "type": "object",
                    "properties": {
                        "result": {"type": "string"},
                        "command": {"type": "string"},
                        "exit_code": {"type": "integer"},
                        "stdout": {"type": "string"},
                        "stderr": {"type": "string"},
                        "duration_ms": {"type": "integer", "nullable": True},
                        "cwd": {"type": "string"},
                        "session_id": {"type": "string", "format": "uuid", "nullable": True},
                        "dry_run": {"type": "boolean", "nullable": True},
                        "risk": {"type": "string", "nullable": True},
                        "requires_confirmation": {"type": "boolean", "nullable": True},
                        "plan": {
                            "type": "array",
                            "nullable": True,
                            "items": {
                                "type": "object",
                                "additionalProperties": True,
                            },
                        },
                    },
                },
            },
            "responses": {
                "Error": {
                    "description": "Structured Agent API error",
                    "content": {"application/json": {"schema": error_ref}},
                }
            },
        },
        "paths": paths,
        "x-agent": {
            "agent_id": str(agent.pk),
            "enabled_scopes": sorted(agent.scopes or []),
            "deployment_inputs": {
                "archive_zip": True,
                "database_native": True,
                "git": False,
                "existing_image": False,
            },
            "log_sources_are_separate": True,
            "rate_limits": dict(AgentRateThrottle.rate_map),
            "manifest_scope": "agent.manifest.generate",
            "skills_endpoint": "/agent/v1/skills",
            "skills_scope_filtered": True,
            "high_risk_scopes": sorted(HIGH_RISK_SCOPES),
        },
    }
    result["components"]["schemas"].update(schemas)
    result["components"]["schemas"]["AgentCapabilities"] = schemas["AgentCapabilities"]
    result["components"]["schemas"]["OpenAPI"] = schemas["OpenAPI"]

    # Contract metadata is projected directly from the centralized registry.
    # This prevents runtime authorization, OpenAPI, and AGENT.md from drifting.
    for contract in CONTRACTS:
        operation = paths.get(contract.path, {}).get(contract.method.lower())
        if operation is None:
            continue
        if contract.scopes:
            operation["x-required-scopes"] = list(contract.scopes)
        if contract.any_scopes:
            operation["x-required-any-scopes"] = list(contract.any_scopes)
        if contract.idempotent:
            parameters = operation.setdefault("parameters", [])
            if not any(
                item.get("name") == "Idempotency-Key"
                for item in parameters
                if isinstance(item, dict)
            ):
                parameters.append({"$ref": "#/components/parameters/IdempotencyKey"})
        operation["x-mutating"] = contract.mutating
        operation["x-idempotent"] = contract.idempotent
        operation["x-throttle-scope"] = contract.throttle_scope
        operation["x-enabled-for-agent"] = all(
            scope in set(agent.scopes or []) for scope in contract.scopes
        ) and (
            not contract.any_scopes
            or bool(set(contract.any_scopes) & set(agent.scopes or []))
        )

    result["x-agent"]["contract_operations"] = len(CONTRACTS)
    result["x-agent"]["enabled_operations"] = len(contracts_for_agent(agent))
    result["x-agent"]["contract_source"] = "agent.contracts"

    return result
