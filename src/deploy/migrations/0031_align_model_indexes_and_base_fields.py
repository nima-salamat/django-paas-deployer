from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("deploy", "0030_deploylog_projection_delete_behavior"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="deploymenteventoutbox",
            old_name="deploy_event_dispatched_idx",
            new_name="deploy_depl_dispatc_2c4e43_idx",
        ),
        migrations.RenameIndex(
            model_name="deploymenteventoutbox",
            old_name="deploy_event_deployment_idx",
            new_name="deploy_depl_deploym_380166_idx",
        ),
        migrations.RenameIndex(
            model_name="deploymentresource",
            old_name="deploy_resource_deployment_state_idx",
            new_name="deploy_depl_deploym_655a99_idx",
        ),
        migrations.RenameIndex(
            model_name="deploymentresource",
            old_name="deploy_resource_kind_name_idx",
            new_name="deploy_depl_kind_2de8d1_idx",
        ),
        migrations.AlterField(
            model_name="deploymenteventoutbox",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, verbose_name="Created At"),
        ),
        migrations.AlterField(
            model_name="deploymenteventoutbox",
            name="id",
            field=models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, verbose_name="ID"),
        ),
        migrations.AlterField(
            model_name="deploymenteventoutbox",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, verbose_name="Updated At"),
        ),
        migrations.AlterField(
            model_name="deploymentresource",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, verbose_name="Created At"),
        ),
        migrations.AlterField(
            model_name="deploymentresource",
            name="id",
            field=models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, verbose_name="ID"),
        ),
        migrations.AlterField(
            model_name="deploymentresource",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, verbose_name="Updated At"),
        ),
    ]
