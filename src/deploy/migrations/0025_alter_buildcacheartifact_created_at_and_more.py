from django.db import migrations, models
from django.core.validators import MaxValueValidator


class Migration(migrations.Migration):
    dependencies = [
        ("deploy", "0024_build_cache_governance"),
    ]

    operations = [
        migrations.AlterField(
            model_name="buildcacheartifact",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, verbose_name="Created At"),
        ),
        migrations.AlterField(
            model_name="buildcacheartifact",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, verbose_name="Updated At"),
        ),
        migrations.AlterField(
            model_name="buildcachequota",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, verbose_name="Created At"),
        ),
        migrations.AlterField(
            model_name="buildcachequota",
            name="keep_successful_deployments",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text="Number of newest successful deployments to keep protected. Null inherits the applicable default.",
                null=True,
                validators=[MaxValueValidator(100)],
                verbose_name="Keep successful deployments",
            ),
        ),
        migrations.AlterField(
            model_name="buildcachequota",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, verbose_name="Updated At"),
        ),
    ]
