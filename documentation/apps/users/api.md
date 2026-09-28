# users API

Root mounts:
- /users/ -> users.urls
- /api/users/ -> users.api_urls

All customer-facing user APIs use SessionJWTAuthentication + IsAuthenticated. Administrative user APIs use admin rules/superuser checks in users.admin_apis.

| Method | Route | View | Behavior |
|---|---|---|---|
| GET | /user/ | UserAPIView | Returns the authenticated user's serialized account state. |
| PUT | /user/ | UserAPIView | Uses UpdateUserSerializer. Direct email/phone mutation is rejected; verified contact-change belongs to users.contact_api/auth_users. |
| GET, POST | /profile/list/ | ProfileViewSet.list | Lists only the current user's profile images ordered by order/created_at. |
| POST | /profile/order/ | ProfileViewSet.order | Accepts JSON ordering map and rewrites profile order for the caller. |
| POST | /profile/delete/ | ProfileViewSet.delete | Deletes a profile belonging to the caller; 404 for another user's/nonexistent profile. |
| POST | /profile/set/ | ProfileViewSet.set | Multipart profile-image creation subject to model/image validation and the five-profile cap. |
| GET | /password/status/ | PasswordStatusAPIView | Returns whether the current User has a usable password. |
| POST | /password/set/ | SetPasswordAPIView | Sets a password only when no usable password exists; serializer applies Django password validation. |
| POST | /password/change/ | ChangePasswordAPIView | Requires current password and validated replacement. |
| DELETE | /password/remove/ | RemovePasswordAPIView | Requires current password and removes the usable password. |

Administrative routes under /users/admin/ include:
- GET /permissions/
- GET /me/permissions/
- GET /users/
- GET/PUT/PATCH/DELETE /users/<int:pk>/
- GET/POST/PATCH /users/<int:pk>/rules/

These are operator surfaces and must be read together with users.admin_apis.

## Contact-change routes

Implemented in src/users/contact_api.py and mounted through api_urls. The request endpoint creates a UserContactChange transaction and sends an OTP; confirmation verifies AuthCode, changes User, marks contact verified and invalidates all sessions after commit.

## API-to-model chain

PUT /user/
 -> UpdateUserSerializer
 -> User fields that are safe for direct update
 -> User.full_clean/save

POST /profile/set/
 -> AddImageProfileSerializer
 -> Profile.full_clean/save
 -> file storage side effect

POST /password/change/
 -> ChangePasswordSerializer
 -> User.check_password + validate_password
 -> User.set_password/save

No route in users directly owns login/session validity.