class DeploymentLogRouter:
    """
    Database router for the deployment log database.

    Database layout:

        default
        ├── Deploy
        ├── Service
        └── other application models

        deployment_logs
        └── DeployLog

    Only DeployLog is stored in the deployment_logs database.
    All other models continue using the default database.
    """

    LOG_DATABASE = "deployment_logs"

    DEPLOY_APP_LABEL = "deploy"
    LOG_MODEL_NAME = "deploylog"

    # ============================================================
    # Helpers
    # ============================================================

    @classmethod
    def is_deployment_log(cls, model):
        """
        Return True when the model is the DeployLog model.
        """
        return (
            model._meta.app_label == cls.DEPLOY_APP_LABEL
            and model._meta.model_name == cls.LOG_MODEL_NAME
        )

    @classmethod
    def is_deploy_app(cls, app_label):
        """
        Return True when the model belongs to the deploy app.
        """
        return app_label == cls.DEPLOY_APP_LABEL

    # ============================================================
    # READ
    # ============================================================

    def db_for_read(self, model, **hints):
        """
        Route DeployLog reads to the deployment_logs database.

        Returning None means Django will use the normal/default
        database routing for every other model.
        """
        if self.is_deployment_log(model):
            return self.LOG_DATABASE

        return None

    # ============================================================
    # WRITE
    # ============================================================

    def db_for_write(self, model, **hints):
        """
        Route DeployLog writes to the deployment_logs database.
        """
        if self.is_deployment_log(model):
            return self.LOG_DATABASE

        return None

    # ============================================================
    # RELATIONS
    # ============================================================

    def allow_relation(self, obj1, obj2, **hints):
        """
        Prevent Django from treating DeployLog and normal
        application models as being in the same database.

        DeployLog is stored in deployment_logs while Deploy,
        Service, etc. are stored in default.

        Returning None for normal relations lets Django apply
        its default relation behavior.
        """

        obj1_is_log = self.is_deployment_log(obj1.__class__)
        obj2_is_log = self.is_deployment_log(obj2.__class__)

        # DeployLog is stored in a separate database.
        # Do not allow relations between DeployLog and models
        # stored in the default database.
        if obj1_is_log or obj2_is_log:
            return False

        return None

    # ============================================================
    # MIGRATIONS
    # ============================================================

    def allow_migrate(
        self,
        db,
        app_label,
        model_name=None,
        **hints,
    ):
        """
        Control where models are allowed to migrate.

        Rules:

        DeployLog:
            deployment_logs -> allowed
            default          -> blocked

        Other deploy models:
            default          -> allowed
            deployment_logs  -> blocked

        Other applications:
            default         -> allowed by normal Django routing
            deployment_logs -> blocked
        """

        # --------------------------------------------------------
        # DeployLog
        # --------------------------------------------------------
        if (
            app_label == self.DEPLOY_APP_LABEL
            and model_name == self.LOG_MODEL_NAME
        ):
            return db == self.LOG_DATABASE

        # --------------------------------------------------------
        # Other models in the deploy application
        # --------------------------------------------------------
        if app_label == self.DEPLOY_APP_LABEL:
            return db != self.LOG_DATABASE

        # --------------------------------------------------------
        # Models from other applications
        # --------------------------------------------------------
        # The deployment_logs database must contain ONLY DeployLog.
        # Returning None here would allow Django to run migrations for
        # Wagtail, auth, sessions, etc. on deployment_logs as well.
        # That is especially dangerous for Wagtail because its migration
        # history creates/updates wagtailcore_page and can leave the log DB
        # in an inconsistent state.
        if db == self.LOG_DATABASE:
            return False

        return None
