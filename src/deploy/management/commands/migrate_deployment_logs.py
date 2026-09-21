from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import DEFAULT_DB_ALIAS, transaction

from deploy.models import DeployLog


class Command(BaseCommand):
    help = "Copy legacy deployment logs from the primary database into the deployment log database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="Number of legacy log rows to copy per transaction.",
        )
        parser.add_argument(
            "--delete-source",
            action="store_true",
            help="Delete copied logs from the primary database after a successful copy.",
        )

    def handle(self, *args, **options):
        log_db = settings.DEPLOYMENT_LOG_DB_ALIAS
        batch_size = max(options["batch_size"], 1)
        delete_source = options["delete_source"]
        copied = 0

        queryset = DeployLog.objects.using(DEFAULT_DB_ALIAS).order_by("created_at", "id")

        batch = []
        for log in queryset.iterator(chunk_size=batch_size):
            batch.append(log)
            if len(batch) < batch_size:
                continue

            with transaction.atomic(using=log_db):
                for log in batch:
                    DeployLog.objects.using(log_db).update_or_create(
                        id=log.id,
                        defaults={
                            "deploy_id": log.deploy_id,
                            "service_id": log.service_id,
                            "stage": log.stage,
                            "event_type": log.event_type,
                            "level": log.level,
                            "message": log.message,
                            "progress": log.progress,
                            "details": log.details,
                            "exception_type": log.exception_type,
                            "traceback": log.traceback,
                            "created_at": log.created_at,
                            "updated_at": log.updated_at,
                        },
                    )

            copied += len(batch)
            self.stdout.write(f"Copied {copied} deployment log rows.")

            if delete_source:
                DeployLog.objects.using(DEFAULT_DB_ALIAS).filter(id__in=[log.id for log in batch]).delete()
            batch = []

        if batch:
            with transaction.atomic(using=log_db):
                for log in batch:
                    DeployLog.objects.using(log_db).update_or_create(
                        id=log.id,
                        defaults={
                            "deploy_id": log.deploy_id,
                            "service_id": log.service_id,
                            "stage": log.stage,
                            "event_type": log.event_type,
                            "level": log.level,
                            "message": log.message,
                            "progress": log.progress,
                            "details": log.details,
                            "exception_type": log.exception_type,
                            "traceback": log.traceback,
                            "created_at": log.created_at,
                            "updated_at": log.updated_at,
                        },
                    )
            copied += len(batch)
            self.stdout.write(f"Copied {copied} deployment log rows.")
            if delete_source:
                DeployLog.objects.using(DEFAULT_DB_ALIAS).filter(id__in=[log.id for log in batch]).delete()

        self.stdout.write(self.style.SUCCESS(f"Finished copying {copied} deployment log rows to {log_db}."))
