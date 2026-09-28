# tickets contracts and tests

tickets/tests.py is the app-level regression suite for ticket models/APIs/permissions.

The contract matrix is:
- permission tests protect owner versus assigned/department staff scope;
- serializer tests protect HTML sanitization and Service/Deploy ownership validation;
- attachment tests protect file-type and aggregate-quota controls;
- lifecycle tests protect status/priority/assignment transitions;
- realtime tests protect event notification without making the socket authoritative.

When a ticket can suddenly be seen by the wrong user, start with permissions.py and the queryset in the relevant API before changing serializers.
