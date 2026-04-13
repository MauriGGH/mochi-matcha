# menu/models.py
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


class TipoPromocion(models.Model):
    descripcion = models.CharField(max_length=50)

    class Meta:
        verbose_name = "Tipo de promoción"
        verbose_name_plural = "Tipos de promoción"

    def __str__(self):
        return self.descripcion


class Promocion(models.Model):
    titulo = models.CharField(max_length=100)
    tipo_promocion = models.ForeignKey(TipoPromocion, on_delete=models.PROTECT, related_name="promociones")
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    fecha_inicio = models.DateTimeField()
    fecha_fin = models.DateTimeField()
    activa = models.BooleanField(default=True)
    codigo_cupon = models.CharField(max_length=50, null=True, blank=True, unique=True)
    limite_usos = models.IntegerField(null=True, blank=True)

    class Meta:
        verbose_name = "Promoción"
        verbose_name_plural = "Promociones"

    def __str__(self):
        return self.titulo


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

    @property
    def grupos_json(self):
        """Serializa los grupos de modificadores como JSON para usar en templates."""
        grupos = []
        for g in self.grupos_modificadores.prefetch_related("opciones").all():
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
                    for op in g.opciones.all()
                ],
            })
        return json.dumps(grupos, ensure_ascii=False)


class PromocionProducto(models.Model):
    promocion = models.ForeignKey(Promocion, on_delete=models.CASCADE)
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)

    class Meta:
        unique_together = ("promocion", "producto")
        verbose_name = "Promoción-Producto"

    def __str__(self):
        return f"{self.promocion} → {self.producto}"


class GrupoModificador(models.Model):
    TIPOS = [("única", "Única"), ("múltiple", "Múltiple")]
    nombre_grupo = models.CharField(max_length=100)
    tipo = models.CharField(max_length=10, choices=TIPOS, default="única")
    es_obligatorio = models.BooleanField(default=False)
    max_selecciones = models.IntegerField(null=True, blank=True)
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name="grupos_modificadores")

    class Meta:
        verbose_name = "Grupo de modificador"
        verbose_name_plural = "Grupos de modificadores"

    def __str__(self):
        return f"{self.nombre_grupo} ({self.producto})"


class OpcionModificador(models.Model):
    nombre_opcion = models.CharField(max_length=100)
    precio_extra = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    grupo = models.ForeignKey(GrupoModificador, on_delete=models.CASCADE, related_name="opciones")

    class Meta:
        verbose_name = "Opción de modificador"
        verbose_name_plural = "Opciones de modificador"

    def __str__(self):
        return f"{self.nombre_opcion} (+${self.precio_extra})"