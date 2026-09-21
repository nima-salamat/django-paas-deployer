# users

## Responsibility
User identity/profile data, password state, application permissions and operator user management. Authentication itself belongs to auth_users.

## API
GET /users/user/
GET/POST /users/profile/list/
POST /users/profile/order/
POST /users/profile/delete/
POST /users/profile/set/
GET /users/password/status/
POST /users/password/set/
POST /users/password/change/
POST /users/password/remove/

## Admin
GET /users/admin/permissions/
GET /users/admin/me/permissions/
GET /users/admin/users/
GET/PUT/PATCH /users/admin/users/<int:pk>/
GET/PUT/PATCH /users/admin/users/<int:pk>/rules/
