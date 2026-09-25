from django.db import migrations, models
import django.db.models.deletion
import docs.models
import uuid

class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="Document",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=180)),
                ("slug", models.SlugField(max_length=220, unique=True)),
                ("description", models.CharField(blank=True, default="", max_length=320)),
                ("section", models.CharField(blank=True, default="Documentation", max_length=100)),
                ("icon", models.CharField(blank=True, default="description", max_length=64)),
                ("order", models.PositiveIntegerField(default=0)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("published", "Published")], default="draft", max_length=16)),
                ("content", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={"ordering": ("section", "order", "title")},
        ),
        migrations.CreateModel(
            name="DocumentAsset",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("image", models.ImageField(upload_to=docs.models.document_asset_path)),
                ("alt", models.CharField(blank=True, default="", max_length=240)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("document", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="assets", to="docs.document")),
            ],
        ),
    ]
