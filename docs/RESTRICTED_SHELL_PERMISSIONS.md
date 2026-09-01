# Restricted Shell Permissions

## Permission key

`can_shell` controls access to the per-service restricted shell. It is deny-by-default for shares. Service owners bypass share rules.

## Service Detail

The service access endpoint returns `permissions.can_shell` and a `menu.shell` descriptor. The frontend should hide/disable the Shell menu when `can_shell` is false. This is UI guidance only; every shell endpoint enforces the permission again.

## API enforcement

The following endpoints all require authentication and `can_shell` (owner passes automatically):

- `GET /services/<service_id>/shell/`
- `POST /services/<service_id>/shell/session/`
- `POST /services/<service_id>/shell/command/`
- `POST /services/<service_id>/shell/file/`
- `POST /services/<service_id>/shell/close/`

A shared user cannot obtain a shell token without `can_shell`, and an existing token cannot be used after share permission is revoked because command/session endpoints re-check service authorization on every request.

## Presets

- `viewer`: shell disabled
- `operator`: shell disabled
- `developer`: shell enabled
- `ops`: shell enabled

Group `admin_only` remains enforced by the existing share authorization layer. A non-admin group member does not gain shell access merely because the parent share has `can_shell=true`.

## Security expectations

`can_shell` is an elevated share permission. The UI must not equate service visibility with shell visibility. The backend checks ownership/share state on every shell request.

The shell remains argv-based and does not expose `/bin/sh`, `sh -c`, pipelines, redirects, command substitution, or Docker/socket/host-management commands. Existing path and network guards continue to apply.

For the Service Detail menu, use `GET /services/<service_id>/access/` (or `GET /services/<service_id>/shell/`) and render the Shell menu only when the returned `menu.shell.visible` and `permissions.can_shell` are both true. A hidden menu is not an authorization mechanism.
