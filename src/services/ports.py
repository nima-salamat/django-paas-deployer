"""Published host-port reservation helpers."""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
import socket

from services.models import ServiceEndpoint, ServicePortReservation


def _host_port_is_available(host_port: int, protocol: str) -> bool:
    """Best-effort host-level availability check.

    The database reservation prevents PassDeployer-level collisions, while
    this socket probe also catches ports already occupied by unmanaged host
    processes or Docker resources outside the control plane.
    """
    sock_type = socket.SOCK_DGRAM if protocol == "udp" else socket.SOCK_STREAM
    sock = socket.socket(socket.AF_INET, sock_type)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", int(host_port)))
        return True
    except OSError:
        return False
    finally:
        sock.close()


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

        current = ServicePortReservation.objects.filter(endpoint=endpoint).first()
        same_port = (
            current is not None
            and current.state == ServicePortReservation.State.ACTIVE
            and int(current.host_port) == int(endpoint.published_port)
            and str(current.protocol).lower() == protocol
        )
        if not same_port and not _host_port_is_available(int(endpoint.published_port), protocol):
            raise ValidationError(
                f"Host port {endpoint.published_port}/{protocol} is already in use outside PassDeployer."
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
