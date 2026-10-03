"""Reusable Django admin policies for the full project model surface."""

from django.contrib import admin


class ProjectModelAdmin(admin.ModelAdmin):
    list_per_page = 50
    save_on_top = True

    def _scalar_fields(self):
        return [
            field.name
            for field in self.model._meta.concrete_fields
            if not getattr(field, "auto_created", False)
        ]

    def get_list_display(self, request):
        fields = []
        for name in self._scalar_fields():
            field = self.model._meta.get_field(name)
            if getattr(field, "primary_key", False):
                fields.append(name)
                continue
            if len(fields) < 7 and (
                getattr(field, "choices", None)
                or field.get_internal_type() in {
                    "CharField", "TextField", "EmailField", "BooleanField",
                    "DateField", "DateTimeField", "IntegerField",
                    "PositiveIntegerField", "PositiveSmallIntegerField",
                    "DecimalField", "UUIDField",
                }
            ):
                fields.append(name)
        return tuple(fields[:8]) or ("__str__",)

    def get_search_fields(self, request):
        out = []
        for field in self.model._meta.concrete_fields:
            internal = field.get_internal_type()
            if internal in {"CharField", "TextField", "EmailField", "UUIDField"}:
                out.append(field.name)
            if len(out) >= 6:
                break
        return tuple(out)

    def get_list_filter(self, request):
        out = []
        for field in self.model._meta.concrete_fields:
            if getattr(field, "choices", None) or field.get_internal_type() == "BooleanField":
                out.append(field.name)
            if len(out) >= 6:
                break
        return tuple(out)

    def get_raw_id_fields(self, request):
        return tuple(
            field.name
            for field in self.model._meta.concrete_fields
            if field.is_relation and not field.many_to_many
        )


class ReadOnlyProjectModelAdmin(ProjectModelAdmin):
    """Full visibility without mutating operational/audit/secret state."""

    def get_readonly_fields(self, request, obj=None):
        return tuple(
            field.name
            for field in self.model._meta.concrete_fields
            if not getattr(field, "auto_created", False)
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class SensitiveReadOnlyAdmin(ReadOnlyProjectModelAdmin):
    """Read-only row with sensitive payload fields hidden from admin forms."""

    def get_exclude(self, request, obj=None):
        names = {
            "password", "password_ciphertext", "ciphertext", "token_hash",
            "credential_hash", "secret_config",
        }
        return tuple(
            field.name for field in self.model._meta.concrete_fields
            if field.name in names
        )


class AuditReadOnlyAdmin(ReadOnlyProjectModelAdmin):
    """Audit/history projection: inspectable, never hand-edited/deleted."""

    date_hierarchy = None
