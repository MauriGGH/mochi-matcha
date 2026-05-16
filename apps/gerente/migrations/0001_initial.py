from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Configuracion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("clave", models.CharField(max_length=100, unique=True)),
                ("valor", models.TextField()),
            ],
            options={
                "verbose_name": "Configuración",
                "verbose_name_plural": "Configuraciones",
            },
        ),
    ]
