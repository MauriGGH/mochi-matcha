"""
apps/menu/models.py — Modelos del catálogo de productos y promociones.

Jerarquía principal:
  Categoria → Producto → GrupoModificador → OpcionModificador
  Promocion (con relaciones M2M a Producto y FK a TipoDescuento)

El campo `area` de Categoria es la clave para el filtrado KDS: determina qué
área de preparación (cocina, bar o ambas) procesa cada producto.
"""
import json
from django.db import models


class Categoria(models.Model):
    """
    Agrupación lógica de productos del menú.

    El campo `area` decide en qué KDS aparecen los productos de esta categoría:
      - 'cocina': solo muestra en el KDS de cocina.
      - 'bar':    solo muestra en el KDS de bar.
      - 'ambos':  aparece en ambos KDS.
    `orden` controla el orden de aparición en el menú del cliente (menor = primero).
    El nombre se normaliza a MAYÚSCULAS en el método save().
    """
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
        # Normalizar nombre a mayúsculas para consistencia en toda la BD.
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
    """
    Promoción comercial aplicable al carrito de compras.

    Soporta cinco tipos de descuento (vía TipoDescuento):
      - Porcentaje: reduce un % sobre el subtotal de los productos aplicables.
      - Monto fijo: resta una cantidad fija (por ítem o sobre el total).
      - 2x1: cada dos unidades del mismo producto, la más barata es gratis.
      - Combo precio fijo: precio único para un conjunto de productos.
      - Lleva X paga Y: lleva cantidad_minima, paga valor_descuento unidades.

    Los campos `productos_aplicables` y `productos_beneficiados` delimitan qué
    productos entran en la condición y cuáles reciben el beneficio (útil en combos).
    El campo `dias_semana` restringe la promoción a días específicos de la semana.
    El campo `codigo_cupon` permite activación manual por el cliente.
    """
    APLICACION_CHOICES = [
        ("item",  "Por ítem"),
        ("total", "Sobre total del carrito"),
        ("combo", "Combo (precio fijo por conjunto)"),
    ]

    titulo = models.CharField(max_length=100)
    descripcion_corta = models.CharField(
        max_length=120, null=True, blank=True,
        help_text='Texto corto para el carrusel (ej: "15% off en bebidas").'
    )
    orden = models.PositiveSmallIntegerField(
        default=0,
        help_text='Orden en el carrusel (menor = primero).'
    )
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
        TipoDescuento, on_delete=models.PROTECT,  # PROTECT: no borrar un tipo con promos activas
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
    # Si True, la promo solo es elegible cuando TODOS los productos_aplicables
    # están en el carrito (semántica de "combo"). Útil para promos tipo
    # "MATCHA + POSTRE 15%" que no deben activarse con un solo ítem.
    requiere_todos_productos = models.BooleanField(
        default=False,
        help_text="Exigir que TODOS los productos aplicables estén en el carrito (combo)."
    )
    # Días de la semana en los que aplica la promo. Formato: "0,1,4" (0=lunes…6=domingo).
    # Vacío o NULL = aplica todos los días.
    dias_semana = models.CharField(
        max_length=20, blank=True, default="",
        help_text='Días en que aplica (0=lun … 6=dom). Vacío = todos los días.'
    )

    class Meta:
        verbose_name = "Promoción"
        verbose_name_plural = "Promociones"
        ordering = ['orden', '-fecha_inicio']

    def __str__(self):
        return self.titulo

    def save(self, *args, **kwargs):
        if self.titulo:
            self.titulo = self.titulo.upper()
        super().save(*args, **kwargs)

    def aplica_hoy(self, fecha=None):
        """¿La promo aplica hoy (según días_semana configurados)?

        Si `dias_semana` está vacío, aplica todos los días.
        """
        if not self.dias_semana:
            return True
        try:
            permitidos = {int(x) for x in self.dias_semana.split(",") if x.strip() != ""}
        except (ValueError, TypeError):
            return True
        if not permitidos:
            return True
        from django.utils import timezone as _tz
        hoy = fecha or _tz.localtime(_tz.now()).date()
        return hoy.weekday() in permitidos

    @property
    def imagen_efectiva(self):
        """URL de imagen para mostrar en el carrusel.

        Prioridad:
          1) imagen_url propia (si el gerente subió banner específico)
          2) imagen del primer producto aplicable
          3) imagen del primer producto beneficiado (caso combo)
        """
        if self.imagen_url:
            return self.imagen_url
        if self.pk:
            prod = self.productos_aplicables.first()
            if prod and prod.imagen_url:
                return prod.imagen_url
            prod = self.productos_beneficiados.first()
            if prod and prod.imagen_url:
                return prod.imagen_url
        return None


class Producto(models.Model):
    """
    Ítem del menú que el cliente puede ordenar.

    `disponible`: permite ocultar un producto sin eliminarlo (histórico intacto).
    `categoria`: define el área KDS (cocina/bar/ambos) vía Categoria.area.
    `imagen_url`: URL externa o ruta relativa usada en el carrusel del menú.
    `promociones`: relación M2M a través de PromocionProducto (tabla intermedia legacy).
    `grupos_modificadores`: M2M inversa para personalizar el ítem (leche, azúcar, etc.).
    El nombre y descripción se normalizan a MAYÚSCULAS en save().
    """
    nombre = models.CharField(max_length=100)
    descripcion = models.CharField(max_length=255, null=True, blank=True)
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    imagen_url = models.CharField(max_length=255, null=True, blank=True)
    disponible = models.BooleanField(default=True)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name="productos")
    # PROTECT: no se puede borrar una categoría que tiene productos
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
        """
        Serializa los grupos de modificadores del producto a JSON para el frontend.

        Aprovecha el prefetch cache si ya se hizo prefetch_related('grupos_modificadores')
        en la queryset, evitando consultas adicionales. Retorna un JSON string con la
        estructura: [{id, nombre_grupo, tipo, es_obligatorio, max_selecciones, opciones}].
        """
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
    """
    Conjunto de opciones personalizables para un producto (ej. "Tipo de leche").

    `tipo`: 'única' = selección excluyente (radio); 'múltiple' = varios checks.
    `es_obligatorio`: si True, el cliente debe elegir al menos una opción.
    `max_selecciones`: límite de opciones en grupos múltiple (None = sin límite).
    `es_plantilla`: grupos reutilizables que el gerente puede asignar a varios productos
                    sin recrearlos.
    La relación M2M con Producto reemplaza la antigua FK directa, permitiendo
    compartir un mismo grupo entre varios productos.
    """
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
    """
    Opción individual dentro de un GrupoModificador (ej. "Leche de avena").

    `precio_extra`: costo adicional que se suma al subtotal del ítem cuando el
                    cliente elige esta opción (0.00 si es sin costo).
    `activo`: permite retirar una opción del menú sin borrarla, preservando el
              histórico en DetalleModificador de pedidos pasados.
    `grupo`: CASCADE — la opción desaparece si se elimina su grupo.
    """
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



