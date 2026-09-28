# deploy contracts and tests

The deploy app's small local test module is supplemented by the much larger deployments contract suite.

| Test/contract family | Protected behavior |
|---|---|
| src/deploy/tests.py | deployment API/model compatibility behavior |
| deployments/test_deployment_ownership.py | exactly one active worker owner |
| deployments/test_activation_consistency.py | current Service release cannot be overwritten by stale execution |
| deployments/test_base_image_* | shared base-image cache/build/lease correctness |
| deployments/test_deploy_service_* | DeployService integration/regression paths |
| deployments/test_security.py | tenant configuration and runtime security boundaries |

Do not use deploy model tests alone to validate runtime changes; runtime ownership is in deployments.
