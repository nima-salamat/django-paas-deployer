from rest_framework.permissions import BasePermission

class IsTicketOwnerOrStaff(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser:
            return True
        ticket = obj if hasattr(obj, "department_id") else getattr(obj, "ticket", None)
        if ticket is None:
            return False
        if ticket.user_id == user.id:
            return True
        if not user.is_staff:
            return False
        from .models import DepartmentMembership
        return DepartmentMembership.objects.filter(user=user, department_id=ticket.department_id).exists()

class IsStaffOrSuperuser(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser))

class CanManageTicket(BasePermission):
    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser:
            return True
        if not user.is_staff:
            return False
        from .models import DepartmentMembership
        return DepartmentMembership.objects.filter(user=user, department_id=obj.department_id).exists()
