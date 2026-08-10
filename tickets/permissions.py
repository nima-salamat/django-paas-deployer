from rest_framework.permissions import BasePermission


class IsTicketOwnerOrStaff(BasePermission):
    """Owner of the ticket, any staff, or superuser."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser or user.is_staff:
            return True
        ticket = obj if hasattr(obj, "department_id") else getattr(obj, "ticket", None)
        if ticket is None:
            return False
        return ticket.user_id == user.id


class IsStaffOrSuperuser(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_staff or request.user.is_superuser)
        )


class CanManageTicket(BasePermission):
    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser:
            return True
        if not user.is_staff:
            return False
        # Staff can manage any ticket they can see; dept isolation is list-level only
        return True
