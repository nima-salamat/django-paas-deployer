from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0003_coresettings_operations")]
    operations = [
        migrations.AddField(model_name="coresettings", name="mirror_docker", field=models.CharField(default="docker.arvancloud.ir", max_length=255, verbose_name="Docker registry mirror")),
        migrations.AddField(model_name="coresettings", name="mirror_python", field=models.CharField(default="https://mirror-pypi.runflare.com/simple", max_length=500, verbose_name="PyPI mirror")),
        migrations.AddField(model_name="coresettings", name="mirror_npm", field=models.CharField(default="https://package-mirror.liara.ir/repository/npm/", max_length=500, verbose_name="npm registry")),
        migrations.AddField(model_name="coresettings", name="mirror_composer", field=models.CharField(default="https://package-mirror.liara.ir/repository/composer/", max_length=500, verbose_name="Composer mirror")),
        migrations.AddField(model_name="coresettings", name="mirror_apt", field=models.CharField(default="http://repo.iut.ac.ir/debian/", max_length=500, verbose_name="APT/Debian mirror")),
        migrations.AddField(model_name="coresettings", name="mirror_go", field=models.CharField(blank=True, default="", max_length=500, verbose_name="Go module proxy")),
        migrations.AddField(model_name="coresettings", name="build_resource_mode", field=models.CharField(choices=[("static", "Static"), ("plan", "Plan capped")], default="static", max_length=16, verbose_name="Build resource mode")),
        migrations.AddField(model_name="coresettings", name="build_pids_limit", field=models.PositiveIntegerField(default=2048, verbose_name="Build PID limit")),
        migrations.AddField(model_name="coresettings", name="build_shm_mb", field=models.PositiveIntegerField(default=64, verbose_name="Build shared memory (MB)")),
    ]
