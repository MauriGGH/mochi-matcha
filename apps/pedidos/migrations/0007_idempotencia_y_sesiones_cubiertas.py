from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0006_detallepedido_listo"),
        ("mesas", "0004_ubicacionmesa_alter_mesa_ubicacion"),
    ]

    operations = [
        migrations.AddField(
            model_name="pedido",
            name="token_idempotencia",
            field=models.CharField(
                max_length=64, null=True, blank=True, unique=True,
            ),
        ),
        migrations.AddField(
            model_name="solicitudpago",
            name="sesiones_cubiertas",
            field=models.ManyToManyField(
                blank=True,
                related_name="solicitudes_que_la_cubren",
                to="mesas.sesioncliente",
            ),
        ),
    ]
