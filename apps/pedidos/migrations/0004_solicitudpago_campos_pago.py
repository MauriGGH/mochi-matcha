from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Agrega campos para el detalle de pago mejorado:
    - monto_efectivo: monto recibido en efectivo
    - monto_tarjeta: monto pagado con tarjeta
    - monto_recibido: efectivo físico entregado (para calcular cambio)
    - cambio: cambio entregado al cliente
    - detalle_pago: texto libre con el desglose del método de pago
    """

    dependencies = [
        ('pedidos', '0003_detallemodificador_nombre_historico'),
    ]

    operations = [
        migrations.AddField(
            model_name='solicitudpago',
            name='monto_efectivo',
            field=models.DecimalField(
                max_digits=10, decimal_places=2, null=True, blank=True,
                help_text='Monto pagado en efectivo (pago mixto).'
            ),
        ),
        migrations.AddField(
            model_name='solicitudpago',
            name='monto_tarjeta',
            field=models.DecimalField(
                max_digits=10, decimal_places=2, null=True, blank=True,
                help_text='Monto pagado con tarjeta (pago mixto).'
            ),
        ),
        migrations.AddField(
            model_name='solicitudpago',
            name='monto_recibido',
            field=models.DecimalField(
                max_digits=10, decimal_places=2, null=True, blank=True,
                help_text='Efectivo físico recibido del cliente (para calcular cambio).'
            ),
        ),
        migrations.AddField(
            model_name='solicitudpago',
            name='cambio',
            field=models.DecimalField(
                max_digits=10, decimal_places=2, null=True, blank=True,
                help_text='Cambio entregado al cliente.'
            ),
        ),
        migrations.AddField(
            model_name='solicitudpago',
            name='detalle_pago',
            field=models.TextField(
                blank=True, default='',
                help_text='Texto descriptivo del desglose del pago (para imprimir en ticket).'
            ),
        ),
        migrations.AddField(
            model_name='solicitudpago',
            name='referencia_externa',
            field=models.CharField(
                max_length=200, blank=True, default='',
                help_text='ID de orden PayPal u otra referencia externa.'
            ),
        ),
    ]
