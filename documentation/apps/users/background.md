# users background and implicit behavior

## User deletion

`cleanup_user_resources` is the project-wide pre-delete coordination signal. Before the Django deletion collector removes durable rows it fences every owned Service to `desired_state=deleted`, clears user-owned ServiceNetworkAttachment rows so PrivateNetwork cleanup cannot race the collector, and delegates runtime/volume/network cleanup to the owning resource signals.

Hard deletion through the admin API is a separate destructive path. It first calls `app_catalog.user_deletion.prepare_user_hard_delete` so protected catalog child bindings are removed in the application-owned order; those bindings keep their `PROTECT` contract for direct Service/Deploy deletion.

Profile/deployment artifacts and other user-owned storage are cleaned by their owning app signals. Critical runtime ownership failures are not silently converted into successful deletion.

## Profile deletion

cleanup_profile_image removes the stored image on profile deletion.

## Cache

user cache invalidation is derived infrastructure; the database remains authoritative.

## Tests as contracts

users/tests.py protects identity/account API behavior; tests_contact_changes.py protects contact-change interactions. Contact-change tests should be read with auth_users session tests because verification revokes sessions after commit.
