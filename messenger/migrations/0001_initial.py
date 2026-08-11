# Generated placeholder — run makemigrations in real env
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid
import messenger.models

class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        # Models are defined in models.py — run:
        #   python manage.py makemigrations messenger
        #   python manage.py migrate
        # This placeholder exists so the app can be discovered.
        migrations.CreateModel(
            name="Conversation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True)),
                ("type", models.CharField(choices=[("private", "Private"), ("group", "Group")], db_index=True, default="private", max_length=10)),
                ("title", models.CharField(blank=True, default="", max_length=255)),
                ("description", models.TextField(blank=True, default="")),
                ("avatar", models.ImageField(blank=True, null=True, upload_to="messenger/groups/")),
                ("is_public", models.BooleanField(db_index=True, default=False)),
                ("is_closed", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("last_message_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_conversations", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-last_message_at", "-created_at"]},
        ),
    ]
