class DeploymentLogRouter:
    """Keep deployment event history out of the primary application database."""

    log_database = "deployment_logs"
    app_label = "deploy"
    model_name = "deploylog"

    def db_for_read(self, model, **hints):
        if model._meta.app_label == self.app_label and model._meta.model_name == self.model_name:
            return self.log_database
        return None

    def db_for_write(self, model, **hints):
        return self.db_for_read(model, **hints)

    def allow_relation(self, obj1, obj2, **hints):
        log_models = {
            (self.app_label, self.model_name),
        }
        if (obj1._meta.app_label, obj1._meta.model_name) in log_models:
            return False
        if (obj2._meta.app_label, obj2._meta.model_name) in log_models:
            return False
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label != self.app_label:
            return None
        if model_name == self.model_name:
            return True
        return db != self.log_database
