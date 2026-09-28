# services contracts and tests

| Test | Protected behavior | Invariant at risk |
|---|---|---|
| tests/test_revisioning.py | revision creation/snapshot behavior | historical executable configuration remains immutable |
| tests/test_volume_storage_quota.py | storage allocation/release | plan storage ceiling and volume ownership remain consistent |
| tests_shell_commands.py | command execution | shell commands remain inside the authorized shell boundary |
| tests_shell_permissions.py | owner/share authorization | can_shell is enforced server-side |
| tests_shell_policy.py | command/file policy | restricted shell cannot bypass platform policy |
| tests_shell_regressions.py | known shell regressions | previous security/UX fixes remain intact |
| tests_shell_session_replace_static.py | session replacement/static shell behavior | stale shell sessions cannot keep an invalid capability |

Use revisioning tests when changing Service/Revision fields, serializers or deploy inputs. Use shell tests together when changing any shell endpoint, not one file in isolation.

Cross-app activation and worker ownership contracts live in deployments; see ../../deployments/11-testing-contracts-and-invariants.md.
