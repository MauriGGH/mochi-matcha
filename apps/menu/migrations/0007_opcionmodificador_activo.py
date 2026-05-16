from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('menu', '0006_eliminar_campos_legacy'),
    ]

    operations = [
        migrations.AddField(
            model_name='opcionmodificador',
            name='activo',
            field=models.BooleanField(
                default=True,
                help_text='Las opciones inactivas no aparecen en el menú pero se conservan para histórico.'
            ),
        ),
    ]
