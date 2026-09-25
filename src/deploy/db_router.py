"""
Database router for the deployment / runtime log database.

Database layout:

    default
    ├── Deploy, Service, Plan, …
    deployment_logs
    ├── DeployLog
    └── logs.* (ServiceLogStream, ServiceLogEntry, usage, …)
"""


class DeploymentLogRouter:
    LOG_DATABASE = "deployment_logs"
    DEPLOY_APP_LABEL = "deploy"
    LOGS_APP_LABEL = "logs"
    LOG_MODEL_NAME = "deploylog"

    @classmethod
    def is_deployment_log(cls, model):
        return (
            model._meta.app_label == cls.DEPLOY_APP_LABEL
            and model._meta.model_name == cls.LOG_MODEL_NAME
        )

    @classmethod
    def is_runtime_log_model(cls, model):
        return model._meta.app_label == cls.LOGS_APP_LABEL

    @classmethod
    def is_log_db_model(cls, model):
        return cls.is_deployment_log(model) or cls.is_runtime_log_model(model)

    def db_for_read(self, model, **hints):
        if self.is_log_db_model(model):
            return self.LOG_DATABASE
        return None

    def db_for_write(self, model, **hints):
        if self.is_log_db_model(model):
            return self.LOG_DATABASE
        return None

    def allow_relation(self, obj1, obj2, **hints):
        # Allow relations within same DB; cross-DB returns None (Django default)
        o1 = self.is_log_db_model(obj1.__class__)
        o2 = self.is_log_db_model(obj2.__class__)
        if o1 and o2:
            return True
        if not o1 and not o2:
            return None
        return False

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label == self.LOGS_APP_LABEL:
            return db == self.LOG_DATABASE
        if app_label == self.DEPLOY_APP_LABEL and model_name == self.LOG_MODEL_NAME:
            return db == self.LOG_DATABASE
        if app_label == self.DEPLOY_APP_LABEL:
            # Other deploy models on default
            if model_name == self.LOG_MODEL_NAME:
                return db == self.LOG_DATABASE
            return db == "default"
        if db == self.LOG_DATABASE:
            return False
        return None
