import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("mesas", "0003_alertamesero"),
    ]

    operations = [
        # 1. Create UbicacionMesa
        migrations.CreateModel(
            name="UbicacionMesa",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=60, unique=True)),
            ],
            options={
                "verbose_name": "Ubicación de mesa",
                "verbose_name_plural": "Ubicaciones de mesa",
                "ordering": ["nombre"],
            },
        ),
        # 2. Drop old CharField ubicacion
        migrations.RemoveField(
            model_name="mesa",
            name="ubicacion",
        ),
        # 3. Add FK ubicacion
        migrations.AddField(
            model_name="mesa",
            name="ubicacion",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="mesas", to="mesas.ubicacionmesa",
            ),
        ),
    ]
