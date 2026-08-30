from django.db import migrations, models
import django.db.models.deletion
import docs.models
import uuid


def migrate_old_documents(apps, schema_editor):
    Document = apps.get_model("docs", "Document")
    Category = apps.get_model("docs", "DocumentCategory")
    for doc in Document.objects.all():
        section = (getattr(doc, "section", "") or "").strip()
        if section:
            cat, _ = Category.objects.get_or_create(
                name=section,
                parent=None,
                defaults={"slug": section.lower().replace(" ", "-")[:180]},
            )
            doc.category_id = cat.id
        # Legacy block JSON -> a conservative Markdown conversion.
        content = getattr(doc, "content", None)
        if isinstance(content, list):
            lines = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                kind = block.get("type")
                if kind == "heading":
                    level = max(1, min(3, int(block.get("level", 2))))
                    lines.append("#" * level + " " + str(block.get("text", "")))
                elif kind == "paragraph":
                    lines.append(str(block.get("text", "")))
                elif kind == "code":
                    lang = str(block.get("language", "text"))
                    lines.extend([f"```{lang}", str(block.get("code", "")), "```"])
                elif kind == "quote":
                    lines.append("> " + str(block.get("text", "")))
                elif kind == "list":
                    prefix = "1." if block.get("ordered") else "-"
                    for item in block.get("items", []):
                        lines.append(prefix + " " + str(item))
                elif kind == "link":
                    lines.append(f"[{block.get('label') or block.get('url')}]({block.get('url')})")
                elif kind == "divider":
                    lines.append("---")
                elif kind == "callout":
                    lines.append(f"> **{block.get('title') or 'Note'}**")
                    lines.append("> " + str(block.get("text", "")))
            doc.content = "\n\n".join(lines)
        doc.save(update_fields=["category", "content"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("docs", "0001_initial")]
    operations = [
        migrations.CreateModel(
            name="DocumentCategory",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=140)),
                ("slug", models.SlugField(max_length=180, unique=True)),
                ("description", models.CharField(blank=True, default="", max_length=320)),
                ("icon", models.CharField(blank=True, default="folder", max_length=64)),
                ("order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("parent", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="children", to="docs.documentcategory")),
            ],
            options={"ordering": ("order", "name")},
        ),
        migrations.AddConstraint(
            model_name="documentcategory",
            constraint=models.UniqueConstraint(fields=("parent", "name"), name="docs_category_parent_name_uniq"),
        ),
        migrations.AddField(
            model_name="document",
            name="category",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="documents", to="docs.documentcategory"),
        ),
        migrations.AddField(
            model_name="documentasset",
            name="name",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="documentasset",
            name="kind",
            field=models.CharField(choices=[("image", "Image"), ("video", "Video"), ("audio", "Audio"), ("file", "File")], default="file", max_length=16),
        ),
        migrations.AddField(
            model_name="documentasset",
            name="mime_type",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="documentasset",
            name="size_bytes",
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name="documentasset",
            name="document",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assets", to="docs.document"),
        ),
        migrations.RenameField(model_name="documentasset", old_name="image", new_name="file"),
        migrations.AlterField(
            model_name="documentasset",
            name="file",
            field=models.FileField(upload_to=docs.models.document_asset_path),
        ),
        migrations.AlterField(
            model_name="document",
            name="content",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.RunPython(migrate_old_documents, noop_reverse),
        migrations.RemoveField(model_name="document", name="section"),
    ]
