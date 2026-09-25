"""Ensure deployment_logs database has DeployLog + runtime logs tables."""
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connections

from deploy.models import DeployLog


class Command(BaseCommand):
    help = (
        "Create/update DeployLog and apply logs app migrations on DEPLOYMENT_LOG_DB_ALIAS. "
        "Runtime ServiceLog* tables live only on the log database (not default)."
    )

    def handle(self, *args, **options):
        alias = settings.DEPLOYMENT_LOG_DB_ALIAS
        connection = connections[alias]
        model = DeployLog
        table = model._meta.db_table

        with connection.cursor() as cursor:
            existing_tables = connection.introspection.table_names(cursor)

        with connection.schema_editor() as schema_editor:
            if table not in existing_tables:
                schema_editor.create_model(model)
                self.stdout.write(self.style.SUCCESS(f"Created {table} on {alias}."))
            else:
                description = connection.introspection.get_table_description(
                    connection.cursor(), table
                )
                existing_columns = {col.name for col in description}
                added = []
                for field in model._meta.local_fields:
                    if field.column not in existing_columns:
                        schema_editor.add_field(model, field)
                        added.append(field.column)
                if added:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Updated {table} on {alias}; added columns: {', '.join(added)}."
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.SUCCESS(f"{table} on {alias} is already up to date.")
                    )

        # Runtime logging models (ServiceLogEntry, streams, usage, …)
        self.stdout.write(f"Applying logs migrations on database={alias} …")
        try:
            call_command(
                "migrate",
                "logs",
                database=alias,
                interactive=False,
                verbosity=1,
            )
            self.stdout.write(self.style.SUCCESS(f"logs migrations applied on {alias}."))
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"logs migrate on {alias} failed: {exc}"))
            raise
