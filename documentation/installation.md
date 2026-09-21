# Installation

## Requirements

- Docker Engine with an active Swarm manager.
- PostgreSQL.
- Redis.
- Docker access for the control-plane workers.
- An image registry for multi-node application workloads.

Swarm nodes normally require TCP 2377, TCP/UDP 7946 and UDP 4789 between trusted nodes.

## Single-node

Initialize the manager once:

```bash
docker swarm init --advertise-addr <MANAGER_IP>
docker node ls
```

A single host is still a Swarm. Applications share this cluster.

## Multi-node

On the manager:

```bash
docker swarm init --advertise-addr <MANAGER_IP>
docker swarm join-token worker
docker swarm join-token manager
```

Run the generated join commands on the other machines and verify them with `docker node ls`.

## Control plane

```bash
cp .env.example .env
# configure SECRET_KEY, database, Redis, domains and Swarm settings
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

## Swarm environment

Single node can omit a registry:

```dotenv
SWARM_ENABLED=1
SWARM_CLUSTER_NAME=default
SWARM_IMAGE_REGISTRY=
SWARM_IMAGE_NAMESPACE=passdeployer
SWARM_LOCAL_VOLUME_PIN=1
```

Multi-node requires a registry reachable by all workers:

```dotenv
SWARM_ENABLED=1
SWARM_CLUSTER_NAME=default
SWARM_IMAGE_REGISTRY=registry.example.com
SWARM_IMAGE_NAMESPACE=passdeployer
SWARM_LOCAL_VOLUME_PIN=1
```

## Proxy network and Traefik

`proxy_net` must be an attachable overlay network. Application services with public HTTP-family endpoints join this network and receive Traefik Swarm-provider labels.

## Wagtail

Swarm clusters and nodes are exposed in Wagtail. Desired availability can be active, pause or drain. Desired labels are also managed there. Manager/worker promotion is kept as an explicit infrastructure operation.

## Shell

Interactive shell can only exec into a task on the Docker Engine node connected to PassDeployer. A remote-node shell transport is intentionally not faked.

## Volumes

Local volumes are node-local. With `SWARM_LOCAL_VOLUME_PIN=1`, services using them are pinned to the volume owner unless an explicit node-id placement rule already exists.

## Legacy mode

`SWARM_ENABLED=0` enables the explicit compatibility runtime. Its container-event consumer is profile-gated:

```bash
docker compose --profile legacy-runtime up -d deployment-events
```

## Verification

```bash
docker info
docker node ls
docker network ls
docker service ls
docker service ps <service> --no-trunc
docker service inspect <service>
docker service logs <service> --tail 200
```

Database `force_reinit` can remove managed data volumes and is destructive.
