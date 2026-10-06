from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("services", "0029_restrict_service_network_delete"),
    ]

    operations = [
        migrations.AddField(
            model_name="shellsession",
            name="mode",
            field=models.CharField(
                choices=[("restricted", "Restricted"), ("developer", "Developer")],
                default="restricted",
                max_length=16,
            ),
        ),
    ]