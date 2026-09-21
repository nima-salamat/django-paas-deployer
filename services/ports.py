"""Published host-port reservation helpers."""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction

from services.models import ServiceEndpoint, ServicePortReservation


def reserve_endpoint_port(endpoint: ServiceEndpoint) -> ServicePortReservation | None:
    """Atomically reserve an endpoint's host TCP/UDP port."""
    if endpoint.published_port is None or not endpoint.enabled:
        ServicePortReservation.objects.filter(endpoint=endpoint).update(
            state=ServicePortReservation.State.RELEASED
        )
        return None

    protocol = str(endpoint.protocol or "tcp").lower()
    if protocol not in {"tcp", "udp"}:
        raise ValidationError("Only TCP and UDP endpoints may publish a host port.")

    with transaction.atomic():
        conflict = (
            ServicePortReservation.objects
            .select_for_update()
            .filter(
                host_port=endpoint.published_port,
                protocol=protocol,
                state=ServicePortReservation.State.ACTIVE,
            )
            .exclude(endpoint=endpoint)
            .select_related("service", "endpoint")
            .first()
        )
        if conflict is not None:
            raise ValidationError(
                f"Host port {endpoint.published_port}/{protocol} is already reserved by service "
                f"{conflict.service.name!r}."
            )

        reservation, _ = ServicePortReservation.objects.update_or_create(
            endpoint=endpoint,
            defaults={
                "service": endpoint.service,
                "host_port": endpoint.published_port,
                "protocol": protocol,
                "state": ServicePortReservation.State.ACTIVE,
            },
        )
        return reservation


def release_endpoint_port(endpoint: ServiceEndpoint) -> None:
    ServicePortReservation.objects.filter(
        endpoint=endpoint,
        state=ServicePortReservation.State.ACTIVE,
    ).update(state=ServicePortReservation.State.RELEASED)


def sync_endpoint_reservation(endpoint: ServiceEndpoint) -> ServicePortReservation | None:
    if endpoint.published_port is None or not endpoint.enabled:
        release_endpoint_port(endpoint)
        return None
    return reserve_endpoint_port(endpoint)
