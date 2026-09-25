# Project Layout

```text
.
├── documentation/
├── src/
│   ├── config/
│   ├── app_catalog/
│   ├── auth_users/
│   ├── cms/
│   ├── core/
│   ├── custom_emails/
│   ├── deploy/
│   ├── deployments/
│   ├── docs/          product Django app
│   ├── logs/
│   ├── messenger/
│   ├── plans/
│   ├── services/
│   ├── tickets/
│   ├── users/
│   ├── static/
│   └── templates/
├── scripts/
├── compose.yaml
├── Dockerfile
├── entrypoint.sh
├── manage.py
├── pytest.ini
└── requirements.txt
```

The root contains operational entrypoints, packaging and tooling. Application source is under `src/`.

The `src/docs/` package is product code. Repository documentation belongs under `documentation/`.
