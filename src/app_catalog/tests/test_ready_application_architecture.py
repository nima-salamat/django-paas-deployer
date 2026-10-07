from __future__ import annotations

import threading
import zipfile

import pytest
from django.db.models.deletion import RESTRICT, RestrictedError
from django.db import IntegrityError, connection, close_old_connections
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from app_catalog.catalog import ApplicationCatalog, resolve_variant
from app_catalog.executor import ApplicationStackExecutor
from app_catalog.models import ApplicationInstance, ApplicationInstanceService, ApplicationStatus
from app_catalog.services import create_application_installation
from deploy.models import DeploymentStatusChoices
from plans.models import Plan
from services.models import Service, ServiceEnvironmentVariable
from services.revisioning import ensure_revision_for_deploy, materialize_revision_config
from users.models import User
from core.global_settings.config import NameChoices, PlanTypeChoices, StorageTypeChoices


class ReadyApplicationArchitectureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='catalog-architecture', email='catalog-architecture@example.invalid')
        common = dict(max_cpu=2.0, max_ram=4096, max_storage=64, price_per_hour=0, storage_type=StorageTypeChoices.SSD)
        cls.app_plan = Plan.objects.create(name=NameChoices.BRONZE, platform='docker', plan_type=PlanTypeChoices.APP, **common)
        cls.db_plan = Plan.objects.create(name=NameChoices.BRONZE, platform='postgresql', plan_type=PlanTypeChoices.DB, **common)
        cls.mariadb_plan = Plan.objects.create(name=NameChoices.BRONZE, platform='mariadb', plan_type=PlanTypeChoices.DB, **common)

    def install(self, catalog_id='mattermost', variant='postgresql', name='catalog-architecture'):
        config = {'domain': f'{name}.example.invalid'}
        if catalog_id == 'mattermost':
            config['storage_mb'] = 4096
        return create_application_installation(self.user, {'catalog_id': catalog_id, 'variant': variant, 'name': name, 'plan_id': self.app_plan.pk, 'config': config})

    def test_catalog_compiler_preserves_secret_references(self):
        resolved = resolve_variant(ApplicationCatalog.get('mattermost'), 'postgresql', {'domain': 'chat.example.invalid', 'storage_mb': 4096})
        env = next(s['environment'] for s in resolved['services'] if s['key'] == 'mattermost')
        assert '${secret.postgres_password}' in env['MM_SQLSETTINGS_DATASOURCE']
        assert resolved['secrets']['postgres_password']

    def test_queued_child_deploy_is_accepted_by_deployment_worker_boundary(self):
        instance = self.install(catalog_id="wordpress", variant="default", name="worker-boundary")
        binding = instance.services.get(service_key="wordpress")
        from deployments.core.state.manager import StateManager

        acquired = StateManager.lock_and_get_deployment(
            binding.deploy_id,
            task_id="ready-app-child-worker",
        )

        assert acquired.pk == binding.deploy_id
        binding.service.refresh_from_db()
        binding.deploy.refresh_from_db()
        assert binding.service.status == "deploying"
        assert binding.deploy.status == DeploymentStatusChoices.RUNNING
        assert binding.service.task_id == "ready-app-child-worker"
        assert StateManager.heartbeat_deploy(
            binding.deploy_id,
            task_id="ready-app-child-worker",
        ) is True

    def test_installation_queues_children_and_keeps_selected_deploy_empty(self):
        instance = self.install(name="queued-child-lifecycle")
        rows = {row.service_key: row for row in instance.services.select_related("service", "deploy")}

        assert rows["mattermost"].service.status == "queued"
        assert rows["postgres"].service.status == "queued"
        assert rows["mattermost"].deploy.status == DeploymentStatusChoices.PENDING
        assert rows["postgres"].deploy.status == DeploymentStatusChoices.PENDING
        # selected_deploy is a post-activation compatibility projection; the
        # new deployment is eligible for execution without preselecting it.
        assert rows["mattermost"].service.selected_deploy_id is None
        assert rows["postgres"].service.selected_deploy_id is None

    def test_service_names_are_application_scoped_and_platform_suffixed(self):
        instance = self.install(catalog_id="wordpress", variant="default", name="my-deploy")
        rows = {row.service_key: row.service.name for row in instance.services.select_related("service")}

        assert rows["wordpress"] == "my-deploy-wordpress-docker"
        assert rows["mariadb"] == "my-deploy-mariadb-mariadb"

    def test_wordpress_apache_image_gets_global_server_name_configuration(self):
        instance = self.install(catalog_id="wordpress", variant="default", name="wordpress-apache-servername")
        app = instance.services.get(service_key="wordpress").service
        dockerfile = str((app.build_config or {}).get("dockerfile") or "")
        assert "ServerName localhost" in dockerfile

        start_command = str((app.runtime_config or {}).get("start_command") or "")
        assert start_command == ""

    def test_ready_app_mariadb_accepts_mysql_env_aliases_for_user_database_and_password(self):
        instance = self.install(catalog_id="wordpress", variant="default", name="mariadb-alias-contract")
        binding = instance.services.get(service_key="mariadb")
        materialized = materialize_revision_config(ensure_revision_for_deploy(binding.deploy, force_new=True).revision)

        assert materialized["platform"] == "mariadb"
        assert materialized["username"] == "app"
        assert materialized["database"] == "wordpress"
        assert materialized["password"] == instance.services.get(service_key="wordpress").service.secrets.get(
            key="service_password_wordpress"
        ).get_current_value()
        assert materialized["root_password"] == binding.service.secrets.get(
            key="service_password_root"
        ).get_current_value()


    def test_ready_app_mariadb_root_secret_reference_materializes_to_real_value(self):
        instance = self.install(catalog_id="wordpress", variant="default", name="mariadb-secret-materialization")
        binding = instance.services.get(service_key="mariadb")
        service = binding.service
        root_secret = service.secrets.get(key="service_password_root")
        expected = root_secret.get_current_value()

        deploy = ensure_revision_for_deploy(binding.deploy, force_new=True)
        materialized = materialize_revision_config(deploy.revision)

        assert materialized["root_password"] == expected
        assert materialized["root_password"] != "${secret.service_password_root}"
        refs = [ref for ref in (deploy.revision.secret_refs or []) if ref.get("path") == "root_password"]
        assert refs
        assert refs[0]["key"] == "service_password_root"
        assert refs[0]["version"] == root_secret.current_version
    def test_wordpress_selected_version_flows_through_installation_and_deploy_artifact(self):
        instance = create_application_installation(
            self.user,
            {
                "catalog_id": "wordpress",
                "variant": "default",
                "name": "wordpress-selected-version",
                "plan_id": self.app_plan.pk,
                "config": {
                    "domain": "wordpress-selected-version.example.invalid",
                    "software_version": "7.1.1",
                },
            },
        )

        binding = instance.services.get(service_key="wordpress")
        service = binding.service
        deploy = binding.deploy

        assert instance.software_version == "7.1.1"
        assert instance.config["software_version"] == "7.1.1"
        assert service.source_config["software_version"] == "7.1.2"
        assert service.source_config["selected_software_version"] == "7.1.1"
        assert service.runtime_config["selected_software_version"] == "7.1.1"

        dockerfile = str((service.build_config or {}).get("dockerfile") or "")
        assert "FROM wordpress:7.1.1-php8.3-apache" in dockerfile
        assert "FROM wordpress:7.1.2-php8.3-apache" not in dockerfile

        assert deploy.zip_file and deploy.zip_file.name
        with deploy.zip_file.open("rb") as handle:
            with zipfile.ZipFile(handle) as archive:
                archived_dockerfile = archive.read("Dockerfile").decode("utf-8")

        assert archived_dockerfile == dockerfile
        assert "FROM wordpress:7.1.1-php8.3-apache" in archived_dockerfile
    def test_wordpress_app_receives_materialized_mariadb_connection_contract(self):
        instance = self.install(
            catalog_id="wordpress",
            variant="default",
            name="wordpress-db-env-contract",
        )
        app = instance.services.get(service_key="wordpress").service

        env = {
            row.key: row.resolve_value()
            for row in app.environment_variables.filter(enabled=True)
        }

        assert env["WORDPRESS_DB_HOST"] == "mariadb"
        assert env["WORDPRESS_DB_USER"] == "app"
        assert env["WORDPRESS_DB_NAME"] == "wordpress"
        assert env["WORDPRESS_DB_PASSWORD"] == app.secrets.get(
            key="service_password_wordpress"
        ).get_current_value()


    def test_real_installation_materializes_db_child_and_composite_secret(self):
        instance = self.install(name='mattermost-real-materialization')
        bindings = {row.service_key: row for row in instance.services.select_related('service', 'deploy')}
        db = bindings['postgres'].service
        app = bindings['mattermost'].service
        assert db.plan.plan_type == PlanTypeChoices.DB
        assert db.plan.platform == 'postgresql'
        assert bindings['postgres'].deploy.zip_file.name in ('', None)
        assert bindings['postgres'].deploy.config['platform'] == 'postgresql'
        assert '${secret.postgres_password}' in bindings['postgres'].deploy.config['password']
        composite = ServiceEnvironmentVariable.objects.get(service=app, key='MM_SQLSETTINGS_DATASOURCE')
        assert composite.secret_id is not None
        assert composite.value == ''
        assert 'postgres://mmuser:' in composite.resolve_value()
        assert '${secret.postgres_password}' not in composite.resolve_value()

    def test_secrets_are_scoped_to_referencing_services(self):
        instance = create_application_installation(self.user, {'catalog_id': 'n8n-with-postgres-and-worker', 'variant': 'default', 'name': 'n8n-secret-scope', 'plan_id': self.app_plan.pk, 'config': {'domain': 'n8n-secret-scope.example.invalid'}})
        keys = {row.service_key: set(row.service.secrets.values_list('key', flat=True)) for row in instance.services.select_related('service')}
        assert keys['redis'] == set()
        assert keys['postgresql']
        assert keys['n8n']
        assert keys['n8n-worker']

    def test_catalog_bindings_restrict_direct_child_deletion(self):
        self.assertIs(
            ApplicationInstanceService._meta.get_field("service").remote_field.on_delete,
            RESTRICT,
        )
        self.assertIs(
            ApplicationInstanceService._meta.get_field("deploy").remote_field.on_delete,
            RESTRICT,
        )

    def test_installation_snapshot_is_immutable(self):
        instance = self.install(name='immutable-intent')
        original = dict(instance.definition_snapshot)
        instance.definition_snapshot = {**original, '_tampered': True}
        with pytest.raises(ValueError, match='immutable'):
            instance.save()
        instance.refresh_from_db()
        assert instance.definition_snapshot == original

    def test_executor_ignores_mutable_service_dependency_metadata(self):
        instance = self.install(name='snapshot-authority')
        service = instance.services.get(service_key='mattermost').service
        service.runtime_config['depends_on'] = []
        service.save(update_fields=['runtime_config', 'updated_at'])
        _, plan = ApplicationStackExecutor(str(instance.pk))._load()
        assert plan.service('mattermost').dependencies == ('postgres',)

    def test_executor_fails_closed_when_bindings_do_not_match_snapshot(self):
        instance = self.install(name='broken-binding')
        instance.services.get(service_key='mattermost').delete()
        with pytest.raises(ValueError, match='immutable application graph'):
            ApplicationStackExecutor(str(instance.pk))._load()

    def test_required_failure_cancels_pending_siblings(self):
        instance = self.install(name='failure-convergence')
        rows = list(instance.services.select_related('deploy'))
        failed = next(row for row in rows if row.service_key == 'postgres')
        sibling = next(row for row in rows if row.service_key == 'mattermost')
        failed.deploy.status = DeploymentStatusChoices.FAILED
        failed.deploy.error_message = 'database failed'
        failed.deploy.save(update_fields=['status', 'error_message', 'updated_at'])
        sibling.deploy.status = DeploymentStatusChoices.PENDING
        sibling.deploy.save(update_fields=['status', 'updated_at'])
        instance.status = ApplicationStatus.DEPLOYING
        instance.save(update_fields=['status', 'updated_at'])
        ApplicationStackExecutor(str(instance.pk))._reconcile_terminal(instance, ApplicationStackExecutor(str(instance.pk))._load()[1])
        instance.refresh_from_db()
        sibling.deploy.refresh_from_db()
        assert instance.status == ApplicationStatus.FAILED
        assert sibling.deploy.status == DeploymentStatusChoices.CANCELLED
        assert "required application service 'postgres' failed" in sibling.deploy.status_message
        assert sibling.deploy.error_message == ""

    def test_unrelated_integrity_error_is_not_a_name_conflict(self):
        from unittest.mock import patch
        with patch(
            "app_catalog.services.ApplicationInstance.objects.create",
            side_effect=IntegrityError("foreign key failure"),
        ):
            with pytest.raises(IntegrityError):
                create_application_installation(
                    self.user,
                    {
                        "catalog_id": "mattermost",
                        "variant": "postgresql",
                        "name": "integrity-classification",
                        "plan_id": self.app_plan.pk,
                        "config": {
                            "domain": "integrity-classification.example.invalid",
                            "storage_mb": 4096,
                        },
                    },
                )

    def test_catalog_child_service_delete_is_rejected(self):
        instance = self.install(name='protected-child')
        service = instance.services.get(service_key='mattermost').service
        request = APIRequestFactory().delete(f'/services/{service.pk}/')
        force_authenticate(request, user=self.user)
        from services.api.user_services import ServiceViewSet
        response = ServiceViewSet.as_view({'delete': 'destroy'})(request, pk=service.pk)
        assert response.status_code == 409
        assert response.data['code'] == 'catalog_service_managed'
        assert Service.objects.filter(pk=service.pk).exists()

    def test_user_delete_with_catalog_binding_uses_compound_cascade(self):
        user = User.objects.create_user(
            username="catalog-user-compound-delete",
            email="catalog-user-compound-delete@example.invalid",
        )
        common = dict(
            max_cpu=1.0,
            max_ram=512,
            max_storage=10,
            price_per_hour=0,
            storage_type=StorageTypeChoices.SSD,
        )
        plan = Plan.objects.create(
            name=NameChoices.BRONZE,
            platform="docker",
            plan_type=PlanTypeChoices.APP,
            **common,
        )
        from services.models import PrivateNetwork
        network = PrivateNetwork.objects.create(user=user, name="compound-delete-net")
        instance = ApplicationInstance.objects.create(
            user=user,
            name="compound-delete",
            slug="compound-delete",
            catalog_id="mattermost",
            definition_version="1",
            software_version="1",
            variant_id="default",
            definition_snapshot={"_application_orchestration": {"services": [{"key": "app"}]}},
            network=network,
            status=ApplicationStatus.FAILED,
        )
        service = Service.objects.create(
            name="compound-delete-service",
            user=user,
            plan=plan,
            network=network,
            source_kind=Service.SourceKind.CATALOG,
            source_config={"application_instance": str(instance.pk)},
        )
        deploy = __import__("deploy.models", fromlist=["Deploy"]).Deploy.objects.create(
            name="compound-delete-deploy",
            service=service,
            created_by=user,
            version=1.0,
        )
        binding = ApplicationInstanceService.objects.create(
            instance=instance,
            service=service,
            deploy=deploy,
            service_key="app",
        )

        from unittest.mock import patch
        with patch("services.signals._cancel_active_deployments_for_service"), \
             patch("services.signals.Container.exists", return_value=False), \
             patch("services.signals.Image.remove_by_name"), \
             patch("services.signals._cleanup_service_cache_images"), \
             patch("services.signals._cleanup_service_volumes"), \
             patch("services.signals._cleanup_service_log_records"):
            user.delete()

        self.assertFalse(User.objects.filter(pk=user.pk).exists())
        self.assertFalse(Service.objects.filter(pk=service.pk).exists())
        self.assertFalse(__import__("deploy.models", fromlist=["Deploy"]).Deploy.objects.filter(pk=deploy.pk).exists())
        self.assertFalse(ApplicationInstanceService.objects.filter(pk=binding.pk).exists())
        self.assertFalse(ApplicationInstance.objects.filter(pk=instance.pk).exists())
        self.assertFalse(PrivateNetwork.objects.filter(pk=network.pk).exists())

    def test_catalog_child_deploy_delete_is_protected(self):
        instance = self.install(name="protected-deploy")
        binding = instance.services.get(service_key="mattermost")
        with pytest.raises(RestrictedError):
            binding.deploy.delete()

    def test_database_process_keeps_web_name_compatibility(self):
        instance = self.install(name='db-process')
        process = instance.services.get(service_key='postgres').service.processes.get(name='web')
        assert process.process_type == 'database'


    def test_reconcile_routes_active_cancellation_to_runtime_cleanup(self):
        from unittest.mock import patch

        instance = self.install(catalog_id="wordpress", variant="default", name="cancel-route-active")
        instance.status = ApplicationStatus.DEPLOYING
        instance.cancel_requested = True
        instance.stage = "cancellation_requested"
        instance.save(update_fields=["status", "cancel_requested", "stage", "updated_at"])

        with patch.object(ApplicationStackExecutor, "cancel") as cancel,              patch.object(ApplicationStackExecutor, "_cleanup_cancelled_children", return_value=True) as cleanup:
            result = ApplicationStackExecutor(str(instance.pk)).reconcile()

        assert result == []
        cancel.assert_called_once()
        cleanup.assert_called_once_with()

    def test_cancellation_converges_pending_children(self):
        instance = self.install(name="cancel-convergence")
        executor = ApplicationStackExecutor(str(instance.pk))
        executor.cancel(reason="cancelled by test")
        instance.refresh_from_db()
        assert instance.cancel_requested is True
        assert all(
            row.deploy.status == DeploymentStatusChoices.CANCELLED
            for row in instance.services.select_related("deploy")
        )

    def test_cancelled_installation_cleanup_removes_children_and_network(self):
        from unittest.mock import patch

        instance = self.install(name="cancel-cleanup")
        bindings = list(instance.services.select_related("service", "deploy"))
        instance.status = ApplicationStatus.CANCELLED
        instance.cancel_requested = True
        for binding in bindings:
            binding.deploy.status = DeploymentStatusChoices.CANCELLED
            binding.deploy.save(update_fields=["status", "updated_at"])
        instance.save(update_fields=["status", "cancel_requested", "updated_at"])

        network = instance.network
        with patch.object(network, "delete", autospec=True) as network_delete,              patch.object(bindings[0].service, "delete", autospec=True) as first_service_delete,              patch.object(bindings[1].service, "delete", autospec=True) as second_service_delete:
            ApplicationStackExecutor(str(instance.pk))._cleanup_cancelled_children()

        network_delete.assert_called_once()
        first_service_delete.assert_called_once()
        second_service_delete.assert_called_once()
        instance.refresh_from_db()
        assert instance.status == ApplicationStatus.CANCELLED
        assert instance.stage == "cancelled"
        assert instance.network_id is None
        assert not ApplicationInstanceService.objects.filter(instance_id=instance.pk).exists()

    def test_reconcile_cleans_already_cancelled_children(self):
        from unittest.mock import patch

        instance = self.install(name="already-cancelled")
        bindings = list(instance.services.select_related("service", "deploy"))
        instance.status = ApplicationStatus.CANCELLED
        instance.cancel_requested = True
        instance.save(update_fields=["status", "cancel_requested", "updated_at"])
        for binding in bindings:
            binding.deploy.status = DeploymentStatusChoices.CANCELLED
            binding.deploy.save(update_fields=["status", "updated_at"])

        network = instance.network
        with patch.object(network, "delete", autospec=True),              patch.object(bindings[0].service, "delete", autospec=True),              patch.object(bindings[1].service, "delete", autospec=True):
            result = ApplicationStackExecutor(str(instance.pk)).reconcile()

        assert result == []
        instance.refresh_from_db()
        assert instance.network_id is None
        assert not ApplicationInstanceService.objects.filter(instance_id=instance.pk).exists()

    def test_cancelled_installation_keeps_parent_when_network_is_cleaned(self):
        from services.models import PrivateNetwork

        instance = self.install(name="cancel-network-parent")
        network = instance.network
        instance.status = ApplicationStatus.CANCELLED
        instance.cancel_requested = True
        instance.save(update_fields=["status", "cancel_requested", "updated_at"])

        network.delete()
        instance.refresh_from_db()

        assert ApplicationInstance.objects.filter(pk=instance.pk).exists()
        assert instance.network_id is None
        assert not PrivateNetwork.objects.filter(pk=network.pk).exists()


