from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("app_catalog", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="applicationinstance",
            name="stage",
            field=models.CharField(default="pending", max_length=64),
        ),
        migrations.AddField(
            model_name="applicationinstance",
            name="execution_task_id",
            field=models.CharField(blank=True, db_index=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="applicationinstance",
            name="started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="applicationinstance",
            name="execution_deadline",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="applicationinstance",
            name="cancel_requested",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="applicationinstanceservice",
            name="dispatch_task_id",
            field=models.CharField(blank=True, db_index=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="applicationinstanceservice",
            name="dispatched_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
