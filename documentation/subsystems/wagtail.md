# Wagtail Administration

## Service administration

Wagtail exposes safe metadata editing. Runtime source-of-truth fields such as active revision and lifecycle state are controlled by service workflows rather than arbitrary forms.

## Swarm infrastructure

`SwarmCluster` and `SwarmNode` provide operator views.

Node desired state includes:

- availability: active / pause / drain
- desired labels

Observed fields are synchronized from Docker.

## Permissions

Infrastructure forms avoid arbitrary node add/delete and manager/worker role mutation. Promotion/demotion remains an explicit cluster operation.

## Reconciliation

A periodic Celery task reads Docker node state and applies Wagtail desired availability/labels.
