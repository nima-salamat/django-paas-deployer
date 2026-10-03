from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0005_alter_user_is_superuser"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="deletion_requested_at",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                editable=False,
                help_text="Account deletion has been requested and is awaiting runtime convergence.",
                null=True,
            ),
        ),
    ]
