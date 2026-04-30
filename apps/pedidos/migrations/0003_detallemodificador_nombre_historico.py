from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pedidos', '0002_alter_pedido_motivo_cancelacion'),
    ]

    operations = [
        migrations.AddField(
            model_name='detallemodificador',
            name='nombre_opcion_historico',
            field=models.CharField(
                blank=True,
                default='',
                max_length=100,
                help_text='Nombre de la opción en el momento en que se creó el pedido.'
            ),
        ),
    ]
