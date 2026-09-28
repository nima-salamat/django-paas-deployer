# users contracts and tests

| Test | Protected behavior |
|---|---|
| tests.py | account/user/profile API behavior and identity rules |
| tests_contact_changes.py | verified contact-change transaction, uniqueness and session revocation interaction |

Contact changes span users and auth_users. A green users-only test is not sufficient when changing AuthCode/session semantics.
