# users — detailed endpoint behavior reference

Root mounts are `/users/` and `/api/users/`. Customer endpoints use SessionJWTAuthentication + IsAuthenticated. Admin endpoints require the declared staff/rule or superuser boundary. Contact values are not changed by a normal profile update; they use the OTP-backed contact-change workflow.

## Endpoint behavior matrix

### Personal account, password and profile

| Method | Route | Handler | What it does |
|---|---|---|---|
| GET | `/users/user/` | UserAPIView | Returns the authenticated user's account representation. |
| PUT | `/users/user/` | UserAPIView | Updates permitted profile/account fields; direct email/phone mutation is rejected. |
| GET, POST | `/users/profile/list/` | ProfileViewSet.list | Lists the current user's profile images (POST is a compatibility alias of the same list action). |
| POST | `/users/profile/order/` | ProfileViewSet.order | Reorders profile images owned by the caller. |
| POST | `/users/profile/delete/` | ProfileViewSet.delete | Deletes a profile image only when it belongs to the caller. |
| POST | `/users/profile/set/` | ProfileViewSet.set | Uploads a validated profile image; the model enforces the per-user image cap. |
| GET | `/users/password/status/` | PasswordStatusAPIView | Reports whether the current account has a usable password. |
| POST | `/users/password/set/` | SetPasswordAPIView | Sets an initial password only when the account does not already have one. |
| POST | `/users/password/change/` | ChangePasswordAPIView | Changes an existing password after checking the current password and validating the replacement. |
| DELETE | `/users/password/remove/` | RemovePasswordAPIView | Removes the usable password after verifying the current password. |

### Contact and language aliases

| Method | Route | Handler | What it does |
|---|---|---|---|
| GET | `/api/users/user/` | UserAPIView | Same account representation as the /users/ mount. |
| PUT | `/api/users/user/` | UserAPIView | Same safe profile update contract as the /users/ mount. |
| GET | `/api/users/user/language/` | LanguagePreferenceAPIView | Returns the saved language preference and supported choices. |
| PATCH | `/api/users/user/language/` | LanguagePreferenceAPIView | Changes the caller's language preference to a supported value. |
| POST | `/api/users/user/contact-change/` | ContactChangeRequestAPIView | Starts a verified email or phone change and sends a purpose-scoped OTP; exactly one destination is supplied. |
| POST | `/api/users/user/contact-change/<uuid:change_id>/confirm/` | ContactChangeConfirmAPIView | Confirms the OTP, applies the pending contact change and invalidates existing sessions. |
| GET | `/api/users/password-status/` | PasswordStatusAPIView | Alias for current password-status read. |
| POST | `/api/users/set-password/` | SetPasswordAPIView | Alias for initial password setup. |
| POST | `/api/users/change-password/` | ChangePasswordAPIView | Alias for password change. |
| DELETE | `/api/users/remove-password/` | RemovePasswordAPIView | Alias for password removal. |

### Administrative identity and session management

| Method | Route | Handler | What it does |
|---|---|---|---|
| GET | `/users/admin/permissions/`, `/api/users/admin/permissions/` | AdminPermissionCatalogAPIView | Lists the permission/rule catalogue available to the admin UI. |
| GET | `/users/admin/me/permissions/`, `/api/users/admin/me/permissions/` | MePermissionsAPIView | Returns the authenticated administrator's effective permission set. |
| GET, POST | `/users/admin/users/`, `/api/users/admin/users/` | AdminUserListAPIView | Lists users with filters/pagination or creates a new user. Creation is scope-dependent: users.create can create only a basic non-staff account; users.manage can manage staff/rules and only a superuser can create another superuser. |
| GET, PATCH, DELETE | `/users/admin/users/<int:pk>/`, `/api/users/admin/users/<int:pk>/` | AdminUserDetailAPIView | Reads a target user, updates permitted fields/rules, or deactivates the account. Hard deletion is superuser-only and asynchronous with `?hard=1`; there is no PUT handler. |
| PUT | `/users/admin/users/<int:pk>/rules/`, `/api/users/admin/users/<int:pk>/rules/` | AdminUserRulesAPIView | Replaces the target user's rules with the submitted `rules` array after validating that the caller is allowed to grant every requested rule. This endpoint has no GET, POST or PATCH handler. |
| GET | `/users/admin/users/<int:pk>/sessions/`, `/api/users/admin/users/<int:pk>/sessions/` | AdminUserSessionListAPIView | Lists a target user's sessions under auth_sessions.view/manage. |
| POST | `/users/admin/users/<int:pk>/sessions/logout-all/`, `/api/users/admin/users/<int:pk>/sessions/logout-all/` | AdminUserSessionLogoutAllAPIView | Revokes all eligible sessions for the target user. |
| DELETE | `/users/admin/users/<int:pk>/sessions/<str:session_id>/`, `/api/users/admin/users/<int:pk>/sessions/<str:session_id>/` | AdminUserSessionRevokeAPIView | Revokes one target user's session. |

### Admin table browser and per-user profile management

