# Hand-written migration: adds 'running' to SERVICE_STATUS_CHOICES.
# The status field is a CharField with a choices constraint only at the
# application layer; the DB column already stores arbitrary strings, so
# only the choices metadata needs to be updated.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('services', '0006_alter_volume_service'),
    ]

    operations = [
        migrations.AlterField(
            model_name='service',
            name='status',
            field=models.CharField(
                choices=[
                    ('stopped',   'stopped'),
                    ('queued',    'queued'),
                    ('deploying', 'deploying'),
                    ('running',   'running'),
                    ('failed',    'failed'),
                    ('succeeded', 'succeeded'),
                    ('stopping',  'stopping'),
                ],
                default='stopped',
                verbose_name='Deploy Status',
            ),
        ),
    ]
