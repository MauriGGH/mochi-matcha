import json
from django.db import models


class Categoria(models.Model):
    AREAS = [("cocina", "Cocina"), ("bar", "Bar"), ("ambos", "Ambos")]
    nombre = models.CharField(max_length=100)
    orden = models.IntegerField(default=0)
    area = models.CharField(max_length=10, choices=AREAS, default="ambos")

    class Meta:
        verbose_name = "Categoría"
        verbose_name_plural = "Categorías"
        ordering = ["orden"]

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        if self.nombre:
            self.nombre = self.nombre.upper()
        super().save(*args, **kwargs)


class TipoPromocion(models.Model):
    """Catálogo legacy — se mantiene por compatibilidad con datos existentes."""
    descripcion = models.CharField(max_length=50)

    class Meta:
        verbose_name = "Tipo de promoción (legacy)"
        verbose_name_plural = "Tipos de promoción (legacy)"

    def __str__(self):
        return self.descripcion


class TipoDescuento(models.Model):
    """
    Catálogo de tipos de descuento para el nuevo sistema de promociones.
    Valores canónicos creados por migración de datos:
      "Porcentaje", "Monto fijo", "2x1", "Combo precio fijo", "Lleva X paga Y"
    """
    descripcion = models.CharField(max_length=50, unique=True)

    class Meta:
        verbose_name = "Tipo de descuento"
        verbose_name_plural = "Tipos de descuento"

    def __str__(self):
        return self.descripcion


class Promocion(models.Model):
    APLICACION_CHOICES = [
        ("item",  "Por ítem"),
        ("total", "Sobre total del carrito"),
        ("combo", "Combo (precio fijo por conjunto)"),
    ]

    titulo = models.CharField(max_length=100)
    fecha_inicio = models.DateTimeField()
    fecha_fin = models.DateTimeField()
    activa = models.BooleanField(default=True)
    codigo_cupon = models.CharField(max_length=50, null=True, blank=True, unique=True)
    imagen_url = models.CharField(
        max_length=500, null=True, blank=True,
        help_text="URL de imagen para banner de promoción (opcional)."
    )
    limite_usos = models.IntegerField(null=True, blank=True)

    # Legacy — conservado para referencias FK existentes en datos viejos
    tipo_promocion = models.ForeignKey(
        TipoPromocion, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="promociones"
    )

    # Nuevo sistema
    tipo_descuento = models.ForeignKey(
        TipoDescuento, on_delete=models.PROTECT,
        null=True, blank=True, related_name="promociones"
    )
    valor_descuento = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Porcentaje (0-100), monto fijo, precio combo, o cantidad a pagar en Lleva X paga Y"
    )
    cantidad_minima = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Unidades requeridas para activar la promoción (Lleva X paga Y)"
    )
    aplicacion = models.CharField(
        max_length=20, choices=APLICACION_CHOICES, default="item"
    )
    productos_aplicables = models.ManyToManyField(
        "Producto", related_name="promociones_aplicables", blank=True,
        help_text="Productos sobre los que aplica la promoción"
    )
    productos_beneficiados = models.ManyToManyField(
        "Producto", related_name="promociones_beneficiadas", blank=True,
        help_text="Productos que reciben el descuento (combos)"
    )

    class Meta:
        verbose_name = "Promoción"
        verbose_name_plural = "Promociones"

    def __str__(self):
        return self.titulo

    def save(self, *args, **kwargs):
        if self.titulo:
            self.titulo = self.titulo.upper()
        super().save(*args, **kwargs)


class Producto(models.Model):
    nombre = models.CharField(max_length=100)
    descripcion = models.CharField(max_length=255, null=True, blank=True)
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    imagen_url = models.CharField(max_length=255, null=True, blank=True)
    disponible = models.BooleanField(default=True)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name="productos")
    promociones = models.ManyToManyField(
        Promocion, through="PromocionProducto", blank=True, related_name="productos"
    )

    class Meta:
        verbose_name = "Producto"
        verbose_name_plural = "Productos"

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        if self.nombre:
            self.nombre = self.nombre.upper()
        if self.descripcion:
            self.descripcion = self.descripcion.upper()
        super().save(*args, **kwargs)

    @property
    def grupos_json(self):
        if hasattr(self, '_prefetched_objects_cache') and 'grupos_modificadores' in self._prefetched_objects_cache:
            grupos_qs = self._prefetched_objects_cache['grupos_modificadores']
        else:
            grupos_qs = self.grupos_modificadores.all()

        grupos = []
        for g in grupos_qs:
            opciones_qs = (
                g._prefetched_objects_cache.get('opciones', g.opciones.all())
                if hasattr(g, '_prefetched_objects_cache')
                else g.opciones.all()
            )
            grupos.append({
                "id": g.pk,
                "nombre_grupo": g.nombre_grupo,
                "tipo": g.tipo,
                "es_obligatorio": g.es_obligatorio,
                "max_selecciones": g.max_selecciones,
                "opciones": [
                    {
                        "id": op.pk,
                        "nombre_opcion": op.nombre_opcion,
                        "precio_extra": float(op.precio_extra),
                    }
                    for op in opciones_qs
                ],
            })
        return json.dumps(grupos, ensure_ascii=False)


class PromocionProducto(models.Model):
    """Tabla intermedia legacy para la relación Promocion↔Producto."""
    promocion = models.ForeignKey(Promocion, on_delete=models.CASCADE)
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)

    class Meta:
        unique_together = ("promocion", "producto")
        verbose_name = "Promoción-Producto (legacy)"

    def __str__(self):
        return f"{self.promocion} → {self.producto}"


class GrupoModificador(models.Model):
    TIPOS = [("única", "Única"), ("múltiple", "Múltiple")]
    nombre_grupo = models.CharField(max_length=100)
    tipo = models.CharField(max_length=10, choices=TIPOS, default="única")
    es_obligatorio = models.BooleanField(default=False)
    max_selecciones = models.IntegerField(null=True, blank=True)
    es_plantilla = models.BooleanField(
        default=False,
        help_text="Marcar para que aparezca como plantilla reutilizable."
    )

    # NUEVO: ManyToMany (reemplaza la FK producto)
    productos = models.ManyToManyField(
        Producto, related_name="grupos_modificadores", blank=True
    )

    class Meta:
        verbose_name = "Grupo de modificador"
        verbose_name_plural = "Grupos de modificadores"

    def __str__(self):
        return self.nombre_grupo

    def save(self, *args, **kwargs):
        if self.nombre_grupo:
            self.nombre_grupo = self.nombre_grupo.upper()
        super().save(*args, **kwargs)


class OpcionModificador(models.Model):
    nombre_opcion = models.CharField(max_length=100)
    precio_extra = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    grupo = models.ForeignKey(GrupoModificador, on_delete=models.CASCADE, related_name="opciones")
    activo = models.BooleanField(
        default=True,
        help_text="Las opciones inactivas no aparecen en el menú pero se conservan para histórico."
    )

    class Meta:
        verbose_name = "Opción de modificador"
        verbose_name_plural = "Opciones de modificador"

    def __str__(self):
        sufijo = "" if self.activo else " [inactiva]"
        return f"{self.nombre_opcion} (+${self.precio_extra}){sufijo}"

    def save(self, *args, **kwargs):
        if self.nombre_opcion:
            self.nombre_opcion = self.nombre_opcion.upper()
        super().save(*args, **kwargs)



