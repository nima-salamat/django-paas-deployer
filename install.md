# PassDeployer Docker Swarm installation

PassDeployer now treats Docker Swarm as the runtime scheduler for application workloads.

The separation is:

\`\`\`
Service
  -> Revision
  -> one Swarm Service per enabled process
  -> one Swarm Task per process (currently replica = 1)
\`\`\`

The project \`Dockerfile\` still builds the application image. Runtime execution is described as a Compose/Stack-shaped specification and applied through the Docker Engine Swarm Service API. The control-plane stack in \`compose.yaml\` is still started with Docker Compose; user workloads are **not** started with \`docker compose up\`.

## 1. Requirements

Install a recent Docker Engine on the machine that will be the Swarm manager and make sure the Docker daemon is reachable by PassDeployer.

Verify:

\`\`\`bash
docker version
docker info
\`\`\`

PassDeployer must connect to a **Swarm manager**, not a worker.

For a multi-node Swarm, nodes must be able to communicate over these default ports:

- TCP 2377: Swarm management/control traffic
- TCP/UDP 7946: node discovery and control
- UDP 4789: overlay/VXLAN data traffic

Keep 4789 reachable only between trusted Swarm nodes.

## 2. Single-node Swarm

A single Docker host is still a real Swarm. This is the recommended starting point if you want PassDeployer to use the Swarm runtime without adding more machines.

Find the manager's stable IP:

\`\`\`bash
ip addr
\`\`\`

Initialize Swarm:

\`\`\`bash
docker swarm init --advertise-addr <MANAGER_IP>
\`\`\`

Verify:

\`\`\`bash
docker info
docker node ls
\`\`\`

You should see one manager with \`Ready\` / \`Active\`.

Do **not** run \`docker swarm init\` again when adding another PassDeployer application. One Swarm can contain many Docker Services.

## 3. Multi-node Swarm

Initialize the manager once:

\`\`\`bash
docker swarm init --advertise-addr <MANAGER_IP>
\`\`\`

On the manager, obtain the worker join command:

\`\`\`bash
docker swarm join-token worker
\`\`\`

Run the displayed command on every worker.

For an additional manager:

\`\`\`bash
docker swarm join-token manager
\`\`\`

Then verify from the manager:

\`\`\`bash
docker node ls
\`\`\`

Example layout:

\`\`\`
Swarm
├── manager-1
├── worker-1
└── worker-2
\`\`\`

PassDeployer does not create a new Swarm per application. All application Services share this Swarm cluster.

## 4. Initialize the Swarm network used by Traefik

The project Compose file defines \`proxy_net\` as an attachable overlay network.

Start the PassDeployer control plane from the manager:

\`\`\`bash
cp .env.example .env
# edit .env
docker compose up -d
\`\`\`

Verify the network:

\`\`\`bash
docker network inspect proxy_net
\`\`\`

It must report:

- driver: \`overlay\`
- attachable: \`true\`

If an older installation already has \`proxy_net\` as a bridge network, **do not deploy applications until it has been migrated**. PassDeployer intentionally rejects a bridge network where a Swarm overlay is required.

A migration normally looks like:

\`\`\`bash
docker compose down
docker network rm proxy_net
docker compose up -d
\`\`\`

Only remove the old network after verifying that no unrelated workload still depends on it.

## 5. Configure the PassDeployer environment

The minimum Swarm settings are:

\`\`\`dotenv
SWARM_ENABLED=1
SWARM_CLUSTER_NAME=default
SWARM_IMAGE_REGISTRY=
SWARM_IMAGE_NAMESPACE=passdeployer
SWARM_LOCAL_VOLUME_PIN=1
\`\`\`

### Single node

A registry is optional because the manager is also the only scheduler node:

\`\`\`dotenv
SWARM_IMAGE_REGISTRY=
\`\`\`

### Multi node

Configure a registry that every Swarm node can pull from:

\`\`\`dotenv
SWARM_IMAGE_REGISTRY=registry.example.com
SWARM_IMAGE_NAMESPACE=passdeployer
\`\`\`

Authenticate on the manager or provide the optional PassDeployer registry credentials:

\`\`\`dotenv
SWARM_IMAGE_REGISTRY_USERNAME=
SWARM_IMAGE_REGISTRY_PASSWORD=
\`\`\`

The deployment worker builds the image on the manager and publishes it to the registry before Swarm schedules the task. Without a registry, a multi-node deployment is rejected instead of creating a task that cannot pull its image.

## 6. Docker socket / remote manager

PassDeployer and Traefik currently use the Docker Engine socket:

\`\`\`
/var/run/docker.sock
\`\`\`

The control-plane containers in \`compose.yaml\` already mount this socket.

If PassDeployer is moved to another host, configure the Docker SDK connection explicitly with the normal Docker environment variables, for example:

\`\`\`dotenv
DOCKER_HOST=unix:///var/run/docker.sock
\`\`\`

For a remote Docker Engine, use a properly secured TLS or SSH Docker endpoint. Do not expose an unauthenticated Docker TCP socket.

## 7. Traefik and Swarm routing

The bundled Traefik configuration enables both:

- the normal Docker provider for the PassDeployer control-plane containers
- the Docker Swarm provider for application Swarm Services

The Swarm provider watches **service labels**, not task/container labels.

PassDeployer therefore generates routing labels on the Swarm Service itself, including the explicit internal target port.

The intended traffic path for this installation is:

\`\`\`
Internet
  -> host Nginx / TLS
  -> 127.0.0.1:8021
  -> Traefik
  -> proxy_net (overlay)
  -> application Swarm Service
  -> Swarm Task
\`\`\`

Public HTTPS is normally terminated by the host Nginx. Traefik receives HTTP on its internal \`web\` entrypoint.

## 8. One PassDeployer Service

You do **not** create a dedicated Swarm for the application.

Create/deploy the PassDeployer Service normally from the application API or admin.

For a simple application with only \`web\`, the runtime becomes:

\`\`\`
PassDeployer Service: my-app
        |
        +--> Docker Swarm Service: <service-name>
                    |
                    +--> 1 Task
\`\`\`

Useful inspection commands:

\`\`\`bash
docker service ls
docker service ps <service-name>
docker service inspect <service-name>
docker service logs <service-name>
\`\`\`

## 9. A Service with web + worker + scheduler

A PassDeployer Service may contain several \`ServiceProcess\` definitions.

Example:

\`\`\`
PassDeployer Service
├── web
├── worker
└── scheduler
\`\`\`

The runtime becomes:

\`\`\`
Docker Swarm
├── <service>-web
├── <service>-worker
└── <service>-scheduler
\`\`\`

Every process currently runs with exactly **one replica**.

There is deliberately no general scale API yet. Replica counts other than 1 are rejected during revision/runtime compilation.

Stopping the application is different: the existing Docker Swarm Service objects can be scaled to zero as part of the declarative stopped state.

## 19. Database services

Database plans (PostgreSQL, MySQL, MariaDB, MongoDB, Redis and Oracle) also run as Docker Swarm Services.

The database deployment layer keeps engine-specific initialization and credential reconciliation, but it no longer creates a standalone Docker container. The runtime path is:

```text
Database Service
  -> ServiceRevision
  -> Swarm Service
  -> Swarm Task
  -> persistent volume
