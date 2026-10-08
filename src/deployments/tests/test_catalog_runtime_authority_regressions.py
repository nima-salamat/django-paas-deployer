from types import SimpleNamespace

from deployments.core.runtime_graph import ServiceRuntimeGraph
from services.revisioning import _catalog_revision_requires_refresh


WORDPRESS_DOCKERFILE = """FROM wordpress:7.1.2-php8.4-apache
ENTRYPOINT ["/usr/local/bin/docker-ensure-installed.sh"]
CMD ["/usr/local/bin/passdeployer-wordpress-entrypoint.sh", "/usr/local/bin/apache2-foreground"]
"""


def test_catalog_image_cmd_replaces_stale_shell_wrapped_process_command():
    stale_command = (
        "/bin/sh -lc /usr/local/bin/passdeployer-wordpress-entrypoint.sh "
        "apache2-foreground"
    )
    revision = SimpleNamespace(
        pk="revision-wordpress-stale-command",
        revision_number=12,
        config_snapshot={"source_kind": "catalog", "catalog_managed": True},
        source_snapshot={"catalog_id": "wordpress", "definition_version": "1.3"},
        build_snapshot={
            "dockerfile": WORDPRESS_DOCKERFILE,
            "files": {
                "passdeployer-wordpress-entrypoint.sh": "#!/bin/sh\nset -eu\n"
            },
        },
        runtime_snapshot={
            "catalog_managed": True,
            "start_command": stale_command,
            "entry_point": "/bin/sh -lc",
        },
        process_snapshot=[{
            "name": "web",
            "process_type": "web",
            "command": stale_command,
            "entrypoint": "/bin/sh -lc",
            "replicas": 1,
            "enabled": True,
        }],
        environment_snapshot={},
        endpoint_snapshot=[],
        volume_snapshot=[],
        network_snapshot=[],
    )

    graph = ServiceRuntimeGraph.from_revision(revision)

    assert graph.processes[0].command == (
        "/usr/local/bin/passdeployer-wordpress-entrypoint.sh "
        "/usr/local/bin/apache2-foreground"
    )
    assert graph.processes[0].entrypoint is None
    assert graph.execution_contract is not None
    assert graph.execution_contract.entrypoint_source == "IMAGE"
    assert graph.execution_contract.command is None
    assert graph.execution_contract.args == (
        "/usr/local/bin/passdeployer-wordpress-entrypoint.sh",
        "/usr/local/bin/apache2-foreground",
    )


def test_catalog_revision_refresh_checks_dockerfile_even_if_current_files_are_empty():
    service = SimpleNamespace(
        source_kind="catalog",
        build_config={
            "dockerfile": WORDPRESS_DOCKERFILE,
            "files": {},
        },
    )
    revision = SimpleNamespace(
        config_snapshot={"source_kind": "catalog"},
        build_snapshot={
            "dockerfile": (
                "FROM wordpress:7.1.2-php8.4-apache\n"
                'ENTRYPOINT ["docker-entrypoint.sh"]\n'
                'CMD ["apache2-foreground"]\n'
            ),
            "files": {},
        },
    )

    assert _catalog_revision_requires_refresh(service, revision) is True
