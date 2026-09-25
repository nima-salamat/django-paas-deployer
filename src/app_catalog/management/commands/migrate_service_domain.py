from django.core.management.base import BaseCommand

from app_catalog.models import ApplicationInstance
from services.revisioning import ensure_revision_for_deploy


class Command(BaseCommand):
    help = (
        "Backfill legacy ApplicationInstance child Deploy rows into the "
        "Service -> ServiceRevision domain. No legacy plaintext data is deleted."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--application",
            dest="application_id",
            help="Migrate only one ApplicationInstance UUID.",
        )

    def handle(self, *args, **options):
        qs = ApplicationInstance.objects.all().prefetch_related("services__deploy__service")
        application_id = options.get("application_id")
        if application_id:
            qs = qs.filter(pk=application_id)

        total = 0
        migrated = 0
        skipped = 0
        errors = 0

        for instance in qs.iterator():
            total += 1
            self.stdout.write(f"Migrating application {instance.pk} ({instance.name})")
            rows = list(instance.services.select_related("deploy", "service").all())
            for row in rows:
                deploy = row.deploy
                if deploy is None:
                    skipped += 1
                    continue
                if deploy.revision_id:
                    skipped += 1
                    continue
                try:
                    ensure_revision_for_deploy(deploy)
                    migrated += 1
                except Exception as exc:
                    errors += 1
                    self.stderr.write(
                        self.style.ERROR(
                            f"  failed child service {row.service_id}: {exc}"
                        )
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f"Processed applications={total}, revisions_created={migrated}, "
                f"already_migrated_or_skipped={skipped}, errors={errors}."
            )
        )
        if errors:
            raise SystemExit(1)
