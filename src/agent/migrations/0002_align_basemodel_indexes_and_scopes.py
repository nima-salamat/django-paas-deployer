from uuid import uuid4

from django.db import migrations, models

from agent.scopes import default_agent_scopes


class Migration(migrations.Migration):
    dependencies = [
        ("agent", "0001_initial"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="agent",
            old_name="agent_user_status_idx",
            new_name="agent_agent_user_id_2f5d4e_idx",
        ),
        migrations.RenameIndex(
            model_name="agent",
            old_name="agent_status_last_idx",
            new_name="agent_agent_status_fe6fd9_idx",
        ),
        migrations.RenameIndex(
            model_name="agentauditevent",
            old_name="agent_audit_agent_time_idx",
            new_name="agent_agent_agent_i_feff6c_idx",
        ),
        migrations.RenameIndex(
            model_name="agentauditevent",
            old_name="agent_audit_user_time_idx",
            new_name="agent_agent_user_id_372b79_idx",
        ),
        migrations.RenameIndex(
            model_name="agentauditevent",
            old_name="agent_audit_resource_time_idx",
            new_name="agent_agent_resourc_e6024b_idx",
        ),
        migrations.RenameIndex(
            model_name="agentcredential",
            old_name="agent_credential_state_idx",
            new_name="agent_agent_agent_i_e963d8_idx",
        ),
        migrations.RenameIndex(
            model_name="agentcredential",
            old_name="agent_token_prefix_idx",
            new_name="agent_agent_token_p_cacd86_idx",
        ),
        migrations.RenameIndex(
            model_name="agentenrollmenttoken",
            old_name="agent_enrollment_state_idx",
            new_name="agent_agent_agent_i_0200ca_idx",
        ),
        migrations.RenameIndex(
            model_name="agentidempotencyrecord",
            old_name="agent_idem_agent_exp_idx",
            new_name="agent_agent_agent_i_45ef5c_idx",
        ),
        migrations.AlterField(
            model_name="agent",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, verbose_name="Created At"),
        ),
        migrations.AlterField(
            model_name="agent",
            name="id",
            field=models.UUIDField(
                default=uuid4,
                editable=False,
                primary_key=True,
                serialize=False,
                verbose_name="ID",
            ),
        ),
        migrations.AlterField(
            model_name="agent",
            name="scopes",
            field=models.JSONField(blank=True, default=default_agent_scopes),
        ),
        migrations.AlterField(
            model_name="agent",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, verbose_name="Updated At"),
        ),
        migrations.AlterField(
            model_name="agentauditevent",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, verbose_name="Created At"),
        ),
        migrations.AlterField(
            model_name="agentauditevent",
            name="id",
            field=models.UUIDField(
                default=uuid4,
                editable=False,
                primary_key=True,
                serialize=False,
                verbose_name="ID",
            ),
        ),
        migrations.AlterField(
            model_name="agentauditevent",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, verbose_name="Updated At"),
        ),
        migrations.AlterField(
            model_name="agentcredential",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, verbose_name="Created At"),
        ),
        migrations.AlterField(
            model_name="agentcredential",
            name="id",
            field=models.UUIDField(
                default=uuid4,
                editable=False,
                primary_key=True,
                serialize=False,
                verbose_name="ID",
            ),
        ),
        migrations.AlterField(
            model_name="agentcredential",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, verbose_name="Updated At"),
        ),
        migrations.AlterField(
            model_name="agentenrollmenttoken",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, verbose_name="Created At"),
        ),
        migrations.AlterField(
            model_name="agentenrollmenttoken",
            name="id",
            field=models.UUIDField(
                default=uuid4,
                editable=False,
                primary_key=True,
                serialize=False,
                verbose_name="ID",
            ),
        ),
        migrations.AlterField(
            model_name="agentenrollmenttoken",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, verbose_name="Updated At"),
        ),
        migrations.AlterField(
            model_name="agentidempotencyrecord",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, verbose_name="Created At"),
        ),
        migrations.AlterField(
            model_name="agentidempotencyrecord",
            name="id",
            field=models.UUIDField(
                default=uuid4,
                editable=False,
                primary_key=True,
                serialize=False,
                verbose_name="ID",
            ),
        ),
        migrations.AlterField(
            model_name="agentidempotencyrecord",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, verbose_name="Updated At"),
        ),
    ]
