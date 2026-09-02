from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils.html import format_html

from .models import Document, DocumentAsset, DocumentCategory


class OrderedModelAdminMixin:
    """Shared ordering tools for the docs tree models.

    Adds:
      * ▲/▼ per-row buttons that swap an item with its neighbor and rewrite
        the whole sibling sequence as 10, 20, 30 … (legacy order=0 ties are
        normalized away on every move),
      * an "order" column editable inline in the changelist,
      * a bulk "Renumber" action for the affected sections,
      * new items appended at the end of their section automatically.

    Concrete admins must set:
      * sibling_field — the FK that scopes a sibling group
        ("parent" for categories, "category" for documents),
      * sibling_ordering — fallback tie-break fields that exist on the model
        (e.g. ("order", "title", "pk")),
      * move_url_name — the URL name registered in get_urls (e.g.
        "docs_document_move"); reverse() uses the namespaced
        "admin:<move_url_name>" form.
    """

    sibling_field = None
    sibling_ordering = None
    move_url_name = None

    # ---- changelist presentation ----------------------------------------
    @admin.display(description="Move")
    def move_up_down(self, obj):
        up_url = reverse(f"admin:{self.move_url_name}", args=[obj.pk, "up"])
        down_url = reverse(f"admin:{self.move_url_name}", args=[obj.pk, "down"])
        return format_html(
            '<a class="button" href="{}" style="padding:2px 7px;" title="Move up">&#9650;</a> '
            '<a class="button" href="{}" style="padding:2px 7px;" title="Move down">&#9660;</a>',
            up_url,
            down_url,
        )

    # ---- move view (custom URL, registered by concrete get_urls) --------
    def _sibling_filter(self, obj):
        return {self.sibling_field: getattr(obj, self.sibling_field)}

    def _siblings_of(self, obj):
        return list(
            self.model.objects.filter(**self._sibling_filter(obj)).order_by(
                *self.sibling_ordering
            )
        )

    def move_view(self, request, pk, direction):
        """Swap the item with its adjacent sibling and renumber the group."""
        if not self.has_change_permission(request):
            raise PermissionDenied
        obj = get_object_or_404(self.model, pk=pk)
        siblings = self._siblings_of(obj)
        ids = [item.pk for item in siblings]
        try:
            index = ids.index(obj.pk)
        except ValueError:
            ids = [obj.pk]
            index = 0
        target = index - 1 if direction == "up" else index + 1
        if 0 <= target < len(ids):
            ids[index], ids[target] = ids[target], ids[index]
            with transaction.atomic():
                for position, item_id in enumerate(ids):
                    self.model.objects.filter(pk=item_id).update(order=(position + 1) * 10)
            self.message_user(request, f"“{obj}” moved {direction}.")
        else:
            edge = "top" if direction == "up" else "bottom"
            self.message_user(request, f"“{obj}” is already at the {edge} of its group.")
        return redirect(
            f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist"
        )

    # ---- bulk action ------------------------------------------------------
    @admin.action(description="Renumber order values (10, 20, 30 …) in the affected sections")
    def renumber_orders(self, request, queryset):
        scopes = set()
        for obj in queryset:
            scopes.add(getattr(obj, f"{self.sibling_field}_id"))
        updated = 0
        with transaction.atomic():
            for scope in scopes:
                items = list(
                    self.model.objects.filter(**{f"{self.sibling_field}_id": scope}).order_by(
                        *self.sibling_ordering
                    )
                )
                for position, item in enumerate(items):
                    new_order = (position + 1) * 10
                    if item.order != new_order:
                        self.model.objects.filter(pk=item.pk).update(order=new_order)
                        updated += 1
        self.message_user(request, f"Renumbered {updated} row(s).")

    # NOTE: no save_model override — Document.save / DocumentCategory.save
    # already append new rows at the end of their sibling group, which keeps
    # the DRF viewsets, the Django admin and direct ORM creates consistent.


@admin.register(DocumentCategory)
class DocumentCategoryAdmin(OrderedModelAdminMixin, admin.ModelAdmin):
    sibling_field = "parent"
    sibling_ordering = ("order", "name", "pk")
    move_url_name = "docs_documentcategory_move"

    list_display = ("name", "parent", "order", "move_up_down", "updated_at")
    list_editable = ("order",)
    list_display_links = ("name",)
    search_fields = ("name", "slug", "description")
    list_filter = ("parent",)
    prepopulated_fields = {"slug": ("name",)}
    actions = ["renumber_orders"]
    # Root categories first (parents before children by their own order),
    # then siblings by order — mirrors the tree the public docs page shows.
    ordering = ("parent__order", "parent__name", "order", "name")

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "move/<uuid:pk>/<str:direction>/",
                self.admin_site.admin_view(self.move_view),
                name=self.move_url_name,
            ),
        ]
        return custom + urls


@admin.register(Document)
class DocumentAdmin(OrderedModelAdminMixin, admin.ModelAdmin):
    sibling_field = "category"
    sibling_ordering = ("order", "title", "pk")
    move_url_name = "docs_document_move"

    list_display = ("title", "category", "status", "order", "move_up_down", "updated_at")
    list_editable = ("order",)
    list_display_links = ("title",)
    search_fields = ("title", "slug", "description")
    list_filter = ("status", "category")
    prepopulated_fields = {"slug": ("title",)}
    actions = ["renumber_orders"]
    # Grouped by section (sections themselves in their own order), then by
    # the article order inside each section — the exact sequence visitors
    # see in the docs sidebar.
    ordering = ("category__order", "category__name", "order", "title")

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "move/<uuid:pk>/<str:direction>/",
                self.admin_site.admin_view(self.move_view),
                name=self.move_url_name,
            ),
        ]
        return custom + urls

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "category":
            kwargs["queryset"] = DocumentCategory.objects.order_by(
                "parent__order", "parent__name", "order", "name"
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(DocumentAsset)
class DocumentAssetAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "document", "size_bytes", "created_at")
    search_fields = ("name", "alt", "mime_type")
    list_filter = ("kind",)
