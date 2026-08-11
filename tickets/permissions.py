from rest_framework.permissions import BasePermission


def _ticket_from(obj):
    if obj is None:
        return None
    if hasattr(obj, "department_id") and hasattr(obj, "user_id"):
        return obj  # Ticket-like
    return getattr(obj, "ticket", None)


class IsTicketOwnerOrStaff(BasePermission):
    """
    Object access for ticket-related resources.
    Allows: superuser, ticket owner, assigned staff, department staff.
    Denies: inactive users, plain users who do not own the ticket,
            staff without membership on the ticket department.
    """

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and getattr(u, "is_active", True))

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user or not user.is_authenticated or not getattr(user, "is_active", True):
            return False
        if user.is_superuser:
            return True

        ticket = _ticket_from(obj)
        if ticket is None:
            return False

        if ticket.user_id == user.id:
            return True

        if not user.is_staff:
            return False

        if getattr(ticket, "assigned_to_id", None) and ticket.assigned_to_id == user.id:
            return True

        dept_id = getattr(ticket, "department_id", None)
        if not dept_id:
            return False

        from .models import DepartmentMembership
        return DepartmentMembership.objects.filter(
            user=user, department_id=dept_id
        ).exists()


class IsStaffOrSuperuser(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "is_active", True)
            and (request.user.is_staff or request.user.is_superuser)
        )


class CanManageTicket(BasePermission):
    """Staff management actions — same scope as object access for staff."""

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user or not user.is_authenticated or not getattr(user, "is_active", True):
            return False
        if user.is_superuser:
            return True
        if not user.is_staff:
            return False
        ticket = _ticket_from(obj)
        if ticket is None:
            return False
        if getattr(ticket, "assigned_to_id", None) and ticket.assigned_to_id == user.id:
            return True
        dept_id = getattr(ticket, "department_id", None)
        if not dept_id:
            return False
        from .models import DepartmentMembership
        return DepartmentMembership.objects.filter(
            user=user, department_id=dept_id
        ).exists()
