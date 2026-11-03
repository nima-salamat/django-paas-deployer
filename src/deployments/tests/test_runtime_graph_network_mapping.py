"""Regression tests for immutable runtime graph reconstruction."""

from types import SimpleNamespace

from deployments.core.runtime_graph import ServiceRuntimeGraph


def test_from_revision_normalizes_mapping_and_legacy_string_networks():
    revision = SimpleNamespace(
        pk="revision-network-mapping",
        config_snapshot={},
        build_snapshot={},
        runtime_snapshot={},
        source_snapshot={},
        process_snapshot=[],
        endpoint_snapshot=[],
        environment_snapshot={},
        volume_snapshot=[],
        network_snapshot=[
            {
                "name": "private-net",
                "driver": "overlay",
                "aliases": ["api"],
            },
            "legacy-net",
        ],
    )

    graph = ServiceRuntimeGraph.from_revision(revision)

    assert graph.networks == (
        {
            "name": "private-net",
            "driver": "overlay",
            "aliases": ["api"],
        },
        {"name": "legacy-net"},
    )
