from django.db import models
from apps.accounts.models import Empleado
from apps.mesas.models import Mesa
from apps.pedidos.models import Pedido, SolicitudPago


class Auditoria(models.Model):
    fecha_hora = models.DateTimeField(auto_now_add=True)
    accion = models.CharField(max_length=100)
    detalle = models.TextField(null=True, blank=True)
    # PROTECT: la auditoría no debe borrarse si se da de baja un empleado
    empleado = models.ForeignKey(
        Empleado, on_delete=models.PROTECT, related_name="auditorias"
    )
    # SET_NULL: si la mesa es eliminada, el registro de auditoría se conserva
    mesa = models.ForeignKey(
        Mesa, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="auditorias"
    )
    # SET_NULL: si el pedido es eliminado (no debería), la auditoría se conserva
    pedido = models.ForeignKey(
        Pedido, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="auditorias"
    )
    # SET_NULL: referencia a la solicitud de pago involucrada (cancelaciones, cobros)
    solicitud_pago = models.ForeignKey(
        SolicitudPago, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="auditorias"
    )

    class Meta:
        verbose_name = "Auditoría"
        verbose_name_plural = "Auditorías"
        ordering = ["-fecha_hora"]

    def __str__(self):
        return f"[{self.fecha_hora:%Y-%m-%d %H:%M}] {self.accion} — {self.empleado}"
