from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("messenger", "0020_matrix_identity_and_room_binding"),
    ]

    operations = [
        migrations.AddField(
            model_name="matrixdevice",
            name="logged_out_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
    ]
