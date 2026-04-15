from django.db import models
from apps.accounts.models import Empleado
from apps.catalogs.models import ModalidadIngreso


class Mesa(models.Model):
    ESTADOS = [("libre", "Libre"), ("ocupada", "Ocupada")]

    numero_mesa = models.IntegerField(unique=True)
    capacidad = models.IntegerField()
    ubicacion = models.CharField(max_length=50, null=True, blank=True)
    codigo_qr = models.CharField(max_length=255, unique=True)
    pin_actual = models.CharField(max_length=60, null=True, blank=True)
    estado = models.CharField(max_length=10, choices=ESTADOS, default="libre")
    id_mesero_asignado = models.ForeignKey(
        Empleado,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="mesas_asignadas",
        limit_choices_to={"rol": "mesero"},
    )

    class Meta:
        verbose_name = "Mesa"
        verbose_name_plural = "Mesas"
        ordering = ["numero_mesa"]

    def __str__(self):
        return f"Mesa {self.numero_mesa}"


class SesionCliente(models.Model):
    ESTADOS = [
        ("activa", "Activa"),
        ("pagada", "Pagada"),
        ("cerrada", "Cerrada"),
    ]

    alias = models.CharField(max_length=50)
    token_cookie = models.CharField(max_length=255, unique=True)
    estado = models.CharField(max_length=10, choices=ESTADOS, default="activa")
    fecha_inicio = models.DateTimeField(auto_now_add=True)
    mesa = models.ForeignKey(Mesa, on_delete=models.PROTECT, related_name="sesiones")
    modalidad_ingreso = models.ForeignKey(
        ModalidadIngreso, on_delete=models.PROTECT, related_name="sesiones"
    )

    class Meta:
        # FIX: eliminado unique_together (mesa, alias) que impedía reutilizar
        # alias cuando la mesa se liberaba y volvía a ocuparse.
        # La unicidad se valida en la vista filtrando solo estado='activa'.
        verbose_name = "Sesión de cliente"
        verbose_name_plural = "Sesiones de clientes"

    def __str__(self):
        return f"{self.alias} @ {self.mesa}"
