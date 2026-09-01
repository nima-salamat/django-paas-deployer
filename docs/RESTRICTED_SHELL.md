# Restricted Service Shell API

The deployer exposes a restricted, non-interactive command API for a running service container. It is **not** a general Docker shell.

## Lifecycle

1. `POST /services/<service_id>/shell/session/` creates one active session for the service.
2. The response contains a short-lived bearer token. Send it as `X-Shell-Token` (or in `token`) to command/close endpoints.
3. `POST /services/<service_id>/shell/command/` executes exactly one allow-listed argv command with no shell parsing, pipes, redirects, `&&`, command substitution, or arbitrary shell binaries.
4. `POST /services/<service_id>/shell/close/` closes it.

Only the service owner can use this interface; shared service access is intentionally excluded because shell access is more privileged than logs or deploy selection.

## Session rules

- One active session per service.
- Session expires after 30 minutes of inactivity and renews on command execution.
- Working directory is constrained to the platform work-root.
- Commands execute in the service's **existing running container**.
- No TTY is exposed. This prevents escape through terminal control sequences and interactive programs. Commands are executed as argv directly, never through `/bin/sh -c`.
- File changes affect the running container/filesystem only. They are not guaranteed to survive a rebuild or replacement unless stored on a mounted persistent volume.

## Common commands

Read/write filesystem: `pwd`, `ls`, `cat`, `head`, `tail`, `mkdir`, `touch`, `rm`, `cp`, `mv`, `find`, `grep`, `wc`, `stat`, `date`, `df`, `du`.

Diagnostics: `whoami`, `id`, `env`, `printenv`, `which`, `uname`, `hostname`, `ping`, `curl`.

### Laravel / PHP

Allowed platform executables: `php`, `composer`.

Selected Artisan operations: `migrate`, `migrate:fresh`, `migrate:refresh`, `db:seed`, `route:list`, `config:clear`, `cache:clear`, `view:clear`, `optimize`, `storage:link`, `tinker`, `about`.

Composer: `install`, `update`, `dump-autoload`, `show`, `validate`, `outdated`.

### Django / Python

Allowed platform executables: `python`, `python3`, `pip`, `pip3`.

Selected `manage.py`: `migrate`, `makemigrations`, `createsuperuser`, `collectstatic`, `check`, `shell`.

Python inline/eval (`python -c`, `python -m`) is intentionally disabled.

### Node / frontend

Allowed platform executables: `node`, `npm`, `npx`, `yarn`, `pnpm`.

Package commands are restricted to install/ci/run/test/list/outdated/audit. Only `npx vite` and `npx tsc` are accepted through `npx`.

## Forbidden capabilities

No `sh`, `bash`, `ash`, `busybox`, Docker/Podman tooling, privilege escalation, package-manager OS installation, process killing, host/network namespace manipulation, mounts, SSH, credential-management commands, arbitrary capability changes, or arbitrary shell metacharacters.

`curl`/`ping` block localhost, Docker host, private RFC1918, loopback, and link-local targets to reduce SSRF access to platform infrastructure.

## File editing / nano

A raw `nano` TTY is intentionally **not exposed** because the API is non-interactive and a raw PTY would create an escape path around command filtering. The file endpoint provides the safe equivalent for reading and writing text files.

`POST /services/<service_id>/shell/file/` accepts `{action: "read", path}` or `{action: "write", path, content}`. The same session token and work-root restriction apply.

## Share security

`can_shell` is intentionally separate from `can_view`, logs, deploy, and lifecycle permissions. A share recipient receives shell access only when the effective share/member rules contain `can_shell=true`. Revoking the permission blocks subsequent session/command/file/close API calls even when the recipient already knows an old token.

The Service Detail frontend should treat `menu.shell.visible/enabled` as presentation metadata only. The backend remains the authorization boundary.
