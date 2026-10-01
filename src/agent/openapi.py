from __future__ import annotations

from .manifest import api_base_url
from .contracts import CONTRACTS, contracts_for_agent


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
                "summary": "Read observed runtime CPU/RAM usage and plan limits"
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
                "ShellCommandResult": {
                    "type": "object",
                    "properties": {
                        "result": {"type": "string"},
                        "command": {"type": "string"},
                        "exit_code": {"type": "integer"},
                        "stdout": {"type": "string"},
                        "stderr": {"type": "string"},
                        "duration_ms": {"type": "integer"},
                        "cwd": {"type": "string"},
                        "session_id": {"type": "string", "format": "uuid"},
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
            "rate_limits": {"read":"120/min","mutation":"30/min","deployment":"10/min","upload":"5/min","shell":"10/min","exchange":"10/min"},
            "manifest_scope": "agent.manifest.generate",
        },
    }
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
