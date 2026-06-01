"""
0005_datos_tipodescuento_y_modificadores_m2m

Migración de DATOS:
1. Crea los 5 TipoDescuento canónicos.
2. Para cada Promocion existente, infiere tipo_descuento desde tipo_promocion.descripcion
   y copia valor → valor_descuento.
3. Copia PromocionProducto → Promocion.productos_aplicables.
4. Copia GrupoModificador.producto (FK) → GrupoModificador.productos (M2M).
"""
from django.db import migrations


TIPOS_DESCUENTO = [
    "Porcentaje",
    "Monto fijo",
    "2x1",
    "Combo precio fijo",
    "Lleva X paga Y",
]

# Mapeo de palabras clave en tipo_promocion.descripcion → TipoDescuento.descripcion
KEYWORD_MAP = {
    "porcentaje": "Porcentaje",
    "percent":    "Porcentaje",
    "%":          "Porcentaje",
    "2x1":        "2x1",
    "dos por uno": "2x1",
    "combo":      "Combo precio fijo",
    "fijo":       "Monto fijo",
    "monto":      "Monto fijo",
    "lleva":      "Lleva X paga Y",
}


def _inferir_tipo(descripcion_legacy: str) -> str:
    """Devuelve el nombre canónico de TipoDescuento más cercano al texto legacy."""
    desc_lower = (descripcion_legacy or "").lower()
    for keyword, canonical in KEYWORD_MAP.items():
        if keyword in desc_lower:
            return canonical
    return "Monto fijo"  # fallback seguro


def migrar_datos(apps, schema_editor):
    TipoDescuento = apps.get_model("menu", "TipoDescuento")
    Promocion = apps.get_model("menu", "Promocion")
    PromocionProducto = apps.get_model("menu", "PromocionProducto")
    GrupoModificador = apps.get_model("menu", "GrupoModificador")

    # 1. Crear TipoDescuento canónicos
    tipo_map = {}
    for desc in TIPOS_DESCUENTO:
        obj, _ = TipoDescuento.objects.get_or_create(descripcion=desc)
        tipo_map[desc] = obj

    # 2. Migrar cada Promocion existente
    for promo in Promocion.objects.select_related("tipo_promocion").all():
        # Inferir tipo_descuento
        desc_legacy = promo.tipo_promocion.descripcion if promo.tipo_promocion else ""
        canonical = _inferir_tipo(desc_legacy)
        promo.tipo_descuento = tipo_map[canonical]

        # Migrar valor → valor_descuento
        if promo.valor is not None:
            promo.valor_descuento = promo.valor

        # Inferir aplicacion
        if canonical in ("Combo precio fijo",):
            promo.aplicacion = "combo"
        elif canonical in ("Porcentaje", "Monto fijo"):
            promo.aplicacion = "item"
        else:
            promo.aplicacion = "item"

        promo.save(update_fields=["tipo_descuento", "valor_descuento", "aplicacion"])

        # 3. Copiar PromocionProducto → productos_aplicables
        producto_ids = list(
            PromocionProducto.objects.filter(promocion=promo).values_list("producto_id", flat=True)
        )
        if producto_ids:
            promo.productos_aplicables.set(producto_ids)

    # 4. Copiar GrupoModificador.producto (FK) → GrupoModificador.productos (M2M)
    for grupo in GrupoModificador.objects.all():
        # Acceder al campo FK antiguo usando la BD directamente
        try:
            producto_id = grupo.producto_id  # FK aún existe en este paso
            if producto_id:
                grupo.productos.add(producto_id)
        except AttributeError:
            # Si la FK ya fue eliminada en una migración anterior, ignorar
            pass


def revertir_datos(apps, schema_editor):
    """No es seguro revertir automáticamente — la migración inversa es no-op."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("menu", "0004_tipodescuento_promocion_nuevos_campos_grupomodificador_m2m"),
    ]

    operations = [
        migrations.RunPython(migrar_datos, revertir_datos),
    ]
