# custom_emails

## Responsibility
Transactional email templates, sending, email logs, retry operations and email administration.

## API
GET/POST /api/emails/templates/
GET/PUT/PATCH/DELETE /api/emails/templates/<int:pk>/
POST /api/emails/templates/preview/
POST /api/emails/send/
GET /api/emails/logs/
GET /api/emails/logs/<int:pk>/
POST /api/emails/logs/<int:pk>/retry/
GET /api/emails/stats/
GET /api/emails/users/
