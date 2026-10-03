# users background and implicit behavior

## User deletion

`cleanup_user_resources` is the project-wide pre-delete safety boundary for final account removal. The normal hard-delete API is two-phase: it records `deletion_requested_at`, deactivates the account, revokes authentication sessions and queues `users.tasks.finalize_user_deletion`; the worker fences Services, cancels active Deploys and only then allows `User.delete()` to run the owning cleanup signals.

Profile/deployment artifacts and other user-owned storage are cleaned by their owning app signals. Critical runtime ownership failures are not silently converted into successful deletion.

## Profile deletion

cleanup_profile_image removes the stored image on profile deletion.

## Cache

user cache invalidation is derived infrastructure; the database remains authoritative.

## Tests as contracts

users/tests.py protects identity/account API behavior; tests_contact_changes.py protects contact-change interactions. Contact-change tests should be read with auth_users session tests because verification revokes sessions after commit.
