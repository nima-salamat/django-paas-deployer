# app_catalog state and choice contracts

ApplicationStatus is pending, deploying, running, failed or cancelled.

Coordinator transitions are task-driven. Child Service/Deploy lifecycle is separate. A coordinator stuck in deploying does not mean every child Deploy is still running; inspect ApplicationInstanceService and child Deploy state.

definition_snapshot/config/secret_config are provenance/configuration data, not runtime observation.
