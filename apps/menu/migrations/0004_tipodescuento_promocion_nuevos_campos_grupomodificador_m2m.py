"""
0004_tipodescuento_promocion_nuevos_campos_grupomodificador_m2m

Cambios estructurales:
- Crea TipoDescuento
- Agrega campos nuevos a Promocion (tipo_descuento null=True, valor_descuento,
  cantidad_minima, aplicacion, productos_aplicables, productos_beneficiados)
- Cambia tipo_promocion de PROTECT → SET_NULL (nullable)
- Agrega M2M GrupoModificador.productos
- Mantiene FK GrupoModificador.producto (se elimina en migración 0006)
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("menu", "0003_grupomodificador_es_plantilla"),
    ]

    operations = [
        # 1. Crear TipoDescuento
        migrations.CreateModel(
            name="TipoDescuento",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("descripcion", models.CharField(max_length=50, unique=True)),
            ],
            options={
                "verbose_name": "Tipo de descuento",
                "verbose_name_plural": "Tipos de descuento",
            },
        ),

        # 2. Hacer tipo_promocion nullable (legacy → SET_NULL)
        migrations.AlterField(
            model_name="promocion",
            name="tipo_promocion",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="promociones",
                to="menu.tipopromocion",
            ),
        ),

        # 3. Hacer valor nullable (se migrará a valor_descuento)
        migrations.AlterField(
            model_name="promocion",
            name="valor",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=10, null=True,
                help_text="DEPRECATED — usar valor_descuento"
            ),
        ),

        # 4. Nuevos campos en Promocion
        migrations.AddField(
            model_name="promocion",
            name="tipo_descuento",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="promociones",
                to="menu.tipodescuento",
            ),
        ),
        migrations.AddField(
            model_name="promocion",
            name="valor_descuento",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=10, null=True,
                help_text="Porcentaje, monto fijo, precio combo, o cantidad a pagar"
            ),
        ),
        migrations.AddField(
            model_name="promocion",
            name="cantidad_minima",
            field=models.PositiveIntegerField(
                blank=True, null=True,
                help_text="Unidades requeridas para activar la promoción"
            ),
        ),
        migrations.AddField(
            model_name="promocion",
            name="aplicacion",
            field=models.CharField(
                choices=[("item", "Por ítem"), ("total", "Sobre total del carrito"), ("combo", "Combo")],
                default="item", max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="promocion",
            name="productos_aplicables",
            field=models.ManyToManyField(
                blank=True,
                help_text="Productos sobre los que aplica la promoción",
                related_name="promociones_aplicables",
                to="menu.producto",
            ),
        ),
        migrations.AddField(
            model_name="promocion",
            name="productos_beneficiados",
            field=models.ManyToManyField(
                blank=True,
                help_text="Productos que reciben el descuento (combos)",
                related_name="promociones_beneficiadas",
                to="menu.producto",
            ),
        ),

        # 5. M2M GrupoModificador.productos (la FK producto se elimina en 0006)
        migrations.AddField(
            model_name="grupomodificador",
            name="productos",
            field=models.ManyToManyField(
                blank=True,
                related_name="grupos_modificadores",
                to="menu.producto",
            ),
        ),
    ]
