# deployments/core/platforms

## Responsibility
Framework/runtime detection and platform-specific build/runtime resolution.

PlatformRegistry inspects a source tree, runs plugin detection, selects the best platform, and resolves ProjectConfig.

Current plugin families are Python, Node, PHP, Go, static and generic.

## Plugin contract
Plugins detect a project and resolve safe platform configuration. They do not create Docker containers, update Service database state or activate revisions.

## Public API
No HTTP endpoints. PlatformRegistry is an internal Python API.
