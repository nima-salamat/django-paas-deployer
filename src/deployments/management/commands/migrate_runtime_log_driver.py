"""Migrate existing managed Swarm services to the Fluent Bit log transport."""
from __future__ import annotations

from copy import deepcopy

from django.core.management.base import BaseCommand, CommandError

from deployments.core.swarm import SwarmRuntime
from deployments.common.runtime_logging import fluentd_log_driver_options


def updated_service_spec(spec: dict, options: dict[str, str]) -> dict:
    """Return a copy of a Swarm ServiceSpec with a new log driver and task generation."""
    result = deepcopy(spec or {})
    task_template = dict(result.get("TaskTemplate") or {})
    current_force_update = task_template.get("ForceUpdate") or 0
    try:
        current_force_update = int(current_force_update)
    except (TypeError, ValueError):
        current_force_update = 0
    task_template["LogDriver"] = {
        "Name": "fluentd",
        "Options": dict(options),
    }
    task_template["ForceUpdate"] = current_force_update + 1
    result["TaskTemplate"] = task_template
    return result


class Command(BaseCommand):
    help = (
        "Migrate existing PassDeployer Swarm services to Fluent Bit. "
        "Dry-run by default; --apply performs a rolling task update."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply the logging-driver change and replace running tasks.",
        )
        parser.add_argument(
            "--service-id",
            default="",
            help="Only migrate services owned by this PassDeployer Service UUID.",
        )

    def handle(self, *args, **options):
        runtime = SwarmRuntime()
        try:
            runtime.assert_active()
            services = runtime.client.services.list(
                filters={"label": "managed-by=django-paas-deployer"}
            )
        except Exception as exc:
            raise CommandError(f"Unable to inspect Docker Swarm services: {exc}") from exc

        driver_options = fluentd_log_driver_options()
        service_filter = str(options.get("service_id") or "").strip()
        apply_changes = bool(options.get("apply"))
        scanned = changed = skipped = failed = 0

        for service in services:
            try:
                service.reload()
                attrs = service.attrs or {}
                spec = dict(attrs.get("Spec") or {})
                labels = dict(spec.get("Labels") or {})
                owner = str(labels.get("passdeployer.service") or "").strip()
                if not owner or (service_filter and owner != service_filter):
                    skipped += 1
                    continue

                scanned += 1
                task_template = dict(spec.get("TaskTemplate") or {})
                log_driver = dict(task_template.get("LogDriver") or {})
                current_options = dict(log_driver.get("Options") or {})
                already_configured = (
                    str(log_driver.get("Name") or "").lower() == "fluentd"
                    and all(current_options.get(k) == v for k, v in driver_options.items())
                )
                if already_configured:
                    skipped += 1
                    continue

                name = str(service.name or service.id)
                if not apply_changes:
                    self.stdout.write(
                        f"Would migrate {name} (service={owner}) to fluentd."
                    )
                    continue

                version = int((attrs.get("Version") or {}).get("Index") or 0)
                if version <= 0:
                    raise RuntimeError("Docker service version is missing")

                new_spec = updated_service_spec(spec, driver_options)
                api = runtime.client.api
                url = api._url("/services/{0}/update", service.id)
                response = api._post_json(
                    url,
                    data=new_spec,
                    params={"version": version},
                )
                api._result(response, json=True)
                changed += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Migrated {name} (service={owner}); Swarm will replace its tasks."
                    )
                )
            except Exception as exc:
                failed += 1
                self.stderr.write(
                    self.style.ERROR(
                        f"Failed to migrate {getattr(service, 'name', service.id)}: {exc}"
                    )
                )

        mode = "applied" if apply_changes else "dry-run"
        self.stdout.write(
            f"Fluent Bit log-driver migration ({mode}): "
            f"scanned={scanned}, changed={changed}, skipped={skipped}, failed={failed}"
        )
        if failed:
            raise CommandError(f"{failed} Swarm service(s) could not be migrated.")
        if not apply_changes and scanned:
            self.stdout.write(
                "Review the list, then rerun with --apply to roll the task generation."
            )
