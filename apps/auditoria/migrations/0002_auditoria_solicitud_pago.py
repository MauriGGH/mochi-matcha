from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('auditoria', '0001_initial'),
        ('pedidos', '0003_detallemodificador_nombre_historico'),
    ]

    operations = [
        migrations.AddField(
            model_name='auditoria',
            name='solicitud_pago',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='auditorias',
                to='pedidos.solicitudpago',
            ),
        ),
    ]
