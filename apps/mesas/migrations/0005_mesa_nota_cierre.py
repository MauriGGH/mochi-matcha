from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("mesas", "0004_ubicacionmesa_alter_mesa_ubicacion"),
    ]

    operations = [
        migrations.AddField(
            model_name="mesa",
            name="nota_cierre",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]
