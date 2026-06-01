from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("menu", "0002_categoria_area"),
    ]

    operations = [
        migrations.AddField(
            model_name="grupomodificador",
            name="es_plantilla",
            field=models.BooleanField(
                default=False,
                help_text="Marcar para que aparezca como plantilla reutilizable al crear modificadores en otros productos.",
            ),
        ),
    ]
