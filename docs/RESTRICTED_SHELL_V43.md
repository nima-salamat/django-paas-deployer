# Restricted Shell V43

## Command execution model

Single commands that need interactive stdin use the WebSocket PTY consumer. This keeps the process alive so commands such as `python manage.py createsuperuser` can prompt for multiple lines without starting a new process for every answer.

Compound commands are parsed by the backend and each leaf command is executed directly through Docker argv. Supported operators are `|`, `&&`, `||`, and `;`. The backend does not invoke `/bin/sh` for these operators.

## File access policy

Every file operation is scoped to the session workspace root. The backend additionally evaluates the container's effective rootfs/mount policy and the filesystem's write bit before a mutation.

The tree endpoint exposes `writable`, `mode` (`rw`/`ro`) and `read_only_reason` metadata. The file endpoint exposes the same information.

## Interactive safety

Interactive PTY is intended for commands that genuinely need stdin. Unrestricted interpreters and script launchers are blocked, including shell binaries, Python inline execution, direct PHP script execution, Django shell/dbshell, Laravel Tinker/PsySH, and package-manager execution of arbitrary package scripts.