```

For MySQL/MariaDB, PassDeployer waits for the actual Swarm task to become reachable before reconciling root/application credentials. On multi-node Swarm, database Services with local persistent volumes are pinned to the node that owns the local Docker volume.

The force_reinit rebuild option removes and recreates the managed data volumes before the database Service is updated. Treat this as a destructive operation.

## 11. Volumes on multiple nodes

Docker's default local volume driver is node-local.

That means this:

\`\`\`
worker-1 -> /var/lib/docker/volumes/my-data
worker-2 -> /var/lib/docker/volumes/my-data
\`\`\`

does **not** mean the same storage.

PassDeployer therefore defaults:

\`\`\`dotenv
SWARM_LOCAL_VOLUME_PIN=1
\`\`\`

On a multi-node Swarm, services using local Docker volumes are pinned to the manager node that performed the deployment unless an explicit node-id constraint already exists.

This preserves correctness, but it is not shared-storage HA.

For true multi-node storage, add a shared Docker volume driver and move those services to an explicit storage/placement policy later.

## 11. Node management from Wagtail

Open the Wagtail control panel and use:

- Docker Swarm clusters
- Docker Swarm nodes

The node list is synchronized from the live Docker manager.

For each node, Wagtail exposes declarative operator settings for:

- desired availability: \`active\`, \`pause\`, \`drain\`
- desired node labels

Observed fields include:

- Docker node ID
- hostname
- manager/worker role
- current availability
- current state
- node address
- labels
- CPU count
- memory
- sync timestamp/errors

Node changes are reconciled by the background infrastructure sync. This means the Wagtail database stores the desired operator state and Docker is the observed runtime.

Example label:

\`\`\`
storage=ssd
\`\`\`

After the label is synchronized, future placement policies can target it with a constraint such as:

\`\`\`
node.labels.storage == ssd
\`\`\`

Do not edit the Docker node role (manager/worker) from the current UI. Promotion/demotion is deliberately kept as an explicit cluster-topology operation instead of a casual form edit.

## 12. Interactive shell on multi-node Swarm

The application shell is intentionally conservative in multi-node mode.

The Docker Swarm manager can inspect a Service and its Tasks, but `docker exec` operates against a container on the Docker Engine that owns that container. PassDeployer therefore allows the current shell implementation to exec into a task only when that task is running on the connected Docker node.

When the task is scheduled on another node, the shell returns a clear "connected Docker node" error instead of pretending the manager can execute on a remote container.

Application logs and runtime state remain available from the Swarm manager.

A future multi-node shell transport can connect directly to the task's node using a secured Docker SSH/TLS endpoint.

## 13. Multiple PassDeployer Services

One Swarm can run many independent PassDeployer Services:

\`\`\`
Swarm
├── app-a-web
├── app-a-worker
├── app-b-web
├── app-c-web
└── app-c-scheduler
\`\`\`

Each deployment remains isolated by its own Docker Service names, labels, network attachments, revision, and deployment history.

You should **not**:

- initialize a new Swarm for every application
- use \`docker compose up\` for the application runtime
- manually create the application's Docker Service before deploying through PassDeployer

PassDeployer creates/updates the runtime Swarm Services from the active ServiceRevision.

## 14. Updating a node

To temporarily stop scheduling new tasks on a node:

\`\`\`bash
docker node update --availability drain <NODE>
\`\`\`

To restore it:

\`\`\`bash
docker node update --availability active <NODE>
\`\`\`

The same desired availability can be managed from Wagtail.

After making an infrastructure change, check:

\`\`\`bash
docker node ls
docker service ls
docker service ps <service-name>
\`\`\`

## 15. Updating application code

The normal PassDeployer deployment flow remains:

\`\`\`
source
  -> platform detection
  -> Dockerfile/image build
  -> immutable image
  -> ServiceRevision
  -> Compose/Stack-shaped runtime specification
  -> Docker Swarm Service update
  -> Swarm Task
\`\`\`

Swarm owns restart/scheduling/task replacement. PassDeployer owns the desired Service/Revision model and deployment operation history.

## 16. Rollout behavior

Application Swarm Services are created with conservative update/rollback settings:

- one task updated at a time
- start-first update ordering where possible
- automatic rollback on failed service updates
- rollback monitoring enabled

The platform still records the deployment as a PassDeployer operation so API/admin history remains independent from Swarm's task history.

## 17. Troubleshooting checklist

### Swarm is not active

\`\`\`bash
docker info | grep -A10 -i swarm
docker node ls
\`\`\`

PassDeployer requires an active manager.

### A worker cannot start the new task

Check:

\`\`\`bash
docker service ps <service-name> --no-trunc
\`\`\`

Common multi-node causes:

- missing registry configuration
- worker cannot authenticate to the registry
- required volume exists only on another node
- node is \`Drain\` or \`Pause\`
- placement constraints match no nodes
- node firewall blocks Swarm traffic

### Traefik does not see the application

Check:

\`\`\`bash
docker service inspect <service-name>
docker network inspect proxy_net
docker logs deploy-traefik
\`\`\`

The application service must be attached to \`proxy_net\`, and the generated service labels must include the explicit load-balancer target port.

### An old installation has a bridge proxy network

PassDeployer intentionally fails rather than silently mixing bridge and Swarm networking. Migrate the network to an attachable overlay before deploying application workloads.

## 18. Useful verification commands

Manager:

\`\`\`bash
docker info
docker node ls
docker network ls
docker service ls
\`\`\`

One application:

\`\`\`bash
docker service inspect <service-name>
docker service ps <service-name> --no-trunc
docker service logs <service-name> --tail 200
\`\`\`

Node:

\`\`\`bash
docker node inspect <NODE>
\`\`\`

Registry:

\`\`\`bash
docker login <REGISTRY>
docker pull <REGISTRY>/<NAMESPACE>/<IMAGE>:<TAG>
\`\`\`

## 19. Architecture invariant

Do not bypass the runtime abstraction by creating application containers manually.

The intended runtime is:

\`\`\`
PassDeployer Service
       |
       v
ServiceRevision
       |
       v
Compose/Stack specification
       |
       v
Docker Swarm Service
       |
       v
Docker Task / container
\`\`\`

The container/task is an implementation detail of the Swarm Service, not the primary runtime object managed by PassDeployer.

## References

- Docker Swarm initialization: https://docs.docker.com/reference/cli/docker/swarm/init/
- Docker Swarm tutorial: https://docs.docker.com/engine/swarm/swarm-tutorial/
- Docker Swarm networking: https://docs.docker.com/engine/swarm/networking/
- Docker SDK for Python nodes: https://docker-py.readthedocs.io/en/7.1.0/nodes.html
- Docker SDK for Python services: https://docker-py.readthedocs.io/en/7.1.0/services.html
- Traefik Docker Swarm provider: https://doc.traefik.io/traefik/reference/install-configuration/providers/swarm/
