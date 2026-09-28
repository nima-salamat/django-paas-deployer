# users background and implicit behavior

## User deletion

cleanup_user_resources is a pre-delete coordination signal. It removes user-owned deployment/profile media and asks the owning Service/Volume/PrivateNetwork layers to clean their resources. The signal is intentionally defensive so cleanup errors are logged rather than preventing all identity deletion paths.

## Profile deletion

cleanup_profile_image removes the stored image on profile deletion.

## Cache

user cache invalidation is derived infrastructure; the database remains authoritative.

## Tests as contracts

users/tests.py protects identity/account API behavior; tests_contact_changes.py protects contact-change interactions. Contact-change tests should be read with auth_users session tests because verification revokes sessions after commit.
