from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0005_alter_solicitudpago_detalle_pago_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="detallepedido",
            name="listo",
            field=models.BooleanField(
                default=False,
                help_text="True cuando el área correspondiente terminó este ítem.",
            ),
        ),
        migrations.AddField(
            model_name="detallepedido",
            name="fecha_listo",
            field=models.DateTimeField(blank=True, null=True),
        ),
        # Los pedidos ya "listo" o "entregado" tienen todos sus ítems terminados:
        # marcarlos para no romper el cálculo de estado global tras la migración.
        migrations.RunSQL(
            sql="""
                UPDATE pedidos_detallepedido d
                JOIN pedidos_pedido p ON p.id = d.pedido_id
                SET d.listo = 1
                WHERE p.estado IN ('listo', 'entregado');
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
