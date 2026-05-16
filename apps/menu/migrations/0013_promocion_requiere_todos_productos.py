from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("menu", "0012_promocion_dias_semana"),
    ]

    operations = [
        migrations.AddField(
            model_name="promocion",
            name="requiere_todos_productos",
            field=models.BooleanField(
                default=False,
                help_text="Exigir que TODOS los productos aplicables estén en el carrito (combo).",
            ),
        ),
    ]
