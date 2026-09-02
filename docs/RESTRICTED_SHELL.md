# Restricted Service Shell API

The deployer exposes a restricted command API (and optional interactive PTY) for a
running service container. It is **not** a general Docker host shell.

## Security model

The hard security boundary is:

1. **Authorization** — `can_shell` on every request (owner or explicit share).
2. **Session binding** — opaque hashed token bound to `(service, user)`, idle expiry, concurrent limits.
3. **Container isolation** — commands run only inside the service’s existing container.
4. **Workspace confinement** — paths must stay inside the platform work-root; symlink escapes are probed.
5. **No user-controlled shell** — argv only; shells (`sh`, `bash`, …), `sudo`, Docker clients, and similar binaries are blocked.
6. **SSRF limits** — `curl`/`ping` cannot target localhost or private networks.
7. **Resource limits** — output/pipe/file size caps, idle timeout, concurrent sessions.
8. **Risk-based confirmation** — genuinely destructive operations require `confirm=true`.

The command policy is **capability/risk-based**, not an exhaustive subcommand menu.
Legitimate framework CLIs, package scripts, and git inspection work without being
manually registered. Dangerous execution mechanisms remain blocked.

## Lifecycle

1. `POST /services/<service_id>/shell/session/` creates a session and returns a short-lived token (`X-Shell-Token`).
2. `POST /services/<service_id>/shell/command/` executes one argv command (or a limited compound sequence).
3. WebSocket `/ws/services/shell/<service_id>/` provides an interactive PTY for single allowed commands that need stdin.
4. `POST /services/<service_id>/shell/close/` closes the session.

## Risk classification

| Risk | Examples | Confirmation |
|------|----------|--------------|
| `READ_ONLY` | `ls`, `git status`, `php artisan route:list` | No |
| `NORMAL_MUTATION` | `php artisan migrate`, `npm run build` | No |
| `DESTRUCTIVE` | `php artisan migrate:fresh`, `rm`, `git reset --hard`, `npm install` | Yes (`confirm=true`) |
| `INTERACTIVE` | `php artisan tinker`, `python manage.py shell` | Advanced permission |
| `PRIVILEGED` | (reserved) | Yes |

Unknown / custom Artisan and Django management commands are treated as
`NORMAL_MUTATION`, not destructive.

## Developer workflows supported

### Laravel / PHP
- `php artisan <any-valid-command>` including custom commands
- `php artisan migrate` (no confirmation)
- Info flags: `php -v`, `php -m`, `php --ini`
- Composer package management (with confirmation for destructive verbs)
- **Blocked:** `php -r`, arbitrary `.php` scripts, long-running servers/workers without bounds, `tinker` without advanced permission

### Django / Python
- `python manage.py <command>` including custom management commands
- **Blocked:** `python -c`, arbitrary `.py` scripts, `runserver`/`dbshell`, `shell` without advanced permission

### Node
- `npm` / `yarn` / `pnpm` / `bun` including `npm run <script>` for any project script
- `npx <tool>` for normal frontend tooling
- **Blocked:** publish/login/token operations; inline `node -e`

### Git
- Read-only: `status`, `log`, `diff`, `show`, `branch -a`, `remote -v`, `rev-parse`, …
- Mutating git operations require confirmation
- **Blocked:** `git daemon` and options that override external programs

### Base tools
Filesystem inspection and limited mutation (`ls`, `cat`, `mkdir`, `rm`, …) with workspace confinement.

## Error codes

API failures return a stable `code` field when possible:

- `AUTHORIZATION_FAILED`
- `POLICY_REJECTED`
- `CONFIRMATION_REQUIRED`
- `INVALID_WORKDIR`
- `RUNTIME_ERROR`
- `TIMEOUT`
- `RESOURCE_LIMIT_EXCEEDED`

Non-zero process exits are **not** policy failures: the response is `result=success`
with the real `exit_code`, `stdout`, and `stderr`.

## File editing

Raw `nano`/`vi` PTYs are not exposed. Use `POST /services/<service_id>/shell/file/`
with `{action: "read"|"write", path, content?}`.

## Share security

`can_shell` is separate from view/logs/deploy permissions. Tokens are re-checked
against current share state on every request.
