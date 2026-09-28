# deployments models

The deployments app package does not define a meaningful Django model/domain schema of its own on the current branch.

Its architecture is implemented through application services, planning/runtime contracts, Celery tasks and adapters under src/deployments/. Persistent domain records remain in services and deploy.

For model ownership, read:
- ../services/models.md for Service/Revision desired/executable state.
- ../deploy/models.md for Deploy/provenance/base-image/Swarm metadata.

Do not create a second deployments database model merely to represent runtime state already observed from Docker/Swarm.
