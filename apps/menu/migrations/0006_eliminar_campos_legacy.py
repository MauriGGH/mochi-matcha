"""
0006_eliminar_campos_legacy

Después de migrar los datos:
- Elimina GrupoModificador.producto (FK, reemplazada por M2M .productos)
- Elimina Promocion.valor (reemplazado por valor_descuento)
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("menu", "0005_datos_tipodescuento_y_modificadores_m2m"),
    ]

    operations = [
        # Eliminar FK legacy de GrupoModificador
        migrations.RemoveField(
            model_name="grupomodificador",
            name="producto",
        ),
        # Eliminar campo valor deprecated de Promocion
        migrations.RemoveField(
            model_name="promocion",
            name="valor",
        ),
    ]
