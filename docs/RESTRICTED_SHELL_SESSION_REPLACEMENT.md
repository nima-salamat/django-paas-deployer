# Restricted Shell session replacement API

A service has at most one active restricted-shell session. Creating another session returns HTTP 409 instead of silently terminating the existing user.

## Create session

`POST /services/<service_id>/shell/session/`

Success: `201`

```json
{
  "result": "success",
  "session_id": "<uuid>",
  "token": "<opaque-token>",
  "platform": "laravel",
  "cwd": "/var/www/html",
  "expires_at": "..."
}
```

When another session is active, response `409`:

```json
{
  "result": "error",
  "code": "SHELL_SESSION_ACTIVE",
  "detail": "This service already has an active shell session.",
  "can_replace": true,
  "active_session": {
    "session_id": "<uuid>",
    "user_id": "<uuid>",
    "username": "alice",
    "expires_at": "..."
  }
}
```

`can_replace` is true for the service owner and for a shared user with the explicit `can_shell_replace` permission. `can_shell` alone does not grant the ability to terminate someone else's session.

## Replace active session

`POST /services/<service_id>/shell/session/replace/`

Body:

```json
{
  "confirm": true
}
```

The endpoint revokes the active session and creates a new session for the caller. It does **not** stop, restart, or kill the service container.

Success: `201` with the normal session payload plus `replaced` and `previous_session_id`.

## Authorization

Every shell endpoint re-checks service access server-side. The frontend visibility of the Shell tab is not an authorization boundary.
