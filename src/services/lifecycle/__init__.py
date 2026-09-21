"""Service lifecycle fencing and authoritative activation helpers.

Invariants
----------
* ``Service.active_revision`` is the sole runtime activation authority.
* ``Service.selected_deploy`` is a compatibility projection derived from the
  active revision when possible; it must not drive cancel/recover/delete decisions.
* ``Service.lifecycle_generation`` is a monotonic fence. Workers capture it at
  the start of a lifecycle operation and may only apply side effects when the
  generation is unchanged (compare-and-set).
"""

from .authority import (
    get_authoritative_deploy,
    get_authoritative_revision,
    project_selected_deploy_from_revision,
    sync_selected_deploy_projection,
)
from .fencing import (
    assert_generation,
    bump_lifecycle,
    capture_generation,
    cas_desired_state,
    is_deleted_generation,
    mark_deleted,
)

__all__ = [
    "get_authoritative_deploy",
    "get_authoritative_revision",
    "project_selected_deploy_from_revision",
    "sync_selected_deploy_projection",
    "assert_generation",
    "bump_lifecycle",
    "capture_generation",
    "cas_desired_state",
    "is_deleted_generation",
    "mark_deleted",
]
