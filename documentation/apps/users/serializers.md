# users serializers

## CreateUserSerializer

Creates an inactive User. username is required; at least one of email or phone_number is required. All three are write-only. create() calls User.full_clean() and save(); authentication activation belongs to auth_users.

## GetUserSerializer

Read-only account representation. Exposes identity/contact/theme/color/birthdate, verification flags and staff/superuser flags plus derived has_password. It does not expose password material.

## UpdateUserSerializer

Accepts username, birthdate, theme and color. email and phone_number are intentionally rejected even though serializer fields exist: contact changes must use the verified users.contact_api flow. Theme and color are presentation state, not runtime policy.

## SetPasswordSerializer

Write-only new_password and confirmation. Requires equality and Django password validators. save() refuses to overwrite an existing usable password.

## ChangePasswordSerializer

Requires current_password plus validated new password/confirmation. The serializer is instantiated with the current User; it checks the current password before save.

## RemovePasswordSerializer

Requires current_password and an existing usable password; then removes the usable password.

## Profile serializers

AddImageProfileSerializer accepts an image and order and creates Profile after model validation. OrderImageProfileSerializer accepts the JSON ordering map consumed by the profile API. ProfileImager/related read serializers expose stored image metadata/URLs.

## Sensitivity and permission

Serializers do not replace authorization. API views scope user/Profile querysets to request.user; serializers reject dangerous contact mutations but cannot authorize another resource's ownership.

## API -> serializer -> model

PUT /user/ -> UpdateUserSerializer -> User.full_clean/save.

POST /password/change/ -> ChangePasswordSerializer -> password validation -> User.set_password/save.

POST /profile/set/ -> AddImageProfileSerializer -> Profile.full_clean/save -> media storage.

Source: src/users/serializers.py and users/apis.py.