| Method | Route | Handler | What it does |
|---|---|---|---|
| GET | `/api/users/admin/tables/` | AdminTableListView | Lists the allow-listed model/table descriptors, counts and display metadata; it does not create rows. |
| GET | `/api/users/admin/tables/<str:model_key>/` | AdminTableRowsView | Lists rows for an allow-listed model key. |
| GET | `/api/users/admin/tables/<str:model_key>/fk-search/` | AdminTableFKSearchAPIView | Searches selectable related rows for a foreign-key editor. |
| GET, DELETE | `/api/users/admin/tables/<str:model_key>/<str:pk>/` | AdminTableRowView | Reads one allow-listed row or deletes it only when its registry entry is deletable; protected rows and the final active superuser are not deletable. This view has no PATCH handler. |
| GET, POST | `/api/users/admin/users/<int:pk>/profiles/` | AdminProfileListCreateAPIView | Lists a target user's profile images or uploads an image for that user. |
| POST | `/api/users/admin/users/<int:pk>/profiles/reorder/` | AdminProfileReorderAPIView | Reorders a target user's profile images. |
| PATCH, DELETE | `/api/users/admin/users/<int:pk>/profiles/<int:profile_id>/` | AdminProfileDetailAPIView | Updates metadata or deletes one target user's profile image. |

`/users/plans/` is an include of the Plans router/HTML surface; use the [Plans API reference](../plans/api.md) for that contract.

The endpoint-specific payload requirements and validation rules follow below. They are intentionally not inferred from fields read by unrelated handlers in the same Python module.

## Personal account endpoints

### GET `/user/`

No body. Returns the authenticated User representation.

### GET/PATCH `/user/language/`

This authenticated endpoint reads and persists the preferred interface language for the current user.

| Method | Request field | Required | Contract |
|---|---|---:|---|
| GET | — | — | Returns the saved `language` and the supported options (`en-us`, `fa`). |
| PATCH | `language` | Yes | Accepts only `en-us` or `fa`; unsupported values return HTTP 400 with code `unsupported_language`. |

The preference is stored on the User row and is used as the fallback language for authenticated requests that do not send an explicit `Accept-Language` header.

### PUT `/user/`

All request fields are optional individually, but a non-empty request must use the supported fields below. `email` and `phone_number` are deliberately rejected here because contact changes require OTP verification.

| Field | Required | Notes |
|---|---:|---|
| `username` | No | Max 150 characters; updated directly. |
| `birthdate` | No | Date; `null` is accepted by the serializer. |
| `theme` | Yes | Must match `User.ThemeChoices`; the serializer does not set `required=False`. |
| `color` | Yes | Must match configured color choices; the serializer does not set `required=False`. |
| `email` | No | Rejected when supplied; use contact-change flow. |
| `phone_number` | No | Rejected when supplied; use contact-change flow. |

### POST `/user/contact-change/`

Exactly one of `email` or `phone_number` is required.

The existing contact is not changed until the destination OTP is successfully verified. An earlier pending contact change is cancelled before a new one is created.

### POST `/user/contact-change/{change_id}/confirm/`

| Field | Required |
|---|---:|
| `code` | Yes |

`change_id` is a UUID path parameter. Successful confirmation updates the contact, marks it verified and invalidates all sessions.

## Password endpoints

### POST `/password/set/`

| Field | Required | Contract |
|---|---:|---|
| `new_password` | Yes | Minimum 8 characters and Django password validation. |
| `new_confirm_password` | Yes | Must equal `new_password`. |

The operation fails when the account already has a usable password.

### POST `/password/change/`

Requires all three fields:

`current_password`, `new_password`, `new_confirm_password`.

The current password must validate; the new password is checked against Django password validation and confirmation.

### DELETE `/password/remove/`

| Field | Required |
|---|---:|
| `current_password` | Yes |

The operation requires a valid current password and an existing usable password.

## Profile endpoints

### POST `/profile/set/`

Multipart/form-data:

| Field | Required |
|---|---:|
| `image` | Yes |
| `order` | Yes |

The Profile model limits each user to five images and validates image size/dimensions.

### POST `/profile/order/`

JSON body:

`order` is required and must be a non-empty object whose keys are numeric Profile ids and whose values are integers.

### POST `/profile/delete/`

Body:

`id` is required and must identify a Profile belonging to the authenticated user.

## Administrative route aliases declared by `src/users/api_urls.py`

These are additional HTTP mounts that must not be confused with the shorter routes in `users.urls`:

| Method | Route |
|---|---|
| GET/PATCH | `/api/users/user/language/` |
| POST | `/api/users/user/contact-change/` |
| POST | `/api/users/user/contact-change/{change_id}/confirm/` |
| GET | `/api/users/password-status/` |
| POST | `/api/users/set-password/` |
| POST | `/api/users/change-password/` |
| DELETE | `/api/users/remove-password/` |
| GET/POST | `/api/users/admin/tables/` |
| GET | `/api/users/admin/tables/{model_key}/` |
| GET | `/api/users/admin/tables/{model_key}/fk-search/` |
| GET/PATCH/DELETE | `/api/users/admin/tables/{model_key}/{pk}/` |
| GET/POST | `/api/users/admin/users/{pk}/profiles/` |
| POST | `/api/users/admin/users/{pk}/profiles/reorder/` |
| PATCH/DELETE | `/api/users/admin/users/{pk}/profiles/{profile_id}/` |