@pytest.mark.skipif(connection.vendor != 'postgresql', reason='Real transaction race requires PostgreSQL row locking.')
class ApplicationInstallationConcurrencyTests(TransactionTestCase):
    def test_same_user_same_slug_has_one_winner_and_no_orphans(self):
        user = User.objects.create_user(username='catalog-race', email='catalog-race@example.invalid')
        common = dict(max_cpu=2.0, max_ram=4096, max_storage=20, price_per_hour=0, storage_type=StorageTypeChoices.SSD)
        plan = Plan.objects.create(name=NameChoices.BRONZE, platform='docker', plan_type=PlanTypeChoices.APP, **common)
        barrier = threading.Barrier(2)
        results, errors = [], []

        def worker():
            close_old_connections()
            try:
                local_user = User.objects.get(pk=user.pk)
                local_plan = Plan.objects.get(pk=plan.pk)
                barrier.wait(timeout=10)
                try:
                    created = create_application_installation(local_user, {'catalog_id': 'mattermost', 'variant': 'postgresql', 'name': 'same-race-name', 'plan_id': local_plan.pk, 'config': {'domain': 'same-race-name.example.invalid', 'storage_mb': 4096}})
                    results.append(str(created.pk))
                except Exception as exc:
                    errors.append(type(exc).__name__)
            finally:
                close_old_connections()

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        assert len(results) == 1
        assert errors.count('ApplicationNameConflict') == 1
        instances = ApplicationInstance.objects.filter(user=user, slug='same-race-name')
        assert instances.count() == 1
        assert instances.get().services.count() == 2

    def test_concurrent_distinct_installations_retry_global_service_name_collision(self):
        user_a = User.objects.create_user(
            username="catalog-service-name-race-a",
            email="catalog-service-name-race-a@example.invalid",
        )
        user_b = User.objects.create_user(
            username="catalog-service-name-race-b",
            email="catalog-service-name-race-b@example.invalid",
        )
        barrier = threading.Barrier(2)
        results, errors = [], []

        common = {
            "catalog_id": "wordpress",
            "variant": "default",
            "plan_id": self.app_plan.pk,
            "config": {},
        }
        shared_prefix = "a" * 24
        payloads = [
            {**common, "name": f"{shared_prefix}-one"},
            {**common, "name": f"{shared_prefix}-two"},
        ]

        def worker(user, payload):
            close_old_connections()
            try:
                local_user = User.objects.get(pk=user.pk)
                local_plan = Plan.objects.get(pk=self.app_plan.pk)
                local_payload = dict(payload)
                local_payload["plan_id"] = local_plan.pk
                barrier.wait(timeout=10)
                instance = create_application_installation(local_user, local_payload)
                results.append((str(local_user.pk), str(instance.pk)))
            except Exception as exc:
                errors.append((type(exc).__name__, str(exc)))
            finally:
                close_old_connections()

        threads = [
            threading.Thread(target=worker, args=(user_a, payloads[0])),
            threading.Thread(target=worker, args=(user_b, payloads[1])),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert not errors, errors
        assert len(results) == 2

        service_names = list(
            Service.objects.filter(
                user_id__in=[user_a.pk, user_b.pk],
                source_kind=Service.SourceKind.CATALOG,
            ).values_list("name", flat=True)
        )
        assert len(service_names) == 4
        assert len(service_names) == len(set(service_names))

